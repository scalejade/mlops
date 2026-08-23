# Evaluation

**Nothing gets deployed without passing through here.**

The failure mode this exists to prevent: a fine-tune with a better training loss
and worse real-world extraction, shipped because loss went down and nobody checked
the actual clauses. Training metrics do not measure whether the product works.

## Layout

| Path | What |
|---|---|
| `golden/` | Verified input/output pairs. The ground truth. Gitignored if it contains client documents. |
| `suites/` | Runners. Each takes an endpoint URL and a golden set and emits scores. |
| `results/` | Scored runs, one JSON per run. Committed — this is the history. |

## Golden set

For PJP clause extraction the golden set is a handful of real contracts with a
human-verified clause list per document. Start small — three documents fully
verified beats thirty half-checked. Seed material is in `scratch/` (BCA and Jago
requests, `klausa-BCA-mBCA.xlsx`).

Store it in a **private HF dataset repo** and reference it by revision, the same
way training data works. Never commit client contracts.

## What every suite must report

- **Precision / recall / F1 per clause type** — an aggregate number hides which
  clause types the model stopped finding.
- **Clause count vs expected** — the truncation bug showed up as ~7 missing clauses
  out of 144, which no loss curve would ever reveal.
- **`finish_reason` distribution** — any `"length"` is a failed run, not a low score.
- **Token usage and wall-clock** — so a quality gain that triples cost is visible.
- **Model, adapter, endpoint, and config revision** — a result you cannot trace to
  an exact configuration is not a result.

## Gate

A model may be deployed when it beats the current production model on the golden
set, or matches it at meaningfully lower cost. Write the comparison into
`results/` and link it from the PR.
