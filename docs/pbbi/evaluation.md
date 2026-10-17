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
make evaluate ARGS="--dry-run"                # resolves the pod, sends nothing
make evaluate                                 # test.jsonl to every served model, scored
python runpod/deploy.py delete pbbi-eval      # BILLING STOPS — do not leave it running
```

`make evaluate` is `preparation/evaluate.py --target pbbi-eval`. It finds the pod by
name on the account, sends each row to each model (base and adapters, from
`GET /models`), and prints one line per reply and a table per model. Everything,
raw replies included, goes to `preparation/data/scores/<UTC time>/` (gitignored:
the replies quote the contract). Common variations:

```bash
make evaluate ARGS="--model pbbi-clause-extraction"            # the adapter only
make evaluate ARGS="--data preparation/data/eval.jsonl"         # the validation split
make evaluate TARGET=pbbi-serverless-extraction ARGS="--model pbbi-clause-extraction"
python preparation/evaluate.py --url <base>/v1 --api-key-env <VAR>   # anything else
python preparation/evaluate.py --check        # labels vs themselves, offline
```

The serverless target is the real endpoint, cold starts and all: use it once it has
a GPU, as the last check before the app is pointed at an adapter. A dry run never
contacts the endpoint (any request can wake a billed worker). Exit code 1 if any
request failed outright.

Secrets are in `runpod/pbbi-eval/.env` (template beside it): `HF_TOKEN` (read) and
`VLLM_API_KEY` — a long random string, because the proxy URL is public.

To compare adapters, list each under its own name in `engine.lora_modules` and send
every row to each name on the same pod, in the same run. vLLM pulls a Hub repo's
`main` — the latest push — and cannot pin a tag, so two *versions of the same repo*
cannot be loaded this way side by side; evaluate the new version right after it is
pushed, against the numbers recorded below for the old one.

## `openai`: gpt-4.1-mini, no pod

`make evaluate TARGET=openai` sends the same rows, in the same request, to
`gpt-4.1-mini` on `https://api.openai.com/v1`, and scores the replies the same way.
Set `OPENAI_API_KEY` in the root `.env` first. Nothing is deployed and nothing needs
deleting, but every token is billed to the key.

```bash
make evaluate TARGET=openai ARGS="--dry-run"           # what would be sent
make evaluate TARGET=openai ARGS="--rows 5,16"          # two short documents first
make evaluate TARGET=openai                             # all of test.jsonl
make evaluate TARGET=openai ARGS="--model gpt-4.1"      # another OpenAI model
```

There are two differences from the app's request:

- **`max_tokens` is 32,768, not 65,536.** That is gpt-4.1-mini's output cap, and
  OpenAI rejects a request that asks for more. A document whose answer is longer
  ends `length` and scores 0, as it would in the app. Counted with OpenAI's
  `o200k_base` tokenizer, three test answers are over the cap: DBS (38k), SEABANK
  (47k) and SHOPEEPAY (35k). OCBC Kartu Kredit (30k) is close.
- **No `temperature` means OpenAI's default, 1.0.** The request still sends none,
  as the app does. Expect run-to-run variance.

A 429 (rate limit) or a 5xx is retried up to 4 times, waiting for `Retry-After`.
`insufficient_quota` is not retried. At tier-1 limits, keep `--parallel` at the
default 2: OpenAI counts `max_tokens` against the per-minute token budget. The
whole test split is ~425k input tokens and ~270k output tokens at the labels' length.

## How a reply is scored

The same rules as training's quality check — both import `preparation/score.py` —
so the numbers are comparable with the W&B `quality/` panels.

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

### 2026-10-17 — `v0.1.1` on one whole document (OVO), superseded

Trained on whole documents (1 row, GOPAY, 3 steps, `max_seq_length` 81,920); eval
loss on OVO 0.1018 → 0.0957. Scored by hand on `pbbi-eval` (RTX PRO 6000) with the
app's real call on the whole OVO PDF (305 labelled clauses), sampled at the base
model's temperature 1.0:

| Recall | Precision | F1 | Lenient recall | Reply |
|---|---|---|---|---|
| 0.784 (239/305) | 0.693 (239/345) | 0.735 | 0.931 | 47,896 tokens, `stop`, 33 min at 24 tok/s |

- The content was there: with the lenient match (≥ 90% of a clause's words inside
  one returned clause) recall was 0.931. The strict gap came from **section headings
  copied into `clause_text`** — 326 of 345 clauses, against 0 in the labels and in
  the training data — and from `DEFINISI` split one clause per term where Legal's
  OVO labels group ranges (`|2-3`, `|6-8`).
- One contract that is also in the validation split, so it is not comparable with
  the test-split numbers below. Superseded by `v0.1.2`, which no longer copies the
  headings (17 of 1,849 clauses on the test split).

### 2026-10-17 — `v0.1.2` and `v0.1.3` on the test split, temperature 0

`pbbi-eval` on an H200 · all 17 rows of `test.jsonl` (2,074 labelled clauses) ·
`--temperature 0` (the app sends none; vLLM then samples at the base model's 1.0).
Full write-up: [reports/pbbi-extraction-eval-v0.1.3.md](reports/pbbi-extraction-eval-v0.1.3.md).

| | `v0.1.2`, no temperature | `v0.1.2`, temperature 0 | **`v0.1.3`**, temperature 0 |
|---|---|---|---|
| Recall | 0.659 | 0.645 | **0.658** |
| Precision | 0.739 | **0.789** | 0.784 |
| F1 | 0.696 | 0.709 | **0.716** |
| Finished, valid JSON | 17/17, 17/17 | 17/17, 17/17 | 17/17, 17/17 |

**Read:**

- **Temperature 0 is worth sending:** +0.013 F1, more precision, repeatable output.
- **v0.1.3** is 8 validation contracts moved to training (39 train / 4 eval);
  test unchanged, hyperparameters unchanged, best checkpoint step 20 again.
  - +0.007 F1: 2 contracts better (DBS +0.112, BJB +0.057), 6 worse, 9 the same.
  - It is the `stable` tag and the serving pin.
- **OCBC Internet Banking stays at ~0.36:** a labelling question, not a data-size one.

## Not built yet

- Comparing two versions of the same adapter repo on one pod (vLLM pulls `main`
  only; see above).
