#!/usr/bin/env python3
"""
Turn a `=== MODEL === / === SYSTEM PROMPT === / === USER MESSAGE ===` request file
into RunPod-ready JSON, with an exact token budget.

    python runpod/scripts/build_request.py "scratch/[jago] - req - extraction.txt"
    python runpod/scripts/build_request.py <file> --model scalejade/qwen-sea-lion-v4.5-27b-it --context 262144
    python runpod/scripts/build_request.py <file> --out runpod/requests/jago

Counts tokens with the real Qwen3 tokenizer (the base of every SEA-LION v4 model),
including chat-template overhead. If the request does not fit the context window it
splits the document on section boundaries and emits one request per chunk.

Why the split is not optional: a request that overflows the context is rejected, and
one that fits the *input* but not the *output* comes back HTTP 200 with clauses
silently missing. Both are avoided here by budgeting for generation up front.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    from transformers import AutoTokenizer
except ImportError:
    sys.exit("transformers is required:  pip install transformers")

# v4 and v4.5 do NOT share a tokenizer. v4 is Qwen3 (vocab 151,936); v4.5 is Qwen3.5
# (vocab 248,320) and is ~24% more efficient on Indonesian text. Counting the Jago
# document with the wrong one overstated it by 13,400 tokens.
TOKENIZER = "aisingapore/Qwen-SEA-LION-v4.5-27B-IT"
TOKENIZERS = {
    "v4.5": "aisingapore/Qwen-SEA-LION-v4.5-27B-IT",
    "v4":   "Qwen/Qwen3-32B",
}

# Measured on the BCA run (docs/reports/2026-08-16-runpod-deployment-trials.md):
# 10,280 document tokens produced 17,258 output tokens across 144 clauses.
# Extraction is verbatim copy plus JSON scaffolding, so output scales with input.
OUTPUT_RATIO = 17258 / 10280          # ~1.68

SAFETY = 0.92                          # never plan to use the last 8% of the window
SECTION_RE = re.compile(r"(?m)^\s*[IVXLC]+\s*-\s*.+$")


def parse_request_file(path: Path) -> tuple[str, str, str]:
    raw = path.read_text(encoding="utf-8")

    def section(name: str) -> str:
        m = re.search(rf"^=== {name} ===\n(.*?)(?=^=== |\Z)", raw, re.S | re.M)
        if not m:
            sys.exit(f"'{path.name}' has no '=== {name} ===' section")
        return m.group(1).strip("\n")

    return section("MODEL").strip(), section("SYSTEM PROMPT"), section("USER MESSAGE")


def split_sections(doc: str) -> list[str]:
    """Split on top-level roman-numeral headers, keeping each header with its body."""
    starts = [m.start() for m in SECTION_RE.finditer(doc)]
    if not starts:
        # Fall back to blank-line paragraphs so we never split mid-sentence.
        return [p for p in re.split(r"\n\s*\n", doc) if p.strip()]
    if starts[0] > 0:
        starts.insert(0, 0)             # preamble before the first header
    bounds = starts + [len(doc)]
    return [doc[a:b] for a, b in zip(bounds, bounds[1:]) if doc[a:b].strip()]


def pack(units: list[str], budget: int, count) -> list[str]:
    """Greedily pack units into chunks of at most `budget` tokens each."""
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for unit in units:
        n = count(unit)
        if n > budget:
            # A single section is too big on its own — split it by paragraph.
            if current:
                chunks.append("".join(current))
                current, current_tokens = [], 0
            paras = [p for p in re.split(r"(\n\s*\n)", unit) if p]
            chunks.extend(pack(paras, budget, count))
            continue
        if current_tokens + n > budget:
            chunks.append("".join(current))
            current, current_tokens = [unit], n
        else:
            current.append(unit)
            current_tokens += n
    if current:
        chunks.append("".join(current))
    return chunks


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path, help="the === MODEL/SYSTEM PROMPT/USER MESSAGE === file")
    ap.add_argument("--model", help="model name sent to the API (default: from the file)")
    ap.add_argument("--context", type=int, default=40960, help="MAX_MODEL_LEN of the target endpoint")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--out", type=Path, default=Path("runpod/requests"))
    ap.add_argument("--thinking", action="store_true", help="enable Qwen3 thinking mode")
    ap.add_argument("--tokenizer", default=TOKENIZER,
                    help=f"tokenizer repo. Shortcuts: {', '.join(TOKENIZERS)}")
    args = ap.parse_args()

    file_model, system, user = parse_request_file(args.source)
    model = args.model or file_model

    tok = AutoTokenizer.from_pretrained(TOKENIZERS.get(args.tokenizer, args.tokenizer))
    count = lambda s: len(tok.encode(s, add_special_tokens=False))

    def templated(sys_text: str, usr_text: str) -> int:
        text = tok.apply_chat_template(
            [{"role": "system", "content": sys_text}, {"role": "user", "content": usr_text}],
            tokenize=False, add_generation_prompt=True, enable_thinking=args.thinking,
        )
        return count(text)

    n_system = count(system)
    n_user = count(user)
    n_input = templated(system, user)
    overhead = n_input - n_system - n_user
    est_output = round(n_user * OUTPUT_RATIO)
    usable = int(args.context * SAFETY)

    print(f"\n  source        {args.source.name}")
    print(f"  model         {model}")
    print(f"  context       {args.context:,}  (planning against {usable:,} at {SAFETY:.0%} safety)")
    print(f"\n  system prompt {n_system:>9,} tokens")
    print(f"  document      {n_user:>9,} tokens")
    print(f"  chat template {overhead:>9,} tokens")
    print(f"  {'input total':<13} {n_input:>9,} tokens")
    print(f"  est. output   {est_output:>9,} tokens   (measured ratio {OUTPUT_RATIO:.2f}x document)")
    print(f"  {'REQUIRED':<13} {n_input + est_output:>9,} tokens")

    fits = n_input + est_output <= usable
    if fits:
        print(f"\n  fits in one request — {usable - n_input - est_output:,} tokens of headroom\n")
        chunks = [user]
    else:
        over = n_input + est_output - args.context
        print(f"\n  DOES NOT FIT — over the {args.context:,} window by {over:,} tokens")
        # system + chunk + ratio*chunk <= usable  ->  chunk <= (usable - system - overhead)/(1+ratio)
        per_chunk = int((usable - n_system - overhead) / (1 + OUTPUT_RATIO))
        print(f"  splitting document into chunks of <= {per_chunk:,} tokens\n")
        chunks = pack(split_sections(user), per_chunk, count)

    args.out.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^a-z0-9]+", "-", args.source.stem.lower()).strip("-")

    manifest = []
    for i, chunk in enumerate(chunks, 1):
        n_chunk = count(chunk)
        n_in = templated(system, chunk)
        # Give generation everything the window has left, capped at a sane multiple
        # of the estimate so one runaway response cannot eat a whole worker-hour.
        room = args.context - n_in - 64
        max_tokens = min(room, max(round(n_chunk * OUTPUT_RATIO * 1.35), 1024))

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": chunk},
            ],
            "max_tokens": max_tokens,
            "temperature": args.temperature,
            "top_p": 1.0,
            "stream": False,
            "response_format": {"type": "json_object"},
            "chat_template_kwargs": {"enable_thinking": args.thinking},
        }

        name = stem if len(chunks) == 1 else f"{stem}-{i:02d}-of-{len(chunks):02d}"
        path = args.out / f"{name}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        used = n_in + max_tokens
        manifest.append({
            "file": str(path),
            "chunk": i,
            "document_tokens": n_chunk,
            "input_tokens": n_in,
            "max_tokens": max_tokens,
            "worst_case_context": used,
            "headroom": args.context - used,
        })
        print(f"  {path.name:<44} doc {n_chunk:>7,}  in {n_in:>7,}  max_out {max_tokens:>7,}  peak {used:>7,}/{args.context:,}")

    (args.out / f"{stem}.manifest.json").write_text(
        json.dumps({
            "source": str(args.source),
            "model": model,
            "context": args.context,
            "tokenizer": TOKENIZERS.get(args.tokenizer, args.tokenizer),
            "output_ratio": round(OUTPUT_RATIO, 4),
            "totals": {
                "system_tokens": n_system,
                "document_tokens": n_user,
                "single_request_input": n_input,
                "single_request_estimated_output": est_output,
                "fits_single_request": fits,
                "chunks": len(chunks),
            },
            "requests": manifest,
        }, indent=2),
        encoding="utf-8",
    )
    print(f"\n  manifest      {args.out / f'{stem}.manifest.json'}")
    print(f"\n  send with:    curl -X POST \\\n"
          f"                  https://api.runpod.ai/v2/$ENDPOINT_ID/openai/v1/chat/completions \\\n"
          f"                  -H \"Authorization: Bearer $RUNPOD_API_KEY\" \\\n"
          f"                  -H 'Content-Type: application/json' \\\n"
          f"                  -d @{manifest[0]['file']}\n")
    if len(chunks) > 1:
        print("  NOTE: merge the `clauses` arrays from every chunk response, and re-number\n"
              "        header-less clauses across the merged set (system prompt rule 1.3.1).\n")


if __name__ == "__main__":
    main()
