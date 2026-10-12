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
import hashlib
import inspect
import json
import math
import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path

import torch
import yaml
from datasets import Dataset, load_dataset
from transformers import TrainerCallback, set_seed
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

    if cfg.get("status") == "draft":
        raise Fail(f"{path.name} is marked `status: draft` — it is not ready to train. "
                   "Finish its TODOs, then remove that line.")

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
    ds.lengths = lengths      # read by RunMetrics for the W&B run summary
    return ds


# --------------------------------------------------------------- run record

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_report(cfg: dict) -> dict:
    """preparation/data/build-report.json next to the local train file, or {}.

    Copied to the pod by `make train-push-data` alongside the JSONL. It knows which
    document and annotation tags each row came from; the JSONL only has messages.
    """
    ref = cfg["data"].get("train")
    if not ref or cfg["data"].get("hub_repo"):
        return {}
    path = resolve_path(ref).parent / "build-report.json"
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def row_meta(report: dict, split: str, n_rows: int) -> list[dict] | None:
    """Per-row metadata for a split, in file order — or None when the report is from
    another build (its row count disagrees), so rows are never labelled wrongly."""
    meta = (report.get(split) or {}).get("meta")
    if not meta:
        return None
    if len(meta) != n_rows:
        info(f"build-report.json lists {len(meta)} {split} rows, the file has {n_rows} — "
             f"it is from another build; per-row labels are off for this run")
        return None
    return meta


def fingerprint(cfg: dict, config_path: Path, report: dict) -> dict:
    """What the run was made from, beyond the config. W&B records the git commit on
    its own, but not the data: two runs on one commit with a `make data` between
    them look identical without this."""
    fp = {"config_file": config_path.name, "config_sha256": sha256_file(config_path)[:16]}
    data = cfg["data"]
    if data.get("hub_repo"):
        fp |= {"data_hub_repo": data["hub_repo"], "data_revision": data.get("revision")}
    for split in ("train", "eval"):
        ref = data.get(split)
        if ref and not data.get("hub_repo") and resolve_path(ref).exists():
            fp[f"data_{split}_sha256"] = sha256_file(resolve_path(ref))[:16]
    prompt = REPO / "preparation/prompts/extraction_system.md"
    if prompt.exists():
        fp["system_prompt_sha256"] = sha256_file(prompt)[:16]
    if report:
        fp["build_documents"] = len(report.get("documents") or [])
        for split in ("train", "eval", "test"):
            if split in report:
                fp[f"build_{split}_rows"] = report[split].get("rows")
                fp[f"build_{split}_dropped"] = len(report[split].get("dropped") or [])
    git = lambda *a: subprocess.run(["git", "-C", str(REPO), *a], capture_output=True,
                                    text=True, timeout=10).stdout.strip()
    try:
        fp["git_commit"] = git("rev-parse", "HEAD") or None
        fp["git_dirty"] = bool(git("status", "--porcelain", "--untracked-files=no"))
    except (OSError, subprocess.SubprocessError):
        pass
    return fp


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
| Data | {meta['rows']} rows, {meta['train_tokens']}, train.jsonl sha256 `{meta.get('data_sha', '?')}` |
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


# ------------------------------------------------------------------ metrics

class TokenCounter:
    """Wraps the data collator to count what each batch carries, as it is built.

    The trainer knows how many steps ran, not how many tokens went through them,
    and with rows from 8k to 30k tokens a step is not a unit of work. Counts only
    while the model is in training mode, so eval batches stay out of the totals.
    """

    def __init__(self, collator, model):
        self.collator, self.model = collator, model
        self.tokens = self.answer_tokens = 0

    def __call__(self, features):
        batch = self.collator(features)
        if self.model.training:
            mask = batch.get("attention_mask")
            ids = batch["input_ids"]
            self.tokens += int(mask.sum() if mask is not None else ids.numel())
            labels = batch.get("labels")
            if labels is not None:
                # -100 is the ignore index: prompt tokens under train_on_responses_only.
                self.answer_tokens += int((labels != -100).sum())
        return batch


class EvalRowLosses:
    """The loss of every eval row, at no extra GPU cost.

    The eval loop calls trainer.prediction_step once per batch, in dataset order
    (eval is never shuffled), and already computes each batch's loss there; the
    Trainer just averages it away. Wrapping the method keeps each one. With
    per_device_eval_batch_size 1 a batch is a row, so the list lines up with
    eval.jsonl and with build-report.json's meta for it.
    """

    def __init__(self, trainer):
        self.losses: list[float] = []
        inner = trainer.prediction_step

        def recording(model, inputs, prediction_loss_only, ignore_keys=None):
            out = inner(model, inputs, prediction_loss_only, ignore_keys=ignore_keys)
            self.losses.append(float(out[0]) if out[0] is not None else math.nan)
            return out

        trainer.prediction_step = recording

    def take(self) -> list[float]:
        got, self.losses = self.losses, []
        return got


def label_key(value) -> str:
    """An annotation value as a W&B metric-name segment."""
    return re.sub(r"[^0-9A-Za-z]+", "_", str(value)).strip("_") or "unknown"


class RunMetrics(TrainerCallback):
    """What the HF Trainer does not send to W&B on its own. All of it is bookkeeping
    on numbers already in hand — no extra forward pass, so no extra GPU time.

      eval/   perplexity, best_loss, best_step, loss_gap (eval - train),
              loss_by_<field>/<value> and an eval/rows table (via EvalRowLosses)
      train/  perplexity
      perf/   tokens_per_second, seconds_per_step, eta_minutes
      data/   tokens_seen, answer_tokens_seen, answer_fraction
      gpu/    mem_allocated_gb, mem_reserved_gb, peak_reserved_gb
      cost/   usd_so_far, usd_projected        (POD_USD_PER_HOUR, set by pod.py)
      summary: dataset shape, best eval step, the kept checkpoint closest to it,
              the worst eval row
      config:  the run fingerprint (data / prompt / config hashes, git, build counts)

    Logged on the trainer's own x-axis (train/global_step), so the panels line up
    with train/loss and eval/loss.
    """

    def __init__(self, counter: TokenCounter, train_lengths: list[int],
                 eval_lengths: list[int] | None, max_seq_length: int,
                 fingerprint: dict | None = None, rows: EvalRowLosses | None = None,
                 eval_meta: list[dict] | None = None, group_by: list[str] | None = None):
        import wandb
        self.wandb, self.counter = wandb, counter
        self.fingerprint, self.rows, self.eval_meta = fingerprint or {}, rows, eval_meta
        self.group_by = group_by or []
        self.worst: tuple[float, str] | None = None
        self.train_lengths, self.eval_lengths = train_lengths, eval_lengths or []
        self.max_seq_length = max_seq_length
        self.usd_per_hour = float(os.environ.get("POD_USD_PER_HOUR") or 0)
        self.best_loss, self.best_step = math.inf, None
        self.last_train_loss = None

    def _log(self, step: int, metrics: dict) -> None:
        if self.wandb.run is not None:
            self.wandb.log({"train/global_step": step, **metrics})

    @staticmethod
    def _shape(lengths: list[int]) -> dict:
        if not lengths:
            return {}
        s = sorted(lengths)
        return {"rows": len(s), "tokens_total": sum(s), "tokens_max": s[-1],
                "tokens_median": s[len(s) // 2], "tokens_p95": s[int(0.95 * (len(s) - 1))]}

    def on_train_begin(self, args, state, control, **kw):
        self.started = self.last_time = time.time()
        self.last_tokens = self.last_step = 0
        run = self.wandb.run
        if run is None:
            return
        summary = {f"data/train_{k}": v for k, v in self._shape(self.train_lengths).items()}
        summary |= {f"data/eval_{k}": v for k, v in self._shape(self.eval_lengths).items()}
        summary["data/train_rows_over_max_seq_length"] = sum(
            1 for n in self.train_lengths if n > self.max_seq_length)
        run.summary.update(summary)
        run.config.update({"pod_usd_per_hour": self.usd_per_hour or None,
                           "fingerprint": self.fingerprint}, allow_val_change=True)

    def on_log(self, args, state, control, logs=None, **kw):
        logs, step, now = logs or {}, state.global_step, time.time()
        out = {}
        if "loss" in logs:                               # a training log line
            self.last_train_loss = logs["loss"]
            out["train/perplexity"] = math.exp(min(logs["loss"], 20))
            dt, dsteps = now - self.last_time, step - self.last_step
            dtok = self.counter.tokens - self.last_tokens
            if dt > 0 and dsteps > 0:
                out["perf/tokens_per_second"] = dtok / dt
                out["perf/seconds_per_step"] = dt / dsteps
                if state.max_steps:
                    out["perf/eta_minutes"] = (state.max_steps - step) * dt / dsteps / 60
            self.last_time, self.last_step, self.last_tokens = now, step, self.counter.tokens

            out["data/tokens_seen"] = self.counter.tokens
            out["data/answer_tokens_seen"] = self.counter.answer_tokens
            if self.counter.tokens:
                out["data/answer_fraction"] = self.counter.answer_tokens / self.counter.tokens

            if torch.cuda.is_available():
                out["gpu/mem_allocated_gb"] = torch.cuda.memory_allocated() / 1e9
                out["gpu/mem_reserved_gb"] = torch.cuda.memory_reserved() / 1e9
                out["gpu/peak_reserved_gb"] = torch.cuda.max_memory_reserved() / 1e9

            if self.usd_per_hour:
                hours = (now - self.started) / 3600
                out["cost/usd_so_far"] = hours * self.usd_per_hour
                if step and state.max_steps:
                    out["cost/usd_projected"] = hours * state.max_steps / step * self.usd_per_hour
        if out:
            self._log(step, out)

    def on_evaluate(self, args, state, control, metrics=None, **kw):
        loss = (metrics or {}).get("eval_loss")
        if loss is None:
            return
        if loss < self.best_loss:
            self.best_loss, self.best_step = loss, state.global_step
        out = {"eval/perplexity": math.exp(min(loss, 20)),
               "eval/best_loss": self.best_loss, "eval/best_step": self.best_step}
        if self.last_train_loss is not None:
            # Positive and growing: the model is fitting the train rows, not the task.
            out["eval/loss_gap"] = loss - self.last_train_loss
        out |= self._per_row(state.global_step)
        self._log(state.global_step, out)

    def _per_row(self, step: int) -> dict:
        """eval/loss split by annotation field, and a table of every row's loss."""
        losses = self.rows.take() if self.rows else []
        if not losses:
            return {}
        meta = self.eval_meta if self.eval_meta and len(self.eval_meta) == len(losses) else None
        out, groups, table = {}, {}, []
        for i, loss in enumerate(losses):
            m = meta[i] if meta else {}
            ann = m.get("annotation") or {}
            doc = m.get("doc") or f"row {i}"
            table.append([step, i, doc, m.get("kind", "?"), m.get("tokens"), m.get("clauses"),
                          *[ann.get(f, "?") for f in self.group_by], loss])
            for f in self.group_by:
                groups.setdefault((f, ann.get(f, "?")), []).append(loss)
        for (f, v), ls in groups.items():
            out[f"eval/loss_by_{label_key(f)}/{label_key(v)}"] = sum(ls) / len(ls)
        worst = max(table, key=lambda r: r[-1] if not math.isnan(r[-1]) else -1)
        self.worst = (worst[-1], f"{worst[2]} (row {worst[1]})")
        print(f"  eval rows       worst {worst[-1]:.4f} {self.worst[1]}   "
              f"best {min(r[-1] for r in table):.4f}   ({len(table)} rows)")
        if self.wandb.run is not None:
            cols = ["step", "row", "doc", "kind", "tokens", "clauses", *self.group_by, "loss"]
            out["eval/rows"] = self.wandb.Table(columns=cols, data=table)
        return out

    def on_train_end(self, args, state, control, **kw):
        run = self.wandb.run
        if run is None or self.best_step is None:
            return
        # Checkpoints exist only every save_steps, and save_total_limit deletes all but
        # the newest few — so name the one nearest the best eval among those still on
        # disk, and say when the best one itself is gone.
        kept = sorted(int(d.name.split("-")[1]) for d in Path(args.output_dir).glob("checkpoint-*")
                      if d.name.split("-")[1].isdigit())
        nearest = min(kept, key=lambda s: abs(s - self.best_step)) if kept else None
        if self.worst:
            run.summary.update({"eval/worst_row": self.worst[1], "eval/worst_row_loss": self.worst[0]})
        run.summary.update({
            "eval/best_loss": self.best_loss, "eval/best_step": self.best_step,
            "eval/best_checkpoint": f"checkpoint-{nearest}" if nearest else None,
            "eval/best_checkpoint_steps_off": abs(nearest - self.best_step) if nearest else None,
            "eval/best_is_final": self.best_step == state.global_step,
            "data/tokens_seen": self.counter.tokens,
            "data/answer_tokens_seen": self.counter.answer_tokens,
            **({"cost/usd_total": (time.time() - self.started) / 3600 * self.usd_per_hour}
               if self.usd_per_hour else {}),
        })


CLAUSE_MATCH = 0.8   # word-set overlap at which a predicted clause counts as a labelled one


def clause_words(app, clause) -> frozenset:
    """A clause's text as the set of its words, normalised the way the app keys pasal."""
    return frozenset(app.normalize_clause_name(clause.clause_text).split())


def match_clauses(app, predicted: list, labelled: list) -> int:
    """How many labelled clauses the prediction found, one-to-one.

    A predicted clause matches a labelled one when their word sets overlap by at
    least CLAUSE_MATCH (Jaccard). Word sets, not exact strings: the model may
    unwrap a line or fix a space differently, and that is not a missed clause.
    Pairs are taken closest-first across both lists, so a missing clause cannot
    claim the match of a near-identical sibling that is present.
    """
    pred = [clause_words(app, c) for c in predicted]
    gold = [clause_words(app, c) for c in labelled]
    pairs = []
    for i, g in enumerate(gold):
        for j, w in enumerate(pred):
            union = len(g | w)
            score = len(g & w) / union if union else 1.0
            if score >= CLAUSE_MATCH:
                pairs.append((score, i, j))
    pairs.sort(key=lambda x: (-x[0], x[1], x[2]))
    used_gold, used_pred = set(), set()
    for _, i, j in pairs:
        if i not in used_gold and j not in used_pred:
            used_gold.add(i)
            used_pred.add(j)
    return len(used_gold)


def score_reply(app, reply: str, labels: str) -> dict:
    """Score one generated reply against the row's labelled answer, through the app's
    own steps 6-7 (parse_reply, finalize): what the app would have kept."""
    gold, _ = app.finalize(app.parse_reply(labels))
    try:
        pred, _ = app.finalize(app.parse_reply(reply))
        valid = True
    except app.AppError:
        pred, valid = [], False
    found = match_clauses(app, pred, gold)
    return {"json_valid": valid, "labelled": len(gold), "predicted": len(pred), "matched": found}


class QualityCheck(TrainerCallback):
    """Generate the extraction for a few validation rows and score it the way the app
    would — the one metric here about the product rather than the optimiser.

      quality/json_valid          share of replies the app's parser accepts
      quality/finished            share that stopped on their own, inside max_new_tokens
      quality/clause_recall       labelled clauses found / labelled clauses
      quality/clause_precision    found / clauses the model returned
      quality/clause_f1
      quality/clause_count_ratio  returned / labelled
      quality/output_tokens, quality/seconds
      quality/rows                a table, one line per generated row

    Greedy decoding with the serving prompt (enable_thinking off), like the app's
    temperature-0 call. Runs at each epoch end ("epoch") or once at the end
    ("end"). It costs real H200 time — minutes per row — and is guarded so that
    an error or OOM in it is logged and training carries on.
    """

    def __init__(self, rows: list[dict], meta: list[dict] | None, tokenizer,
                 when: str, max_new_tokens: int):
        sys.path.insert(0, str(REPO / "preparation"))
        import app_request
        import wandb
        self.app, self.wandb, self.tok = app_request, wandb, tokenizer
        self.rows, self.meta = rows, meta
        self.when, self.max_new_tokens = when, max_new_tokens
        self.done_at: int | None = None

    def on_epoch_end(self, args, state, control, model=None, **kw):
        if self.when == "epoch":
            self.check(model, state)

    def on_train_end(self, args, state, control, model=None, **kw):
        if self.when in ("epoch", "end") and self.done_at != state.global_step:
            self.check(model, state)

    def check(self, model, state) -> None:
        if model is None or self.done_at == state.global_step:
            return
        self.done_at = state.global_step
        print(f"\n  quality check   step {state.global_step}: generating {len(self.rows)} "
              f"validation row(s), up to {self.max_new_tokens:,} tokens each")
        from unsloth import FastModel
        # unsloth's generate reads config.architectures to pick a path, and a
        # text_only load leaves it None — the same fix as test.py's generate stage.
        cfg = getattr(model, "config", None)
        if cfg is not None and getattr(cfg, "architectures", None) is None:
            inner = getattr(getattr(model, "base_model", None), "model", model)
            cfg.architectures = [type(inner).__name__]
        results, table = [], []
        try:
            if getattr(FastModel, "for_inference", None):
                FastModel.for_inference(model)
            for i, row in enumerate(self.rows):
                msgs = row["messages"]
                prompt = self.tok.apply_chat_template(msgs[:-1], tokenize=False,
                                                      add_generation_prompt=True,
                                                      enable_thinking=False)
                inputs = self.tok(prompt, return_tensors="pt",
                                  add_special_tokens=False).to(model.device)
                started = time.time()
                with torch.no_grad():
                    out = model.generate(**inputs, max_new_tokens=self.max_new_tokens,
                                         do_sample=False, use_cache=True)
                new = out[0][inputs["input_ids"].shape[1]:]
                seconds = time.time() - started
                r = score_reply(self.app, self.tok.decode(new, skip_special_tokens=True),
                                msgs[-1]["content"])
                r |= {"finished": len(new) < self.max_new_tokens,
                      "output_tokens": len(new), "seconds": seconds}
                results.append(r)
                doc = (self.meta[i].get("doc") if self.meta else None) or f"row {i}"
                table.append([state.global_step, i, doc, r["json_valid"], r["finished"],
                              r["labelled"], r["predicted"], r["matched"],
                              r["output_tokens"], round(seconds, 1)])
                print(f"    row {i:<3} {doc[:40]:<40} valid={r['json_valid']} "
                      f"finished={r['finished']} matched {r['matched']}/{r['labelled']} "
                      f"(returned {r['predicted']})  {r['output_tokens']:,} tok  {seconds:.0f}s")
                del inputs, out
                torch.cuda.empty_cache()
        except Exception as e:  # noqa: BLE001 — a metric must never cost the run
            print(f"  quality check   FAILED after {len(results)} row(s): "
                  f"{type(e).__name__}: {str(e)[:300]} — training continues")
            torch.cuda.empty_cache()
            self._log(state.global_step, {"quality/error": 1})
        finally:
            if getattr(FastModel, "for_training", None):
                FastModel.for_training(model)
            model.train()
        if not results:
            return
        labelled = sum(r["labelled"] for r in results)
        predicted = sum(r["predicted"] for r in results)
        matched = sum(r["matched"] for r in results)
        recall = matched / labelled if labelled else 0.0
        precision = matched / predicted if predicted else 0.0
        metrics = {
            "quality/json_valid": sum(r["json_valid"] for r in results) / len(results),
            "quality/finished": sum(r["finished"] for r in results) / len(results),
            "quality/clause_recall": recall,
            "quality/clause_precision": precision,
            "quality/clause_f1": 2 * recall * precision / (recall + precision)
                                 if recall + precision else 0.0,
            "quality/clause_count_ratio": predicted / labelled if labelled else 0.0,
            "quality/output_tokens": sum(r["output_tokens"] for r in results) / len(results),
            "quality/seconds": sum(r["seconds"] for r in results),
        }
        print(f"  quality         recall {recall:.3f}  precision {precision:.3f}  "
              f"valid {metrics['quality/json_valid']:.2f}  finished {metrics['quality/finished']:.2f}  "
              f"({metrics['quality/seconds'] / 60:.1f} min)")
        if self.wandb.run is not None:
            metrics["quality/rows"] = self.wandb.Table(
                columns=["step", "row", "doc", "json_valid", "finished", "labelled",
                         "returned", "matched", "output_tokens", "seconds"], data=table)
        self._log(state.global_step, metrics)

    def _log(self, step: int, metrics: dict) -> None:
        if self.wandb.run is not None:
            self.wandb.log({"train/global_step": step, **metrics})


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
    # eval_raw keeps the messages: the quality check generates from them.
    eval_raw = load_split(cfg["data"], "eval")
    eval_ds = render(eval_raw, tokenizer, max_len, "eval") if eval_raw is not None else None

    report = build_report(cfg)
    eval_meta = row_meta(report, "eval", len(eval_raw)) if eval_raw is not None else None
    fp = fingerprint(cfg, args.config, report)
    head("fingerprint  (W&B config: fingerprint.*)")
    for k, v in fp.items():
        info(f"{k:<24} {v}")

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

    # After train_on_responses_only: it swaps in its own collator, and the labels it
    # masks are what answer_tokens counts. Added with or without W&B — the per-row
    # and quality results print to the log either way; W&B just keeps them.
    counter = TokenCounter(trainer.data_collator, trainer.model)
    trainer.data_collator = counter
    rows = None
    if eval_ds is not None and int(t.get("per_device_eval_batch_size", 1)) == 1:
        rows = EvalRowLosses(trainer)
    trainer.add_callback(RunMetrics(
        counter, train_ds.lengths, getattr(eval_ds, "lengths", None), max_len,
        fingerprint=fp, rows=rows, eval_meta=eval_meta,
        group_by=list(tracking.get("eval_group_by") or [])))
    info("extra metrics   perf/ data/ gpu/ cost/ eval/best_* eval/loss_by_* (RunMetrics)")

    when = str(tracking.get("quality_check", "never")).lower()
    if when not in ("epoch", "end", "never"):
        raise Fail(f"tracking.quality_check={when!r} — use epoch, end or never")
    if when != "never" and eval_raw is not None:
        n = int(tracking.get("quality_rows", 2))
        trainer.add_callback(QualityCheck(
            [eval_raw[i] for i in range(min(n, len(eval_raw)))],
            eval_meta[:n] if eval_meta else None, tokenizer, when,
            int(tracking.get("quality_max_new_tokens", 24576))))
        info(f"quality check   {when}: {min(n, len(eval_raw))} validation row(s), generated "
             f"and scored with preparation/app_request.py — minutes of GPU per row")
    elif when != "never":
        info("quality check   skipped — there is no eval split to generate from")

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
                "data_sha": fp.get("data_train_sha256", "?"),
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
    info("4. make pod-stop pbbi-training   # the pod bills until you do")


if __name__ == "__main__":
    try:
        main()
    except Fail as e:
        sys.exit(f"\n  error  {e}\n")
    except KeyboardInterrupt:
        sys.exit("\n  interrupted — the pod is still running and still billing\n")
