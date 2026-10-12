#!/usr/bin/env python3
"""
What a training run sends to Weights & Biases — simulated on this laptop, no GPU.

    python training/scripts/wandb_example.py                   # the PBBI config
    python training/scripts/wandb_example.py <config.yaml>
    python training/scripts/wandb_example.py --project <name>  # default: <wandb_project>-example

It logs a fake run with the same metric names, step axis, run name and config
that train.py produces through the HF Trainer (report_to="wandb"), so the
dashboard looks like the real one before an H200 is rented: train/loss,
train/learning_rate (warmup then linear decay), train/grad_norm, eval/loss every
eval_steps, the end-of-run summary — and the extras train.py adds: perf/, data/,
gpu/, cost/, train|eval/perplexity, eval/best_*, eval/loss_gap, eval/loss_by_*,
quality/ at each epoch end, and the fingerprint in the run config. The numbers are made up. No model is
loaded and no data is read — only the config and the row count in
preparation/data/build-report.json, to size the run like the real one.

It goes to its own project (<wandb_project>-example) and is tagged "simulated",
so it never sits among real runs in a comparison.

WANDB_API_KEY is read from the environment, else the root .env (this laptop),
else runpod/pbbi-training/.env. The real run on the pod reads only the latter.

Needs:  pip install wandb   (make setup installs it)
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO / "training/configs/pbbi-extraction.yaml"
KEY_FILES = (REPO / ".env", REPO / "runpod/pbbi-training/.env")


def find_key() -> str | None:
    if os.environ.get("WANDB_API_KEY"):
        return os.environ["WANDB_API_KEY"]
    for path in KEY_FILES:
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            key, _, value = line.strip().partition("=")
            if key == "WANDB_API_KEY" and value.strip().strip("'\""):
                return value.strip().strip("'\"")
    return None


def train_rows() -> int:
    """Rows train.py would see, from the last `make data`. 40 when none are built yet."""
    report = REPO / "preparation/data/build-report.json"
    try:
        rows = json.loads(report.read_text())["train"]["rows"]
    except (OSError, KeyError, ValueError):
        rows = 0
    return rows or 40


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("config", nargs="?", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument("--project", help="W&B project (default: <tracking.wandb_project>-example)")
    ap.add_argument("--speed", type=float, default=0.15, help="seconds per simulated step")
    args = ap.parse_args()

    try:
        import wandb
    except ImportError:
        sys.exit("wandb is not installed:  pip install wandb   (or: make setup)")

    key = find_key()
    if not key:
        sys.exit("WANDB_API_KEY not found in the environment, .env or runpod/pbbi-training/.env")
    os.environ["WANDB_API_KEY"] = key

    cfg = yaml.safe_load(args.config.read_text())
    t, lora, m = cfg["train"], cfg["lora"], cfg["model"]
    project = args.project or f"{cfg.get('tracking', {}).get('wandb_project') or 'scalejade-mlops'}-example"

    # Sized like the real run: optimiser steps = rows / effective batch, per epoch.
    rows = train_rows()
    eff_batch = t["per_device_train_batch_size"] * t["gradient_accumulation_steps"]
    steps_per_epoch = math.ceil(rows / eff_batch)
    total = steps_per_epoch * int(t["num_train_epochs"])
    warmup = max(1, round(total * float(t.get("warmup_ratio", 0))))
    lr_peak = float(t["learning_rate"])

    run = wandb.init(
        project=project,
        name=f"{cfg['run_name']}-simulated",
        job_type="example",
        tags=["simulated", "example"],
        notes="SIMULATED on a laptop by training/scripts/wandb_example.py — no model was "
              "trained. Shows what a real train.py run logs.",
        # What the HF Trainer puts in run.config, trimmed to what matters here.
        config={
            "run_name": cfg["run_name"],
            "model": m["base"], "revision": m.get("revision"),
            "max_seq_length": m["max_seq_length"], "load_in_4bit": m.get("load_in_4bit"),
            "lora_r": lora["r"], "lora_alpha": lora["alpha"], "lora_dropout": lora["dropout"],
            "target_modules": lora["target_modules"],
            "per_device_train_batch_size": t["per_device_train_batch_size"],
            "gradient_accumulation_steps": t["gradient_accumulation_steps"],
            "num_train_epochs": t["num_train_epochs"], "learning_rate": lr_peak,
            "warmup_ratio": t.get("warmup_ratio"), "lr_scheduler_type": t.get("lr_scheduler_type"),
            "optim": t.get("optim"), "weight_decay": t.get("weight_decay"), "seed": t.get("seed"),
            "train_rows": rows, "total_steps": total,
            "fingerprint": {"config_file": args.config.name, "data_train_sha256": "simulated",
                            "system_prompt_sha256": "simulated", "git_commit": "simulated"},
        },
    )
    # The Trainer plots everything against the optimiser step, not wandb's own counter.
    wandb.define_metric("train/global_step")
    wandb.define_metric("*", step_metric="train/global_step", step_sync=True)

    print(f"  {run.url}\n  {total} steps ({rows} rows, effective batch {eff_batch}, "
          f"{t['num_train_epochs']} epochs), eval every {t.get('eval_steps')} steps")

    rnd = random.Random(t.get("seed", 3407))
    eval_every = int(t.get("eval_steps") or 0)
    started, losses = time.time(), []
    # What RunMetrics would see on the H200: ~21k-token rows of which ~25% is the
    # answer, ~30 s per optimiser step with the fast kernels, ~95 GB reserved.
    usd_per_hour = 5.29
    sec_per_step = 30.0
    tokens = answer = 0
    best_loss, best_step = math.inf, None
    run.summary.update({"data/train_rows": rows, "data/train_tokens_median": 20817,
                        "data/train_tokens_p95": 29100, "data/train_tokens_max": 29900,
                        "data/train_rows_over_max_seq_length": 0})
    for step in range(1, total + 1):
        epoch = step / steps_per_epoch
        # linear warmup, then linear decay to 0 — lr_scheduler_type: linear
        lr = lr_peak * (step / warmup if step <= warmup else max(0.0, (total - step) / (total - warmup)))
        # A format-following LoRA: loss falls fast, then flattens; small epoch-boundary drops.
        loss = 0.32 + 1.25 * math.exp(-step / (0.18 * total)) - 0.03 * int(epoch) + rnd.gauss(0, 0.035)
        losses.append(loss)
        step_tokens = sum(rnd.randint(14000, 29900) for _ in range(eff_batch))
        tokens += step_tokens
        answer += int(step_tokens * rnd.uniform(0.22, 0.28))
        sps = sec_per_step * rnd.uniform(0.9, 1.1)
        hours = step * sec_per_step / 3600
        wandb.log({
            "train/global_step": step, "train/epoch": round(epoch, 4),
            "train/loss": round(loss, 4), "train/learning_rate": lr,
            "train/grad_norm": round(abs(0.25 + 1.6 * math.exp(-step / (0.12 * total)) + rnd.gauss(0, 0.06)), 4),
            # RunMetrics
            "train/perplexity": math.exp(loss),
            "perf/tokens_per_second": step_tokens / sps, "perf/seconds_per_step": sps,
            "perf/eta_minutes": (total - step) * sec_per_step / 60,
            "data/tokens_seen": tokens, "data/answer_tokens_seen": answer,
            "data/answer_fraction": answer / tokens,
            "gpu/mem_allocated_gb": 61 + rnd.uniform(0, 4),
            "gpu/mem_reserved_gb": 88 + rnd.uniform(0, 8),
            "gpu/peak_reserved_gb": min(118.0, 92 + step * 0.4),
            "cost/usd_so_far": hours * usd_per_hour,
            "cost/usd_projected": total * sec_per_step / 3600 * usd_per_hour,
        })
        if eval_every and step % eval_every == 0:
            # Tracks train loss, then turns up in the last epoch: what overfitting looks like.
            ev = 0.42 + 1.1 * math.exp(-step / (0.2 * total)) + 0.12 * max(0.0, epoch - 2) ** 2
            ev += rnd.gauss(0, 0.015)
            if ev < best_loss:
                best_loss, best_step = ev, step
            # eval/loss_by_<field>/<value>: credit cards lag mobile banking a little.
            wandb.log({"train/global_step": step,
                       "eval/loss_by_Produk/Mobile_Banking": ev - 0.05 + rnd.gauss(0, 0.02),
                       "eval/loss_by_Produk/Kartu_Kredit": ev + 0.12 + rnd.gauss(0, 0.02)})
            wandb.log({"train/global_step": step, "eval/loss": round(ev, 4),
                       "eval/perplexity": math.exp(ev), "eval/best_loss": best_loss,
                       "eval/best_step": best_step, "eval/loss_gap": ev - loss,
                       "eval/runtime": round(rnd.uniform(38, 44), 2),
                       "eval/samples_per_second": round(rnd.uniform(0.11, 0.13), 3),
                       "eval/steps_per_second": round(rnd.uniform(0.11, 0.13), 3)})
        if step % steps_per_epoch == 0:
            # QualityCheck at each epoch end: generated replies scored by the app's parser.
            e = step // steps_per_epoch
            recall, precision = (0.62, 0.78, 0.88)[min(e, 3) - 1], (0.80, 0.90, 0.93)[min(e, 3) - 1]
            wandb.log({"train/global_step": step, "quality/json_valid": 1.0 if e > 1 else 0.5,
                       "quality/finished": 1.0 if e > 1 else 0.5,
                       "quality/clause_recall": recall, "quality/clause_precision": precision,
                       "quality/clause_f1": 2 * recall * precision / (recall + precision),
                       "quality/clause_count_ratio": recall / precision,
                       "quality/output_tokens": 9000 + rnd.randint(-800, 800),
                       "quality/seconds": 480 + rnd.uniform(-60, 60)})
        time.sleep(args.speed)

    save_steps = int(t.get("save_steps") or 0)
    saved = list(range(save_steps, total + 1, save_steps)) if save_steps else []
    run.summary.update({
        "eval/best_loss": best_loss, "eval/best_step": best_step,
        "eval/best_checkpoint": (f"checkpoint-{min(saved, key=lambda s: abs(s - best_step))}"
                                 if saved and best_step else None),
        "eval/best_is_final": best_step == total,
        "cost/usd_total": total * sec_per_step / 3600 * usd_per_hour,
        "train/train_loss": round(sum(losses) / len(losses), 4),
        "train/train_runtime": round(time.time() - started, 1),
        "train/train_samples_per_second": round(rows * int(t["num_train_epochs"]) / max(1.0, time.time() - started), 3),
    })
    run.finish()
    print(f"\n  done — {run.url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
