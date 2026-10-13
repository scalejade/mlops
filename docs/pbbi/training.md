# Training

One fine-tune = one rented H200, on its own disk, deleted when the adapter is on
the Hub. Everything is driven from the laptop with `make`; you never need to type
a command inside the pod. Back to the [index](README.md).

## The pod

`runpod/pbbi-training/` · driven by `training/scripts/pod.py`

| Setting | Value | Why |
|---|---|---|
| GPU | 1× `NVIDIA H200` (141 GB), Secure Cloud | Unsloth is single-GPU; a 27B bf16 LoRA at 32k context fits one H200 |
| Disk | `volume_disk`, 150 GB, mounted at `/workspace` | not a network volume, so no region pin — see below |
| Region | none pinned | the pod goes wherever an H200 is free |
| Image | `runpod/pytorch:1.1.0-cu1281-torch280-ubuntu2404` | torch 2.8 + CUDA 12.8, pinned; do not upgrade mid-experiment |
| Boot | `runpod/pbbi-training/boot.sh` | starts downloading `BOOT_MODEL` at boot, then hands over to sshd |

**Why no network volume.** On 2026-10-12 a volume-pinned pod could not start: the
only H200s in stock were in datacenters without network volumes. The volume would
have saved one thing, the base download, which *measured* ~2 min (≈ $0.20). The
adapter travels to serving through the Hub, so training and serving share nothing
on disk.

**What the pod reads from where**

| Path on the pod | Comes from | Notes |
|---|---|---|
| `/workspace/mlops` | `git fetch origin/<branch>` | the pod runs what is **pushed**, never your working copy |
| `/workspace/mlops/preparation/data/` | `scp` of `train.jsonl`, `eval.jsonl`, `build-report.json` | `test.jsonl` never leaves the laptop |
| `/workspace/hf` | the Hub, at the config's `model.base` + `model.revision` | `BOOT_MODEL/REVISION` in the chart's `.env` should match, or it downloads twice |
| pod env (`HF_TOKEN`, `WANDB_API_KEY`) | `runpod/pbbi-training/.env`, written to `/etc/rp_environment` by RunPod | `run.sh` / `prepare.sh` source that file — non-interactive ssh does not |

## A run, start to finish

```bash
make help                       # every STATUS line ✓ — it names the next step
make data                       # preparation/raw/ -> preparation/data/*.jsonl
git commit -am "…" && git push  # make train refuses unpushed training/ preparation/ Makefile
make pod-plan                   # validates, checks the base on the Hub, shows the price
make pod-up pbbi-training       # BILLING STARTS (~$5.29/hr)
make train                      # code -> data -> deps + base -> dry run -> training (background)
make train-logs                 # follow it; Ctrl-C stops watching, not training
make pod-delete pbbi-training   # BILLING STOPS — once the log shows the adapter pushed
```

`make train` is four steps you can also run one at a time:

| Step | Takes (*measured*) | What happens |
|---|---|---|
| `train-push-code` | seconds | `/workspace/mlops` at `origin/<branch>`, cloned through your forwarded ssh agent |
| `train-push-data` | seconds | `scp` of the training data |
| `train-pull-model` | ~25 min on a fresh pod | pip deps (~15 min) + waits for the boot download (~2 min) |
| `train-run` | ~10 min, then training | config + data check, dry run (token lengths vs the window), training in the background |

**Ending a run: `pod-delete`, not `pod-stop`.** Delete takes the disk with it —
base, checkpoints, logs, and the training-data copies, which is what the NDA wants.
`pod-stop` only pauses the GPU; the stopped 150 GB disk keeps billing ~$1/day, and
a stopped pod can fail to restart if someone else took its H200.

## Configs

`training/configs/<task>.yaml` — the config **is** the experiment record: `train.py`
takes no hyperparameter flags.

| Config | Task | Pushes to | State |
|---|---|---|---|
| `pbbi-extraction.yaml` | clause extraction | `scalejade/pbbi-clause-extraction-lora` | live; `v0.1.0` trained 2026-10-12 |
| `pbbi-analysis.yaml` | analysis | `scalejade/pbbi-analysis-lora` | **draft** — `status: draft` makes `run.sh` and `train.py` refuse it |

`output.version: auto` tags each push `v0.1.0`, `v0.1.1`, …; the tag and its commit
sha are what serving and the registry pin. The adapter is ~319 MB: LoRA trains small
rank-16 matrices beside a frozen 27B base, so it is ~0.6% of the base's size and is
only usable together with that exact base.

## How long a run takes

*Measured* on 2026-10-12 (H200, slow linear-attention fallback — see
[troubleshooting](troubleshooting.md#fast-kernels-do-not-install)):

| Phase | Rate |
|---|---|
| first optimizer step | ~4.5 min (one-time kernel compile) |
| training | **~10 s per row** (~24k tokens) |
| eval loss | ~3 s per row |
| quality check (generate + score with the app's parser) | ~13 tokens/s → **~7 min per row** |

| Run | Rows | Estimate |
|---|---|---|
| demo, 3 documents (done) | 3 train, 6 eval | ~80 min pod time, ~$7 *measured* |
| full, ~60 documents | ~180 train, ~40 eval | **3–4 h, ~$16–21** |

For the full run, set `eval_steps` below the total step count (~40–50); at the
current `10` the 6-step demo never evaluated mid-run. Consider 2 epochs: on 3 rows
the loss fell 0.154 → 0.069 while extraction recall stayed at 0.690 — more epochs
fit the training rows, they did not improve extraction.

## Watching a run

- `make train-logs`, or inside the pod `tail -F /workspace/run.log /workspace/train.log`.
- W&B project `scalejade-mlops` (set by the config's `tracking.wandb_project`):
  loss, `eval_loss`, per-row eval tables, and the `quality/` panels.
- Healthy: `loss` falls, `eval_loss` follows, `grad_norm` steady. `nan` or
  out-of-memory: `make train-kill`, then `training/README.md`.
- You can ssh in (`make pod-ssh pbbi-training`) and read anything. Do **not** start
  `run.sh` or `train.py` by hand while `make train` is driving — two trainings on one
  GPU both run out of memory.
