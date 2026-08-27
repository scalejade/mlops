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
├── .env.example               template for local secrets (never commit .env)
│
├── models/                    one dir per model on huggingface.co/scalejade
│   └── <model-name>/
│       ├── README.md          the HF model card
│       ├── model.config       vLLM engine args for serving this model
│       └── weights/           gitignored — local snapshot only
│
├── training/                  Unsloth fine-tuning on a rented H200
│   ├── pod.yaml               the H200 pod: GPU, disk, image, env
│   ├── requirements.txt       installed on the pod, not on your laptop
│   ├── configs/               one YAML per run — the config IS the experiment record
│   ├── datasets/              schema + build scripts (real data lives in private HF repos)
│   ├── scripts/               pod.py (rent/stop the GPU), bootstrap.sh, train.py
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
│   ├── runbooks/              procedures for things done under time pressure
│   ├── reports/               deployment trials, incident write-ups, benchmarks
│   └── adr/                   architecture decisions worth not re-litigating
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

pip install -r requirements.txt      # TODO
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

### Fine-tune

1. Build the dataset, push it to a **private** HF dataset repo, note the revision.
2. Copy `training/configs/example-lora.yaml` → `configs/<task>-<date>.yaml`, edit it.
3. Rent the GPU, run against that config, **stop the GPU**:

```bash
python training/scripts/pod.py apply       # 1x H200, ~$4.59/hr, billing starts here
# ssh in: bash training/scripts/bootstrap.sh, then
#         python training/scripts/train.py training/configs/<task>-<date>.yaml
python training/scripts/pod.py stop        # billing stops HERE, not when training ends
```

   Nothing gets tweaked at the command line — if it isn't in the config file, it
   didn't happen and it can't be reproduced.
4. Push the adapter to the Hub, register it in `registry/models.yaml`.
5. Evaluate. Then, and only then, consider deploying.

See `training/README.md`.

### Deploy

1. The model must be registered and must have passed `eval/`.
2. Write or edit `runpod/endpoints/<name>.yaml`.
3. Deploy from your laptop — all you need is `RUNPOD_API_KEY` in `.env`:

```bash
python runpod/deploy.py plan  pjp-clause-extraction    # validate, send nothing
python runpod/deploy.py apply pjp-clause-extraction    # create or update
```

   `apply` is idempotent: it finds the template and endpoint by name and updates them
   in place. Engine args come from `models/<model>/model.config`, secrets from `.env`.
   Preflight refuses to deploy on the four mistakes that have already burned us.

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

**Secrets.** `.env` is the only place credentials live, and it is gitignored. `model.config`
uses `${HF_TOKEN}`, never a literal token. If a credential is ever committed, rotate it
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
