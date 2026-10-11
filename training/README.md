# Training — Unsloth on a RunPod H200

Fine-tuning runs on **one H200 (141 GB HBM3e)** rented from RunPod by the hour, with
Unsloth doing LoRA / QLoRA against **`scalejade/qwen-sea-lion-v4.5-27b-it`** from the
Hugging Face Hub. The artifact is a LoRA adapter pushed back to the Hub. Nothing else
is produced, and nothing large is written to this repo.

Full fine-tuning and multi-node are out of scope. Unsloth is single-GPU by design; if
we outgrow it the move is Axolotl or TRL+FSDP, not more H200s in one pod.

## The base model

`scalejade/qwen-sea-lion-v4.5-27b-it`, pinned at
`81d9102bab84b46085cc0f8539efe578d33e29da`. Everything below was read off the repo
and the Unsloth 2026.8.19 wheel on 2026-08-25, not assumed:

| | |
|---|---|
| Architecture | `Qwen3_5ForConditionalGeneration` (`model_type: qwen3_5`) |
| Weights | 15 shards, 55.56 GB bf16 — the same shape as upstream `aisingapore/Qwen-SEA-LION-v4.5-27B-IT` |
| Context | 262,144 positions, 64 layers, hidden 5120, 4 KV heads |
| Attention | **hybrid** — gated-deltanet linear attention, full attention every 4th layer |
| Modality | text + vision tower. We train text-only. |
| Reasoning | yes — the chat template wraps every assistant turn in `<think>` |

Four consequences that are already handled in the config and the entrypoint, and
that you should not undo:

- **bf16 only.** Unsloth lists `qwen3_5` in `FORCE_FLOAT32` because the gated-deltanet
  layers NaN their grad norms in fp16. The H200 is Hopper so bf16 is native;
  `train.py` refuses to start on a GPU without it rather than train noise.
- **transformers ≥ 5.2.0.** Below it `AutoConfig` cannot parse `model_type: qwen3_5`
  at all. Unsloth's own ceiling is ≤ 5.5.0, and it declares `trl ≤ 0.24.0` — a plain
  `pip install unsloth` pulls transformers 5.15 and trl 1.10 and the import dies.
  `requirements.txt` carries the intersection. `train.py` checks both **before** the
  56 GB download.
- **It is a VLM.** `FastModel.from_pretrained(..., text_only=True)` loads the
  `qwen3_5_text` decoder and skips the vision tower. `FastLanguageModel` is the wrong
  entrypoint for this architecture.
- **The repo's chat template stays.** `model.chat_template: qwen-3` in the config only
  tells `train.py` where to split prompt from completion — it does **not** replace the
  template. Overriding it is possible (`override_chat_template: true`) and loud,
  because Unsloth's stock qwen-3 template does not handle SEA-LION's thinking blocks
  the same way.

**The fast linear-attention kernels are not bundled.** Verified on-pod 2026-08-27:
`unsloth_zoo` alone is not enough, and the model load says so —

```
The fast path is not available because one of the required library is not
installed. Falling back to torch implementation.
```

The gated-deltanet layers want `flash-linear-attention` and `causal-conv1d`, and
without them every step runs a pure-PyTorch path that is **several times slower**.
Nothing is wrong with the result — the loss is the same — you are just paying H200
rates for it. `prepare.sh --fast-kernels` installs both; it is opt-in because
`causal-conv1d` compiles against the image's torch and takes ~10 minutes, which is
not worth it for a smoke test and very much is for a real run.

They also need torch ≥ 2.7 and Triton ≥ 3.3, which is why the pod chart pins a
torch 2.8 / CUDA 12.8 image.

## Layout

| Path | What |
|---|---|
| `run.sh` | **One entry point on the pod.** Checks the config and its data, prepares the pod if needed, dry-runs, then trains in the background. Does not create or stop the pod — billing stays an explicit command. |
| `../runpod/pbbi-training/` | The H200 pod chart: GPU, region, image, env, and the `pbbi-volumes` network volume it mounts. Maps 1:1 to the RunPod API. |
| `requirements.txt` | Installed **on the pod**. Torch deliberately excluded — it comes with the image. |
| `configs/` | One YAML per run. Committed. The config is the experiment record. |
| `configs/example-lora.yaml` | Annotated reference. Copy it; do not run it. |
| `configs/pbbi-extraction-2026-10-10.yaml` | The live PBBI clause-extraction run. |
| `../preparation/` | Data prep (top-level, outside training/): `raw/` (one folder per document, gitignored), `build.py`, `app_request.py`, `serving_text.py`, `prompts/extraction_system.md`, `FORMAT.md`, `README.md`. Builds `data/train.jsonl` / `data/eval.jsonl` / `data/test.jsonl` — the config already points at the first two. |
| `scripts/pod.py` | Create / status / **stop** / delete the pod, from your laptop. |
| `scripts/prepare.sh` | Deps + version check + the 56 GB base. `run.sh` calls it when needed. |
| `scripts/bootstrap.sh` | Caches, dependencies, versions, HF login. Called by `prepare.sh`. |
| `scripts/test.py` | Smoke test: one pass through the whole stack. Also the trial run below. |
| `scripts/train.py` | The training entrypoint. Takes a config path and nothing else. |
| `adapters/` | Local adapter output. Gitignored — the real copy goes to the Hub. |

## The current task: PBBI clause extraction

`preparation/` (at the repo root) builds rows in **the exact request the app
makes** (perjanjian-baku-bi, `sys-prompt` @ `e028187`): the app's 540-line
`extraction_system.md` as the system prompt, and `DOCUMENT:\n` + the PDF text
after `pdftotext -layout` and `keepIndonesianOnly()` as the user message.

The source is `preparation/raw/`, **one folder per labelled document**
(about 60 when complete): a PDF, Legal's xlsx, and an `annotation.txt` whose
`Split :` line puts the whole document in Train, Validation or Test:

| `Split :` | Built into | Used by this training |
|---|---|---|
| `Train` | `data/train.jsonl` | `data.train` — required |
| `Validation` | `data/eval.jsonl` | `data.eval` — the eval loss; optional |
| `Test` | `data/test.jsonl` | not at all — held out for scoring the adapter afterwards |

A Train or Validation document that fits 30k tokens is one row; a larger one is
cut into windows of whole sections. Test rows are always the whole document.

```bash
# laptop or pod — no GPU needed, this is just PDF + labels -> JSONL
python preparation/build.py --tokenizer scalejade/qwen-sea-lion-v4.5-27b-pbbi
```

Read `preparation/README.md` before the first run. It covers the folder layout
and `annotation.txt`, the **serving contract** — change the app's prompt or text
pipeline and the dataset has to be rebuilt to match — and the known gaps
(two-column PDFs, long outputs, labels that predate pedoman v1.5).

`run.sh` stops at its data check, before any GPU work, if the config names a
`train.jsonl` or `eval.jsonl` that is not there — e.g. no folder is marked
`Split : Train` yet.

The data files are gitignored (they embed client contracts), so a pod's `git
clone` does not have them. Copy them up before training:

```bash
scp preparation/data/train.jsonl preparation/data/eval.jsonl root@<pod>:/workspace/mlops/preparation/data/
# test.jsonl stays on the laptop: training never reads it
```

## The run, start to finish

Everything is driven from the laptop with `make` (the `Makefile` at the repo
root); the pod is reached over ssh, found by name through the RunPod API. Data
stays on the laptop until `train-push-data` copies the two files that training
reads. `make` alone lists every target.

```bash
# --- once, on the laptop ------------------------------------------------------
cp .env.example .env        # this laptop: RUNPOD_API_KEY, HF_TOKEN (for make data)
cp runpod/pbbi-training/.env.example runpod/pbbi-training/.env
                            # the pod: HF_TOKEN, SSH_PUBLIC_KEY (WANDB_API_KEY optional)
make setup                  # .venv with the laptop deps; also: brew install poppler

# --- each run -----------------------------------------------------------------
make data                   # preparation/raw/ -> preparation/data/, exact token counts
git commit … && git push    # the pod runs origin/<branch>; train-push-code refuses otherwise

make pod-plan               # validate + price. Sends nothing.
make pod-up pbbi-training   # the meter starts here (~$5.29/hr)
make train                  # = train-push-code  train-push-data  train-pull-model  train-run
make train-logs             # follow it; Ctrl-C stops watching, not training
make pod-stop pbbi-training # GPU billing stops HERE, not at the last step
```

What each step does on the pod:

| Target | On the pod |
|---|---|
| `train-push-code` | `/workspace/mlops` checked out at `origin/<branch>` (ssh agent forwarding, so GitHub sees your key). Refuses if `training/`, `preparation/` or the `Makefile` have uncommitted or unpushed changes |
| `train-push-data` | `scp` of `preparation/data/train.jsonl` (+ `eval.jsonl` if built). `test.jsonl` never leaves the laptop |
| `train-pull-model` | `prepare.sh`: deps + fast kernels the first time, then the config's `model.base` at its pinned `revision` into `/workspace/hf`. The pod already started a download at boot — of `boot.model` in `runpod/pbbi-training/values.yaml`, normally the same repo and sha (`runpod/pbbi-training/boot.sh`), so this waits for it if it is still running and then finds it cached. On a later pod only the deps reinstall (~15 min) — the base is already on the volume. Runs detached — a dropped ssh does not stop it |
| `train-check` | `run.sh --check`: config, data, dry run (loads the model, trains nothing) |
| `train-run` | `run.sh` in the background: logs in `/workspace/run.log`, then `/workspace/train.log`. At the end it pushes the adapter and prints the registry entry |
| `train-kill` | stops a running training; the pod keeps billing |

Change of data only? `make data && make train-push-data && make train-run` on a
pod that is already prepared. Another config: `make train CONFIG=training/configs/<x>.yaml`.

The steps `run.sh` and `prepare.sh` wrap still run on their own on the pod
(`make pod-ssh`), if you want them apart:

```bash
bash training/scripts/prepare.sh --test        # deps + base + a smoke test
python training/scripts/train.py <config> --dry-run
python training/scripts/train.py <config>
```

Then: register the adapter in `registry/models.yaml` (`relation: finetune`), run
`eval/` against it, and only then consider deploying. A better training loss is not
evidence that the product improved.

## A trial run you can push

To see the whole thing work on real rows and end with something on the Hub —
before there is a dataset, a config, or anything to evaluate:

```bash
python training/scripts/test.py --dataset --steps 60 --push
```

That pulls 200 rows of a public instruction set, reshapes them into the `messages`
schema, trains 60 steps at r=16, and pushes the LoRA adapter plus a model card to
`scalejade/qwen-sea-lion-v4.5-27b-lora-smoke`. Takes about 15 minutes on top of a
prepared pod. `--push <repo>` picks a different one, `--private` keeps it out of
sight, `--dataset <repo>` swaps the data (a `messages`, ShareGPT `conversations`,
or Alpaca `instruction/input/output` column is understood; anything else raises).

### Versioning it

The adapter repo is a git repo, so a run does not need a new repo name to be a new
version:

```bash
python training/scripts/test.py --dataset --steps 60 --push --version          # v0.1.0, then v0.1.1, ...
python training/scripts/test.py --dataset --steps 60 --push --version v0.2.0   # or say it
```

Bare `--version` reads the tags already on the repo and takes the next patch. An
explicit tag that already exists is refused before the upload starts — a version
that moves is not a version. Either way the push prints the **commit sha**, and a
`registry/models.yaml` entry pinned to it, ready to paste into a PR.

Pin callers to a tag or a sha, never to `main`. `main` is whatever ran last, which
is the failure this repo pins the base model's sha to avoid. The generated model
card shows the `load_adapter(..., revision=...)` call with the right pin in it.

### Pushing onto a branch of the base repo

`--push-branch <name>` writes to a branch instead of the default one, which is the
only supported way to target the base model's own repo:

```bash
python training/scripts/test.py --dataset --steps 60 \
    --push scalejade/qwen-sea-lion-v4.5-27b-it --push-branch lora-smoke-v0.2.0
```

`main` is untouched, so the sha `registry/models.yaml` pins stays valid. The push
refuses to run against that repo *without* a branch, and refuses `--push-branch
main` outright — adapter files committed over a 15-shard mirror is the one
mistake here that costs more than a rerun.

It still is not the recommended layout. A branch of a model repo looks like a
model: `from_pretrained(repo, revision="lora-smoke-v0.2.0")` finds an
`adapter_config.json` where 15 shards should be. And `registry/models.yaml` is one
entry per repo by its own first line, which branch-versions break. Prefer a
separate adapter repo with tags; use this when something downstream genuinely
needs one repo id.

**The push is public by default and the adapter is not a model.** It has seen a
few hundred generic rows and no eval, which is what the generated card says in its
first line. It exists to prove the pipeline, not to be served. Nothing goes in
`registry/models.yaml` for it unless you decide to keep it.

## Writing a config

Copy `configs/example-lora.yaml` to `configs/<task>-<date>.yaml` and edit it. Every
knob `train.py` reads is in that file and commented. There are **no command-line
hyperparameters** — if it is not in the config, it did not happen and the run cannot
be reproduced.

The four fields that decide whether the run works at all:

- **`model.base`** — the Hub repo. Prefer a `scalejade/` mirror at a pinned revision
  over an upstream repo that can move under us.
- **`model.max_seq_length`** — must equal what the serving config uses. Trained at
  40960 and served at 32768 truncates silently, at HTTP 200.
- **`model.load_in_4bit`** — `false` on an H200 unless the base genuinely does not
  fit. 141 GB is the reason we are paying for this card.
- **`train.per_device_train_batch_size` × `gradient_accumulation_steps`** — the
  effective batch. Keep the product fixed when you change either one.

## What the H200 actually buys

141 GB of HBM3e, ~4.8 TB/s. Practically:

| `max_seq_length` | bf16 LoRA, batch 1 | note |
|---|---|---|
| 8,192 | comfortable | batch 2 usually fits too |
| 16,384 | comfortable | the config default |
| 32,768 | tight | drop to batch 1, watch peak VRAM in the log |
| 65,536+ | needs `load_in_4bit: true` | or a different trainer |

55.56 GB of weights against 141 GB leaves ~85 GB for activations, gradients and
optimizer state. The base's 262,144-token window is a **serving** number — you cannot
train at it on one card, and you do not need to: set `max_seq_length` from what your
longest example actually needs, which `train.py` prints for every split.

At long context it is the **activations** that run you out of memory, not the weights.
The order to reach for when it OOMs: drop `per_device_train_batch_size` to 1 (raise
`gradient_accumulation_steps` to match), keep `use_gradient_checkpointing: unsloth`,
then lower `max_seq_length`, and only then turn on `load_in_4bit`.

## Things that have a cost attached

- **A pod bills while running, idle or not.** Finishing a run does not stop the meter;
  `make pod-stop pbbi-training` does. The pod is on the `pbbi-volumes` network volume, which RunPod
  cannot stop, so `pod-stop` **deletes** the pod. Nothing that matters goes with it:
  `/workspace` is the volume — base model, checkpoints, adapters, logs — and the next
  `make pod-up pbbi-training` mounts it again. The volume bills flat (~$14/mo for 200 GB) either way.
- **The container disk goes with every pod; `/workspace` does not.** That is why
  `HF_HOME` points at `/workspace/hf`, and why a new pod reinstalls the pip deps
  (~15 min with the fast kernels) but never re-downloads the base. Whether deps are
  installed is decided by importing them, not by `versions.txt`, which lives on the
  volume and would outlive them.
- **One volume, two mount points.** The serving endpoint mounts the same volume at
  `/runpod-volume` with `HF_HOME=/runpod-volume/hf` — the same directory as
  `/workspace/hf` here. The base this pod downloads is the one the endpoint loads.
- **Region and GPU type ids are exact strings.** `make pod-gpus` prints the real ids.
  A network volume only attaches inside its own region, so the pod is pinned to
  `pbbi-volumes`' datacenter (US-CO-1) on Secure Cloud. If that datacenter has no
  H200 free, `pod-up` fails at create time: wait, or set `disk.type: volume_disk` in
  the chart and drop the pin — the Hub then carries the model across instead.
- **`versions.txt`** on the pod records the torch/unsloth/transformers versions the
  run actually used. The config records intent; that file records reality. Copy it
  into the run's notes for anything you may need to reproduce.
- **Multi-GPU pods are wasted money here.** Unsloth uses one GPU; `pod.py` refuses
  `gpu.count > 1` for that reason.
