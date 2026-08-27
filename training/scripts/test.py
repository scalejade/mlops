#!/usr/bin/env python3
"""
Smoke test: prove the Unsloth stack actually trains this base on this pod.

    python training/scripts/test.py                    # full run, ~5 min after cache
    python training/scripts/test.py --until tokenizer  # costs nothing, downloads ~5 MB
    python training/scripts/test.py --steps 5 --max-seq-length 512
    python training/scripts/test.py --data training/datasets/pjp-clauses/sample.jsonl

A trial run that trains a little on real rows and publishes the adapter:

    python training/scripts/test.py --dataset --steps 60 --push

    --dataset  pulls 200 rows of a public instruct set and reshapes them into the
               messages schema. --push uploads the LoRA adapter, and a model card
               saying what it is, to a PUBLIC Hub repo. Both take an argument if
               you want a different dataset or repo.

Run this ONCE on a fresh pod, before the real run. It exercises every step that
train.py takes -- versions, tokenizer, chat template, 56 GB model load, LoRA,
loss masking, a handful of optimizer steps, generation, adapter save -- on six
synthetic rows and a short window, so a broken stack costs five minutes instead
of an hour into a real run.

Unlike train.py this takes command-line flags, because it is not an experiment:
nothing it produces is a result, and nothing it writes is kept. It never touches
training/configs/, and it pushes nothing unless you pass --push.

A pushed adapter from here is a trial artifact, not a model. It has seen a few
hundred generic rows, it has been through no eval, and the model card says so.
The real path is still: write a config, run train.py, then eval/.

Exit code is 0 only if every stage passed.
"""

from __future__ import annotations

# Unsloth must be imported before transformers/trl -- it patches them on import.
import unsloth  # noqa: F401  isort:skip
from unsloth import FastModel, is_bfloat16_supported
from unsloth.chat_templates import train_on_responses_only

import argparse
import inspect
import json
import math
import os
import re
import shutil
import sys
import time
from pathlib import Path

import torch
from datasets import Dataset, load_dataset
from transformers import set_seed
from trl import SFTConfig, SFTTrainer

REPO = Path(__file__).resolve().parents[2]

# Kept in sync with configs/example-lora.yaml. Overridable, because a smoke test
# of a different base is still a useful thing to be able to run.
BASE = "scalejade/qwen-sea-lion-v4.5-27b-it"
REVISION = "81d9102bab84b46085cc0f8539efe578d33e29da"

# Same pair train.py uses for qwen-3. The test asserts they are present in the
# rendered text -- if the repo's template changes, masking silently stops working
# and every run after that trains on its own prompt.
INSTRUCTION_PART = "<|im_start|>user\n"
RESPONSE_PART = "<|im_start|>assistant\n"

USD_PER_HOUR = 4.59  # pod.yaml cost.usd_per_hour, secure H200. Only used to print.

STAGES = ["env", "versions", "tokenizer", "model", "train", "generate", "save", "push"]

# Defaults for the trial run. Alpaca-cleaned is small, English, instruction-shaped
# and in the messages schema after one map -- enough for a loss curve that means
# something, and not pretending to be training data for this model's actual job.
DEFAULT_DATASET = "yahma/alpaca-cleaned"
DEFAULT_PUSH_REPO = "scalejade/qwen-sea-lion-v4.5-27b-lora-smoke"

# ShareGPT-style rows name the roles differently. Anything not in here is a shape
# we have not seen, and guessing at it would mislabel who said what.
ROLE_MAP = {"human": "user", "user": "user", "gpt": "assistant",
            "assistant": "assistant", "system": "system", "tool": "tool"}

# Six rows in the shape training/datasets/README.md specifies: one 'messages'
# column, assistant turn is the exact string a caller has to parse. Deliberately
# trivial and repetitive -- the point is that the loss moves, not that the model
# learns anything.
ROWS = [
    ("Tenor pinjaman adalah 36 bulan terhitung sejak tanggal pencairan.",
     {"field": "tenor", "value": "36 bulan"}),
    ("Suku bunga ditetapkan sebesar 9,75% per tahun secara efektif.",
     {"field": "suku_bunga", "value": "9,75% per tahun"}),
    ("Denda keterlambatan sebesar 0,2% per hari dari jumlah tertunggak.",
     {"field": "denda", "value": "0,2% per hari"}),
    ("Jumlah fasilitas kredit adalah Rp2.500.000.000 (dua miliar lima ratus juta rupiah).",
     {"field": "plafon", "value": "Rp2.500.000.000"}),
    ("Agunan berupa sertifikat hak milik nomor 1234 atas nama debitur.",
     {"field": "agunan", "value": "SHM 1234"}),
    ("Biaya provisi sebesar 1% dari plafon dibayar di muka.",
     {"field": "provisi", "value": "1%"}),
]
SYSTEM = "You extract clauses from Indonesian loan agreements. Reply with JSON only."


class Fail(Exception):
    """A problem the user needs to fix. Printed without a traceback."""


def head(msg: str) -> None:
    print(f"\n{msg}")


def info(msg: str) -> None:
    print(f"  {msg}")


def ok(msg: str) -> None:
    print(f"  ok    {msg}")


def bad(msg: str) -> None:
    print(f"  FAIL  {msg}")


def warn(msg: str) -> None:
    print(f"  warn  {msg}")


class Report:
    """Stage results, so one broken check does not hide the four after it."""

    def __init__(self) -> None:
        self.rows: list[tuple[str, bool, str]] = []
        self.pushed: str | None = None
        self.t0 = time.time()
        self.mark = self.t0

    def record(self, stage: str, passed: bool, note: str = "") -> None:
        elapsed = time.time() - self.mark
        self.mark = time.time()
        self.rows.append((stage, passed, f"{note}  ({elapsed:.0f}s)" if note else f"{elapsed:.0f}s"))

    def summary(self) -> int:
        total = time.time() - self.t0
        head("summary")
        for stage, passed, note in self.rows:
            print(f"  {'ok  ' if passed else 'FAIL'}  {stage:<10} {note}")
        info(f"{total / 60:.1f} min of pod time  ~${total / 3600 * USD_PER_HOUR:.2f}")
        failed = [s for s, p, _ in self.rows if not p]
        if failed:
            head(f"FAILED: {', '.join(failed)}")
            info("Fix these before starting a real run -- train.py takes the same path.")
            return 1
        head("all stages passed")
        if self.pushed:
            info(f"pushed  https://huggingface.co/{self.pushed}")
            info("It is a trial adapter and the card says so. Register it in "
                 "registry/models.yaml only if you intend to keep it.")
        info("The stack works. Now write a config and run for real:")
        info("  python training/scripts/train.py training/configs/<task>-<date>.yaml --dry-run")
        info("  python training/scripts/pod.py stop   # the pod bills until you do")
        return 0


# --------------------------------------------------------------------- stages

def stage_env(args) -> None:
    if not torch.cuda.is_available():
        raise Fail("no CUDA device. This is meant to run on the H200 pod, not a laptop.")
    p = torch.cuda.get_device_properties(0)
    vram = p.total_memory / 1e9
    info(f"gpu             {p.name}  {vram:.0f} GB  x{torch.cuda.device_count()}")
    info(f"torch           {torch.__version__}  cuda {torch.version.cuda}")

    if torch.cuda.device_count() > 1:
        warn("Unsloth is single-GPU. The extra GPUs idle and still bill.")

    # The one hard requirement. Qwen3.5's gated-deltanet layers NaN their grad
    # norms in fp16, so without bf16 the run below would 'succeed' and learn noise.
    if not is_bfloat16_supported():
        raise Fail(
            "this GPU has no bf16. Qwen3.5's linear-attention layers produce NaN "
            "gradients in fp16, so training here would silently learn nothing. "
            "Use Ampere or newer (the H200 is Hopper)."
        )
    ok("bf16 supported")

    if not args.load_in_4bit and vram < 100:
        warn(f"{vram:.0f} GB for a 55.56 GB bf16 base is tight. Expect an OOM at the "
             f"real max_seq_length even if this test passes. Try --load-in-4bit.")

    cache = os.environ.get("HUGGINGFACE_HUB_CACHE") or os.environ.get("HF_HOME", "unset")
    info(f"hf cache        {cache}")
    if "workspace" not in str(cache):
        warn("the HF cache is not under /workspace. The container disk is wiped on "
             "stop/start -- the 56 GB base will be re-downloaded every restart.")
    if not os.environ.get("HF_TOKEN"):
        warn("HF_TOKEN unset -- private scalejade/ repos will 401")


def stage_versions() -> None:
    """Exactly train.py's check_versions, so a pass here means a pass there."""
    import transformers
    import trl
    from packaging.version import Version

    info(f"unsloth         {getattr(unsloth, '__version__', '?')}")
    info(f"transformers    {transformers.__version__}")
    info(f"trl             {trl.__version__}")
    for pkg in ("peft", "datasets", "accelerate"):
        try:
            info(f"{pkg:<15} {__import__(pkg).__version__}")
        except Exception as e:  # noqa: BLE001 -- a missing dep is the finding
            raise Fail(f"{pkg} is not importable ({e}). "
                       f"pip install -r training/requirements.txt")

    # Below 5.2.0 AutoConfig cannot parse model_type qwen3_5 at all; above 5.5.0 is
    # outside what Unsloth declares. A plain `pip install unsloth` lands outside both.
    if Version(transformers.__version__) < Version("5.2.0"):
        raise Fail(
            f"transformers {transformers.__version__} cannot read model_type qwen3_5. "
            f"Need >=5.2.0:  pip install -r training/requirements.txt"
        )
    if Version(trl.__version__) >= Version("1.0"):
        raise Fail(
            f"trl {trl.__version__} is a 1.x release; Unsloth declares trl<=0.24.0. "
            f"Reinstall from training/requirements.txt."
        )
    ok("versions are inside the supported intersection")


def stage_tokenizer(args):
    """
    Tokenizer files are a few MB against the base's 55.56 GB, so every template
    assumption is checkable before anything expensive starts.
    """
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(
        args.model, revision=args.revision, token=os.environ.get("HF_TOKEN")
    )
    if tok.chat_template is None:
        raise Fail(f"{args.model} ships no chat template -- train.py would need "
                   f"model.override_chat_template: true")
    ok("chat template present in the repo (train.py uses this one, not Unsloth's)")

    text = tok.apply_chat_template(build_rows()[0]["messages"],
                                   tokenize=False, add_generation_prompt=False)
    for name, marker in (("instruction", INSTRUCTION_PART), ("response", RESPONSE_PART)):
        if marker not in text:
            raise Fail(
                f"the {name} marker {marker!r} is not in the rendered text. "
                f"train_on_responses_only would mask nothing and the run would "
                f"train on our own prompts. Rendered:\n{text[:400]}"
            )
    ok("response markers found -- loss masking will work")

    # The repo's template inserts an empty <think> block on the final assistant
    # turn. Print it: it is what the serving prompt has to agree with, and getting
    # it wrong is a silent quality loss, not an error.
    if "<think>" in text:
        info("template wraps the assistant turn in <think> (reasoning model) -- the "
             "endpoint must send enable_thinking:false or strip the empty block")
    print("\n".join("      " + ln for ln in text.strip().splitlines()[:12]))
    return tok


def cache_state(args) -> None:
    """Say whether the 56 GB is already local, before it starts arriving."""
    from huggingface_hub import snapshot_download

    try:
        snapshot_download(args.model, revision=args.revision, local_files_only=True)
        ok("base model already in the local cache")
    except Exception:  # noqa: BLE001 -- any miss means "not fully cached"
        warn(f"{args.model} is not fully cached. The load below will pull ~56 GB "
             f"(~15 min). Prefer doing it as its own resumable step:")
        info(f"  hf download {args.model} --revision {args.revision}")


def stage_model(args):
    cache_state(args)
    t = time.time()
    model, tok = FastModel.from_pretrained(
        model_name=args.model,
        revision=args.revision,
        max_seq_length=args.max_seq_length,
        dtype=torch.bfloat16,
        load_in_4bit=args.load_in_4bit,
        text_only=True,          # this base is a VLM; we never train the tower
        token=os.environ.get("HF_TOKEN"),
    )
    info(f"loaded in {(time.time() - t) / 60:.1f} min   "
         f"vram {torch.cuda.max_memory_reserved() / 1e9:.1f} GB")

    model = FastModel.get_peft_model(
        model,
        r=args.lora_r,           # 8 tests plumbing; --push raises it to 16
        lora_alpha=args.lora_r,
        lora_dropout=0.0,
        bias="none",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        use_gradient_checkpointing="unsloth",
        random_state=args.seed,
        max_seq_length=args.max_seq_length,
    )

    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    if trainable == 0:
        raise Fail("LoRA attached but nothing is trainable -- target_modules matched "
                   "no layer in this architecture")
    info(f"trainable       {trainable / 1e6:.1f}M / {total / 1e9:.1f}B "
         f"({100 * trainable / total:.3f}%)")
    ok("LoRA attached")
    return model, tok


def build_rows() -> list[dict]:
    return [
        {"messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": doc},
            {"role": "assistant", "content": json.dumps(ans, ensure_ascii=False)},
        ]}
        for doc, ans in ROWS
    ]


def to_messages(ds: Dataset) -> Dataset:
    """
    Reshape a public dataset into the one schema train.py accepts: a 'messages'
    list of {role, content}. Three shapes cover almost everything on the Hub;
    anything else raises rather than guesses, because a wrong guess here trains
    the model on text labelled as the wrong speaker and nothing downstream
    notices.
    """
    cols = set(ds.column_names)

    if "messages" in cols:
        return ds

    if "conversations" in cols:      # ShareGPT: [{"from": "human", "value": ...}]
        def conv(batch):
            out = []
            for turns in batch["conversations"]:
                out.append([{"role": ROLE_MAP.get(t.get("from", ""), ""),
                             "content": t.get("value", "")} for t in turns])
            return {"messages": out}
        ds = ds.map(conv, batched=True, remove_columns=ds.column_names)
        unknown = {m["role"] for row in ds["messages"] for m in row} - set(ROLE_MAP.values())
        if unknown:
            raise Fail(f"unmapped speaker labels {unknown} in the conversations column")
        return ds

    if {"instruction", "output"} <= cols:   # Alpaca
        def alpaca(batch):
            msgs = []
            for instr, inp, out in zip(batch["instruction"],
                                       batch.get("input", [""] * len(batch["output"])),
                                       batch["output"]):
                user = f"{instr}\n\n{inp}" if inp else instr
                msgs.append([{"role": "user", "content": user},
                             {"role": "assistant", "content": out}])
            return {"messages": msgs}
        return ds.map(alpaca, batched=True, remove_columns=ds.column_names)

    raise Fail(
        f"cannot reshape columns {sorted(cols)} into messages. Supported: a "
        f"'messages' column, a ShareGPT 'conversations' column, or Alpaca "
        f"instruction/input/output. Convert it yourself and pass --data."
    )


def build_dataset(args, tok) -> Dataset:
    if args.dataset:
        # Slice in the split spec, not after: this downloads a few hundred rows,
        # not the whole set.
        ds = load_dataset(args.dataset, split=f"train[:{args.rows}]",
                          token=os.environ.get("HF_TOKEN"))
        info(f"data            {args.dataset}, {len(ds)} rows, columns "
             f"{ds.column_names}")
        ds = to_messages(ds)
        info(f"                reshaped to messages ({len(ds[0]['messages'])} turns in row 0)")
    elif args.data:
        path = Path(args.data)
        path = path if path.is_absolute() else REPO / path
        if not path.exists():
            raise Fail(f"--data does not exist: {path}")
        ds = load_dataset("json", data_files=str(path), split="train")
        if "messages" not in ds.column_names:
            raise Fail(f"{path.name} has columns {ds.column_names}; every row needs a "
                       f"'messages' list. See training/datasets/README.md.")
        ds = ds.select(range(min(len(ds), args.rows)))
        info(f"data            {path.name}, {len(ds)} rows (capped at --rows)")
    else:
        ds = Dataset.from_list(build_rows())
        info(f"data            {len(ds)} synthetic rows")

    ds = ds.map(
        lambda b: {"text": [tok.apply_chat_template(m, tokenize=False,
                                                    add_generation_prompt=False)
                            for m in b["messages"]]},
        batched=True, remove_columns=ds.column_names,
    )
    lengths = [len(tok(t, add_special_tokens=False)["input_ids"]) for t in ds["text"]]
    info(f"lengths         max {max(lengths)} tok against a "
         f"{args.max_seq_length} window")
    if max(lengths) > args.max_seq_length:
        warn("rows will be truncated mid-example -- fine for a smoke test, never "
             "acceptable in a real run")
    return ds


def sft_config(**kw) -> SFTConfig:
    """trl renamed max_seq_length -> max_length and dropped args between versions."""
    accepted = set(inspect.signature(SFTConfig.__init__).parameters)
    if "max_seq_length" in kw and "max_seq_length" not in accepted:
        kw["max_length"] = kw.pop("max_seq_length")
    for k in [k for k in kw if k not in accepted]:
        kw.pop(k)
    return SFTConfig(**kw)


def check_masking(trainer, tok) -> None:
    """
    The check that matters most and is easiest to lose: after
    train_on_responses_only, the supervised tokens must be the assistant turn and
    nothing else. If this silently degrades, every future run trains the model to
    predict our own prompts back at us, and the loss curve still looks fine.
    """
    try:
        batch = trainer.data_collator([trainer.train_dataset[0]])
        labels = batch["labels"][0]
        kept = labels[labels != -100]
        if kept.numel() == 0:
            raise Fail("train_on_responses_only masked the entire sequence -- nothing "
                       "would be learned. The response marker no longer matches.")
        share = 100 * kept.numel() / labels.numel()
        supervised = tok.decode(kept)
        info(f"supervised      {kept.numel()}/{labels.numel()} tokens ({share:.0f}%)")
        info(f"                {supervised[:160]!r}")
        if INSTRUCTION_PART.strip() and SYSTEM[:20] in supervised:
            raise Fail("the system prompt is inside the supervised tokens -- masking "
                       "is not working, the model would learn to emit our prompt")
        if share > 80:
            warn("over 80% of the sequence is supervised; on chat data that usually "
                 "means the prompt is being trained on too")
        ok("loss is on the assistant turn only")
    except Fail:
        raise
    except Exception as e:  # noqa: BLE001 -- trl internals move between versions
        warn(f"could not inspect the collated batch on this trl ({e}). Masking is "
             f"unverified; check a real run's first loss against ~2-4, not ~0.5.")


def stage_train(args, model, tok) -> dict:
    ds = build_dataset(args, tok)
    workdir = Path(args.adapter_dir)
    sft = sft_config(
        output_dir=str(workdir / "checkpoints"),
        run_name="smoke-test",
        seed=args.seed,
        dataset_text_field="text",
        max_seq_length=args.max_seq_length,
        packing=False,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=2,
        max_steps=args.steps,
        learning_rate=2e-4,
        warmup_steps=1,
        lr_scheduler_type="linear",
        optim="adamw_torch_fused",
        weight_decay=0.01,
        logging_steps=1,
        save_strategy="no",     # a smoke test's checkpoints are worth nothing
        report_to="none",       # and it is not an experiment, so nothing is tracked
        bf16=True,
        fp16=False,
    )

    tok_kw = ("processing_class"
              if "processing_class" in inspect.signature(SFTTrainer.__init__).parameters
              else "tokenizer")
    trainer = SFTTrainer(model=model, train_dataset=ds, args=sft, **{tok_kw: tok})
    trainer = train_on_responses_only(
        trainer, instruction_part=INSTRUCTION_PART, response_part=RESPONSE_PART
    )
    check_masking(trainer, tok)

    head(f"train  {args.steps} steps")
    stats = trainer.train()

    losses = [h["loss"] for h in trainer.state.log_history if "loss" in h]
    grads = [h["grad_norm"] for h in trainer.state.log_history if "grad_norm" in h]
    if not losses:
        raise Fail("the trainer logged no loss at all -- it ran zero optimizer steps")

    meta = {"rows": len(ds), "steps": len(losses),
            "loss_first": losses[0], "loss_last": losses[-1]}
    info(f"loss            {losses[0]:.4f} -> {losses[-1]:.4f} over {len(losses)} steps")
    info(f"peak vram       {torch.cuda.max_memory_reserved() / 1e9:.1f} GB  "
         f"at max_seq_length={args.max_seq_length}")
    info(f"throughput      {stats.metrics.get('train_runtime', 0) / max(args.steps, 1):.1f} s/step")

    # The failure this whole test exists to catch. NaN grad norms here mean the
    # gated-deltanet layers are running in the wrong precision, and a real run
    # would burn an hour of H200 time producing an adapter of noise.
    if any(not math.isfinite(g) for g in grads):
        raise Fail(f"non-finite grad norm ({grads}). The linear-attention layers are "
                   f"not in bf16. Do not start a real run.")
    if any(not math.isfinite(v) for v in losses):
        raise Fail(f"non-finite loss ({losses}). Same cause as a NaN grad norm.")
    ok(f"loss and grad norms finite (grad norm {grads[-1]:.3f})" if grads
       else "loss finite")

    if losses[-1] >= losses[0]:
        warn("the loss did not go down. Over this few steps that is not conclusive, "
             "but if a real run does the same, check the data and the LR.")
    return meta


def stage_generate(args, model, tok) -> None:
    """
    Generate with the serving prompt shape, not a bare string. This is the last
    place to notice that the trained template and the endpoint's template disagree.
    """
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": ROWS[0][0]}]
    prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tok(prompt, return_tensors="pt").to(model.device)

    for_inference = getattr(FastModel, "for_inference", None)
    if for_inference:
        for_inference(model)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=args.max_new_tokens,
                             do_sample=False, use_cache=True)
    text = tok.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=False)
    info(f"prompt ends     {prompt[-60:]!r}")
    info(f"generated       {text[:300]!r}")
    if not text.strip():
        raise Fail("the model generated nothing. The adapter or the prompt shape is wrong.")
    ok("generation works through the adapter")

    for_training = getattr(FastModel, "for_training", None)
    if for_training:
        for_training(model)


def stage_save(args, model, tok) -> None:
    d = Path(args.adapter_dir)
    d.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(d))
    tok.save_pretrained(str(d))

    cfg = d / "adapter_config.json"
    if not cfg.exists():
        raise Fail(f"no adapter_config.json in {d} -- save_pretrained wrote a full "
                   f"model or nothing at all")
    weights = list(d.glob("adapter_model.*"))
    if not weights:
        raise Fail(f"no adapter weights in {d}")
    size = sum(f.stat().st_size for f in weights) / 1e6
    info(f"adapter         {d}  ({size:.0f} MB, {len(weights)} file(s))")
    if size > 5000:
        warn("that is far too large for a LoRA adapter -- the base may have been "
             "merged in. Check output.merge_16bit in the real config.")
    ok("adapter saved and shaped like a LoRA adapter")
    if not args.push:
        info("nothing pushed to the Hub -- a smoke test's adapter is not a result")


SEMVER = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def resolve_version(api, repo: str, requested: str | None) -> str | None:
    """
    Pick the tag this push gets, BEFORE the upload starts -- a version that is
    already taken should cost nothing, not fail after a few hundred MB.

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
                f"not a version -- pick the next one, or delete that tag deliberately."
            )
        return requested

    versions = sorted(tuple(int(g) for g in m.groups())
                      for m in (SEMVER.match(t) for t in tags) if m)
    if not versions:
        return "v0.1.0"
    major, minor, patch = versions[-1]
    return f"v{major}.{minor}.{patch + 1}"


def model_card(args, meta: dict, version: str | None) -> str:
    """
    A public repo with no card is a model nobody can tell the provenance of. This
    one's whole job is to say, in the first line, that this is a trial adapter
    from a smoke test and has not been evaluated -- the loss curve alone will not
    stop someone from wiring it into something.
    """
    source = args.dataset or (Path(args.data).name if args.data else "6 synthetic rows")
    loss = (f"{meta['loss_first']:.4f} -> {meta['loss_last']:.4f}"
            if meta else "not recorded")
    steps, rows = meta.get("steps", "?"), meta.get("rows", "?")
    pin = version or "main"
    shown = version or "untagged -- pin the commit sha instead"
    name = args.push.split("/")[-1]

    return f"""---
base_model: {args.model}
library_name: peft
pipeline_tag: text-generation
tags:
- lora
- peft
- unsloth
- trl
- sft
- smoke-test
---

# {name}

**This is a trial adapter, not a model.** It was produced by
`training/scripts/test.py` in scalejade/mlops -- a smoke test whose purpose is to
prove the training stack works end to end. It trained for {steps} optimizer steps
on {rows} rows of a generic instruction set, and it has been through **no
evaluation of any kind**. Do not serve it, and do not read anything into the loss.

| | |
|---|---|
| Version | {shown} |
| Base | [`{args.model}`](https://huggingface.co/{args.model}) @ `{args.revision}` |
| Method | LoRA, r={args.lora_r}, alpha={args.lora_r}, dropout 0.0 |
| Targets | q,k,v,o,gate,up,down_proj |
| Steps | {steps} (batch 1 x accum 2), lr 2e-4, linear, warmup 1 |
| Window | {args.max_seq_length} tokens |
| Precision | bf16 (this base NaNs in fp16 -- its gated-deltanet layers) |
| Data | {source}, {rows} rows |
| Loss | {loss} |

## Versions

Every run of the script that made this pushes a new commit here. The tags are the
readable handles; the commit sha under a tag is what actually identifies a build.
`git log`, or the Hub's commit list, is the history.

## Use

```python
from unsloth import FastModel

model, tokenizer = FastModel.from_pretrained(
    "{args.model}", revision="{args.revision}",
    max_seq_length={args.max_seq_length}, dtype=None, text_only=True,
)
model.load_adapter("{args.push}", revision="{pin}")
```

Pin `revision` to a tag or a commit sha, never to `main`. `main` moves the next
time this run is repeated, and a model that changes under its caller is the exact
failure this repo is arranged to prevent.

The base is a reasoning VLM: load it with `text_only=True`, keep its own chat
template, and expect the assistant turn to open with a `<think>` block.

## Provenance

Trained on one H200 via `training/scripts/test.py`. A real run in that repo goes
through `training/configs/<task>-<date>.yaml` and `train.py`, which records the
config alongside the adapter; this one has no config because it is not an
experiment.
"""


def registry_entry(args, meta: dict, sha: str, version: str | None) -> str:
    """
    The entry to paste into registry/models.yaml. Printed, not written: the pod's
    checkout is not where anything gets committed from, and a registry entry
    should arrive as a reviewed PR.
    """
    version_line = f"\n    version: {version}" if version else ""
    source = args.dataset or args.data or "synthetic rows"
    return f"""
  - name: {args.push.split('/')[-1]}
    hub_repo: {args.push}
    revision: {sha}{version_line}
    upstream: {args.model}
    relation: finetune
    params: 27B                     # a LoRA over a 27B base; the adapter itself is tiny
    context_len: {args.max_seq_length}                # what it was TRAINED at, not what the base serves
    license: MIT
    status: candidate               # nothing is production until eval/ says so
    notes: >-
      Trial LoRA from training/scripts/test.py, {meta.get('steps', '?')} steps on
      {meta.get('rows', '?')} rows of {source}. Base pinned at
      {args.revision[:12]}. Not evaluated.
"""


def stage_push(args, model, tok, meta: dict) -> None:
    from huggingface_hub import HfApi

    token = os.environ.get("HF_TOKEN")
    if not token:
        raise Fail("--push needs HF_TOKEN in the environment (pod.py passes it "
                   "through from .env; bootstrap.sh logs in with it)")

    visibility = "private" if args.private else "PUBLIC"
    info(f"target          {args.push}  ({visibility})")
    if not args.private:
        info("                a public repo is world-readable and indexed the moment "
             "it exists; deleting it later does not un-publish it")

    api = HfApi(token=token)
    # create_repo first: pushing to a repo that already exists cannot change its
    # visibility, so --private is only meaningful at creation. Say so rather than
    # let it silently not apply.
    created = api.create_repo(args.push, private=args.private, exist_ok=True,
                              repo_type="model")
    existing = getattr(created, "private", None)
    if existing is not None and existing != args.private:
        warn(f"{args.push} already exists and is "
             f"{'private' if existing else 'public'}; a push does not change that. "
             f"Flip it in the repo settings if it is wrong.")

    version = resolve_version(api, args.push, args.version)
    if version:
        note = "  (next after the tags already on the repo)" if args.version == "auto" else ""
        info(f"version         {version}{note}")

    model.push_to_hub(args.push, token=token, private=args.private)
    tok.push_to_hub(args.push, token=token, private=args.private)

    # peft writes its own stub card on push; ours replaces it, so it has to go last.
    card = Path(args.adapter_dir) / "README.md"
    card.parent.mkdir(parents=True, exist_ok=True)
    card.write_text(model_card(args, meta, version))
    api.upload_file(path_or_fileobj=str(card), path_in_repo="README.md",
                    repo_id=args.push, repo_type="model")

    files = [f for f in api.list_repo_files(args.push) if not f.startswith(".")]
    if not any(f.startswith("adapter_model") for f in files):
        raise Fail(f"pushed, but {args.push} has no adapter_model file: {files}")

    # The sha of main as it now stands. This is what registry/models.yaml pins --
    # the same discipline the base model itself is pinned with.
    sha = api.model_info(args.push).sha
    if version:
        api.create_tag(args.push, tag=version, revision=sha, repo_type="model")
        info(f"tagged          {version} -> {sha[:12]}")

    ok(f"https://huggingface.co/{args.push}   ({len(files)} files, {visibility})")
    info(f"commit          {sha}")
    head("registry/models.yaml -- paste this in if you are keeping it")
    print(registry_entry(args, meta, sha, version))


# ----------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=BASE)
    ap.add_argument("--revision", default=REVISION)
    ap.add_argument("--steps", type=int, default=None,
                    help="optimizer steps. Default 10 (enough to see the loss move), "
                         "or 60 with --push, where the adapter is kept")
    ap.add_argument("--lora-r", type=int, default=None,
                    help="LoRA rank. Default 8, or 16 with --push")
    ap.add_argument("--max-seq-length", type=int, default=1024,
                    help="short on purpose -- this tests the stack, not the window. "
                         "Raise it to probe VRAM headroom before a long-context run.")
    ap.add_argument("--load-in-4bit", action="store_true",
                    help="only if the card cannot hold 55.56 GB of bf16")
    ap.add_argument("--data", help="local JSONL to use instead of the synthetic "
                                   "rows, to smoke-test a real dataset")
    ap.add_argument("--dataset", nargs="?", const=DEFAULT_DATASET, default=None,
                    help=f"a public Hub dataset to train on, reshaped into the "
                         f"messages schema. Bare --dataset means {DEFAULT_DATASET}.")
    ap.add_argument("--rows", type=int, default=200,
                    help="rows to take from --dataset / --data (default 200)")
    ap.add_argument("--push", nargs="?", const=DEFAULT_PUSH_REPO, default=None,
                    metavar="REPO",
                    help=f"push the adapter and a model card to the Hub, PUBLIC by "
                         f"default. Bare --push means {DEFAULT_PUSH_REPO}.")
    ap.add_argument("--private", action="store_true",
                    help="create the pushed repo private instead of public")
    ap.add_argument("--version", nargs="?", const="auto", default=None,
                    metavar="TAG",
                    help="tag the pushed commit (--version v0.2.0). Bare --version "
                         "takes the next patch after the tags already on the repo. "
                         "Without it the push is untagged, but the commit sha is "
                         "still printed and is still a pinnable version.")
    ap.add_argument("--until", choices=STAGES, default=STAGES[-1],
                    help="stop after this stage. --until tokenizer downloads only a "
                         "few MB and checks everything that does not need the weights.")
    ap.add_argument("--max-new-tokens", type=int, default=64)
    ap.add_argument("--adapter-dir", default=str(REPO / "training/adapters/_smoke-test"),
                    help="scratch output. Deleted afterwards unless --keep.")
    ap.add_argument("--keep", action="store_true", help="keep the scratch adapter dir")
    ap.add_argument("--seed", type=int, default=3407)
    args = ap.parse_args()

    # A pushed adapter is kept, so it gets the settings of a small real run
    # rather than the ten-step plumbing check. Explicit flags still win.
    args.steps = args.steps if args.steps is not None else (60 if args.push else 10)
    args.lora_r = args.lora_r if args.lora_r is not None else (16 if args.push else 8)
    if args.data and args.dataset:
        return sys.exit("  error  pass --data or --dataset, not both\n")
    if args.version and not args.push:
        return sys.exit("  error  --version only means something with --push\n")
    if args.push and args.until != STAGES[-1]:
        return sys.exit(f"  error  --push cannot run with --until {args.until}; the "
                        f"adapter has to be trained and saved first\n")

    set_seed(args.seed)
    wanted = STAGES[: STAGES.index(args.until) + 1]
    report = Report()
    print(f"\nsmoke test  {args.model} @ {args.revision[:8]}")
    print(f"            {args.steps} steps, r={args.lora_r}, "
          f"{args.max_seq_length} tok window")
    if args.push:
        print(f"            will push to {args.push} "
              f"({'private' if args.private else 'PUBLIC'}) when it passes")
    print(f"            stages: {' '.join(wanted)}")

    model = tok = None
    try:
        head("env")
        stage_env(args)
        report.record("env", True)

        if "versions" in wanted:
            head("versions")
            stage_versions()
            report.record("versions", True)

        if "tokenizer" in wanted:
            head("tokenizer")
            tok = stage_tokenizer(args)
            report.record("tokenizer", True)

        if "model" in wanted:
            head("model")
            model, tok = stage_model(args)
            report.record("model", True, f"{torch.cuda.max_memory_reserved() / 1e9:.0f} GB")

        meta: dict = {}
        if "train" in wanted:
            head("data")
            meta = stage_train(args, model, tok)
            report.record("train", True, f"{args.steps} steps")

        if "generate" in wanted:
            head("generate")
            stage_generate(args, model, tok)
            report.record("generate", True)

        if "save" in wanted:
            head("save")
            stage_save(args, model, tok)
            report.record("save", True)

        # Last, and only on request: everything above has to have passed, because
        # a push is the one step here that other people can see.
        if "push" in wanted and args.push:
            head("push")
            stage_push(args, model, tok, meta)
            report.pushed = args.push
            report.record("push", True, args.push)

    except Fail as e:
        bad(str(e))
        report.record(wanted[len(report.rows)] if len(report.rows) < len(wanted)
                      else "unknown", False, "see above")
    except torch.cuda.OutOfMemoryError:
        bad(f"OOM at max_seq_length={args.max_seq_length}. In order: lower "
            f"--max-seq-length, then --load-in-4bit. The real run needs the same "
            f"headroom at its own window.")
        report.record(wanted[len(report.rows)] if len(report.rows) < len(wanted)
                      else "unknown", False, "OOM")
    finally:
        if not args.keep:
            shutil.rmtree(args.adapter_dir, ignore_errors=True)

    return report.summary()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit("\n  interrupted -- the pod is still running and still billing\n")
