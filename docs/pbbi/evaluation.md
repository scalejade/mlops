# Evaluation

How to tell whether an adapter works, and whether it is better than what came
before — before it reaches an endpoint. Back to the [index](README.md).

## `pbbi-eval`: a vLLM pod for testing adapters

`runpod/pbbi-eval/` · deployed with `runpod/deploy.py` · deleted after each evaluation

One GPU pod running **vLLM 0.30** — the same vLLM as the serverless worker
(`runpod/worker-v1-vllm:v2.28.0`) — serving the base model and the LoRA adapters
side by side on one OpenAI-compatible URL:

| `"model"` in the request | Serves |
|---|---|
| `scalejade/qwen-sea-lion-v4.5-27b-pbbi` | the base, no adapter |
| `pbbi-clause-extraction` | base + `scalejade/pbbi-clause-extraction-lora` |

**Why it exists.** A serverless endpoint lives in its network volume's datacenter
and can only use that datacenter's GPUs. On 2026-10-16 those kept selling out (a
worker sat *throttled*; a loader could not get a CPU), so the endpoint could not
answer the one question that mattered: *does the adapter work?* `pbbi-eval` has its
own disk and no region pin, and takes whichever of four GPU types is free anywhere —
it got one on the first try.

| Setting | Value |
|---|---|
| Image | `vllm/vllm-openai:v0.30.0` |
| GPU | any of H100 80GB, H100 NVL, H200, RTX PRO 6000 Server — whichever is free |
| Disk | own 100 GB disk (`volume_disk`), no region pin |
| Base | pinned at `8d32a4b9…`, as the endpoint |
| Context | `max_model_len: 131072` — the app's longest call (prompt + 65,536 output) fits |
| Adapters | `engine.lora_modules`: served name → Hub repo (vLLM pulls each at startup) |
| Access | `https://<pod id>-8000.proxy.runpod.net/v1`, `Authorization: Bearer $VLLM_API_KEY` |
| Cost | $2.49/hr on an RTX PRO 6000 (up to ~$5.29 on an H200), from `apply` to `delete` |

**What it does not test:** the serverless pieces — network volume, loader, the
worker wrapper, cold starts. A good result here says the *model* works; the endpoint
still needs one real request once it has a GPU.

### Running an evaluation

```bash
python runpod/deploy.py plan   pbbi-eval      # GPU list, vllm serve command, nothing sent
python runpod/deploy.py apply  pbbi-eval      # BILLING STARTS; prints the pod URL
#   wait until GET <url>/v1/models lists every adapter (~15 min: 55.6 GB download + load)
#   send the validation rows to each model name and score them (below)
python runpod/deploy.py delete pbbi-eval      # BILLING STOPS — do not leave it running
```

Secrets are in `runpod/pbbi-eval/.env` (template beside it): `HF_TOKEN` (read) and
`VLLM_API_KEY` — a long random string, because the proxy URL is public.

To compare adapters, list each under its own name in `engine.lora_modules` and send
every row to each name on the same pod, in the same run. vLLM pulls a Hub repo's
`main` — the latest push — and cannot pin a tag, so two *versions of the same repo*
cannot be loaded this way side by side; evaluate the new version right after it is
pushed, against the numbers recorded below for the old one.

## How a reply is scored

The same rules as training's quality check (`training/scripts/train.py`), so the
numbers are comparable with the W&B `quality/` panels.

1. **Data: the validation split** (`preparation/data/eval.jsonl`), documents marked
   `Split : Validation` — never trained on. Each row is the app's request plus
   Legal's labelled answer.
2. **Request: exactly the app's** (`preparation/app_request.py`, `request_body`):
   the system prompt byte-for-byte, `"DOCUMENT:\n" + text`, `max_tokens: 65536`,
   `response_format: json_object`, no temperature. Only `stream: true` is added, so a
   long reply cannot hit a proxy timeout.
3. **Same input to every model.** Each row goes to the base and to each adapter, on
   the same pod — the adapter is the only variable.
4. **Parse as the app does:** `parse_reply` then `finalize`. A reply the app cannot
   parse is `valid=False` with zero clauses. Legal's answer goes through the same
   steps to give the gold clauses.
5. **Match clauses:** a predicted clause finds a labelled one when their word sets
   overlap ≥ 0.8 (Jaccard), one-to-one, closest pairs first. Word sets, not exact
   strings, so a re-wrapped line is not a miss.

| Metric | Meaning |
|---|---|
| `finish` | `stop` = complete; `length` = cut off, which the app must treat as a failure |
| `valid` | the app could parse the reply |
| **recall** | labelled clauses found / labelled clauses |
| **precision** | matched / clauses returned |

Sanity check before trusting a run: Legal's labels scored against themselves must
match 100%.

## Results

### 2026-10-16 — `pbbi-clause-extraction-lora` `v0.1.0` vs base

`pbbi-eval` on an RTX PRO 6000 Server · eval rows 0–1 (OVO, 84 labelled clauses) ·
the demo adapter trained on 3 rows of one other document (GOPAY).

| | Base | **Adapter `v0.1.0`** |
|---|---|---|
| Recall | 0.405 (34/84) | **0.690** (58/84) |
| Precision | 0.596 (34/57) | **0.806** (58/72) |
| Finished, valid JSON | 2/2, 2/2 | 2/2, 2/2 |
| Speed | 26 tok/s | 24 tok/s (~7 s to first token) |

| Row | Base | Adapter |
|---|---|---|
| 0 (46 labelled) | 16 matched, 34 returned | **40 matched, 49 returned** |
| 1 (38 labelled) | 18 matched, 23 returned | 18 matched, 23 returned — unchanged |

**Read:**

- The adapter loads in vLLM 0.30 and returns valid, finished JSON the app accepts.
- It reproduces training exactly: 0.690 / 0.806 is what training's final quality
  check measured, so export → Hub → vLLM lost nothing.
- What it learned is Legal's house style, not knowledge. Legal repeats a list's
  lead-in sentence ("Kecuali ditentukan lain secara tegas…") at the start of every
  item; the adapter does too, the base splits the lead-in off as its own clause —
  and its clauses then no longer match Legal's wording. That is most of row 0's gap.
- **All the gain is on row 0.** Row 1 is identical to the base, as it never moved in
  training. Two rows of one document show the fine-tune changes behaviour; they do
  not estimate production quality — that needs the full-data run and the test split.

## Not built yet

- The scoring script used above lives outside the repo; it belongs in
  `preparation/` or `training/scripts/` (it needs no GPU — only `requests` and
  `app_request.py`).
- Scoring `preparation/data/test.jsonl` — the gate before a deploy. Its document is
  ~64k tokens and Legal's answer ~40k: check `finish` first, a cut-off reply is the
  likely failure.
