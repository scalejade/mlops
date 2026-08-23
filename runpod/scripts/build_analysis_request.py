#!/usr/bin/env python3
"""
Build the stage-2 (analysis / compliance scoring) request from stage-1 output.

    python runpod/scripts/build_analysis_request.py runpod/requests/merged.json
    python runpod/scripts/build_analysis_request.py <clauses.json> --prompt runpod/prompts/analysis.md

Stage 1 (extraction) turns a document into clauses. Stage 2 takes those clauses and
scores each one against Bank Indonesia regulations. The input here is the CLAUSES,
not the original document — feeding the raw document again would re-do stage 1.

Token budgeting is measured, not guessed: the clause payload is tokenized with the
model's own tokenizer, and max_tokens is derived from a per-clause output cost you
can calibrate as soon as you have one real run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from transformers import AutoTokenizer
except ImportError:
    sys.exit("transformers is required:  pip install transformers")

REPO = Path(__file__).resolve().parent.parent.parent
TOKENIZER = "aisingapore/Qwen-SEA-LION-v4.5-27B-IT"

# From the BCA run (docs/reports/2026-08-16-runpod-deployment-trials.md):
# 120 tokens/clause at extraction, 252 tokens/clause after scoring. Scoring roughly
# doubles a clause because it adds a verdict, a regulation reference, and reasoning
# on top of the clause text that gets echoed back.
OUTPUT_TOKENS_PER_CLAUSE = 252
SAFETY = 0.92

# Shape of one scored clause. Adjust to match whatever the analysis prompt asks for —
# then the schema and the prompt cannot drift apart silently.
ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "pasal": {"type": "string", "minLength": 1},
                    "topic": {"type": "string", "minLength": 1},
                    "status": {"type": "string", "enum": ["patuh", "tidak_patuh", "perlu_ditinjau"]},
                    "dasar_hukum": {"type": "string"},
                    "alasan": {"type": "string", "minLength": 1},
                },
                "required": ["pasal", "topic", "status", "dasar_hukum", "alasan"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}


def load_clauses(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    clauses = data.get("clauses", data if isinstance(data, list) else None)
    if not clauses:
        sys.exit(f"{path} has no 'clauses' array — is this stage-1 output?")
    missing = [i for i, c in enumerate(clauses) if not all(k in c for k in ("pasal", "topic", "clause_text"))]
    if missing:
        sys.exit(f"{len(missing)} clause(s) missing pasal/topic/clause_text, first at index {missing[0]}")
    return clauses


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("clauses", type=Path, help="stage-1 output (the merged clauses JSON)")
    ap.add_argument("--prompt", type=Path, default=REPO / "runpod" / "prompts" / "analysis.md",
                    help="analysis system prompt (markdown)")
    ap.add_argument("--model", default="scalejade/qwen-sea-lion-v4.5-27b-it")
    ap.add_argument("--context", type=int, default=262144)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--per-clause", type=int, default=OUTPUT_TOKENS_PER_CLAUSE,
                    help="expected output tokens per scored clause")
    ap.add_argument("--out", type=Path, default=REPO / "runpod" / "requests")
    ap.add_argument("--no-schema", action="store_true", help="omit the json_schema response format")
    args = ap.parse_args()

    if not args.prompt.exists():
        sys.exit(
            f"no analysis prompt at {args.prompt}\n"
            f"  Write the compliance-scoring system prompt there first.\n"
            f"  {args.prompt.parent / 'analysis.md'} has a skeleton describing what it must contain."
        )
    system = args.prompt.read_text(encoding="utf-8")
    if "TODO" in system:
        print(f"  WARNING: {args.prompt.name} still contains TODO markers — the prompt is a stub.\n")

    clauses = load_clauses(args.clauses)

    # Send the clauses as JSON. It is unambiguous, and the model already emits this
    # exact shape at stage 1, so nothing has to be re-parsed or re-formatted.
    user = "KLAUSA UNTUK DINILAI:\n" + json.dumps({"clauses": clauses}, ensure_ascii=False, indent=2)

    tok = AutoTokenizer.from_pretrained(TOKENIZER)
    count = lambda s: len(tok.encode(s, add_special_tokens=False))

    n_system = count(system)
    n_user = count(user)
    n_input = count(tok.apply_chat_template(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        tokenize=False, add_generation_prompt=True,
    ))
    est_output = len(clauses) * args.per_clause
    usable = int(args.context * SAFETY)

    print(f"\n  clauses       {len(clauses):>9,}")
    print(f"  system prompt {n_system:>9,} tokens")
    print(f"  clause payload{n_user:>9,} tokens")
    print(f"  {'input total':<13} {n_input:>9,} tokens")
    print(f"  est. output   {est_output:>9,} tokens   ({args.per_clause}/clause, measured on BCA)")
    print(f"  {'REQUIRED':<13} {n_input + est_output:>9,} tokens  of {args.context:,}")

    if n_input + est_output > usable:
        over = n_input + est_output - args.context
        print(f"\n  DOES NOT FIT — over the window by {over:,} tokens.")
        print(f"  Split the clause list and run several requests, or raise --context.\n")
        sys.exit(1)

    room = args.context - n_input - 64
    max_tokens = min(room, round(est_output * 1.35))

    payload = {
        "model": args.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": args.temperature,
        "top_p": 1.0,
        "seed": 0,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if not args.no_schema:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "clause_analysis", "strict": True, "schema": ANALYSIS_SCHEMA},
        }

    args.out.mkdir(parents=True, exist_ok=True)
    stem = args.clauses.stem.replace("merged", "analysis")
    if stem == args.clauses.stem:
        stem = f"{stem}-analysis"
    path = args.out / f"{stem}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    peak = n_input + max_tokens
    print(f"\n  wrote  {path}")
    print(f"  max_tokens {max_tokens:,}  ->  peak {peak:,}/{args.context:,}  "
          f"({args.context - peak:,} headroom)")
    print(f"\n  send with:\n"
          f"    python runpod/scripts/send_request.py {path} --pod-id <pod-id>\n")
    print("  After the first real run, replace --per-clause with the measured value:\n"
          "    completion_tokens / number of clauses\n")


if __name__ == "__main__":
    main()
