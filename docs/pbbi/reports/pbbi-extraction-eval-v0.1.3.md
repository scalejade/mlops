# PBBI clause extraction — v0.1.3 vs v0.1.2

**Test set:** the same 17 Perjanjian Baku contracts as the v0.1.2 report, never used in training · **Date:** 2026-10-17 · **Release:** v0.1.3 is tagged `stable`

## Summary

**v0.1.3** reaches **F1 0.716** on the 17 test contracts, against **0.709** for v0.1.2 under the same conditions. It is at least as good as v0.1.2, so it passes the release gate and is now the stable release. The gain is small, however, and most of it comes from one contract (DBS Mobile Banking). It should not be presented as a clear improvement.

v0.1.3 differs from v0.1.2 in one thing only: **8 contracts moved from the validation split to training** (31 → 39 training contracts, +37% labelled clauses). The hyperparameters are unchanged. This report also measures the first recommendation of the v0.1.2 report: **requesting `temperature: 0`**. On its own that moved v0.1.2 from 0.696 to 0.709.

| | v0.1.2, app default (temperature 1.0) | v0.1.2, temperature 0 | **v0.1.3, temperature 0** |
|---|---|---|---|
| **Recall**: Legal's clauses found | 0.659 | 0.645 | **0.658** |
| **Precision**: returned clauses that are right | 0.739 | **0.789** | 0.784 |
| **F1** | 0.696 | 0.709 | **0.716** |
| Lenient recall (≥ 90% of a clause's words inside one returned clause) | 0.714 | 0.692 | 0.708 |
| Clauses returned ÷ labelled | 0.89 | 0.82 | 0.84 |
| Labelled clauses truly absent (< 60% of words anywhere) | 64 (3.1%) | 58 (2.8%) | 60 (2.9%) |
| Returned clauses that merge 2+ labelled clauses | 230 | 210 | 227 |
| Valid JSON / finished on its own | 17/17 / 17/17 | 17/17 / 17/17 | 17/17 / 17/17 |
| Time for the longest contract | 15.6 min | 15.3 min | 15.8 min |

Against v0.1.2 at temperature 0, v0.1.3 has the higher F1 on **2** contracts, the lower F1 on **6**, and the same on **9**. For reference, gpt-4.1-mini scored F1 0.470 on the same contracts (v0.1.2 report).

## What changed in v0.1.3

- **Data.** The validation split was only used to compute eval loss and pick the checkpoint, so 8 of its 12 contracts moved to training. The test split was not touched: `test.jsonl` is byte-identical to the one the v0.1.2 report used, so the numbers here compare directly.

| Split | v0.1.2 | v0.1.3 |
|---|---|---|
| Train | 31 contracts, 3,206 clauses | **39 contracts, 4,381 clauses** |
| Validation | 12 contracts, 1,610 clauses | **4 contracts, 435 clauses** |
| Test | 17 contracts, 2,074 clauses | 17 contracts, 2,074 clauses (unchanged) |

- **Moved to training:** ACEH Mobile Banking, BCA Internet Banking, BCA Mobile Banking, CIMB Kartu Kredit, JATENG Mobile Banking, JTRUST Mobile & Internet Banking, STANCHART Kartu Kredit, UOB Internet Banking. These were chosen because they are the product types and penyelenggara with the lowest test F1: long Mobile Banking, Kartu Kredit, Internet Banking, Multinational.
- **Kept for validation:** BNI Mobile Banking, CIMB Kartu Debit, JAMBI Kartu Debit (labels under review, so better not trained on) and OVO (the reference eval contract since v0.1.0).
- **Training.** The same configuration as v0.1.2: LoRA r=16 on the same base, learning rate 5e-5, 2 epochs (40 steps), and the checkpoint with the lowest eval loss is the one pushed.

| Step | 4 | 8 | 12 | 16 | **20** | 24 | 28 | 32 | 36 | 40 |
|---|---|---|---|---|---|---|---|---|---|---|
| Eval loss | 0.326 | 0.280 | 0.252 | 0.245 | **0.2436** | 0.2443 | 0.2451 | 0.2464 | 0.2469 | 0.2472 |

- **Best checkpoint: step 20,** about one epoch, as for v0.1.2. Eval loss then rose slowly while training loss fell to about 0.0001, so the second epoch only fitted the training rows.
- These eval losses cannot be compared with v0.1.2's (~0.158), because the validation set is different. JAMBI alone sits at ~0.65.

## Results per contract

| Contract | Penyelenggara | Labelled | v0.1.2 (t=0) found / returned | **v0.1.2 F1** | v0.1.3 found / returned | **v0.1.3 F1** | Change |
|---|---|---|---|---|---|---|---|
| DBS Mobile Banking | Utama / Multinational | 262 | 129 / 165 | 0.604 | 168 / 207 | **0.716** | **+0.112** |
| BJB Mobile Banking | Utama / BPD | 110 | 57 / 96 | 0.553 | 69 / 116 | **0.611** | **+0.057** |
| JATENG Kartu Debit | Utama / BPD | 15 | 15 / 15 | 1.000 | 15 / 15 | 1.000 | 0 |
| MUAMALAT Internet Banking | Utama / Swasta Nasional | 46 | 46 / 46 | 1.000 | 46 / 46 | 1.000 | 0 |
| BCA Kartu Debit | Utama / Swasta Nasional | 87 | 79 / 80 | 0.946 | 79 / 80 | 0.946 | 0 |
| SINARMAS UE Server-Based | Utama / Swasta Nasional | 49 | 44 / 49 | 0.898 | 44 / 49 | 0.898 | 0 |
| MANDIRI Mobile Banking | Utama / BUMN | 98 | 88 / 102 | 0.880 | 88 / 102 | 0.880 | 0 |
| SULTRA Kartu Debit | BPD | 18 | 15 / 18 | 0.833 | 15 / 18 | 0.833 | 0 |
| SEABANK Mobile Banking | Utama / Swasta Nasional | 358 | 247 / 290 | 0.762 | 247 / 290 | 0.762 | 0 |
| SMBC Kartu Kredit | Utama / Swasta Nasional | 172 | 127 / 197 | 0.688 | 127 / 197 | 0.688 | 0 |
| OCBC Kartu Kredit | Utama / Multinational | 233 | 131 / 154 | 0.677 | 131 / 154 | 0.677 | 0 |
| OCBC Internet Banking | Utama / Multinational | 176 | 53 / 115 | 0.364 | 52 / 116 | 0.356 | −0.008 |
| BRI UE Chip-Based | Utama / BUMN | 27 | 25 / 32 | 0.847 | 25 / 33 | 0.833 | −0.014 |
| OY Payment Gateway | Swasta Nasional | 89 | 71 / 90 | 0.793 | 67 / 86 | 0.766 | −0.028 |
| SHOPEEPAY UE Server-Based | Utama / LSB | 211 | 141 / 158 | 0.764 | 130 / 147 | 0.726 | −0.038 |
| NAGARI Mobile Banking | BPD | 44 | 39 / 44 | 0.886 | 37 / 44 | 0.841 | −0.045 |
| BOC Mobile & Internet Banking | Utama / Multinational | 79 | 30 / 44 | 0.488 | 25 / 41 | 0.417 | −0.071 |
| **All 17** | | **2,074** | **1,337 / 1,695** | **0.709** | **1,365 / 1,741** | **0.716** | **+0.007** |

### By product

| Product | Contracts | v0.1.2 F1 (t=0) | v0.1.3 F1 |
|---|---|---|---|
| Kartu Debit | 3 | 0.936 | 0.936 |
| Uang Elektronik Chip-Based | 1 | **0.847** | 0.833 |
| Payment Gateway | 1 | **0.793** | 0.766 |
| Uang Elektronik Server-Based | 2 | **0.792** | 0.763 |
| Mobile Banking | 5 | 0.714 | **0.747** |
| Kartu Kredit | 2 | 0.683 | 0.683 |
| Internet Banking | 2 | **0.517** | 0.510 |
| Mobile Banking & Internet Banking | 1 | **0.488** | 0.417 |

### By penyelenggara

| Penyelenggara | Contracts | v0.1.2 F1 (t=0) | v0.1.3 F1 |
|---|---|---|---|
| Utama / BUMN | 2 | **0.873** | 0.869 |
| BPD | 2 | **0.871** | 0.839 |
| Utama / Swasta Nasional | 5 | 0.790 | 0.790 |
| Swasta Nasional | 1 | **0.793** | 0.766 |
| Utama / LSB | 1 | **0.764** | 0.726 |
| Utama / BPD | 2 | 0.610 | **0.656** |
| Utama / Multinational | 4 | 0.559 | **0.593** |

### By contract length

| Labelled clauses | Contracts | v0.1.2 F1 (t=0) | v0.1.3 F1 |
|---|---|---|---|
| under 100 | 10 | **0.843** | 0.827 |
| 100–199 | 3 | 0.547 | **0.559** |
| 200 or more | 4 | 0.708 | **0.726** |

## What the results show

1. **More training data helped the contract types that were added, and only those.**
   - Four Mobile Banking contracts entered training (ACEH, BCA, JATENG, and JTRUST Mobile & Internet Banking), and the two biggest gains are long Mobile Banking test contracts: DBS (+39 clauses found) and BJB (+12).
   - By group, Mobile Banking, Multinational and long contracts improved. Small contracts, and the product types that got no new training examples (Uang Elektronik, Payment Gateway), lost a little.
2. **Most contracts did not change at all.**
   - On 8 of the 17, v0.1.3 returns exactly the same clause texts and pasal as v0.1.2; only some `topic` wording differs. A ninth, SULTRA, differs slightly but scores the same.
   - Both adapters share 31 training contracts, and the split decisions they learned from them are the same.
3. **OCBC Internet Banking is unchanged** (0.364 → 0.356), even with two more Internet Banking contracts in training.
   - This supports the v0.1.2 diagnosis: Legal grouped its definitions into ranges, the model gives one clause per term, and more data does not resolve a rule the labels contradict.
   - It remains the single largest loss of F1 in the test set.
4. **Deterministic generation is worth keeping, but it is not where F1 comes from.**
   - On v0.1.2, temperature 0 raised precision (0.739 → 0.789) and lowered recall (0.659 → 0.645), for +0.013 F1.
   - It also copies the contract's characters more faithfully (it keeps curly quotes that sampling had replaced).
   - Its main value is that two runs of the same model now give the same answer, which makes a release gate meaningful.
5. **The misses are still about splitting, not lost content.** Only 60 of 2,074 labelled clauses (2.9%) are truly absent from v0.1.3's output; the rest are present but grouped differently from the labels.

## Recommendations

| # | Change | Effort | Expected effect |
|---|---|---|---|
| 1 | **Send `temperature: 0` in the app's request** | Very low | Measured: +0.013 F1 on v0.1.2, higher precision, and repeatable output. All numbers in this report assume it. |
| 2 | **One labelling rule for definitions and sub-clauses**, agreed with Legal | Medium, Legal time | Still the largest single lever: OCBC Internet Banking alone accounts for more F1 than the whole v0.1.3 data change. |
| 3 | **Validate more contracts**, prioritising Uang Elektronik, Payment Gateway and Multinational | Medium to high, Legal time | v0.1.3 shows that new examples lift their own contract type, and the types that got none (Uang Elektronik, Payment Gateway) slipped. Internet Banking is held back by its labels (recommendation 2), not by the number of contracts. |
| 4 | **Train for 1 epoch** (20 steps) | Very low | The best checkpoint was step 20 in both v0.1.2 and v0.1.3. Saves ~20 min of H200 time (~$2) per run with no loss in quality. |
| 5 | **Check JAMBI Kartu Debit's labels** with Legal | Low | It is the worst validation contract in both runs (loss ~0.65 against ~0.09 for the best), so its labels or text may be wrong. |

## How the test was run

- **Models.**
  - **v0.1.3:** `scalejade/pbbi-clause-extraction-lora` at tag `v0.1.3` (commit `63773a48`, also tagged `stable`).
  - **v0.1.2:** same repo, tag `v0.1.2` (commit `03f30a73`). The Hub's `main` was checked before each run to hold the same adapter weights as the tag being tested.
  - **Engine:** both ran on vLLM 0.30, the production engine, on one H200.
- **Request.**
  - The app's exact extraction call (`extraction_system.md`, then `"DOCUMENT:\n"` + the app's PDF text, `response_format: json_object`, `max_tokens` 65,536), **plus `temperature: 0`**. The app does not send a temperature yet (recommendation 1).
  - The temperature-1.0 column is the v0.1.2 report's run, made without `temperature`, as the app sends it.
- **Scoring.**
  - Every reply goes through the app's own `parse_reply` and `finalize`.
  - A clause counts as found when it shares at least 80% of its words with a labelled clause, matched one to one, closest pairs first.
  - Legal's labels scored against themselves get 100%.
  - The lenient, absent and merged counts were recomputed for all three runs with the same code. The lenient match is one to one, closest pairs first, like the strict match; it gives v0.1.2 0.714, against the 0.708 in the v0.1.2 report.
- **Cost.**
  - Training v0.1.3: ~1 h 10 min on one H200, ≈ $6.50.
  - Each test run: ≈ $2 (H200 pod, ~25 min including model load).

## Caveats

- **17 test contracts.** One contract can move total F1 by about 0.01, so +0.007 is within the size of a single contract's swing. Several groups above have only one or two contracts.
- **The validation set is now 4 contracts.** That is enough to pick the checkpoint (both runs agree on step 20), but its eval loss is noisier and not comparable to v0.1.2's.
- **Same-bank documents.** Six banks have a different product in training than in test: BCA, JATENG, MANDIRI, OCBC, SINARMAS, SMBC. BCA and JATENG are new in v0.1.3, because their Mobile and Internet Banking contracts moved from validation. Their test contracts (BCA Kartu Debit, JATENG Kartu Debit) scored exactly the same as before, so there is no sign that this helped them.
- **The match threshold** (≥ 0.8 word overlap) is strict about splitting. The lenient recall shows how much of the gap is splitting style rather than missing content.

## Release

- **Hub.** `scalejade/pbbi-clause-extraction-lora` tag **`stable`** → `v0.1.3` (commit `63773a48`).
- **Serving pins.** Set to `v0.1.3`: `ADAPTER_REVISION` for `pbbi-serverless-extraction` and `BOOT_ADAPTERS` for `pbbi-loader`; `deploy.py plan` passes.
- **Not deployed.** The endpoint is not deployed. To ship it: `make volume-fill`, then `python runpod/deploy.py apply pbbi-serverless-extraction` (see [serving.md](../serving.md)).

## Files

- `docs/pbbi/reports/pbbi-extraction-eval-v0.1.3.{md,csv,pdf}`: this report, plus the per-contract numbers. Scores and bank names only, no contract text.
- `preparation/data/scores/test-v0.1.3-t0/` and `preparation/data/scores/test-v0.1.2-t0/`: `report.json` and every raw reply. These are gitignored, because the replies quote the client contracts. Re-run with `make evaluate ARGS="--model pbbi-clause-extraction --temperature 0"` (see [evaluation.md](../evaluation.md)).
