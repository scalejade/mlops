#!/usr/bin/env python3
"""
Unsloth LoRA/QLoRA fine-tune, driven entirely by one YAML config.

    python training/scripts/train.py training/configs/<task>-<date>.yaml
    python training/scripts/train.py <config> --dry-run     # resolve + print, train nothing

Runs on the H200 pod created by training/scripts/pod.py. Nothing is tunable at
the command line on purpose: if a hyperparameter is not in the config file, it
did not happen and the run cannot be reproduced.

Reads HF_TOKEN / WANDB_API_KEY from the environment (the pod gets them from .env
via pod.py). Writes the adapter to output.adapter_dir and, if output.push_to_hub
is set, pushes it to the Hub.
"""

from __future__ import annotations

# Unsloth must be imported before transformers/trl — it patches them on import.
import unsloth  # noqa: F401  isort:skip
from unsloth import FastModel, is_bfloat16_supported
from unsloth.chat_templates import get_chat_template, train_on_responses_only

import argparse
import inspect
import json
import os
import random
import re
import sys
from pathlib import Path

import torch
import yaml
from datasets import Dataset, load_dataset
from transformers import set_seed
from trl import SFTConfig, SFTTrainer

REPO = Path(__file__).resolve().parents[2]

# Where train_on_responses_only splits prompt from completion, per chat template.
# Loss is computed on the assistant turn only — training on the prompt teaches the
# model to predict our own instructions back at us.
RESPONSE_MARKERS = {
    "qwen-2.5": ("<|im_start|>user\n", "<|im_start|>assistant\n"),
    "qwen-3":   ("<|im_start|>user\n", "<|im_start|>assistant\n"),
    "chatml":   ("<|im_start|>user\n", "<|im_start|>assistant\n"),
    "llama-3.1": ("<|start_header_id|>user<|end_header_id|>\n\n",
                  "<|start_header_id|>assistant<|end_header_id|>\n\n"),
    "gemma-3":  ("<start_of_turn>user\n", "<start_of_turn>model\n"),
}


class Fail(Exception):
    """A problem the user needs to fix. Printed without a traceback."""


def info(msg: str) -> None:
    print(f"  {msg}")


def head(msg: str) -> None:
    print(f"\n{msg}")


# ------------------------------------------------------------------- config

def load_config(path: Path) -> dict:
    if not path.exists():
        raise Fail(f"config not found: {path}")
    cfg = yaml.safe_load(path.read_text()) or {}

    for key in ("run_name", "model", "data", "train", "output"):
        if key not in cfg:
            raise Fail(f"{path.name} is missing the required top-level key '{key}'")

    m = cfg["model"]
    if not m.get("base"):
        raise Fail("model.base is required — the Hub repo of the base model")
    if not m.get("max_seq_length"):
        raise Fail(
            "model.max_seq_length is required. It must equal what the serving config "
            "uses; a model trained long and served short truncates silently."
        )
    return cfg


def resolve_path(p: str) -> Path:
    """Config paths are repo-relative unless absolute."""
    path = Path(p)
    return path if path.is_absolute() else REPO / path


# --------------------------------------------------------------------- data

def load_split(data: dict, which: str) -> Dataset | None:
    """
    Load one split. Either from a private HF dataset repo:

        data:
          hub_repo: scalejade/pjp-clauses
          revision: <commit sha>
          train_split: train
          eval_split: test

    or from local JSONL:

        data:
          train: preparation/data/train.jsonl
    """
    if data.get("hub_repo"):
        split = data.get(f"{which}_split")
        if not split:
            return None
        ds = load_dataset(
            data["hub_repo"],
            revision=data.get("revision"),
            split=split,
            token=os.environ.get("HF_TOKEN"),
        )
    else:
        ref = data.get(which)
        if not ref:
            return None
        path = resolve_path(ref)
        if not path.exists():
            raise Fail(f"data.{which} does not exist: {path}")
        ds = load_dataset("json", data_files=str(path), split="train")

    if "messages" not in ds.column_names:
        raise Fail(
            f"the {which} split has columns {ds.column_names} but every row must have "
            f"a 'messages' list of {{role, content}} objects. See preparation/FORMAT.md."
        )
    return ds


def render(ds: Dataset, tokenizer, max_seq_length: int, label: str) -> Dataset:
    """messages -> a single 'text' field, using the model's own chat template."""

    def to_text(batch):
        return {
            "text": [
                tokenizer.apply_chat_template(m, tokenize=False, add_generation_prompt=False)
                for m in batch["messages"]
            ]
        }

    ds = ds.map(to_text, batched=True, remove_columns=ds.column_names)

    # Rows longer than the window are truncated by the trainer without a word, so
    # count them here where they can still be acted on.
    lengths = [len(tokenizer(t, add_special_tokens=False)["input_ids"]) for t in ds["text"]]
    over = sum(1 for n in lengths if n > max_seq_length)
    info(f"{label:<6} {len(ds):>6} rows   max {max(lengths):>7,} tok   "
         f"p95 {sorted(lengths)[int(0.95 * (len(lengths) - 1))]:>7,} tok")
    if over:
        info(f"       {over} row(s) exceed max_seq_length={max_seq_length:,} and WILL be "
             f"truncated mid-example. Raise the window or drop those rows.")
    return ds


# ---------------------------------------------------------------- versioning

SEMVER = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def resolve_version(api, repo: str, requested: str | None) -> str | None:
    """
    Pick the tag this push gets, BEFORE anything is trained -- a tag that is
    already taken should cost nothing, not surface after 45 minutes on an H200.

    The tag is the readable handle; the commit sha it points at is the real
    version, because a tag can be moved or deleted and a sha cannot. Both are
    printed, and it is the sha that goes in registry/models.yaml.
    """
    if not requested:
        return None
    try:
        tags = [t.name for t in api.list_repo_refs(repo).tags]
    except Exception:      # noqa: BLE001 -- a repo created seconds ago has no refs
        tags = []

    if requested != "auto":
        if requested in tags:
            raise Fail(
                f"tag {requested} already exists on {repo}. A version that moves is "
                f"not a version -- pick the next one in output.version, or delete "
                f"that tag deliberately."
            )
        return requested

    versions = sorted(tuple(int(g) for g in m.groups())
                      for m in (SEMVER.match(t) for t in tags) if m)
    if not versions:
        return "v0.1.0"
    major, minor, patch = versions[-1]
    return f"v{major}.{minor}.{patch + 1}"


def model_card(cfg: dict, meta: dict, version: str | None) -> str:
    """
    An adapter with no card is one nobody can trace. The first line says it has
    not passed eval/, because a training loss on its own will not stop someone
    wiring it into production.
    """
    m, out = cfg["model"], cfg["output"]
    pin = version or meta["sha"][:12]
    return f"""---
base_model: {m['base']}
library_name: peft
tags: [lora, unsloth, clause-extraction, bahasa-indonesia]
---

# {out['push_to_hub'].split('/')[-1]}  {version or '(untagged)'}

LoRA adapter for Stage-2B clause extraction in Perjanjian Baku BI: an Indonesian
PJP standard-form contract in, its clauses as JSON out.

**Not evaluated.** `status: candidate` until `eval/` scores it against a golden
set the model has never seen. A lower training loss is not evidence of anything.

| | |
|---|---|
| Base | `{m['base']}` @ `{m.get('revision', 'main')[:12]}` |
| Run | `{cfg['run_name']}` |
| Data | {meta['rows']} rows, {meta['train_tokens']} |
| Steps | {meta['steps']} ({cfg['train'].get('num_train_epochs')} epochs, effective batch {meta['batch']}) |
| Loss | {meta['loss']:.4f} |
| LoRA | r={cfg.get('lora', {}).get('r', 32)}, alpha={cfg.get('lora', {}).get('alpha', 32)} |
| Trained at | {m['max_seq_length']:,} tokens |

## Use

```python
model.load_adapter("{out['push_to_hub']}", revision="{pin}")
```

Pin the tag or the sha, never `main` -- `main` is whatever ran last.

## Serving contract

The prompt shape this was trained on is not optional. It is the request
perjanjian-baku-bi's clause_extraction.go makes: the system prompt
`preparation/prompts/extraction_system.md` byte-for-byte, and a user message of
`DOCUMENT:\n` + the PDF text after `pdftotext -layout` and `keepIndonesianOnly()`.
A different prompt or text pipeline is an input the adapter never saw in training.

Trained without reasoning in the assistant turns: serve with
`enable_thinking: false`, or strip the empty `<think></think>`.

The run config that produced this is committed as
`training/configs/{meta['config']}` and is also in this repo as `run-config.yaml`.
"""


def registry_entry(cfg: dict, meta: dict, version: str | None) -> str:
    """
    The entry to paste into registry/models.yaml. Printed, not written: the pod's
    checkout is not where anything gets committed from, and a registry entry
    should arrive as a reviewed PR.
    """
    m, out = cfg["model"], cfg["output"]
    version_line = f"\n    version: {version}" if version else ""
    return f"""
  - name: {out['push_to_hub'].split('/')[-1]}
    hub_repo: {out['push_to_hub']}
    revision: {meta['sha']}{version_line}
    upstream: {m['base']}
    relation: finetune
    params: 27B                     # a LoRA over a 27B base; the adapter itself is tiny
    context_len: {m['max_seq_length']}                # what it was TRAINED at, not what the base serves
    license: MIT
    status: candidate               # nothing is production until eval/ says so
    notes: >-
      Clause-extraction LoRA from training/configs/{meta['config']},
      {meta['steps']} steps on {meta['rows']} rows. Base pinned at
      {m.get('revision', 'main')[:12]}. Not evaluated.
"""


# ------------------------------------------------------------------ trainer

def sft_config(**kw) -> SFTConfig:
    """
    Build an SFTConfig across trl versions. trl renamed max_seq_length -> max_length
    and dropped dataset_num_proc/packing arguments at different points; passing an
    unsupported one is a TypeError at construction, which is a bad way to lose an
    hour of pod time.
    """
    accepted = set(inspect.signature(SFTConfig.__init__).parameters)
    if "max_seq_length" in kw and "max_seq_length" not in accepted:
        kw["max_length"] = kw.pop("max_seq_length")
    dropped = sorted(k for k in kw if k not in accepted)
    for k in dropped:
        kw.pop(k)
    if dropped:
        info(f"trl {getattr(__import__('trl'), '__version__', '?')} ignores: {', '.join(dropped)}")
    return SFTConfig(**kw)


def check_versions(cfg: dict) -> None:
    """
    Fail before the download, not after. A 27B base is ~56 GB over the wire; finding
    out then that transformers cannot parse its config is an hour and a few dollars.
    """
    import transformers
    from packaging.version import Version

    need = cfg["model"].get("min_transformers")
    have = transformers.__version__
    if need and Version(have) < Version(need):
        raise Fail(
            f"transformers {have} is installed but {cfg['model']['base']} needs "
            f">={need}. On the pod:  pip install -r training/requirements.txt"
        )
    info(f"transformers    {have}")

    import trl
    info(f"trl             {trl.__version__}")
    if Version(trl.__version__) >= Version("1.0"):
        raise Fail(
            f"trl {trl.__version__} is a 1.x release; Unsloth {unsloth.__version__} "
            f"declares trl<=0.24.0. Reinstall from training/requirements.txt."
        )


def build(cfg: dict):
    m, lora = cfg["model"], cfg.get("lora", {})
    seed = int(cfg.get("train", {}).get("seed", 3407))

    head("model")
    info(f"base            {m['base']}  @ {m.get('revision', 'main')}")
    info(f"max_seq_length  {int(m['max_seq_length']):,}")
    info(f"load_in_4bit    {bool(m.get('load_in_4bit', False))}")
    info(f"text_only       {bool(m.get('text_only', True))}")

    # Gated-deltanet (linear attention) layers NaN their grad norms in fp16 — Unsloth
    # lists qwen3_5 in FORCE_FLOAT32 for that reason. Refuse rather than train garbage.
    if m.get("dtype") == "bfloat16" and not is_bfloat16_supported():
        raise Fail(
            "config asks for bfloat16 and this GPU does not support it. Qwen3.5's "
            "linear-attention layers produce NaN gradients in fp16, so this run would "
            "silently learn nothing. Use an Ampere-or-newer GPU (the H200 is Hopper)."
        )

    # FastModel, not FastLanguageModel: this base is a Qwen3_5ForConditionalGeneration
    # — a text decoder plus a vision tower. FastModel dispatches on the architecture
    # and, with text_only, loads the qwen3_5_text decoder and skips the tower.
    model, tokenizer = FastModel.from_pretrained(
        model_name=m["base"],
        revision=m.get("revision", "main"),
        max_seq_length=int(m["max_seq_length"]),
        dtype=None if m.get("dtype") in (None, "auto") else getattr(torch, m["dtype"]),
        load_in_4bit=bool(m.get("load_in_4bit", False)),
        text_only=bool(m.get("text_only", True)),
        token=os.environ.get("HF_TOKEN"),
    )

    # model.chat_template names the MARKER PAIR, it does not replace the template.
    # This base ships its own chat_template.jinja (thinking blocks, vision content)
    # and overwriting it with Unsloth's stock qwen-3 would change what the model is
    # trained to emit. Overriding is opt-in and loud.
    template = m.get("chat_template")
    if m.get("override_chat_template"):
        if not template:
            raise Fail("model.override_chat_template is true but model.chat_template "
                       "does not name one")
        tokenizer = get_chat_template(tokenizer, chat_template=template)
        info(f"chat_template   {template} — OVERRIDING the one the repo ships")
    elif tokenizer.chat_template is None:
        raise Fail(
            f"{m['base']} ships no chat template. Set model.chat_template to one of "
            f"{', '.join(sorted(RESPONSE_MARKERS))} and model.override_chat_template: true"
        )
    else:
        info(f"chat_template   from the repo; response markers: {template or 'none set'}")

    model = FastModel.get_peft_model(
        model,
        r=int(lora.get("r", 32)),
        lora_alpha=int(lora.get("alpha", 32)),
        lora_dropout=float(lora.get("dropout", 0.0)),
        bias=lora.get("bias", "none"),
        target_modules=lora.get("target_modules") or [
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        use_gradient_checkpointing=lora.get("use_gradient_checkpointing", "unsloth"),
        use_rslora=bool(lora.get("use_rslora", False)),
        random_state=int(lora.get("random_state", seed)),
        max_seq_length=int(m["max_seq_length"]),
    )
    return model, tokenizer


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("config", type=Path, help="training/configs/<task>-<date>.yaml")
    ap.add_argument("--dry-run", action="store_true",
                    help="load config + data, report shapes, train nothing")
    args = ap.parse_args()

    cfg = load_config(args.config)
    t, out = cfg["train"], cfg["output"]
    seed = int(t.get("seed", 3407))
    random.seed(seed)
    set_seed(seed)

    head(f"run  {cfg['run_name']}   (config {args.config.name}, seed {seed})")
    if torch.cuda.is_available():
        p = torch.cuda.get_device_properties(0)
        info(f"gpu             {p.name}  {p.total_memory / 1e9:.0f} GB  "
             f"x{torch.cuda.device_count()}")
        if torch.cuda.device_count() > 1:
            info("Unsloth is single-GPU. The extra GPUs will sit idle and still bill.")
    elif not args.dry_run:
        raise Fail("no CUDA device. This is meant to run on the H200 pod, not a laptop.")

    tracking = cfg.get("tracking") or {}
    if tracking.get("wandb_project") and os.environ.get("WANDB_API_KEY"):
        os.environ["WANDB_PROJECT"] = tracking["wandb_project"]
        report_to = "wandb"
    else:
        report_to = "none"
        if tracking.get("wandb_project"):
            info("WANDB_API_KEY not set — running without experiment tracking")

    check_versions(cfg)

    # Resolve the push target before anything expensive. A missing HF_TOKEN or a
    # tag that is already taken used to surface after the run, when the adapter
    # exists only in the pod's disk and the meter has been running for an hour.
    push_repo = out.get("push_to_hub")
    api = version = None
    if push_repo:
        if not os.environ.get("HF_TOKEN"):
            raise Fail("output.push_to_hub is set but HF_TOKEN is not in the "
                       "environment. pod.py passes it from .env; on a pod you "
                       "prepared by hand, export it before training.")
        from huggingface_hub import HfApi
        api = HfApi(token=os.environ["HF_TOKEN"])
        api.create_repo(push_repo, private=bool(out.get("private", True)),
                        exist_ok=True, repo_type="model")
        version = resolve_version(api, push_repo, out.get("version", "auto"))
        head("push target")
        info(f"repo            {push_repo}  ({'private' if out.get('private', True) else 'PUBLIC'})")
        info(f"version         {version or 'untagged — pin the commit sha instead'}")

    model, tokenizer = build(cfg)

    head("data")
    max_len = int(cfg["model"]["max_seq_length"])
    train_ds = load_split(cfg["data"], "train")
    if train_ds is None:
        raise Fail("data.train (or data.hub_repo + data.train_split) is required")
    train_ds = render(train_ds, tokenizer, max_len, "train")
    eval_ds = load_split(cfg["data"], "eval")
    if eval_ds is not None:
        eval_ds = render(eval_ds, tokenizer, max_len, "eval")

    if args.dry_run:
        head("dry run — nothing trained")
        print(json.dumps({"sample": train_ds[0]["text"][:1200]}, indent=2)[:2000])
        return

    adapter_dir = resolve_path(out["adapter_dir"])
    sft = sft_config(
        output_dir=str(adapter_dir / "checkpoints"),
        run_name=cfg["run_name"],
        seed=seed,
        dataset_text_field="text",
        max_seq_length=max_len,
        packing=bool(t.get("packing", False)),
        per_device_train_batch_size=int(t.get("per_device_train_batch_size", 1)),
        gradient_accumulation_steps=int(t.get("gradient_accumulation_steps", 8)),
        num_train_epochs=float(t.get("num_train_epochs", 2)),
        max_steps=int(t.get("max_steps", -1)),
        learning_rate=float(t.get("learning_rate", 2e-4)),
        warmup_ratio=float(t.get("warmup_ratio", 0.03)),
        lr_scheduler_type=t.get("lr_scheduler_type", "linear"),
        optim=t.get("optim", "adamw_torch_fused"),
        weight_decay=float(t.get("weight_decay", 0.01)),
        logging_steps=int(t.get("logging_steps", 1)),
        save_strategy=t.get("save_strategy", "steps"),
        save_steps=int(t.get("save_steps", 100)),
        save_total_limit=int(t.get("save_total_limit", 3)),
        eval_strategy="steps" if eval_ds is not None else "no",
        eval_steps=int(t.get("eval_steps", 100)),
        per_device_eval_batch_size=int(t.get("per_device_eval_batch_size", 1)),
        bf16=is_bfloat16_supported(),
        fp16=not is_bfloat16_supported(),
        report_to=report_to,
    )

    # trl renamed the tokenizer argument to processing_class. Passing the wrong one
    # is a TypeError after the model is already on the GPU — an expensive way to fail.
    tok_kw = ("processing_class"
              if "processing_class" in inspect.signature(SFTTrainer.__init__).parameters
              else "tokenizer")
    trainer = SFTTrainer(
        model=model,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        args=sft,
        **{tok_kw: tokenizer},
    )

    template = cfg["model"].get("chat_template") or cfg["data"].get("markers")
    markers = RESPONSE_MARKERS.get(template)
    if cfg["data"].get("train_on_responses_only", True):
        if markers:
            trainer = train_on_responses_only(
                trainer, instruction_part=markers[0], response_part=markers[1]
            )
            info(f"loss on assistant turns only ({template} markers)")
        else:
            info("train_on_responses_only requested but no markers known for this "
                 "template — training on the full sequence, prompt included. Set "
                 "model.chat_template (or data.markers) to one of: "
                 + ", ".join(sorted(RESPONSE_MARKERS)))

    head("train")
    stats = trainer.train(resume_from_checkpoint=bool(t.get("resume", False)))
    info(f"loss {stats.training_loss:.4f}   {stats.metrics.get('train_runtime', 0) / 60:.1f} min")
    info(f"peak vram {torch.cuda.max_memory_reserved() / 1e9:.1f} GB")

    head("output")
    adapter_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    (adapter_dir / "run-config.yaml").write_text(args.config.read_text())
    info(f"adapter         {adapter_dir}")

    if push_repo:
        if out.get("merge_16bit"):
            # 55 GB of rewritten weights. No card and no tag here: this path exists
            # for a serving stack that cannot take an adapter, and it is slow enough
            # that nobody should reach it by accident.
            model.push_to_hub_merged(push_repo, tokenizer, save_method="merged_16bit",
                                     token=os.environ["HF_TOKEN"],
                                     private=bool(out.get("private", True)))
            info(f"pushed merged   https://huggingface.co/{push_repo}")
        else:
            meta = {
                "rows": len(train_ds),
                "train_tokens": f"max {max_len:,} tok/row",
                "steps": stats.global_step,
                "batch": int(t.get("per_device_train_batch_size", 1))
                         * int(t.get("gradient_accumulation_steps", 8)),
                "loss": stats.training_loss,
                "config": args.config.name,
                "sha": "",
            }
            # Upload the folder save_pretrained just wrote rather than re-serialising
            # from VRAM: one call, one commit, and the returned sha covers all of it.
            commit = api.upload_folder(
                repo_id=push_repo,
                folder_path=str(adapter_dir),
                repo_type="model",
                commit_message=f"{version or 'untagged'}: {stats.global_step} steps on "
                               f"{len(train_ds)} rows ({cfg['run_name']})",
                ignore_patterns=["checkpoints/*", "**/optimizer.pt", "**/rng_state*"],
            )
            meta["sha"] = (getattr(commit, "oid", None)
                           or api.model_info(push_repo).sha)

            files = [f for f in api.list_repo_files(push_repo) if not f.startswith(".")]
            if not any(f.startswith("adapter_model") for f in files):
                raise Fail(f"pushed, but {push_repo} has no adapter_model file: {files}")

            # The card is written after the upload so it can quote the sha, then
            # committed on its own. A repo whose card contradicts its weights is
            # worse than one with no card.
            (adapter_dir / "README.md").write_text(model_card(cfg, meta, version))
            api.upload_file(path_or_fileobj=str(adapter_dir / "README.md"),
                            path_in_repo="README.md", repo_id=push_repo,
                            repo_type="model", commit_message="model card")

            if version:
                api.create_tag(push_repo, tag=version, revision=meta["sha"],
                               repo_type="model")
                info(f"tagged          {version} -> {meta['sha'][:12]}")
            info(f"pushed adapter  https://huggingface.co/{push_repo}  ({len(files)} files)")
            info(f"commit          {meta['sha']}")

            head("registry/models.yaml — paste this in")
            print(registry_entry(cfg, meta, version))

    head("next")
    info("1. paste the registry/models.yaml entry printed above into a PR")
    info("2. run eval/ against it — a lower training loss is not evidence of anything")
    info("3. only then deploy, and update registry/deployments.yaml in the same PR")
    info("4. python training/scripts/pod.py stop   # the pod bills until you do")


if __name__ == "__main__":
    try:
        main()
    except Fail as e:
        sys.exit(f"\n  error  {e}\n")
    except KeyboardInterrupt:
        sys.exit("\n  interrupted — the pod is still running and still billing\n")
