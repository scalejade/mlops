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

The linear-attention Triton kernels ship inside `unsloth_zoo`; nothing extra to
install, but they need torch ≥ 2.7 and Triton ≥ 3.3, which is why `pod.yaml` pins a
torch 2.8 / CUDA 12.8 image. Without them transformers falls back to a pure-PyTorch
path that is several times slower, and Unsloth says so at load time.

## Layout

| Path | What |
|---|---|
| `pod.yaml` | The H200 pod: GPU, region, disk, image, env. Maps 1:1 to the RunPod API. |
| `requirements.txt` | Installed **on the pod**. Torch deliberately excluded — it comes with the image. |
| `configs/` | One YAML per run. Committed. The config is the experiment record. |
| `datasets/` | Schema and build scripts. Real data goes to a private HF dataset repo. |
| `scripts/pod.py` | Create / status / **stop** / delete the pod, from your laptop. |
| `scripts/prepare.sh` | **Start here on a new pod.** Deps + version check + the 56 GB base. |
| `scripts/bootstrap.sh` | Caches, dependencies, versions, HF login. Called by `prepare.sh`. |
| `scripts/test.py` | Smoke test: one pass through the whole stack. Also does the trial run below. |
| `scripts/train.py` | The training entrypoint. Takes a config path and nothing else. |
| `adapters/` | Local adapter output. Gitignored — the real copy goes to the Hub. |

## The run, start to finish

```bash
# --- laptop -----------------------------------------------------------------
cp .env.example .env                       # HF_TOKEN, RUNPOD_API_KEY, WANDB_API_KEY,
                                           # SSH_PUBLIC_KEY
pip install pyyaml

python training/scripts/pod.py gpus h200   # confirm the GPU type id and the live rate
python training/scripts/pod.py plan        # validate + price. Sends nothing.
python training/scripts/pod.py apply       # the meter starts here
```

```bash
# --- pod (ssh in; RunPod prints the command under Connect) ------------------
git clone git@github.com:scalejade/mlops.git /workspace/mlops
cd /workspace/mlops
# Deps, a version check, and the 55.56 GB base pulled as its own resumable step;
# --test then proves the whole stack trains before you spend an hour on it.
# ~25 min the first time, ~1 min on a pod that was only stopped and restarted.
bash training/scripts/prepare.sh --test

# It wraps bootstrap.sh and `hf download`, which still run on their own if you
# want the steps apart:
#   bash training/scripts/bootstrap.sh       # deps, caches, versions.txt
#   hf download scalejade/qwen-sea-lion-v4.5-27b-it \
#      --revision 81d9102bab84b46085cc0f8539efe578d33e29da
#   python training/scripts/test.py          # smoke test alone

python training/scripts/train.py training/configs/<task>-<date>.yaml --dry-run
nohup python training/scripts/train.py training/configs/<task>-<date>.yaml \
      > /workspace/train.log 2>&1 &
tail -f /workspace/train.log               # ssh drops kill a foreground run
```

```bash
# --- laptop, when it finishes ----------------------------------------------
python training/scripts/pod.py stop        # GPU billing stops HERE, not at the last step
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

Do **not** version by pushing adapters onto `scalejade/qwen-sea-lion-v4.5-27b-it`.
That repo is a `redistribution` mirror that has to stay shard-for-shard identical
to upstream — `registry/models.yaml` records the day it silently wasn't, and the
sha pinned there is what everything else trusts.

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
  `pod.py stop` does. `stop` keeps the disk (still billed, far less) so the next run
  does not re-download the base model. `delete` loses the disk — push to the Hub first.
- **The container disk is wiped on stop/start; `/workspace` is not.** That is why
  `HF_HOME` points at `/workspace/hf`. Get this wrong and every restart re-downloads
  the checkpoint.
- **Region and GPU type ids are exact strings.** `pod.py gpus h200` prints the real
  ones. A network volume only attaches inside its own region, which is why the
  training pod defaults to a plain volume disk rather than `pbbi-volumes`.
- **`versions.txt`** on the pod records the torch/unsloth/transformers versions the
  run actually used. The config records intent; that file records reality. Copy it
  into the run's notes for anything you may need to reproduce.
- **Multi-GPU pods are wasted money here.** Unsloth uses one GPU; `pod.py` refuses
  `gpu.count > 1` for that reason.
