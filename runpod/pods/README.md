# Pods

A **pod** is a GPU you rent by the hour that stays up. A **serverless endpoint** scales
to zero and cold-starts on demand. For a batch extraction run — a handful of long
documents, minutes of compute each — a pod is the right shape: no cold start, no
per-request scaling drama, and you can SSH in when the engine refuses to boot.

Use serverless for bursty production traffic. Use a pod for trials, batch jobs, and
anything where you want to watch the logs.

## Config

`sea-lion-v45-27b.yaml` — GPU, disk, container, and engine args for
`scalejade/qwen-sea-lion-v4.5-27b-it`.

`start-vllm.sh` — the container start command.

## The sizing, and where it comes from

```bash
python runpod/scripts/vram_budget.py --model qwen-sea-lion-v4.5-27b-it
```

SEA-LION v4.5-27B is a **Qwen3.5 hybrid-attention** model. Only 16 of its 64 layers
keep a growing KV cache — the other 48 use linear attention with fixed-size state.
That is the whole reason a 262,144-token window is affordable on one GPU:

| | v4-32B (Qwen3) | v4.5-27B (Qwen3.5) |
|---|---|---|
| Full-attention layers | 64 of 64 | **16 of 64** |
| KV heads × head dim | 8 × 128 | 4 × 256 |
| KV per token (fp8) | 128 KiB | **32 KiB** |
| Native context | 40,960 | **262,144** |

Four times cheaper per token, six times the window.

**Budget at fp8 KV cache, bf16 weights (55.6 GB), 4 GB overhead:**

| context | 1 seq | 2 seq | 4 seq | 8 seq |
|---:|---:|---:|---:|---:|
| 40,960 | 60.8 | 62.1 | 64.6 | 69.6 |
| 131,072 | 63.6 | 67.6 | 75.6 | 91.6 |
| 163,840 | 64.6 | 69.6 | 79.6 | 99.6 |
| 262,144 | 67.6 | 75.6 | 91.6 | 123.6 |

**GPU choice** (usable = VRAM × 0.90):

| GPU | VRAM | usable | best config | $/hr |
|---|---:|---:|---|---:|
| **RTX PRO 6000** | 96 | 86.4 | **262,144 × 2** | **2.09** |
| H100 NVL | 94 | 84.6 | 262,144 × 2 | 3.19 |
| H100 SXM | 80 | 72.0 | 262,144 × 1 | 3.29 |
| H200 | 141 | 126.9 | 262,144 × 8 | 4.59 |
| B200 | 180 | 162.0 | 262,144 × 8 | 6.79 |

**RTX PRO 6000 at $2.09/hr** does the job — full native context, two concurrent
requests, 10.8 GB to spare. It is also the cheapest option on the list. Move to H200
only when you need more than two concurrent long requests; it costs 2.2× for 4× the
concurrency, which is worth it under load and wasteful for a batch of six.

Nothing at 80 GB or below. 55.6 GB of weights leaves too little room for KV cache to
be useful.

## Disk

| | size | mount | survives stop | survives delete |
|---|---:|---|---|---|
| Container disk | 50 GB | system | no | no |
| Volume disk *(trial)* | 150 GB | `/workspace` | yes | **no** |
| Network volume *(later)* | 150 GB | `/workspace` | yes | yes |

We are on **volume disk** for the trial. It keeps the 55.6 GB of weights across pod
stops, which is all a trial needs. The catch is that deleting the pod deletes the
disk with it — so **stop the pod, never delete it**, until the run is finished.

Cost difference, 150 GB:

| | running | stopped | monthly if mostly stopped |
|---|---:|---:|---:|
| Volume disk | $0.10/GB/mo | **$0.20/GB/mo** | ~$30 |
| Network volume | $0.07/GB/mo | $0.07/GB/mo | ~$10 |

Volume disk bills *double* while the pod is stopped. If this pod outlives the trial,
move to a network volume — it is cheaper, survives deletion, and the serverless
endpoint needs one anyway, so one volume can serve both.

Note the mount path differs by product: pods mount at `/workspace`, serverless workers
mount at `/runpod-volume`. `HF_HOME` is set to `/workspace/huggingface-cache` here.

## Launch

1. Deploy a pod: pick the GPU, set **container disk 50 GB** and **volume disk 150 GB**
   (mounts at `/workspace`), template **vLLM Latest** (Verified), expose ports
   `8000/http` and `22/tcp`.
2. Set env: `HF_TOKEN`, `HF_HOME=/workspace/huggingface-cache`, `VLLM_API_KEY`.
3. Container start command: the contents of `start-vllm.sh`.
4. Watch the logs. First start downloads 55.6 GB — expect 10–20 minutes. Subsequent
   starts read from the volume.

Ready when the log shows `Application startup complete` and `/v1/models` answers.

## Send the Jago job

```bash
export POD_URL="https://<pod-id>-8000.proxy.runpod.net/v1"

curl -s "$POD_URL/chat/completions" \
  -H "Authorization: Bearer $VLLM_API_KEY" \
  -H 'Content-Type: application/json' \
  -d @runpod/requests/jago-extraction-SINGLE-262k.json | jq '.usage, .choices[0].finish_reason'
```

That request is 56,620 input + 103,410 `max_tokens` = **160,030 peak**, which fits the
262,144 window in a single call. No chunking, so no clause renumbering and no lost
parent/child inheritance.

Confirm `finish_reason` is `"stop"`. If it says `"length"` the output is truncated and
clauses are missing, with HTTP 200 and no error.

## Cost

At $2.09/hr, billed per second while the pod is **running** — a pod costs money when
idle, unlike serverless. Stop it when you are not using it.

A six-document batch at a few minutes each is well under an hour. Storage on the
network volume bills separately and continuously, so delete the volume when the trial
is over if you are not keeping the model warm.

## Known risk

`Qwen3_5ForConditionalGeneration` is a newer architecture than `Qwen3ForCausalLM`.
vLLM added support in **0.17.0**; the pinned `v0.27.1` is well past that, so it should
load. But this is the exact class of failure that killed Gemma 4 on this stack, so
verify before planning around it:

```bash
# on the pod, before committing to a long run
python -c "from vllm import LLM; LLM('$MODEL', max_model_len=4096)"
```

If the architecture is rejected, bump to a newer `vllm/vllm-openai` tag rather than
fighting it.

## Container start command (RunPod UI)

The `vllm/vllm-openai` image already has `vllm serve` as its ENTRYPOINT, so RunPod's
"Container start command" box takes **arguments only** — starting with the model name.
It is not a shell, so `start-vllm.sh` cannot be pasted there and `$VAR` does not expand.

Paste the contents of `start-command.txt`. Use `start-vllm.sh` only when running over
SSH or from a custom image with its own entrypoint.
