"""
How an extraction reply is scored against Legal's labels -- one definition, used by
training's quality check (training/scripts/train.py) and by the endpoint evaluation
(preparation/evaluate.py), so their numbers are the same numbers.

Both sides go through the app's own steps 6-7 (app_request.parse_reply, finalize):
"labelled" and "returned" mean what the app would have kept. No torch, no network.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import app_request as app  # noqa: E402

CLAUSE_MATCH = 0.8   # word-set overlap at which a predicted clause counts as a labelled one


def clause_words(clause) -> frozenset:
    """A clause's text as the set of its words, normalised the way the app keys pasal."""
    return frozenset(app.normalize_clause_name(clause.clause_text).split())


def match_clauses(predicted: list, labelled: list) -> int:
    """How many labelled clauses the prediction found, one-to-one.

    A predicted clause matches a labelled one when their word sets overlap by at
    least CLAUSE_MATCH (Jaccard). Word sets, not exact strings: the model may
    unwrap a line or fix a space differently, and that is not a missed clause.
    Pairs are taken closest-first across both lists, so a missing clause cannot
    claim the match of a near-identical sibling that is present.
    """
    pred = [clause_words(c) for c in predicted]
    gold = [clause_words(c) for c in labelled]
    pairs = []
    for i, g in enumerate(gold):
        for j, w in enumerate(pred):
            union = len(g | w)
            score = len(g & w) / union if union else 1.0
            if score >= CLAUSE_MATCH:
                pairs.append((score, i, j))
    pairs.sort(key=lambda x: (-x[0], x[1], x[2]))
    used_gold, used_pred = set(), set()
    for _, i, j in pairs:
        if i not in used_gold and j not in used_pred:
            used_gold.add(i)
            used_pred.add(j)
    return len(used_gold)


def score_reply(reply: str, labels: str) -> dict:
    """Score one generated reply against the row's labelled answer, through the app's
    own steps 6-7 (parse_reply, finalize): what the app would have kept."""
    gold, _ = app.finalize(app.parse_reply(labels))
    try:
        pred, _ = app.finalize(app.parse_reply(reply))
        valid = True
    except app.AppError:
        pred, valid = [], False
    found = match_clauses(pred, gold)
    return {"json_valid": valid, "labelled": len(gold), "predicted": len(pred), "matched": found}


def summarize(results: list[dict]) -> dict:
    """Totals over rows scored with score_reply: micro recall / precision / F1."""
    labelled = sum(r["labelled"] for r in results)
    predicted = sum(r["predicted"] for r in results)
    matched = sum(r["matched"] for r in results)
    recall = matched / labelled if labelled else 0.0
    precision = matched / predicted if predicted else 0.0
    return {
        "rows": len(results),
        "labelled": labelled, "predicted": predicted, "matched": matched,
        "recall": recall, "precision": precision,
        "f1": 2 * recall * precision / (recall + precision) if recall + precision else 0.0,
        "count_ratio": predicted / labelled if labelled else 0.0,
        "json_valid": sum(r["json_valid"] for r in results) / len(results) if results else 0.0,
    }
