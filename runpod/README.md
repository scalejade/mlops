# RunPod

Inference. Everything about how a model is served lives here, and every deployment
goes through `deploy.py` — no clicking around the RunPod console.

The console is fine for looking at things. It is a bad place to *change* things,
because a change made there exists nowhere in git and nobody can tell what a
service is supposed to look like.

## Charts

A **chart** is one deployable service: a directory holding `chart.yaml` (what it is)
and `values.yaml` (how it is configured). Every service sits at the same level,
whatever its kind:

```
runpod/
  deploy.py
  pbbi-volumes/          kind: volume       chart.yaml  values.yaml
  pbbi-serverless-extraction/      kind: serverless   chart.yaml  values.yaml
  pbbi-training/         kind: pod          chart.yaml  values.yaml
```

`pbbi-training` is the H200 training pod, on its own disk (no network volume, no
region pin). Its `boot.sh` is its start command: on every start it pulls
`boot.model` (values.yaml; empty pulls nothing) into `/workspace/hf` in the
background, then hands over to the image's `/start.sh`. It runs no engine, so
`deploy.py` refuses it and points at `make pod-plan` / `pod-up` /
`pod-delete pbbi-training` (`training/scripts/pod.py`) instead.

`pbbi-eval` is a vLLM pod with no volume and no region pin, for testing an adapter
on whichever GPU is free anywhere — `deploy.py apply pbbi-eval`, evaluate, `deploy.py
delete pbbi-eval`. See `docs/pbbi/evaluation.md`.

`pbbi-loader` is a CPU pod on `pbbi-volumes` that exists for minutes: `make
volume-fill` creates it, its `boot.sh` pulls the serving base model (HF cache,
`/workspace/hf`) and the LoRA adapter (`/workspace/adapters/<repo>/<revision>`),
verifies both, and the target deletes the pod. The endpoint sees the same
directories under `/runpod-volume`, so no worker downloads weights on a cold start.
`pod-up`, `pod-down`, `pod-stop` and `pod-delete` always need the chart named.

Adding a fourth service means adding a fourth directory. `deploy.py` discovers charts
by globbing `*/chart.yaml`, so nothing needs registering. The directory name **is** the
service name, and it is also the name the resource carries on RunPod — that is what
makes `apply` idempotent, because every kind is looked up by name and PATCHed if it
already exists.

### chart.yaml — identity

```yaml
apiVersion: v1
kind: serverless            # serverless | pod | volume
name: pbbi-serverless-extraction # must equal the directory name
version: 0.1.0
description: Clause extraction over Indonesian loan agreements.
dependencies:
  - name: pbbi-volumes
    kind: volume
```

`dependencies` is the part that earns the chart shape. A serverless endpoint needs a
network volume, and hardcoding the volume's id in two places is how the two drift
apart. Instead the endpoint names the volume it needs; at deploy time `deploy.py`
looks that volume up on the account and injects its real id. Apply the volume first —
a dependency that is not deployed is a hard failure, in `plan` as well as `apply`.

### values.yaml — configuration

Everything tunable, and nothing else. Field names under `template:`, `endpoint:` and
the pod blocks map 1:1 to the RunPod REST API, so there is no hidden translation layer
to reason about. `${VAR}` is resolved at deploy time from the chart's own
`runpod/<chart>/.env` — and only from it, never the root `.env` — which is how
secrets stay out of git and each service gets only its own.

One exception, on purpose: **serverless engine arguments are not here.** They live in
`models/<model>/model.config`, so the same model gets the same engine config wherever
it is served, and `deploy.py` sends that file as the template env. A pod has no
template, so its `engine:` block lives in `values.yaml` and `deploy.py` renders it into
the pod's start command.

## The three kinds

| kind | RunPod resource | when |
|---|---|---|
| `volume` | network volume | shared checkpoint storage. Apply this first — the others depend on it. |
| `serverless` | template + endpoint | bursty production traffic. Scales to zero, cold-starts on demand. |
| `pod` | pod | trials, batch jobs, anything where you want to watch the logs or SSH in. |

The pod/serverless split is the one people get wrong. A pod is a GPU you rent by the
hour that stays up; it bills whether or not it is serving. Serverless scales to zero
and costs nothing idle, at the price of a cold start on the first request. For a batch
run — a handful of long documents, minutes of compute each — a pod is the right shape:
no cold start and no per-request scaling drama. For traffic that arrives unpredictably,
serverless.

## Commands

```bash
python runpod/deploy.py list                           # charts on disk vs what is live
python runpod/deploy.py plan   <service>               # validate + show, sends nothing
python runpod/deploy.py apply  <service>               # create or update
python runpod/deploy.py status <service>               # what is actually live
python runpod/deploy.py delete <service>               # tear down (asks for confirmation)
python runpod/deploy.py stop   <service>               # pods only — stop billing, keep disk
python runpod/deploy.py start  <service>               # pods only — resume
```

The same verbs from the repo root, through `make`, with the chart as the word after
the target:

```bash
make pod-plan pbbi-volumes        # -> deploy.py plan  pbbi-volumes
make pod-up   pbbi-serverless-extraction      # -> deploy.py apply pbbi-serverless-extraction
make pod-up   pbbi-training      # -> the training pod (pod.py)
make pod-up                       # -> refused: pod-up always names its chart
```

A pod chart without an `engine:` block goes to `training/scripts/pod.py`; every other
chart goes to `deploy.py`.

Same verbs for every kind. `apply` is idempotent; always run `plan` first, since it
does the full validation pass — dependency resolution included — without touching the
account.

Order matters on a cold account:

```bash
python runpod/deploy.py apply pbbi-volumes        # volume first
python runpod/deploy.py apply pbbi-serverless-extraction    # then what mounts it
```

Then update `registry/deployments.yaml` with the id it prints, in the same PR.

## Setup

```bash
pip install pyyaml

cp .env.example .env
# RUNPOD_API_KEY   RunPod console -> Settings -> API Keys (needs write access).
#                  This laptop's key: used to call the API, never sent to RunPod.

# One .env per chart, next to its chart.yaml. Each folder's .env.example lists
# what that chart needs; charts without secrets (pbbi-volumes) have none.
cp runpod/pbbi-serverless-extraction/.env.example runpod/pbbi-serverless-extraction/.env
# HF_TOKEN         the workers pull private scalejade/ weights (read access)
cp runpod/pbbi-training/.env.example  runpod/pbbi-training/.env
# HF_TOKEN         pull the base, push the adapter (write access)
# SSH_PUBLIC_KEY   how ssh gets into the pod
# WANDB_API_KEY    optional
```

A serving pod chart would carry `VLLM_API_KEY` in its own `.env` — the pod proxy URL
is public, so set a real random value.

Network volume ids are **not** in `.env` any more. They are resolved by name through
the dependency graph.

## Preflight

`plan` and `apply` both run it. Each check exists because it has already cost us an
evening; see `docs/reports/2026-08-16-runpod-deployment-trials.md`.

**Fatal:**

- `TENSOR_PARALLEL_SIZE` must equal `gpuCount` (serverless) or `gpu.count` (pod).
  Mismatched, the worker dies with `DP adjusted local rank N is out of bounds for 1
  devices`. RunPod's `gpuCount` means *GPUs per worker* — `workersMax` is the replica
  count. Confusing the two cost us three separate attempts.
- `MAX_MODEL_LEN` / `engine.max_model_len` must be a positive integer. Left empty it is
  passed as `0`, and vLLM ≥0.27 rejects `0` rather than reading it as "auto".
- A serverless endpoint must have a volume. Without a shared volume every worker
  downloads the full checkpoint itself: ~2 hours of cold start instead of ~26 seconds.
- A volume and everything that mounts it must be in the same datacenter. Network
  volumes are region-local and simply will not attach across regions.
- `max_tokens` must leave room for the prompt inside the context window, and a pod's
  `workload.peak_context_needed` must fit inside `engine.max_model_len`.
- A volume's `size` may not be reduced below what is live. Volumes grow, never shrink.

**Warning:**

- No `dataCenterIds` — workers spread across regions get throttled.
- `disk.type: volume_disk` on a pod — the disk dies with the pod. Stop it, never
  delete it.
- `max_tokens` small relative to the context window. This is the truncation trap: a
  response that hits the limit comes back **HTTP 200** with content silently missing.
  At `max_tokens: 16384` against a real need of 17,258 we lost roughly seven clauses
  per document and nothing errored.

## Calling a service

`apply` prints the base URL. Both kinds speak the OpenAI API — serverless at
`https://api.runpod.ai/v2/{id}/openai/v1`, a pod at
`https://{id}-8000.proxy.runpod.net/v1`.

```python
from openai import OpenAI

client = OpenAI(api_key=..., base_url=BASE_URL)

resp = client.chat.completions.create(
    model="scalejade/qwen-sea-lion-v4-32b-it",
    messages=[...],
    max_tokens=24576,
    temperature=0.0,
)

# Non-negotiable. A truncated response is a failure, not a result.
if resp.choices[0].finish_reason == "length":
    raise RuntimeError("output truncated — raise max_tokens or split the document")
```

## Cost

Serverless bills per second of worker runtime, including cold start. `workersMin: 0`
scales to zero and costs nothing idle. A pod bills by the second while **running**,
idle or not — `deploy.py stop` is how you stop paying without losing the disk. A
network volume bills continuously at $0.07/GB/mo regardless of what is attached.

`plan` prints the hourly or monthly figure before anything is sent.

## API version

`deploy.py` targets RunPod REST **v1** (`https://rest.runpod.io/v1`), which is
deprecated and retires **2026-11-15**. v2 is not a drop-in replacement — nested request
bodies, `/endpoints` becomes `/serverless`, list responses are wrapped in an object,
and errors move to RFC 9457. Everything version-specific is confined to `api()`,
`find_by_name()` and the `KINDS` table, so the migration is a contained change rather
than a rewrite.
