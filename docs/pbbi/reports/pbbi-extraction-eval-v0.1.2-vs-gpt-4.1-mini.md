# PBBI clause extraction — fine-tuned v0.1.2 vs gpt-4.1-mini

**Test set:** 17 Perjanjian Baku contracts never used in training · **Date:** 2026-10-17

## Summary

The fine-tuned model **v0.1.2** finds **almost twice as many** of Legal's clauses as **gpt-4.1-mini**, at the same precision: **F1 0.696 vs 0.470**. It has the higher F1 on 15 of the 17 contracts and ties on 1. gpt-4.1-mini wins on one contract, OCBC Internet Banking.

v0.1.2's misses are mostly **where clauses are split**, not lost content. Only **3.1%** of Legal's clauses are truly absent from its output. The rest are present but grouped differently from the labels. Two of the causes can be fixed **without new training**. They are covered under Recommendations.

| | **v0.1.2** (fine-tuned Qwen-SEA-LION 27B + LoRA) | gpt-4.1-mini |
|---|---|---|
| **Recall**: Legal's clauses found | **0.659** | 0.349 |
| **Precision**: returned clauses that are right | **0.739** | 0.720 |
| **F1** | **0.696** | 0.470 |
| Clauses returned ÷ labelled | **0.89** | 0.48 |
| Valid JSON / finished on its own | 17/17 / 17/17 | 17/17 / 17/17 |
| Higher F1 on | **15** contracts | 1 (plus 1 tie) |
| Cost of this run | ~$2.10 (H200 pod, 23.6 min), ≈ $0.12 per contract | ~$0.50, ≈ $0.03 per contract |
| Time for the longest contract | 15.6 min | 2.8 min |

On the 14 contracts whose answers fit gpt-4.1-mini's 32,768-token output cap, the result is the same: v0.1.2 F1 **0.695** vs **0.518**.

## How the test was run

- **Models.** v0.1.2 is `scalejade/pbbi-clause-extraction-lora` at tag `v0.1.2` (revision `03f30a73`). It is the best checkpoint by eval loss (step 20), trained on 31 contracts at learning rate 5e-5. It ran on vLLM 0.30, the same engine as the production endpoint, on one H200. gpt-4.1-mini ran on the OpenAI API.
- **Same request for both.** Each model got the app's exact extraction call: `extraction_system.md` byte for byte, then `"DOCUMENT:\n"` + the PDF text produced by the app's pipeline, with `response_format: json_object` and **no temperature**, as the app sends it.
  - Output limit: v0.1.2 got the app's 65,536 tokens. gpt-4.1-mini got 32,768, its API maximum.
- **Same scoring for both.** Each reply goes through the app's own `parse_reply` and `finalize`. A clause counts as found when it shares at least 80% of its words with a labelled clause, matched one to one. Legal's labels scored against themselves get 100%, which confirms the scorer works.
- **Data.** These are the 17 `Split: Test` contracts from the mainsheet, 2,074 labelled clauses in total. None of them was used in training or for selecting the checkpoint.

## Results per contract

| Contract | Penyelenggara | Labelled | v0.1.2 found / returned | **v0.1.2 F1** | mini found / returned | **mini F1** |
|---|---|---|---|---|---|---|
| JATENG Kartu Debit | Utama / BPD | 15 | 15 / 15 | **1.000** | 15 / 15 | **1.000** |
| MUAMALAT Internet Banking | Utama / Swasta Nasional | 46 | 46 / 46 | **1.000** | 32 / 35 | 0.790 |
| BCA Kartu Debit | Utama / Swasta Nasional | 87 | 80 / 81 | **0.952** | 79 / 80 | 0.946 |
| NAGARI Mobile Banking | BPD | 44 | 41 / 45 | **0.921** | 29 / 33 | 0.753 |
| SINARMAS UE Server-Based | Utama / Swasta Nasional | 49 | 44 / 49 | **0.898** | 4 / 14 | 0.127 |
| MANDIRI Mobile Banking | Utama / BUMN | 98 | 88 / 101 | **0.884** | 32 / 41 | 0.460 |
| BRI UE Chip-Based | Utama / BUMN | 27 | 25 / 33 | **0.833** | 17 / 26 | 0.642 |
| SULTRA Kartu Debit | BPD | 18 | 15 / 18 | **0.833** | 14 / 16 | 0.824 |
| SEABANK Mobile Banking | Utama / Swasta Nasional | 358 | 247 / 290 | **0.762** | 42 / 66 | 0.198 |
| SHOPEEPAY UE Server-Based | Utama / LSB | 211 | 150 / 202 | **0.726** | 58 / 85 | 0.392 |
| SMBC Kartu Kredit | Utama / Swasta Nasional | 172 | 132 / 203 | **0.704** | 84 / 100 | 0.618 |
| OCBC Kartu Kredit | Utama / Multinational | 233 | 140 / 189 | **0.664** | 17 / 42 | 0.124 |
| BJB Mobile Banking | Utama / BPD | 110 | 86 / 175 | **0.604** | 4 / 19 | 0.062 |
| OY Payment Gateway | Swasta Nasional | 89 | 43 / 57 | **0.589** | 20 / 32 | 0.331 |
| DBS Mobile Banking | Utama / Multinational | 262 | 130 / 185 | **0.582** | 130 / 190 | 0.575 |
| BOC Mobile & Internet Banking | Utama / Multinational | 79 | 31 / 45 | **0.500** | 13 / 28 | 0.243 |
| OCBC Internet Banking | Utama / Multinational | 176 | 53 / 115 | 0.364 | 134 / 183 | **0.747** |
| **All 17** | | **2,074** | **1,366 / 1,849** | **0.696** | **724 / 1,005** | **0.470** |

### By product

| Product | Contracts | v0.1.2 F1 | gpt-4.1-mini F1 |
|---|---|---|---|
| Kartu Debit | 3 | **0.940** | 0.935 |
| Uang Elektronik Chip-Based | 1 | **0.833** | 0.642 |
| Uang Elektronik Server-Based | 2 | **0.759** | 0.345 |
| Mobile Banking | 5 | **0.710** | 0.388 |
| Kartu Kredit | 2 | **0.683** | 0.369 |
| Payment Gateway | 1 | **0.589** | 0.331 |
| Internet Banking | 2 | 0.517 | **0.755** |
| Mobile Banking & Internet Banking | 1 | **0.500** | 0.243 |

### By penyelenggara

| Penyelenggara | Contracts | v0.1.2 F1 | gpt-4.1-mini F1 |
|---|---|---|---|
| BPD | 2 | **0.896** | 0.775 |
| Utama / BUMN | 2 | **0.873** | 0.510 |
| Utama / Swasta Nasional | 5 | **0.795** | 0.479 |
| Utama / LSB | 1 | **0.726** | 0.392 |
| Utama / BPD | 2 | **0.641** | 0.239 |
| Swasta Nasional | 1 | **0.589** | 0.331 |
| Utama / Multinational | 4 | **0.551** | 0.493 |

### By contract length

| Labelled clauses | Contracts | v0.1.2 recall | gpt-4.1-mini recall |
|---|---|---|---|
| under 100 | 10 | **0.775** | 0.462 |
| 100–199 | 3 | **0.592** | 0.485 |
| 200 or more | 4 | **0.627** | 0.232 |

## What is behind the errors

1. **gpt-4.1-mini returns half the clauses and sometimes gives up.**
   - Overall it returns 0.48× as many clauses as Legal labelled.
   - On several contracts it stops very early: BJB (4 of 110 found), SINARMAS (4 of 49), OCBC Kartu Kredit (17 of 233), SEABANK (42 of 358). Each of these replies ended normally, so the output cap is not the cause.
   - gpt-4.1 behaved the same way on BJB, on a run that was stopped part-way.
2. **v0.1.2 has the content, but splits it differently.**
   - Only **64 of 2,074** labelled clauses (3.1%) have no clause in v0.1.2's output that covers at least 60% of their words.
   - With a lenient match (at least 90% of the Excel clause's words appear inside one model clause), recall is **0.708**, against **0.659** under the strict match.
   - **230** of v0.1.2's clauses each contain two or more of Legal's clauses: it merged sub-clauses. Most come from the long contracts: SEABANK 66, SHOPEEPAY 43, DBS 28, OCBC Internet Banking 18, OCBC Kartu Kredit 17.
   - On BJB it does the opposite and **splits too finely**: 175 clauses returned against 110 labelled.
3. **The labels group definitions in two different ways.**
   - Some contracts group definitions into ranges (`DEFINISI|3-6`) and repeat the opening sentence. Others give one clause per term.
   - Across the 31 **training** contracts the split is **13 ranges vs 11 per-term**, so the model learned no single rule.
   - OCBC Internet Banking is the clearest case. Legal grouped its definitions (`1. UMUM|A. Definisi|3-6`, `|8-12`). v0.1.2 gave one clause per term (`…|Definisi|41`, `|42`, …), and this explains most of that contract's low score.
4. **The model generated at random, not deterministically.**
   - The base model's `generation_config.json` sets `do_sample: true, temperature: 1.0, top_k: 20, top_p: 0.95`.
   - The app sends no `temperature`, so vLLM applied those defaults, both in this test and in production.
   - The extraction is therefore **sampled at temperature 1.0**. Two runs on the same contract can split clauses differently, and copying can drift.
5. **Long contracts are harder.** Recall drops from 0.78 on contracts with fewer than 100 clauses to about 0.6 on longer ones, where most of the merging happens.
6. **The heading-prefix problem from v0.1.1 is fixed.**
   - On OVO, v0.1.1 put the section heading in front of 326 of 345 clauses.
   - v0.1.2 does this in only 17 of 1,849 clauses.

## Recommendations to improve F1

Ordered by expected payoff for the effort. The F1 effects are **estimates to be confirmed by re-running this test**; only the measured numbers above are facts.

| # | Change | Effort | Expected effect |
|---|---|---|---|
| 1 | **Generate deterministically**: send `temperature: 0` in the app's request, or have vLLM ignore the model's sampling defaults | Very low, no retraining | Steadier splitting and exact copying. Measure first: re-score v0.1.2 at temperature 0 on the same 17 contracts (~$2). |
| 2 | **One labelling rule for definitions and sub-clauses**: Legal picks either ranges or one clause per term, and the existing labels are made consistent | Medium, Legal time | The largest single source of segmentation errors; it explains most of OCBC Internet Banking, and the model can't learn a rule its training data contradicts. |
| 3 | **More training contracts**: the mainsheet has about 40 contracts at *Done Extraction* or *Ongoing Validation*; validate them | Medium to high, Legal time | Roughly doubles the training data. Prioritise long Mobile Banking and Kartu Kredit, Multinational banks, bilingual documents and Payment Gateway, where F1 is lowest. |
| 4 | **Train the linear-attention layers too**: add `linear_attn.in_proj_qkv`, `in_proj_z` and `out_proj` to `target_modules`, and consider rank 32 | Low, ~$5 per run | 48 of the model's 64 layers currently have only their MLP adapted. Check first that vLLM can serve LoRA on those modules. |
| 5 | **Add section-length training rows** alongside the whole-document rows | Low (`build.py` already makes windows) | Several times more examples of splitting inside long contracts, where most of the merging happens. Keep the whole-document rows so the model still sees full calls. |
| 6 | **Train for 1 epoch**, keep `lr 5e-5` and `load_best` | Very low | Eval loss was flat after step 16 (0.1577 → 0.1576 → 0.1581). Saves ~40% of GPU time with no loss in quality. |
| 7 | **Check the labels of the outliers** with Legal: JAMBI Kartu Debit (the worst validation document, loss 0.65) and BJB (175 clauses returned vs 110 labelled) | Low | Rules out label or text-extraction problems before they're treated as model errors. |
| 8 | **Make this test the release gate**: run it for every new version, and also run the base model once, to measure how much the fine-tuning adds | Low, ~$2 per run | Lets each change above be confirmed or rejected by this test. |

**Suggested order:** do 1 and 8 now, since they're cheap and give a clean baseline. Then 2 and 7 with Legal. Then retrain once with 3–6 together, and re-run this test.

## Caveats

- **The test set is 17 contracts**, and several products or penyelenggara types have only one test contract. Small differences between groups are within run-to-run noise.
- **Both models sampled at temperature 1.0**, the API and model defaults, because the app sends no temperature. A second run would give somewhat different numbers.
- **The match threshold** (≥ 0.8 word overlap) is strict about splitting. The lenient match above shows how much of the gap is splitting style rather than missing content.
- **gpt-4.1-mini's output limit** was 32,768 tokens against 65,536 for v0.1.2. All of its replies finished well under the limit, so the difference didn't affect its score.

## Files

- `docs/pbbi/reports/pbbi-extraction-eval-v0.1.2-vs-gpt-4.1-mini.{md,csv,pdf}`: this report, plus the per-contract numbers. Scores and bank names only, no contract text.
- `preparation/data/scores/test-v0.1.2/` and `preparation/data/scores/test-gpt-4.1-mini/`: `report.json` and every raw reply. These are gitignored, because the replies quote the client contracts. Re-run with `make evaluate` (see [evaluation.md](../evaluation.md)).
