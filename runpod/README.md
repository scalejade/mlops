# RunPod

Inference. Everything about how a model is served lives here, and every deployment
goes through `deploy.py` — no clicking around the RunPod console.

The console is fine for looking at things. It is a bad place to *change* things,
because a change made there exists nowhere in git and nobody can tell what the
endpoint is supposed to look like.

## Layout

| Path | What |
|---|---|
| `deploy.py` | The deploy CLI. Reads config, validates it, calls the RunPod REST API. |
| `endpoints/` | One YAML per endpoint. Field names map 1:1 to the RunPod API. |
| `worker/` | Our own vLLM worker image, so the engine version is ours to choose. |

Engine arguments (context length, KV cache dtype, prefix caching, …) are **not**
here — they live in `models/<model>/model.config`, so the same model gets the same
engine config wherever it is served. `deploy.py` reads that file and sends it as
the template's env.

## Setup

```bash
pip install pyyaml

cp .env.example .env
# RUNPOD_API_KEY            RunPod console -> Settings -> API Keys (needs write access)
# RUNPOD_NETWORK_VOLUME_ID  RunPod console -> Storage
# HF_TOKEN                  needed by the worker to pull private scalejade/ weights
```

## Deploying

```bash
python runpod/deploy.py plan   pjp-clause-extraction   # validate + show, sends nothing
python runpod/deploy.py apply  pjp-clause-extraction   # create or update
python runpod/deploy.py status pjp-clause-extraction   # what is actually live
python runpod/deploy.py list                           # every endpoint on the account
python runpod/deploy.py delete pjp-clause-extraction   # tear down (asks for confirmation)
```

`apply` is idempotent. It looks the template and endpoint up **by name** and PATCHes
them if they already exist, so running it twice does not create duplicates. Always run
`plan` first — it does the full validation pass without touching the account.

### What happens on apply

1. Load `.env`, then `runpod/endpoints/<name>.yaml`.
2. Load `models/<model>/model.config` and expand `${VAR}` from `.env`.
3. Run preflight (below). Fail before spending a cent if anything is wrong.
4. Create or update the RunPod template — image, disk, volume mount, engine env.
5. Create or update the endpoint — GPU type, worker counts, scaling, network volume.
6. Print the endpoint ID and OpenAI-compatible base URL.

Then update `registry/deployments.yaml` with the endpoint ID, in the same PR.

## Preflight

These checks exist because each one has already cost us an evening. See
`docs/reports/2026-08-16-runpod-deployment-trials.md`.

**Fatal:**

- `TENSOR_PARALLEL_SIZE` must equal `gpuCount`. Mismatched, the worker dies with
  `DP adjusted local rank N is out of bounds for 1 devices`. Note that RunPod's
  `gpuCount` means *GPUs per worker* — `workersMax` is the replica count. Confusing
  the two cost us three separate attempts.
- `MAX_MODEL_LEN` must be a positive integer. Left empty it is passed as `0`, and
  vLLM ≥0.27 rejects `0` rather than reading it as "auto".
- `networkVolumeId` must be set. Without a shared volume every worker downloads the
  full checkpoint itself: ~2 hours of cold start instead of ~26 seconds.
- `max_tokens` must leave room for the prompt inside `MAX_MODEL_LEN`.

**Warning:**

- No `dataCenterIds` — workers spread across regions get throttled.
- `max_tokens` small relative to the context window. This is the truncation trap:
  a response that hits the limit comes back **HTTP 200** with content silently
  missing. At `max_tokens: 16384` against a real need of 17,258 we lost roughly
  seven clauses per document and nothing errored.

## Calling the endpoint

`deploy.py apply` prints the base URL. It speaks the OpenAI API:

```python
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["RUNPOD_API_KEY"],
    base_url=f"https://api.runpod.ai/v2/{ENDPOINT_ID}/openai/v1",
)

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
scales to zero and costs nothing idle, at the price of a cold start on the first
request. For latency-sensitive interactive work set `workersMin: 1` and accept the
hourly rate. For batch jobs leave it at zero.

Current production: 1× RTX PRO 6000 96GB at $3.49/hr.

## When RunPod's image is too old

The stock vLLM worker lags upstream. Gemma 4 would not run at all on vLLM 0.27.1,
and DeepSeek-V4 needed eight fixes. When a model is newer than the template, build
from `worker/` and set `template.imageName` to your own image. See `worker/README.md`.
