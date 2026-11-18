#!/usr/bin/env python3
"""
The official PBBI extraction score: Jaccard average (docs/pbbi/rfc.md 4.3), from an
evaluate.py run directory. evaluate.py itself prints the strict score (a clause
counts only at >= 0.8 overlap); this is the one reported to BI and used in the
release gate.

    python preparation/jaccard_avg.py preparation/data/scores/test-v0.1.4-t0
    python preparation/jaccard_avg.py <run> --data preparation/data/build-v0.1.3/test.jsonl
    python preparation/jaccard_avg.py <run> --json out.json      # per-document numbers too

Scoring: both sides through the app's parse_reply + finalize, each clause a set of
the app's normalised words; every labelled clause paired one-to-one with a model
clause, closest pairs first, no threshold; score = Jaccard, unmatched = 0.
Recall = total / labelled clauses, precision = total / returned clauses, F1 over
the totals (not averaged per document). A reply cut at max_tokens or with an
error returns 0 clauses, as in the app.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import app_request as app  # noqa: E402
import score  # noqa: E402


def jaccard(a: frozenset, b: frozenset) -> float:
    u = len(a | b)
    return len(a & b) / u if u else 1.0


def jaccard_total(gold: list, pred: list) -> float:
    gw = [score.clause_words(c) for c in gold]
    pw = [score.clause_words(c) for c in pred]
    cand = sorted(((jaccard(g, p), i, j) for i, g in enumerate(gw) for j, p in enumerate(pw)),
                  key=lambda x: (-x[0], x[1], x[2]))
    gi, pj, total = set(), set(), 0.0
    for s, i, j in cand:
        if s <= 0:
            break
        if i in gi or j in pj:
            continue
        gi.add(i), pj.add(j)
        total += s
    return total


def clauses(text: str) -> list:
    try:
        return app.finalize(app.parse_reply(text))[0]
    except app.AppError:
        return []


def prf(total: float, n_gold: int, n_pred: int) -> tuple[float, float, float]:
    r = total / n_gold if n_gold else 0.0
    p = total / n_pred if n_pred else 0.0
    return r, p, (2 * p * r / (p + r) if p + r else 0.0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path, help="evaluate.py --out directory")
    ap.add_argument("--data", type=Path, help="the data file the run scored "
                    "(default: the one its report.json names)")
    ap.add_argument("--rows", help="comma-separated row indices to include (default: all)")
    ap.add_argument("--json", type=Path, help="write per-document numbers here")
    args = ap.parse_args()

    report = json.loads((args.run / "report.json").read_text("utf-8"))
    data = args.data or Path(report["data"])
    rows = [json.loads(l) for l in data.read_text("utf-8").splitlines() if l.strip()]
    keep = {int(x) for x in args.rows.split(",")} if args.rows else None
    out = {}
    for model in report["summary"]:
        results = {r["row"]: r for r in report["results"] if r["model"] == model}
        docs, T, G, P = [], 0.0, 0, 0
        for i in sorted(results):
            if keep is not None and i not in keep:
                continue
            r = results[i]
            gold = clauses(rows[i]["messages"][-1]["content"])
            f = args.run / "replies" / f"{model.replace('/', '__')}__row{i}.txt"
            ok = "error" not in r and r.get("finish") != "length" and f.exists()
            pred = clauses(f.read_text("utf-8")) if ok else []
            t = jaccard_total(gold, pred)
            T, G, P = T + t, G + len(gold), P + len(pred)
            docs.append({"row": i, "labelled": len(gold), "predicted": len(pred),
                         "total": t, **dict(zip(("recall", "precision", "f1"),
                                                prf(t, len(gold), len(pred))))})
        r_, p_, f_ = prf(T, G, P)
        out[model] = {"rows": len(docs), "labelled": G, "predicted": P, "total": T,
                      "recall": r_, "precision": p_, "f1": f_, "docs": docs}
        print(f"  {model:<28} rows {len(docs):>2}  labelled {G:>5}  returned {P:>5}  "
              f"Jaccard avg  R {100*r_:5.1f}  P {100*p_:5.1f}  F1 {100*f_:5.1f}")
    if args.json:
        args.json.write_text(json.dumps(out, indent=1), "utf-8")


if __name__ == "__main__":
    main()
