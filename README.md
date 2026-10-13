# Scalejade MLOps

Internal machine-learning operations for Scalejade. This repository is the single
source of truth for **which models we have, how they are trained, how they are
served, and how we know they work**.

It contains configuration, documentation, and tooling. It does not contain model
weights, client data, or secrets.

---

## The stack

| Concern | Tool | Why |
|---|---|---|
| **Model repository** | Hugging Face Hub (`scalejade/`) | Git for weights. Private repos, revisions, model cards, and no lock-in — a HF repo is portable anywhere. |
| **Training** | [Unsloth](https://github.com/unslothai/unsloth) | Fast single-GPU LoRA/QLoRA. Outputs standard adapters that any serving stack can load. |
| **Inference** | [RunPod](https://runpod.io) Serverless + vLLM | On-demand GPUs, OpenAI-compatible API, pay per second. Scales to zero between jobs. |
| **Experiment tracking** | Weights & Biases | Unsloth logs to it natively. |
| **Registry** | `registry/*.yaml` in this repo | At our size, two YAML files beat running MLflow. |

Each piece is replaceable on its own. Unsloth emits ordinary safetensors, RunPod
serves an ordinary OpenAI API, HF is an ordinary git remote. If any one of them
disappoints us, it swaps out without touching the other two. That property matters
more than any individual feature.

**Known ceilings, so nobody is surprised later:** Unsloth is single-GPU only — full
fine-tuning or multi-node means moving to Axolotl or TRL+FSDP. RunPod's stock vLLM
template lags upstream, so brand-new architectures may not run until we build our
own worker image.

---

## Repository structure

```
mlops/
├── README.md                  ← you are here
├── Makefile                   `make` lists targets: data, pod-up, train, train-logs, pod-stop
├── .env.example               this laptop's keys: RUNPOD_API_KEY, HF_TOKEN (never commit .env)
│
├── models/                    one dir per model on huggingface.co/scalejade
│   └── <model-name>/
│       ├── README.md          the HF model card
│       ├── model.config       vLLM engine args for serving this model
│       └── weights/           gitignored — local snapshot only
│
├── preparation/               training data, in the exact request the app makes
│   ├── raw/                   one folder per document: PDF + xlsx + annotation.txt
│   │                          ("Split : Train | Validation | Test") — gitignored
│   ├── data/                  build.py output: train / eval / test .jsonl — gitignored
│   ├── build.py               raw/ -> data/
│   ├── app_request.py         the app's extraction call, rebuilt offline
│   └── prompts/               the app's system prompt, byte-for-byte
│
├── training/                  Unsloth fine-tuning on a rented H200
│   ├── run.sh                 one entry point on the pod: check, prepare, dry-run, train
│   ├── requirements.txt       installed on the pod, not on your laptop
│   ├── configs/               one YAML per run — the config IS the experiment record
│   ├── scripts/               pod.py (rent/stop the GPU, from runpod/pbbi-training), bootstrap.sh, train.py
│   └── adapters/              local LoRA output — gitignored
│
├── runpod/                    inference — deploy from your laptop
│   ├── deploy.py              plan / apply / status / delete against the RunPod API
│   ├── endpoints/             one YAML per endpoint, fields map 1:1 to the RunPod API
│   └── worker/                our own vLLM image, so we control the engine version
│
├── eval/                      the quality gate — nothing deploys without passing
│   ├── golden/                verified ground truth
│   ├── suites/                scoring runners
│   └── results/               scored runs, committed as history
│
├── registry/
│   ├── models.yaml            every model we host, with provenance and status
│   └── deployments.yaml       what is running right now, and on what hardware
│
├── scripts/                   shared operational tooling
│   ├── download_model.sh      pull a model from the Hub to models/<name>/weights/
│   └── clone_model.py         mirror an upstream model into the scalejade namespace
│
├── docs/
│   ├── README.md              index: one folder per project
│   ├── pbbi/                  PBBI: overview, training, serving, troubleshooting
│   └── reports/               deployment trials, incident write-ups, benchmarks
│
└── scratch/                   gitignored. Working files, one-off outputs, junk.
```

### Why this shape

The split is **by lifecycle stage**, not by file type, because that is how the work
actually moves: a model is acquired, trained, evaluated, then served, and each stage
hands off to the next. Anything in `registry/` is a *claim about the world* and must
be kept true. Anything in `scratch/` is disposable and nobody should ever depend on it.

The two rules that keep it honest:

- **Weights and data live on the Hub. Config and documentation live in git.** If a
  file is large or confidential, it does not belong here.
- **`registry/deployments.yaml` describes production.** If it disagrees with RunPod,
  the file is wrong and fixing it is the priority — not the other way around.

---

## Getting started

```bash
git clone git@github.com:scalejade/mlops.git
cd mlops

cp .env.example .env
# Fill in HF_TOKEN, HF_NAMESPACE, RUNPOD_API_KEY. Never commit this file.

pip install -r requirements.txt      # deployment tooling (runpod/, scripts/)
make setup                           # .venv for data prep and training (see Fine-tune)
make help                            # the training workflow + what is ready on this laptop
```

Confirm access:

```bash
hf auth whoami                       # should show the scalejade org
```

---

## Workflows

### Add a model to our namespace

```bash
# 1. Set SOURCE_MODEL and TARGET_MODEL in .env, then:
./scripts/download_model.sh          # -> models/<TARGET_MODEL>/weights/
python scripts/clone_model.py        # -> huggingface.co/scalejade/<TARGET_MODEL>
```

Then write `models/<name>/README.md` (the model card), write `model.config`, and add
an entry to `registry/models.yaml`. A model that isn't in the registry doesn't exist.

### Fine-tune — the timeline, with `make`

Everything runs from the laptop. Client documents are built into training data
here; only `train.jsonl` / `eval.jsonl` are copied to a rented RunPod H200 for the
run, and the result comes back as a LoRA adapter on the Hub. `make help` prints
this workflow plus a ✓/✗ status of everything below, and names the next step.

```
 LAPTOP (free)                                RUNPOD H200 (~$5.29/hr while running)
 ─────────────                                ─────────────────────────────────────
 T0  one-time setup
 T1  documents → preparation/raw/
 T2  make data
 T3  git commit + push
 T4  make pod-up pbbi-training ─────────────────────────►  pod created          ── billing starts
 T5  make train   ─── code, data ──────────►  deps + 55 GB base    (~25 min, first time)
                                              dry run → training   (20 min – 3 h)
 T6  make train-logs  ◄──── log ────────────  loss / eval_loss
                                              adapter → Hugging Face (tagged)
 T7  make pod-stop pbbi-training ──────────►  deleted              ── billing stops
 T8  register + evaluate on test.jsonl
```

**T0 — once (≈10 min)**

```bash
cp .env.example .env     # this laptop: RUNPOD_API_KEY, HF_TOKEN (for make data)
cp runpod/pbbi-training/.env.example runpod/pbbi-training/.env
                         # the pod: HF_TOKEN, SSH_PUBLIC_KEY (WANDB_API_KEY optional)
make setup               # .venv with the laptop deps
brew install poppler     # pdftotext, if `make help` shows it missing
ssh-add                  # your GitHub key in the agent: the pod clones through it
make help                # every line under STATUS should be ✓ except data and git
```

**T1 — documents (whenever Legal delivers)**

One folder per document in `preparation/raw/` (gitignored): the PDF, Legal's xlsx,
and an `annotation.txt` whose `Split :` line says `Train`, `Validation` or `Test`.
Decide each split once, spread the `Tipe` categories across all three, and never
move a document after seeing results — see `preparation/README.md`.

**T2 — build the data (≈1 min)**

```bash
make data                # preparation/raw/ → preparation/data/{train,eval,test}.jsonl
```

Read the summary: rows per split, the per-split category table, and any dropped
sections (reasons in `preparation/data/build-report.json`). Every row is the exact
request the app sends the model (`make test` checks the local copy of that call).

**T3 — commit and push (≈1 min)**

```bash
git add -A && git commit -m "…" && git push
```

The pod runs `origin/<branch>`, not your working copy; `make train` refuses while
`training/`, `preparation/` or the `Makefile` have unpushed changes. Data is never
committed — it is gitignored and travels by `scp` in T5.

**T4 — rent the GPU (1–3 min) · billing starts**

```bash
make pod-plan            # validate runpod/pbbi-training and show the price; creates nothing
make pod-up pbbi-training  # the meter starts here
```

**T5 — train (first run ≈35 min of setup + training)**

```bash
make train               # = train-push-code  train-push-data  train-pull-model  train-run
```

| Step | Takes | What happens on the pod |
|---|---|---|
| `train-push-code` | seconds | `/workspace/mlops` checked out at `origin/<branch>` |
| `train-push-data` | seconds | `train.jsonl` + `eval.jsonl` copied up; `test.jsonl` stays on the laptop |
| `train-pull-model` | ~25 min once, then skipped | deps, fast kernels, the config's base model into `/workspace/hf` |
| `train-run` | ~10 min, then training | config + data check, a dry run (rows vs the 32k window), the version tag reserved on the Hub, then training in the background |

Training itself: roughly 20–40 min for a few dozen rows, 1.5–3 h with the full
~60-document set. It survives a dropped ssh.

**T6 — watch it**

```bash
make train-logs          # Ctrl-C stops watching, not training
```

`loss` should fall and flatten, and `eval_loss` should follow it. `eval_loss`
rising while `loss` falls is memorising — fewer epochs next time. `nan` in
`grad_norm` or an out-of-memory error: `make train-kill`, then see
`training/README.md`. When it finishes the log shows the adapter pushed to
`scalejade/pbbi-clause-extraction-lora`, its tag (`v0.1.0`, …) and commit sha, and
a `registry/models.yaml` entry to paste.

**T7 — stop paying, immediately**

```bash
make pod-delete pbbi-training   # billing stops HERE, not when training ends
```

The training pod runs on its own disk, not a network volume, so it can go wherever
an H200 is free. Deleting it takes the disk too: the base model (re-downloaded in
~2 min next time), checkpoints, logs, and the copies of `train.jsonl` / `eval.jsonl`
— which is what the NDA wants. Only delete once the log shows the adapter pushed.
`make pod-stop` only pauses the GPU; the 150 GB disk keeps billing (~$1/day).

**To serve it:** `make volume-fill` rents a CPU pod for a few minutes that pulls the
base and the adapter onto `pbbi-volumes` (the endpoint's network volume), checks
them, and deletes itself. Then `python runpod/deploy.py apply pbbi-serverless-extraction`.

**T8 — register and evaluate**

1. Paste the printed entry into `registry/models.yaml` as `status: candidate`, in a PR.
2. Score the adapter on `preparation/data/test.jsonl`: generate each whole document
   the way the app calls it, parse with `preparation/app_request.py`, compare with
   Legal's labels (clause recall, `pasal`, verbatim text). *The generation script
   for this is not built yet.*
3. Only a better test score — not a lower loss — earns a deploy.

**Next runs**

| Changed | Run |
|---|---|
| Data only, pod running | `make data` → `make train-push-data train-run` → `make pod-stop pbbi-training` |
| Anything, no pod | `make pod-up pbbi-training` → `make train` (deps reinstall ~15 min; the base is already on the volume) → `make pod-stop pbbi-training` |
| Another config | `make train CONFIG=training/configs/<x>.yaml` |

Nothing gets tweaked at the command line beyond picking a config — if it isn't in
the config file, it didn't happen and can't be reproduced. Details:
`training/README.md` (the pod, the base model, memory) and `preparation/README.md`
(the data and the serving contract).

### Deploy

1. The model must be registered and must have passed `eval/`.
2. Write or edit `runpod/endpoints/<name>.yaml`.
3. Deploy from your laptop — all you need is `RUNPOD_API_KEY` in `.env`:

```bash
python runpod/deploy.py plan  pjp-clause-extraction    # validate, send nothing
python runpod/deploy.py apply pjp-clause-extraction    # create or update
```

   `apply` is idempotent: it finds the template and endpoint by name and updates them
   in place. Engine args come from `models/<model>/model.config`, secrets from the
   chart's own `runpod/<chart>/.env`. Preflight refuses to deploy on the four mistakes that have already burned us.

4. Smoke-test with a **full-length real document** and confirm `finish_reason == "stop"`.
5. Update `registry/deployments.yaml` in the same PR.

See `runpod/README.md` — it carries the RunPod rules we learned the expensive way.

### Evaluate

Every model change is measured against a human-verified golden set before it reaches
production. Precision and recall per clause type, clause counts, `finish_reason`
distribution, cost, and wall-clock. A better training loss is not evidence that the
product improved.

See `eval/README.md`.

---

## Conventions

**Secrets.** Credentials live in gitignored `.env` files, never in committed config. The
root `.env` holds this laptop's keys (`RUNPOD_API_KEY`, and `HF_TOKEN` for `make data`)
and is never sent anywhere. Each chart's secrets live next to it, in
`runpod/<chart>/.env` (template: `.env.example` in the same folder), and a chart's
`${VAR}`s resolve from that file only — so the training pod and the endpoint can hold
different tokens, and neither sees the other's. `model.config` uses `${HF_TOKEN}`,
never a literal token. If a credential is ever committed, rotate it
first, then clean history — in that order, because rotation is what actually stops the leak.

**Naming.** Model directories match their Hub repo name. Endpoint YAML files match the
RunPod endpoint name. Training configs are `<task>-<date>`. Reports are `YYYY-MM-DD-<topic>`.

**Reproducibility.** Every run pins a base model revision, a dataset revision, and a seed.
A result that cannot be traced back to an exact configuration is not a result.

**Truncation is a failure.** A vLLM response with `finish_reason: "length"` returns HTTP 200
and quietly drops content. Every caller must check it and raise. This has already cost us
roughly seven missing clauses per document in production.

**Registry discipline.** Any PR that changes what is deployed also changes
`registry/deployments.yaml`. A registry nobody trusts is worse than no registry.

---

## Known issues

| Issue | Impact | Status |
|---|---|---|
| Credentials were committed to git history | HF and RunPod tokens exposed on the remote | **Rotate, then rewrite history** |
| `max_tokens: 16384` below measured need of 17,258 | ~7 clauses silently dropped per BCA-sized doc | Fix in endpoint config |
| SEA-LION v4 context is 40,960 (v3 was 128K) | Only ~75 tokens of margin on BCA documents | Batch documents, or trial v4.5 (262K) |
| RunPod vLLM 0.27.1 lags upstream | Gemma 4 unsupported; DeepSeek-V4 needed 8 fixes | Build custom worker image |

Full detail: `docs/reports/2026-08-16-runpod-deployment-trials.md`.

---

## Roadmap

Deliberately deferred, in rough order of when it will start hurting:

1. Golden set and eval runner for PJP clause extraction
2. Custom vLLM worker image, so engine version is ours to choose
3. W&B wired into the training entrypoint
4. Runbooks for deploy, rollback, and credential rotation
5. CI: lint configs, validate registry YAML against schema, block secrets on commit

We are not building a platform. We are building the smallest thing that keeps the
next deployment from repeating the last one's mistakes.
