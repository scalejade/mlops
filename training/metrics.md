# Training metrics — what W&B shows, and what good looks like

Every PBBI training run reports to Weights & Biases (project `scalejade-mlops`,
once `WANDB_API_KEY` is in `runpod/pbbi-training/.env`). This page explains each
metric: what it measures, how it is computed, the range that means the run is
healthy, the range that means something is wrong, and what to do about it.

**The numbers are expectations, not measurements.** They are worked out for this
exact setup — Qwen-SEA-LION v4.5 27B, LoRA r=16, bf16, rows of ~21k tokens
(14k of them the system prompt), effective batch 2, one H200 — from the
2026-10-10 data build and the token arithmetic in `training/README.md`. No real
run has happened yet. After the first one, replace the expected ranges with what
it actually measured; the first run is the baseline every later one is judged by.

Want to see the dashboard first? `make wandb-example` logs a simulated run with
every metric below to the `scalejade-mlops-example` project, no GPU needed.

---

## Quick reference

| Metric | Healthy | Warning | Bad |
|---|---|---|---|
| `quality/json_valid` | 1.0 | — | < 1.0 |
| `quality/finished` | 1.0 | — | < 1.0 |
| `quality/clause_recall` | ≥ 0.9 | 0.7 – 0.9 | < 0.7 |
| `quality/clause_precision` | ≥ 0.9 | 0.7 – 0.9 | < 0.7 |
| `quality/clause_count_ratio` | 0.95 – 1.05 | 0.8 – 0.95 or 1.05 – 1.2 | < 0.8 or > 1.2 |
| `eval/loss` (end of run) | 0.15 – 0.45 | 0.45 – 0.8 | > 0.8, or rising 2+ evals in a row |
| `eval/perplexity` (end) | 1.15 – 1.6 | 1.6 – 2.2 | > 2.2 |
| `eval/best_step` | last third of the run | middle of the run | the first eval |
| `eval/loss_gap` | −0.05 – +0.15, flat | +0.15 – +0.3 | > +0.3, or growing every eval |
| `train/loss` (end) | 0.1 – 0.4 | < 0.05 (memorising) | flat from the start, NaN, spikes |
| `train/perplexity` (end) | 1.1 – 1.5 | < 1.05 | flat > 2, NaN |
| `train/grad_norm` | settles 0.1 – 0.6 | stays > 1.0 | spikes > 10, inf, NaN |
| `perf/tokens_per_second` | ≥ 1,200 | 500 – 1,200 | < 500 |
| `perf/seconds_per_step` | 20 – 40 | 40 – 90 | > 90 |
| `perf/eta_minutes` (after step 10) | ≤ 150 | 150 – 300 | > 300 |
| `data/answer_fraction` | 0.15 – 0.40, steady | 0.05 – 0.15 or 0.40 – 0.9 | 0, or 1.0 |
| `data/tokens_seen` (end) | ≈ rows × 21k × epochs | 30% off that | 0 |
| `gpu/peak_reserved_gb` | ≤ 85% of the card | 85 – 95% | > 95% |
| `cost/usd_projected` | ≤ $20 | $20 – $35 | > $35 |
| `data/train_rows_over_max_seq_length` | 0 | — | ≥ 1 |
| `eval/best_is_final` | true | false, best checkpoint kept | false, best checkpoint deleted |
| `eval/loss_by_<field>/<value>` | within ±0.15 of `eval/loss` | 0.15 – 0.3 above | > 0.3 above |

---

## quality/ — does it extract clauses the app can use?

**The only metrics on this page about the product rather than the optimiser.**
At the end of each epoch (`tracking.quality_check: epoch`; `end` for once at the
end, `never` to switch off) training pauses, and the model generates the full
reply for the first `tracking.quality_rows` (2) validation rows — greedy, with
the serving prompt and thinking off, like the app's temperature-0 call. Each
reply is then put through the app's own steps 6–7, `parse_reply` and `finalize`
in `preparation/app_request.py`, and compared with the row's labels put through
the same steps. So "labelled" means what the app would keep from the label:
`finalize` drops clauses under 8 words and a repeated `pasal`.

**Cost.** Real H200 time: ~3–6 minutes per row, so ~20–35 minutes (~$2–3) for
2 rows × 3 epochs. The `perf/` panels show it as one slow step after each epoch.
**Safety.** Any error inside it — an out-of-memory included — is printed,
logged as `quality/error = 1`, and training carries on.

**Read it with the eval caveat below:** 2 rows is a spot check, not a score. The
adapter's real score is `test.jsonl`, after training.

### `quality/json_valid`

**What it is.** The share of generated replies the app's parser accepts.
**Healthy** 1.0. **Bad** anything less — the app would have retried, and
failed the document after 4 attempts. Usually the reply was cut off (see
`finished`) or the model wrapped the JSON in something the parser cannot strip.

### `quality/finished`

**What it is.** The share of replies that stopped on their own before
`quality_max_new_tokens` (24,576 — the endpoint's `max_tokens`). **Healthy**
1.0. **Bad** less: the model ran to the limit, which on the endpoint is
`finish_reason: length` — the silent truncation the app treats as an error. If
it stays below 1.0, the model is not learning where to stop: look at the end of
the training answers.

### `quality/clause_recall`

**What it is.** Labelled clauses the model found ÷ labelled clauses. A clause
counts as found when its words overlap a returned clause's words by ≥ 80%
(Jaccard on the app's normalised text), one-to-one, closest pairs first — so a
re-wrapped line or a spacing difference is not a miss.
**Healthy** ≥ 0.9. **Bad** < 0.7: whole sections are being skipped.

### `quality/clause_precision`

**What it is.** Clauses found ÷ clauses the model returned. **Healthy** ≥ 0.9.
**Bad** < 0.7: it returns clauses the labellers did not mark — invented ones, or
fragments split differently from the labels. Check the reply before blaming the
model; sometimes the labels missed one.

### `quality/clause_f1`

The harmonic mean of recall and precision — one number to compare runs by.
**Healthy** ≥ 0.9, **bad** < 0.7.

### `quality/clause_count_ratio`

**What it is.** Clauses returned ÷ clauses labelled. **Healthy** 0.95 – 1.05.
Below 0.8 is clauses missed, above 1.2 is clauses invented or over-split. Cheaper
to read than recall/precision, and the first thing to look at when F1 moves.

### `quality/output_tokens`, `quality/seconds`, `quality/rows`

Mean reply length, total time spent generating, and a table with one line per
generated row (document, valid, finished, labelled, returned, matched, tokens,
seconds). `output_tokens` near `quality_max_new_tokens` is the same warning as
`finished < 1.0`.

---

## eval/ — is the model getting better at the task?

These come from the evaluation pass: every `eval_steps` (10 in the current
config) training pauses and the model runs over `eval.jsonl` — the documents
marked `Split : Validation`, which it never trains on.

**First, a caveat that overrides everything in this section.** With one
validation document (today's build), every eval number is the score of one
contract and swings with that contract's quirks. Trust the eval metrics from
about 5 validation documents (~15–20 rows) up.

### `eval/loss` (from the Trainer)

**What it is.** The average cross-entropy on the validation rows, counted on the
answer tokens only (`train_on_responses_only`). In plain terms: how surprised the
model is by the correct extraction, token by token. 0 would mean it predicts
every token of the expected JSON with certainty.

**Healthy.** Falls steeply in the first epoch, flattens in the second, ends
around **0.15 – 0.45**. Extraction copies clause text out of the document, and
copying is easy to predict, so this task can go lower than free-text tasks do.

**Bad.** Ends above **0.8**; or turns upward for two evals in a row (overfitting
— see `loss_gap`); or is **suspiciously low, under 0.05**. Near-zero eval loss on
a held-out contract usually means it is not held out: the same document, or the
same bank's near-identical terms, sits in both Train and Validation. Splits must
be by document.

**If bad.** Rising: fewer epochs, or use the checkpoint at `eval/best_step`.
High and flat: check `data/answer_fraction` (is the answer actually trained?)
and the dry-run sample in `/workspace/run.log` (is the chat template right?).

### `eval/perplexity`

**What it is.** `exp(eval/loss)` — the same number on a scale people read more
easily: roughly, how many tokens the model is choosing between at each step.
**1.0 is perfect**; 2.0 means it is as unsure as a coin flip between two tokens.

**Healthy** 1.15 – 1.6 at the end. **Bad** above 2.2 at the end, or under 1.05
(the leakage case above). It carries no information `eval/loss` does not — it is
there because "1.3" is easier to reason about than "0.26".

### `eval/best_loss` and `eval/best_step`

**What they are.** The lowest `eval/loss` seen so far, and the step it happened
at. They only ever go down (`best_loss`) and forward (`best_step`); a flat line
means the evals since then were all worse.

**Healthy.** `best_step` keeps moving forward and ends in the **last third** of
the run — the model was still improving when training stopped.

**Warning.** `best_step` stops in the **middle** of the run: the second half made
the model worse on held-out documents. It overfit.

**Bad.** `best_step` is the **first eval**: training never improved on the
validation set. Usually a data or template problem, sometimes a learning rate
too high for the dataset size.

### `eval/loss_gap`

**What it is.** `eval/loss − train/loss`, the latest training loss at the moment
of each eval. How much worse the model does on contracts it has not seen than
on the ones it trains on.

**Healthy.** Between **−0.05 and +0.15**, and roughly flat across evals.

**Bad.** Above **+0.3**, or **growing at every eval** — the classic overfitting
signature: train loss keeps falling, eval loss does not follow. Strongly
negative (below −0.2) means the validation contracts are easier than the
training ones, or there are too few to trust.

**Read the trend, not a point.** The training loss in the subtraction is a single
step of 2 rows, which swings ±0.1 on its own; one eval's gap means little, the
direction over four or five evals means a lot.

### `eval/loss_by_<field>/<value>` and the `eval/rows` table

**What they are.** `eval/loss` split by the `annotation.txt` fields in
`tracking.eval_group_by` (`Produk`, `Kombinasi`) — e.g.
`eval/loss_by_Produk/Mobile_Banking` — and a table of every validation row's
loss with its document, kind (whole document or window), tokens and clause count.
**Free:** they reuse the loss the eval pass computes for each row anyway; they
need `per_device_eval_batch_size: 1` and `build-report.json` on the pod
(`make train-push-data` copies it). The log prints the worst and best row at
each eval, and the run summary keeps `eval/worst_row` and `eval/worst_row_loss`.

**Healthy.** Every group within about ±0.15 of `eval/loss`. **Bad.** One group
more than 0.3 above the rest: the model is weak on that kind of contract (say,
BPD banks, or credit cards) — add training documents of that kind. **One row far
above all others** is more often a labelling problem in that document than a
model problem: open its xlsx before adding data.

Labels are only attached when `build-report.json` has the same number of eval
rows as `eval.jsonl`; a report from another build is ignored (the log says so),
and rows show as `row N`.

### `eval/runtime`, `eval/samples_per_second`, `eval/steps_per_second` (from the Trainer)

**What they are.** How long one eval pass took, and how many validation rows /
batches it got through per second. With `per_device_eval_batch_size: 1` the last
two are the same number.

**Expected.** ~2 minutes per pass with ~30 validation rows; ~0.1–0.15 rows per
second (each row is ~27k tokens). They should be flat across the run. They are
cost, not quality: 24 evals × 2 minutes is ~45 minutes of H200 time, which is
why raising `eval_steps` to 30 is worth considering for a ~240-step run.

---

## train/ — is the optimiser behaving?

### `train/loss` (from the Trainer)

**What it is.** The same cross-entropy as `eval/loss`, on the training batch of
that step (2 rows, answer tokens only). Logged every step, so it is noisy.

**Healthy.** Starts somewhere around 0.6 – 1.2 (the base model already reads
Indonesian contracts; it does not yet know the output notation), falls fast,
ends **0.1 – 0.4**, with small drops at each epoch boundary.

**Bad.** Flat from the start (nothing is learning — check `answer_fraction`);
**NaN** (fp16 on gated-deltanet layers — `train.py` refuses fp16 for that reason,
so a NaN here is new and worth stopping for); sudden spikes that do not recover
(learning rate too high); or **under 0.05** with eval not following, which is
memorisation of the training contracts.

### `train/perplexity`

`exp(train/loss)`. **Healthy** 1.1 – 1.5 at the end. **Warning** under 1.05:
the model is reproducing the training rows almost exactly, which with 3 epochs
over a couple of hundred rows is the start of memorising them. Compare with
`eval/perplexity` — if eval sits well above it, that is `loss_gap` again.

### `train/grad_norm` (from the Trainer)

**What it is.** The size of the gradient at each step, before clipping (the
Trainer clips at 1.0 by default). A proxy for how hard each step pushes the
weights.

**Healthy.** High in the first few steps (1 – 2 is normal while the LoRA
matrices start from zero), then settles to **0.1 – 0.6**.

**Bad.** Stays **above 1.0** for most of the run (every step is being clipped —
the learning rate is too high for this data); **spikes above 10**, or **inf/NaN**
(numerical trouble — stop the run, do not wait for the loss to show it).

### `train/learning_rate` (from the Trainer)

**What it is.** The learning rate at each step. There is no good or bad value,
only the right shape: with `warmup_ratio: 0.1` and `lr_scheduler_type: linear`
it climbs from 0 to `2e-4` over the first 10% of steps, then falls in a straight
line to 0 at the last step. **Bad** is any other shape — flat at 0, or not
reaching the peak — which means the scheduler is not what the config says.

### `train/epoch` (from the Trainer)

Progress in passes over the training data, 0 → 3. Useful as a second x-axis:
overfitting usually shows up once `epoch` passes 2.

---

## perf/ — how fast, and how long?

Computed by `RunMetrics` in `training/scripts/train.py` from wall-clock time
between log lines and the token counts below.

**Two artefacts to ignore in every perf panel.** The first step includes kernel
compilation and is always slow. And every step logged right after an eval
includes the eval pause, so there is a regular dip every `eval_steps` — that is
the eval, not the training slowing down.

### `perf/tokens_per_second`

**What it is.** Training tokens processed per second of wall-clock time — prompt
and answer, everything the forward and backward pass went through. The truest
measure of speed, because rows range from ~8k to 30k tokens and a "step" is not
a fixed amount of work.

**Healthy** ≥ **1,200** tokens/s. **Warning** 500 – 1,200. **Bad** under
**500**: almost certainly the gated-deltanet layers are on the pure-PyTorch
fallback, which is several times slower. Confirm with
`grep -i "fast path" /workspace/run.log`; the fix is `prepare.sh --fast-kernels`
(the Makefile does it on a fresh pod).

### `perf/seconds_per_step`

**What it is.** Wall-clock seconds per optimiser step (2 rows ≈ 42k tokens).

**Healthy** **20 – 40 s**. **Warning** 40 – 90 s. **Bad** over 90 s. Same cause
and fix as `tokens_per_second`, which is the steadier of the two.

### `perf/eta_minutes`

**What it is.** Minutes left at the current pace: steps remaining × seconds per
step. It ignores the remaining eval pauses, so it runs a little optimistic.

**Healthy.** Settles after ~10 steps at **≤ 150 minutes** for a ~240-step run, and
counts down steadily. **Bad.** Over 300, or climbing — the run is getting slower
(another process on the GPU, or memory pressure; check `gpu/`).

---

## data/ — is the data what we think it is?

Counted by the `TokenCounter` wrapper in `train.py` as each training batch is
built; eval batches are not counted.

### `data/tokens_seen`

**What it is.** Running total of training tokens processed (attention-mask
tokens, prompt and answer).

**Healthy.** Climbs steadily and ends near **rows × 21k × epochs** — about
10 million for ~160 rows × 3 epochs.

**Bad.** **Stays at 0**: the counter's hook was bypassed by unsloth's trainer.
The training itself is unaffected; the `perf/tokens_per_second` and `data/`
panels just have nothing to show. Report it, and read speed from
`seconds_per_step`. Far below expectation: rows were dropped or truncated —
check the summary's `data/train_rows`.

### `data/answer_tokens_seen`

**What it is.** Running total of tokens that carry loss — the assistant's
extraction, not the 14k-token system prompt or the document.

**Bad** if it is **0** (nothing is being trained: the response markers did not
match the chat template and every label was masked) or **equal to
`tokens_seen`** (nothing is masked: the model is being trained to recite the
system prompt back, which is waste at best).

### `data/answer_fraction`

**What it is.** `answer_tokens_seen / tokens_seen`: the share of every row that is
the answer.

**Healthy.** **0.15 – 0.40**, steady. The median row is ~21k tokens with ~6k of
answer, so expect around **0.25 – 0.30**.

**Bad.** **0** or **1.0** — the two failures above. **Warning** under 0.05:
answers are being cut off, most likely by truncation (see
`data/train_rows_over_max_seq_length`).

---

## gpu/ — how close to running out of memory?

Read from `torch.cuda` at every log line. The card's total is what `train.py`
prints at startup as `gpu  NVIDIA H200  <N> GB` — use that number for the
percentages below (it reads a little above the 141 GB on the box, because of
GB-vs-GiB units).

### `gpu/mem_allocated_gb`

**What it is.** Memory held by live tensors right now. Its floor is the model:
~53 GB of bf16 weights (vision tower skipped), plus the LoRA weights and their
optimiser state (~1 GB). On top of that, activations rise and fall with each
row's length.

### `gpu/mem_reserved_gb`

**What it is.** Memory the PyTorch allocator is holding, used or not — always ≥
allocated. A large, growing gap between the two is fragmentation;
`PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` (set on the pod) is there to
keep it small.

### `gpu/peak_reserved_gb`

**What it is.** The highest reserved value since the run started. **This is the
one that decides out-of-memory**, because the longest row only has to fit once.

**Healthy.** **≤ 85%** of the card. **Warning** 85 – 95%: a longer row than any
seen so far could tip it over. **Bad** above 95%, or an OOM crash. The order to
reach for (from `training/README.md`): batch 1 (already), keep gradient
checkpointing, lower `max_seq_length`, and only then `load_in_4bit`.

It only goes up, and it gets there early or late depending on when the longest
row comes round — so read it at the end of epoch 1, when every row has been seen.

---

## cost/ — what is this run costing?

`hours since training began × POD_USD_PER_HOUR`. The rate is
`cost.usd_per_hour` in `runpod/pbbi-training/values.yaml` ($5.29 for a Secure
H200 in US-CO-1 as of 2026-10-11), passed to the pod by `pod.py`.

**It undercounts the bill.** The clock starts when training starts. The pod
started billing at `make pod-up` — deps, the model download, the dry run before
it are ~20–40 minutes (~$2–4) not in these numbers, and so is everything after
the run until `make pod-stop pbbi-training`. RunPod's console is the real bill.

### `cost/usd_so_far`

Dollars spent on training so far. A straight line; its slope is the hourly rate.

### `cost/usd_projected`

What training will cost at the current pace: so-far × total steps ÷ steps done.
Unreliable for the first ~10 steps (the slow first step dominates).

**Healthy** ≤ **$20**. **Warning** $20 – $35. **Bad** over **$35**, roughly
twice the estimate: something is slow — check `perf/tokens_per_second` before
paying for the rest.

---

## Run summary — the dataset, and the result

Not charts: single values on the run's Overview page, written at the start and
end of the run.

### Dataset shape

| Key | What it is | Expected |
|---|---|---|
| `data/train_rows`, `data/eval_rows` | rows in each split | ~160 train for ~42 training documents (long ones become several 30k windows) |
| `data/train_tokens_max` | longest row | ≤ 30,000 — `build.py` caps windows there |
| `data/train_tokens_median` | middle row | ~21,000 (14k of it the system prompt) |
| `data/train_tokens_p95` | 95% of rows are shorter | ~29,000 |
| `data/train_tokens_total` | all train tokens, one epoch | ~3.3 M for ~160 rows |

### `data/train_rows_over_max_seq_length`

**The one that must be 0.** A row longer than `max_seq_length` (32,768) is cut
off at the end by the trainer without an error — and the end of a row is the end
of the answer. The model then learns that extractions stop mid-JSON. **Any value
of 1 or more: stop**, rebuild the data with smaller windows or raise
`max_seq_length`. `train.py` also prints this count before training, in
`/workspace/run.log`.

### `eval/best_is_final`, `eval/best_checkpoint`, `eval/best_checkpoint_steps_off`

**What they are.** Whether the best eval happened at the last step; and if not,
the saved checkpoint nearest to the best step **that is still on disk**, and how
many steps away from the best it is.

**Why they matter.** The run pushes the **final** adapter to the Hub, not the
best one. And `save_total_limit: 3` deletes all but the newest three checkpoints
(saved every `save_steps: 20`), so on a ~240-step run only steps 200, 220 and
240 survive.

| Result | Meaning | Action |
|---|---|---|
| `best_is_final: true` | the pushed adapter is the best one | nothing |
| `false`, `steps_off: 0` | the best checkpoint is still on the volume | use `checkpoint-<best_step>` under the run's `adapter_dir/checkpoints/` instead of the pushed one |
| `false`, `steps_off` ≥ `save_steps` | the best checkpoint was deleted | the run cannot give you its best model. Next run: `load_best_model_at_end: true` with `metric_for_best_model: eval_loss` (the Trainer then keeps the best checkpoint out of rotation and ends on it), or fewer epochs |

---

## Run fingerprint — what the run was made from

Not a chart: `fingerprint.*` in the run's **Config** tab, also printed near the
top of `/workspace/run.log`. W&B records the git commit by itself; it cannot
know the data changed between two runs on the same commit. These can.

| Key | What it is |
|---|---|
| `config_file`, `config_sha256` | the training config, and a hash of its exact bytes |
| `data_train_sha256`, `data_eval_sha256` | hashes of the exact `train.jsonl` / `eval.jsonl` trained on |
| `system_prompt_sha256` | hash of `preparation/prompts/extraction_system.md` — the serving contract |
| `build_documents`, `build_<split>_rows`, `build_<split>_dropped` | from `build-report.json`: documents, rows and dropped sections per split |
| `git_commit`, `git_dirty` | the code; `dirty: true` means the pod ran uncommitted changes |

**Use.** Two runs with different results and the same `data_train_sha256`
differ in config or code; different hashes, and `make data` changed what they
trained on. `system_prompt_sha256` must match the prompt the app serves, or
the adapter was trained for a different request than it will get. The model
card on the Hub records the train data hash too.

---

## Check in the first run: what trl may add by itself

The pinned trl (0.18.2 – 0.24.0) may log `train/mean_token_accuracy` and
`train/num_tokens` on its own, if Unsloth's patched trainer keeps them. They are
not added here — on the eval pass, token accuracy needs the full vocabulary
logits, ~26 GB per 27k-token row. If they appear, they are free; read
`mean_token_accuracy` as "share of answer tokens predicted exactly", healthy
above ~0.9 by the end.

---

## Reading a run in five minutes

1. **Step 1 – 10:** `perf/tokens_per_second` ≥ 1,200 and `data/answer_fraction`
   between 0.15 and 0.40. If not, stop now — everything after is wasted money.
2. **End of epoch 1:** `gpu/peak_reserved_gb` ≤ 85% of the card, and
   `cost/usd_projected` within budget.
3. **Every eval:** `eval/loss` falling, `eval/loss_gap` not growing.
4. **End of each epoch:** `quality/finished` and `quality/json_valid` at 1.0,
   `quality/clause_f1` rising — the check that the loss is buying a better
   extractor.
5. **End:** `data/train_rows_over_max_seq_length` = 0, then `eval/best_is_final`.
6. **Then remember:** a good `eval/loss` is not a good extractor. The adapter is
   a candidate until it is scored on `test.jsonl` against the labels.
