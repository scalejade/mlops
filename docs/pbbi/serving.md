# Serving

Two serverless endpoints, one per fine-tuned model, on one network volume that is
filled before any worker needs it. Back to the [index](README.md).

## The two endpoints

| Endpoint | Serves | Adapter (vLLM model name) | State |
|---|---|---|---|
| `pbbi-serverless-extraction` | clause extraction — what the app calls today | `scalejade/pbbi-clause-extraction-lora` → `pbbi-clause-extraction` | ready to deploy — `runpod/pbbi-serverless-extraction/`, `ADAPTER_REVISION=v0.1.0` |
| `pbbi-serverless-analysis` | analysis | `scalejade/pbbi-analysis-lora` → `pbbi-analysis` | **draft** — `runpod/pbbi-serverless-analysis/` exists, `ADAPTER_REVISION` is empty, so `plan` refuses it until the adapter is trained |

Both serve the **same base** (`scalejade/qwen-sea-lion-v4.5-27b-pbbi` @ `8d32a4b9…`)
plus their own LoRA, from the same volume. Same chart shape; only `adapter:` and
`ADAPTER_REVISION` differ.

**Calling them.** OpenAI-compatible. Send the adapter's name as `"model"` to get
the fine-tuned behaviour — `"pbbi-clause-extraction"` for extraction. The base
model's own name still answers on the same endpoint, without the adapter. A
`finish_reason` of `"length"` is a **failure** (HTTP 200 with content silently
cut); every caller must check it and raise.

| Setting (both endpoints) | Value |
|---|---|
| Worker image | `runpod/worker-v1-vllm:v2.28.0` (vLLM 0.30.0) |
| GPU | `NVIDIA RTX PRO 6000 Blackwell Server Edition` (96 GB), 1 per worker |
| Region | `CA-MTL-3` — must equal the volume's |
| Workers | min 0 (scales to zero), max 1 |
| Engine args | `models/qwen-sea-lion-v4.5-27b-pbbi/model.config`, plus the LoRA args `deploy.py` adds |
| Request defaults | `max_tokens: 24576`, `temperature: 0` |

From worker v2.27 on, every env var named like a `vllm serve` flag becomes that
flag. That is how the deployment reaches vLLM:

| Env | Set by | Becomes |
|---|---|---|
| `MODEL_NAME`, `MODEL_REVISION` | model.config | `--model`, `--revision` — pinned, so a cold start never re-resolves `main` |
| `ENABLE_LORA=true`, `MAX_LORAS=1`, `MAX_CPU_LORAS=1`, `MAX_LORA_RANK=16` | `deploy.py`, from `adapter:` | LoRA on; `MAX_CPU_LORAS` must be ≥ `MAX_LORAS` or vLLM refuses to start |
| `LORA_MODULES=pbbi-clause-extraction=/runpod-volume/adapters/pbbi-clause-extraction-lora/v0.1.0` | `deploy.py` | `--lora-modules` |
| `HF_HOME=/runpod-volume/hf` | model.config | where the worker finds the base the loader pulled |

## The volume

`runpod/pbbi-volumes/` · 200 GB · `CA-MTL-3` · ~$14/mo, billed continuously

```
/runpod-volume/                         (= /workspace on the loader pod)
├── hf/hub/models--scalejade--qwen-sea-lion-v4.5-27b-pbbi/   base, 55.6 GB, HF cache layout
├── adapters/
│   ├── pbbi-clause-extraction-lora/v0.1.0/                  ~0.3 GB, plain directory
│   └── pbbi-analysis-lora/<tag>/                            when it exists
├── loader.log                                               every fill, appended
└── loader.done                                              what the last fill verified
```

Adapters are plain directories named by **revision**, not HF-cache entries: vLLM's
`--lora-modules` takes a path, and a path pinned by tag cannot drift the way a repo
id resolving `main` can.

**Why CA-MTL-3:** it is the one datacenter with network volumes, accepted by the
REST API for pods and endpoints, *and* the serving GPU in stock (2026-10-13). A
volume is region-local, so the volume, the loader and both endpoints all sit there.

## Filling the volume: `make volume-fill`

A serverless worker that finds its weights missing downloads them itself, on a cold
start, while a request waits: ~2 h instead of ~26 s (`docs/reports/2026-08-16-…`).
`pbbi-loader` does that download once, ahead of time, on a CPU:

1. creates the CPU pod on the volume (`cpu3c`/`cpu5c`, 4 vCPU, `runpod/base:1.4.0-ubuntu2404`)
2. its boot script pulls the base at `BOOT_REVISION` and each adapter at its tag
3. verifies them (`config.json` + shards; `adapter_config.json` + weights), writes `loader.done`
4. the target prints the result and **deletes the pod** — also when the pull failed

Pins live in `runpod/pbbi-loader/.env`, and must equal what the endpoints ask for:

| Loader `.env` | Must equal |
|---|---|
| `BOOT_MODEL` / `BOOT_REVISION` | `MODEL_NAME` / `MODEL_REVISION` in `models/<model>/model.config` |
| `BOOT_ADAPTERS` — one `repo@tag` per endpoint, comma-separated | each endpoint's `adapter.repo` + `ADAPTER_REVISION` |

```bash
# runpod/pbbi-loader/.env — one fill serves both endpoints
BOOT_ADAPTERS=scalejade/pbbi-clause-extraction-lora@v0.1.0,scalejade/pbbi-analysis-lora@v0.1.0
```

A mismatch does not fail loudly: the worker just downloads the missing revision on
its cold start — the exact problem the loader exists to prevent. Every entry must
carry a tag; `pod.py` refuses an unpinned one. Re-running the fill is cheap: what is
already on the volume is checked, not downloaded again.

## Deploying, in order

```bash
python runpod/deploy.py apply pbbi-volumes                  # once, shared by both; starts ~$14/mo
make volume-fill                                            # base + every adapter in BOOT_ADAPTERS

python runpod/deploy.py plan  pbbi-serverless-extraction    # checks the adapter tag on the Hub, rank, pins
python runpod/deploy.py apply pbbi-serverless-extraction    # its own template + endpoint, idempotent by name

python runpod/deploy.py plan  pbbi-serverless-analysis      # once its adapter exists and ADAPTER_REVISION is set
python runpod/deploy.py apply pbbi-serverless-analysis
```

Each `apply` creates a template and an endpoint named after the chart, so the two
endpoints have separate IDs, workers and GPUs; the app calls each by its own ID.

Then smoke-test with a **full-length real document**, confirm `finish_reason ==
"stop"`, and update `registry/deployments.yaml` in the same PR.

**Shipping a new adapter version** (one endpoint; the other is untouched):

1. its entry in `BOOT_ADAPTERS` (loader `.env`) and its `ADAPTER_REVISION` (endpoint `.env`) → the new tag
2. `make volume-fill`
3. `python runpod/deploy.py apply pbbi-serverless-<task>`

The old version's directory stays on the volume, so rolling back is reverting the
two `.env` values and applying again.

**Bringing the analysis endpoint live:** train `training/configs/pbbi-analysis.yaml`
(remove its `status: draft` first) → add `scalejade/pbbi-analysis-lora@<tag>` to
`BOOT_ADAPTERS` → set `ADAPTER_REVISION=<tag>` in `runpod/pbbi-serverless-analysis/.env`
→ `make volume-fill` → `deploy.py apply pbbi-serverless-analysis`.

## Checks `deploy.py plan` runs

- the adapter's `adapter_config.json` exists on the Hub at the pinned tag (a typo
  fails here, not as a 404 on every request)
- its rank `r` ≤ `MAX_LORA_RANK`, and its recorded base equals the served `MODEL_NAME`
- `MAX_CPU_LORAS` ≥ `MAX_LORAS`
- `MODEL_REVISION` is pinned (warning if not)
- GPUs per worker = `TENSOR_PARALLEL_SIZE`; the volume's region is in `dataCenterIds`;
  `MAX_MODEL_LEN` > 0 and leaves room for `max_tokens`

## Verified, and not yet

**Verified 2026-10-16:**

- `make volume-fill` end to end in US-CA-2: a CPU pod starts, `runpod/base:1.4.0-ubuntu2404`
  brings up sshd through `/start.sh`, base + adapter land and verify, the pod deletes itself.
- `deploy.py apply` creates the template and endpoint, and updates them in place.
- vLLM 0.30 loads Qwen3.5 (`Qwen3_5ForConditionalGeneration`) with the LoRA and answers
  correctly — on `pbbi-eval`, the same vLLM as the worker (see [evaluation.md](evaluation.md)).

**Not yet** — every attempt hit GPU capacity, not a configuration error:

- a serverless worker answering a request: it stayed *throttled* in US-CA-2 with all
  listed GPU types sold out, and CA-MTL-3 had no CPU for the loader. Retry when a
  listed GPU is in stock in the volume's datacenter.
- `MAX_MODEL_LEN=262144` on the worker. KV is small (16 full-attention layers × 32
  KiB/token in fp8 → 8 GiB for one 262k sequence), so it should fit even an 80 GB
  card; if a worker fails at startup, lower it first.
- the app sending `"model": "pbbi-clause-extraction"` — it currently names the base.
