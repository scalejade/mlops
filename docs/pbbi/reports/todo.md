# TODO — training report: v0.1.3 vs gpt-4.1-mini

Notes for writing the training report. Each fact below links to its source, so a number can be checked before it goes in. Tick items off as they are written.

## Outline

- [ ] 1. Summary: one paragraph and the headline table (§ Headline numbers)
- [ ] 2. The task: what extraction is, and why recall matters most
- [ ] 3. The data: 60 contracts, the splits, the products and penyelenggara types
- [ ] 4. The model and training setup: base model, LoRA, hyperparameters, hardware
- [ ] 5. How training went: the lr 2e-4 run that overfit, the retrain, the v0.1.3 data change, eval-loss curves
- [ ] 6. The comparison method: same request, same scoring, temperature 0
- [ ] 7. Results vs gpt-4.1-mini: overall, per contract, by product, penyelenggara and length
- [ ] 8. Error analysis: what each model gets wrong, with examples from the xlsx
- [ ] 9. Cost and time
- [ ] 10. Limitations
- [ ] 11. Recommendations / next steps

## Headline numbers (17 test contracts, both models at temperature 0)

Source: [pbbi-extraction-eval-v0.1.3-vs-gpt-4.1-mini.md](pbbi-extraction-eval-v0.1.3-vs-gpt-4.1-mini.md)

| | **v0.1.3** | gpt-4.1-mini |
|---|---|---|
| Recall | **0.658** (1,365 / 2,074) | 0.283 (587 / 2,074) |
| Precision | **0.784** (1,365 / 1,741) | 0.632 (587 / 929) |
| **F1** | **0.716** | 0.391 |
| Clauses returned ÷ labelled | 0.84 | 0.45 |
| Higher F1 on | 13 of 17 (2 ties) | 2 |
| Recall on contracts with 200+ clauses | **0.635** | 0.200 |

- [ ] Mention gpt-4.1-mini at its **default temperature 1.0**: F1 **0.470** (recall 0.349, precision 0.720), from the [v0.1.2 report](pbbi-extraction-eval-v0.1.2-vs-gpt-4.1-mini.md). It is gpt-4.1-mini's best result, and v0.1.3 still leads by about 0.25 F1.

## 3. Data — facts to use

Sources: commit `d8b2658`; [v0.1.3 report § What changed](pbbi-extraction-eval-v0.1.3.md); the mainsheet *PB Mainsheet (new).xlsx* (Role column).

- [ ] 60 contracts labelled by Legal, each with 4 columns (No, No. Pasal, Topik Klausa, Bunyi Klausa) and one row per whole document.
- [ ] Splits for v0.1.3: **39 train (4,381 clauses) / 4 validation (435) / 17 test (2,074)**.
  - 8 contracts moved from validation to train for v0.1.3: ACEH MB, BCA IB, BCA MB, CIMB KK, JATENG MB, JTRUST MB&IB, STANCHART KK, UOB IB.
  - Validation kept: BNI MB, CIMB KD, JAMBI KD, OVO.
- [ ] Split rule: every penyelenggara + product combination has at least one training contract. 4 documents were moved to get there (CIMB UE, OCBC KD, MANDIRI KD to train; BRI UE Chip to test), and the mainsheet was updated.
- [ ] Rows: one row per whole document, never windowed. The longest training row is 89,298 tokens (UOB Mobile Banking).
- [ ] The text goes through the app's own PDF pipeline (`pdftotext -layout` → `keepIndonesianOnly`), so training sees exactly what the app sends.
- [ ] TODO: table of contracts per product × split (`preparation/data/build-report.json`, or the mainsheet).

## 4. Model and training setup

Source: [training/configs/pbbi-extraction.yaml](../../../training/configs/pbbi-extraction.yaml), as of commit `d8b2658`.

| Setting | Value |
|---|---|
| Base model | `scalejade/qwen-sea-lion-v4.5-27b-pbbi` @ `8d32a4b9`, a copy of Qwen-SEA-LION-v4.5-27B-IT (Qwen3.5 hybrid: 48 linear-attention + 16 full-attention layers) |
| Method | LoRA r=16, alpha 16, dropout 0, bf16 (no 4-bit); 79.7M trainable parameters (0.30%) |
| Target modules | q, k, v, o, gate, up, down projections (the linear-attention projections are **not** adapted) |
| Context | `max_seq_length` 98,304 |
| Optimiser | AdamW (fused), lr **5e-5**, linear decay, warmup 10%, weight decay 0.01 |
| Batch | 1 per device × 2 accumulation = 2 contracts per step |
| Length | 2 epochs = **40 steps**; eval + save every 4 steps |
| Checkpoint | `load_best`: the lowest eval loss is pushed, not the last step |
| Loss | assistant turn only (`train_on_responses_only`) |
| Hardware | 1 × H200 (141 GB), RunPod; peak VRAM ~103 GB on the 89k-token row |
| Stack | Unsloth 2026.10.6, transformers 5.5.0, trl 0.24.0, torch 2.8.0+cu128, flash-linear-attention 0.4.2, `UNSLOTH_EXPERIMENTAL_HYBRID_PACKING=0` |
| Result | `scalejade/pbbi-clause-extraction-lora` tag **v0.1.3** (commit `63773a48`), also tagged **`stable`** |

## 5. How training went — the story

- [ ] **v0.1.0 → v0.1.1**: early demos on 1–3 rows of GoPay. v0.1.1 put section headings into `clause_text` (326 of 345 clauses on OVO). Source: [evaluation.md](../evaluation.md).
- [ ] **First full-data run, lr 2e-4: overfit within epoch 1.** Training loss went 0.07 → 0.00001 by step 11, eval loss went 0.165 (step 8) → **0.232** (step 16). Stopped, nothing pushed. W&B `lsjscwzy`.
- [ ] **Retrain at lr 5e-5 → v0.1.2**: eval loss 0.209 → 0.176 → 0.161 → 0.158 → **0.1576 (step 20, best)** → then flat or slightly rising. W&B `u4sxibof`.
- [ ] **v0.1.3**: same settings, 8 more training contracts. Eval loss 0.326 → … → **0.2436 at step 20 (best)** → 0.2472 at step 40. *It can't be compared with v0.1.2's ~0.158: the validation set is different (4 contracts, including JAMBI at ~0.65).*
- [ ] Lesson: **the best checkpoint was step 20, about 1 epoch, in both v0.1.2 and v0.1.3.** The second epoch only fits the training rows.
- [ ] TODO: **find v0.1.3's W&B run link.** Project: https://forge.coreweave.com/wandb/www-scalejade-com/scalejade-mlops, run name `pbbi-clause-extraction-lora-v0.1.0`, 2026-10-17 ~10:20–11:30 UTC.
- [ ] Figure: eval-loss curves for lr 2e-4 vs lr 5e-5 (v0.1.2), and for v0.1.3, exported from W&B.
- [ ] Figure: train loss vs eval loss for the lr 2e-4 run, showing the overfitting.

## 6. Comparison method

Source: [pbbi-extraction-eval-v0.1.3-vs-gpt-4.1-mini.md § How the test was run](pbbi-extraction-eval-v0.1.3-vs-gpt-4.1-mini.md).

- [ ] **Same request** for both models: the app's exact call (`extraction_system.md`, then `"DOCUMENT:\n"` + the PDF text, `response_format: json_object`) plus `temperature: 0`.
  - Output limit: 65,536 tokens for v0.1.3, 32,768 for gpt-4.1-mini (its API maximum). No gpt-4.1-mini reply came near its limit.
- [ ] **Same scoring**: each reply goes through the app's own `parse_reply` and `finalize`. A clause counts as found when it shares at least 80% of its words with a labelled clause, matched one to one. Legal's labels scored against themselves get 100%.
- [ ] Engines: v0.1.3 on vLLM 0.30 (the production engine), 1 × H200. gpt-4.1-mini on the OpenAI API.
- [ ] Explain recall, precision and F1 in plain words. Recall matters most: a clause that isn't extracted is never reviewed for compliance.

## 7–8. Results and error analysis — what to say

- [ ] Per-contract table, plus by product, penyelenggara and length: copy from the [v0.1.3 vs gpt-4.1-mini report](pbbi-extraction-eval-v0.1.3-vs-gpt-4.1-mini.md).
- [ ] **gpt-4.1-mini returns under half of the clauses (0.45×)** and gives up on long contracts: BJB 4/110, SINARMAS 4/49, OCBC KK 19/233, SEABANK 42/358. All its replies ended normally (`stop`), so the limit isn't the cause: it merges sub-clauses and stops early.
- [ ] **v0.1.3 keeps Legal's level of detail** (0.84×) and is near-perfect on short contracts (recall 0.80 under 100 clauses).
- [ ] **v0.1.3's misses are about where clauses are split, not lost content**: only 60 of 2,074 labelled clauses (2.9%) are truly absent from its output. Source: [v0.1.3 report](pbbi-extraction-eval-v0.1.3.md).
- [ ] **Where gpt-4.1-mini wins**: OCBC Internet Banking (0.458 vs 0.356). Legal groups its definitions into ranges, and v0.1.3 gives one clause per term. In the training labels, 13 contracts use ranges and 11 use one clause per term, so the labels are inconsistent.
- [ ] TODO: pick **2–3 concrete examples** from the xlsx sheet *Perbandingan klausa* (gitignored, local only). Suggested:
  - one contract where gpt-4.1-mini stops early (BJB or SEABANK);
  - OCBC Internet Banking definitions (range vs per-term);
  - one long contract where v0.1.3 merges sub-clauses.
  ⚠️ The xlsx quotes the contracts. Paraphrase, or check with Legal before quoting clause text in the report.

## 9. Cost and time

| Item | Value | Source |
|---|---|---|
| v0.1.3 training | ~1 h 10 min on 1 × H200, ≈ **$6.50** | v0.1.3 report |
| v0.1.2 day (setup, memory test, stopped 2e-4 run, retrain) | ~1 h 23 min, ≈ $7.30 | this session |
| Test run, v0.1.3, 17 contracts | ≈ **$2** (H200 pod ~25 min incl. load), ≈ $0.12 per contract | reports |
| Test run, gpt-4.1-mini, 17 contracts | ≈ **$0.45**, ≈ $0.03 per contract | this session |
| Longest contract | v0.1.3 15.8 min (8 at a time) vs gpt-4.1-mini 2.8 min | reports |
| GPU price | H200 $5.29/hr; RTX PRO 6000 $2.49/hr (~2.5× slower to generate) | RunPod |

- [ ] Note: **v0.1.3 is slower per contract** (~40 tok/s per reply on an H200, against ~170 for gpt-4.1-mini). That is the trade-off for accuracy, and it can be improved (speculative decoding, FP8, splitting by section).
- [ ] Note: **v0.1.3 can be self-hosted.** Contracts don't leave our infrastructure, which matters for Bank Indonesia data.

## 10. Limitations

- [ ] Only 17 test contracts; several products have only 1–2. Group-level results are indicative.
- [ ] One labeller's conventions. Label inconsistency (the definitions) caps the achievable F1.
- [ ] The match threshold (≥ 0.8 word overlap) is strict about splitting. Report the lenient recall too: 0.708 for v0.1.3.
- [ ] gpt-4.1-mini isn't fine-tuned and gets the same prompt. A fine-tuned or few-shot GPT wasn't tested.
- [ ] The app still **doesn't send `temperature`**, so production samples at 1.0 (+0.013 F1 for v0.1.2 at temperature 0).

## 11. Recommendations

Source: the recommendations in [the v0.1.3 report](pbbi-extraction-eval-v0.1.3.md) and [the v0.1.2 report](pbbi-extraction-eval-v0.1.2-vs-gpt-4.1-mini.md).

- [ ] Send `temperature: 0` in the app's request.
- [ ] One labelling rule for definitions and sub-clauses, agreed with Legal (the biggest single lever).
- [ ] Validate more contracts, especially Uang Elektronik, Payment Gateway and Multinational (~40 are at *Done Extraction* or *Ongoing Validation* in the mainsheet).
- [ ] Train for 1 epoch (step 20 was the best both times).
- [ ] Add the linear-attention projections to the LoRA, after checking that vLLM can serve them.
- [ ] Check JAMBI Kartu Debit's labels (the worst validation contract in every run).
- [ ] Deploy v0.1.3: recreate `pbbi-volumes`, run `make volume-fill`, then apply `pbbi-serverless-extraction`. The volume and pods were deleted on 2026-10-17.

## Files to attach or reference

| File | Notes |
|---|---|
| [pbbi-extraction-eval-v0.1.3-vs-gpt-4.1-mini.md / .pdf / .csv](pbbi-extraction-eval-v0.1.3-vs-gpt-4.1-mini.md) | The main comparison (scores only) |
| `pbbi-extraction-clauses-v0.1.3-vs-gpt-4.1-mini.xlsx` | Clause-by-clause output. **Local only, gitignored: it quotes the contracts** |
| [pbbi-extraction-eval-v0.1.3.md](pbbi-extraction-eval-v0.1.3.md) | v0.1.3 vs v0.1.2, the training details and the eval-loss table |
| [pbbi-extraction-eval-v0.1.2-vs-gpt-4.1-mini.md](pbbi-extraction-eval-v0.1.2-vs-gpt-4.1-mini.md) | The first comparison; gpt-4.1-mini at temperature 1.0 |
| [evaluation.md](../evaluation.md) | Method, plus every adapter's history |
| W&B project | https://forge.coreweave.com/wandb/www-scalejade-com/scalejade-mlops |
| Hub | `scalejade/pbbi-clause-extraction-lora` (tags v0.1.0–v0.1.3, `stable`) |
