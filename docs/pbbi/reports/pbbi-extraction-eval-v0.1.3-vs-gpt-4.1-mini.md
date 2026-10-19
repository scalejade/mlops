# PBBI clause extraction — fine-tuned v0.1.3 vs gpt-4.1-mini

**Test set:** 17 Perjanjian Baku contracts never used in training · **Date:** 2026-10-17 · **Both models at temperature 0**

## Summary

The fine-tuned model **v0.1.3** (the current `stable` release) finds **2.3 times as many** of Legal's clauses as **gpt-4.1-mini**, and more of what it returns is right: **F1 0.716 vs 0.391**. It has the higher F1 on 13 of the 17 contracts and ties on 2. gpt-4.1-mini wins on 2 (BRI UE Chip-Based and OCBC Internet Banking).

| | **v0.1.3** (fine-tuned Qwen-SEA-LION 27B + LoRA) | gpt-4.1-mini |
|---|---|---|
| **Recall**: Legal's clauses found | **0.658** (1,365 / 2,074) | 0.283 (587 / 2,074) |
| **Precision**: returned clauses that are right | **0.784** (1,365 / 1,741) | 0.632 (587 / 929) |
| **F1** | **0.716** | 0.391 |
| Clauses returned ÷ labelled | **0.84** | 0.45 |
| Valid JSON / finished on its own | 17/17 / 17/17 | 17/17 / 17/17 |
| Higher F1 on | **13** contracts (2 ties) | 2 |
| Output tokens, all 17 | 230,894 | 186,125 |
| Time for the longest contract | 15.8 min (H200, 8 at a time) | 2.8 min |
| Cost of a 17-contract run | ≈ $2 (H200 pod, ~25 min incl. model load) | ≈ $0.45 (API) |

**Temperature.** Both runs here use temperature 0, so each model gives its single most likely answer and a re-run gives the same output. gpt-4.1-mini does **better at its default temperature, 1.0**: F1 **0.470** (recall 0.349, precision 0.720), as measured in the [v0.1.2 report](pbbi-extraction-eval-v0.1.2-vs-gpt-4.1-mini.md). Even at its best setting it is well behind v0.1.3.

## The clause-by-clause workbook

`pbbi-extraction-clauses-v0.1.3-vs-gpt-4.1-mini.xlsx`, in this folder, shows **what each model generated**, next to Legal's label, for every clause of the 17 contracts:

| Sheet | Contents |
|---|---|
| **Ringkasan** | The scores above, and how to read the other sheets |
| **Per kontrak** | Per contract: returned, matched, recall, precision, F1, minutes, for both models |
| **Perbandingan klausa** | One row per clause Legal labelled (No. Pasal, Topik, Bunyi), with v0.1.3's clause and gpt-4.1-mini's clause beside it. Green means match; red means missed, with the closest clause shown and its similarity. After each contract, the clauses each model returned that match none of Legal's are listed in orange |
| **v0.1.3 (fine-tuned) (mentah)** / **gpt-4.1-mini (mentah)** | Each model's output exactly as generated, in order |

**The workbook quotes the contracts word for word.** It is gitignored (`docs/pbbi/reports/*.xlsx`) and must be shared the way the source contracts are, not through git. This page and the csv hold scores and bank names only.

## Results per contract

| Contract | Penyelenggara | Labelled | v0.1.3 found / returned | **v0.1.3 F1** | mini found / returned | **mini F1** |
|---|---|---|---|---|---|---|
| JATENG Kartu Debit | Utama / BPD | 15 | 15 / 15 | 1.000 | 15 / 15 | 1.000 |
| MUAMALAT Internet Banking | Utama / Swasta Nasional | 46 | 46 / 46 | **1.000** | 32 / 35 | 0.790 |
| BCA Kartu Debit | Utama / Swasta Nasional | 87 | 79 / 80 | **0.946** | 50 / 57 | 0.694 |
| SINARMAS UE Server-Based | Utama / Swasta Nasional | 49 | 44 / 49 | **0.898** | 4 / 14 | 0.127 |
| MANDIRI Mobile Banking | Utama / BUMN | 98 | 88 / 102 | **0.880** | 53 / 68 | 0.639 |
| NAGARI Mobile Banking | BPD | 44 | 37 / 44 | **0.841** | 27 / 32 | 0.711 |
| BRI UE Chip-Based | Utama / BUMN | 27 | 25 / 33 | 0.833 | 25 / 31 | **0.862** |
| SULTRA Kartu Debit | BPD | 18 | 15 / 18 | 0.833 | 15 / 18 | 0.833 |
| OY Payment Gateway | Swasta Nasional | 89 | 67 / 86 | **0.766** | 20 / 32 | 0.331 |
| SEABANK Mobile Banking | Utama / Swasta Nasional | 358 | 247 / 290 | **0.762** | 42 / 66 | 0.198 |
| SHOPEEPAY UE Server-Based | Utama / LSB | 211 | 130 / 147 | **0.726** | 57 / 84 | 0.386 |
| DBS Mobile Banking | Utama / Multinational | 262 | 168 / 207 | **0.716** | 95 / 162 | 0.448 |
| SMBC Kartu Kredit | Utama / Swasta Nasional | 172 | 127 / 197 | **0.688** | 45 / 107 | 0.323 |
| OCBC Kartu Kredit | Utama / Multinational | 233 | 131 / 154 | **0.677** | 19 / 44 | 0.137 |
| BJB Mobile Banking | Utama / BPD | 110 | 69 / 116 | **0.611** | 4 / 19 | 0.062 |
| BOC Mobile & Internet Banking | Utama / Multinational | 79 | 25 / 41 | **0.417** | 18 / 33 | 0.321 |
| OCBC Internet Banking | Utama / Multinational | 176 | 52 / 116 | 0.356 | 66 / 112 | **0.458** |
| **All 17** | | **2,074** | **1,365 / 1,741** | **0.716** | **587 / 929** | **0.391** |

### By product

| Product | Contracts | v0.1.3 F1 | gpt-4.1-mini F1 |
|---|---|---|---|
| Kartu Debit | 3 | **0.936** | 0.762 |
| Uang Elektronik Chip-Based | 1 | 0.833 | **0.862** |
| Payment Gateway | 1 | **0.766** | 0.331 |
| Uang Elektronik Server-Based | 2 | **0.763** | 0.341 |
| Mobile Banking | 5 | **0.747** | 0.363 |
| Kartu Kredit | 2 | **0.683** | 0.230 |
| Internet Banking | 2 | 0.510 | **0.531** |
| Mobile Banking & Internet Banking | 1 | **0.417** | 0.321 |

### By penyelenggara

| Penyelenggara | Contracts | v0.1.3 F1 | gpt-4.1-mini F1 |
|---|---|---|---|
| Utama / BUMN | 2 | **0.869** | 0.696 |
| BPD | 2 | **0.839** | 0.750 |
| Utama / Swasta Nasional | 5 | **0.790** | 0.349 |
| Swasta Nasional | 1 | **0.766** | 0.331 |
| Utama / LSB | 1 | **0.726** | 0.386 |
| Utama / BPD | 2 | **0.656** | 0.239 |
| Utama / Multinational | 4 | **0.593** | 0.360 |

### By contract length

| Labelled clauses | Contracts | v0.1.3 recall | gpt-4.1-mini recall |
|---|---|---|---|
| under 100 | 10 | **0.799** | 0.469 |
| 100–199 | 3 | **0.541** | 0.251 |
| 200 or more | 4 | **0.635** | 0.200 |

## What the results show

1. **gpt-4.1-mini returns less than half of the clauses.**
   - It returns 929 clauses where Legal labelled 2,074 (0.45×), and finds 587 of them.
   - On four contracts it finds almost nothing: BJB (4 of 110), SINARMAS (4 of 49), OCBC Kartu Kredit (19 of 233), SEABANK (42 of 358).
   - Every reply ended normally (`stop`), well under its 32,768-token limit, so it is not being cut off. It merges sub-clauses and stops early. The *Perbandingan klausa* sheet shows where.
2. **v0.1.3 follows Legal's level of detail.** It returns 0.84× as many clauses as Legal, and is near-perfect on short contracts: recall 0.80 on contracts with fewer than 100 clauses.
3. **The gap is largest where it matters most.**
   - On contracts with 200 or more clauses, v0.1.3 finds 0.64 of Legal's clauses and gpt-4.1-mini finds 0.20.
   - A clause the extraction misses is never reviewed for compliance, so recall is the number to watch.
4. **gpt-4.1-mini wins on 2 contracts.**
   - **OCBC Internet Banking** (0.458 vs 0.356) is v0.1.3's known weak point: Legal groups its definitions into ranges, and v0.1.3 gives one clause per term (see the [v0.1.3 report](pbbi-extraction-eval-v0.1.3.md)).
   - **BRI UE Chip-Based** (0.862 vs 0.833) is a 27-clause contract where the two are within one clause of each other.
5. **gpt-4.1-mini is worse at temperature 0 than at 1.0** (F1 0.391 vs 0.470). With its single most likely answer it stops even earlier. Sampling sometimes carries it further through the document.

## How the test was run

- **Models.**
  - **v0.1.3:** `scalejade/pbbi-clause-extraction-lora` tag `v0.1.3` (`stable`, commit `63773a48`) on the base `scalejade/qwen-sea-lion-v4.5-27b-pbbi` at `8d32a4b9`. It ran on vLLM 0.30, the production engine, on one H200.
  - **gpt-4.1-mini:** the OpenAI API.
- **Request.** Both models got the app's exact extraction call: `extraction_system.md` byte for byte, then `"DOCUMENT:\n"` + the app's PDF text, with `response_format: json_object` and **`temperature: 0`**.
  - Output limit: v0.1.3 got the app's 65,536 tokens. gpt-4.1-mini got 32,768, its API maximum. None of its replies came near that limit.
- **Scoring.**
  - Every reply goes through the app's own `parse_reply` and `finalize`.
  - A clause counts as found when it shares at least 80% of its words with a labelled clause, matched one to one, closest pairs first.
  - Legal's labels scored against themselves get 100%.
  - The workbook is built by `preparation/compare_runs.py` with the same matching, and its totals equal these.

## Caveats

- **17 test contracts.** Several products and penyelenggara types have only one or two, so group-level differences are indicative.
- **gpt-4.1-mini at its default temperature** scores higher (F1 0.470) than in this temperature-0 comparison. Either way, v0.1.3 leads by more than 0.24 F1.
- **The match threshold** (≥ 0.8 word overlap) is strict about how clauses are split. A merged or differently split clause counts as a miss even when its words are present.

## Files

- `pbbi-extraction-eval-v0.1.3-vs-gpt-4.1-mini.{md,csv,pdf}`: this report and the per-contract numbers (scores and bank names only). The csv also has gpt-4.1-mini's temperature-1.0 F1 per contract.
- `pbbi-extraction-clauses-v0.1.3-vs-gpt-4.1-mini.xlsx`: every clause each model generated, beside Legal's. **Gitignored: it quotes the contracts.**
- Raw runs (gitignored): `preparation/data/scores/test-v0.1.3-t0/`, `test-gpt-4.1-mini-t0/`, `test-gpt-4.1-mini/` (temperature 1.0). To rebuild the workbook:

```bash
python preparation/compare_runs.py \
  preparation/data/scores/test-v0.1.3-t0 "v0.1.3 (fine-tuned)" \
  preparation/data/scores/test-gpt-4.1-mini-t0 "gpt-4.1-mini" \
  --out docs/pbbi/reports/pbbi-extraction-clauses-v0.1.3-vs-gpt-4.1-mini.xlsx
```
