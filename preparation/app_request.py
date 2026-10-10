#!/usr/bin/env python3
"""
The app's clause-extraction call, rebuilt locally. Nothing here touches a network.

    python preparation/app_request.py <pdf>                       # build the request
    python preparation/app_request.py <pdf> --out <dir>           # ... and write it
    python preparation/app_request.py <pdf> --response <file>     # ... and parse a reply

Mirrors scalejade/perjanjian-baku-bi, branch sys-prompt @ e028187:

    1  ExtractTextFromPDF        pdftotext -layout -> keepIndonesianOnly()   (serving_text.py)
    2  IsEnglishDocument         English-only documents are rejected at upload
    3  ensureDocumentFitsExtractionCall
                                 bytes/4 must fit 262,144 - prompt - 65,536 - 1,000
    4  callLLMWithSystem         system = extraction_system.md, user = "DOCUMENT:\\n" + text
                                 max_tokens 65,536, response_format json_object
    5  postChatCompletion        finish_reason "length" is an error, not a reply
    6  extractClausesFromDocument
                                 extractJSONValue -> {"clauses":[...]} or a bare [...]
    7  finalizeClauses           drop clause_text under 8 words, drop a repeated pasal

Step 4 is where the app POSTs to RunPod. This file builds the identical body and
stops; --response feeds steps 5-7 a reply you already have (a model's raw text,
or a whole chat-completions response JSON), so the app's parsing can be checked
offline against any output -- including the labels themselves.

build.py imports the request shape from here, so training rows and this tool
cannot drift apart. If the app changes any step, change it here first.
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import serving_text  # noqa: E402

APP = "scalejade/perjanjian-baku-bi@e028187 (sys-prompt)"
HERE = Path(__file__).resolve().parent

# domain/constants.go
MODEL = "scalejade/qwen-sea-lion-v4.5-27b-it"          # RunPodModelSeaLion, DefaultAIModel
CONTEXT_WINDOW_TOKENS = 262_144                         # runPodWorkerContextWindowTokens
MAX_OUTPUT_TOKENS = 65_536                              # seaLionMaxOutputTokens
# service/clause_extraction.go
SYSTEM_PROMPT = HERE / "prompts" / "extraction_system.md"   # go:embed, sent byte-for-byte
DOCUMENT_PREFIX = "DOCUMENT:\n"                             # buildExtractionUserMessage
CHARS_PER_TOKEN = 4                                         # estimateTokenCount: len(bytes)/4
SAFETY_MARGIN_TOKENS = 1000                                 # contextWindowSafetyMarginTokens
MIN_CLAUSE_WORDS = 8                                        # minClauseWords
MAX_ATTEMPTS = 4                                            # maxExtractionRetries + 1
# service/ai_service.go
ENDPOINT = "https://api.runpod.ai/v2/{RUNPOD_ENDPOINT_ID}/openai/v1/chat/completions"


class AppError(Exception):
    """What the app would report as a failed upload or a failed analysis."""


def system_prompt() -> str:
    return SYSTEM_PROMPT.read_text("utf-8")      # no strip: go:embed sends it as-is


# ----------------------------------------------------- steps 1-4: request

def estimate_tokens(text: str) -> int:
    return len(text.encode("utf-8")) // CHARS_PER_TOKEN


def check_fits(document: str, system: str) -> tuple[int, int]:
    """ensureDocumentFitsExtractionCall. Returns (document, available) in the
    app's own estimate; raises when the app would fail the analysis."""
    available = (CONTEXT_WINDOW_TOKENS - estimate_tokens(system)
                 - MAX_OUTPUT_TOKENS - SAFETY_MARGIN_TOKENS)
    doc = estimate_tokens(document)
    if doc > available:
        raise AppError(
            f"document is too large for a single extraction call: {doc} tokens, but only "
            f"{available} tokens are available (context window {CONTEXT_WINDOW_TOKENS}, "
            f"extraction prompt {estimate_tokens(system)}, reserved output {MAX_OUTPUT_TOKENS}, "
            f"safety margin {SAFETY_MARGIN_TOKENS})")
    return doc, available


def user_message(document: str) -> str:
    return DOCUMENT_PREFIX + document


def request_body(document: str, system: str, model: str = MODEL) -> dict:
    """The JSON postChatCompletion marshals for the RunPod worker. Field order
    and omissions follow openAICompatibleRequest: no temperature, no
    enable_thinking, max_tokens rather than max_completion_tokens."""
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_message(document)},
        ],
        "max_tokens": MAX_OUTPUT_TOKENS,
        "response_format": {"type": "json_object"},
    }


def document_text(pdf: Path) -> str:
    """Steps 1-2, as Upload() runs them."""
    try:
        text = serving_text.served_document_text(pdf)
    except serving_text.ExtractError as e:
        raise AppError(f"Gagal mengekstrak teks dari PDF ({e})")
    if not text.strip():
        raise AppError("Gagal mengekstrak teks dari PDF (empty text)")
    if serving_text.is_english_document(text):
        raise AppError("Dokumen ditolak karena seluruh isinya berbahasa Inggris.")
    return text


# ------------------------------------------------------ steps 5-7: reply

def strip_code_fences(text: str) -> str:
    text = text.strip()
    for fence in ("```json", "```JSON", "```"):
        if text.startswith(fence):
            text = text[len(fence):]
            break
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def extract_json_value(text: str) -> str:
    """Prefers an array when '[' comes before '{'; first opener to LAST closer."""
    text = strip_code_fences(text)
    a, o = text.find("["), text.find("{")
    if a >= 0 and (o < 0 or a < o):
        end = text.rfind("]")
        if end > a:
            return text[a:end + 1]
    if o >= 0:
        end = text.rfind("}")
        if end > o:
            return text[o:end + 1]
    return text


@dataclass
class Clause:
    pasal: str
    topic: str
    clause_text: str


_FIELDS = {"pasal": "pasal", "topic": "topic", "clause_text": "clause_text"}


def _go_string_fields(obj: dict) -> Clause:
    """encoding/json into extractedClause: keys match case-insensitively,
    unknown keys are ignored, null leaves "", a non-string is an error."""
    got = {"pasal": "", "topic": "", "clause_text": ""}
    for k, v in obj.items():
        f = _FIELDS.get(k.lower())
        if f is None:
            continue
        if v is None:
            continue
        if not isinstance(v, str):
            raise ValueError(f"json: cannot unmarshal {type(v).__name__} into field {f}")
        got[f] = v
    return Clause(**got)


def _as_envelope(value) -> list[Clause]:
    if not isinstance(value, dict):
        raise ValueError("not an object")
    clauses = None
    for k, v in value.items():
        if k.lower() == "clauses":
            clauses = v
    if clauses is None:
        return []
    if not isinstance(clauses, list):
        raise ValueError("clauses is not an array")
    return [_go_string_fields(c) if isinstance(c, dict) else _bad(c) for c in clauses]


def _as_array(value) -> list[Clause]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("not an array")
    return [_go_string_fields(c) if isinstance(c, dict) else _bad(c) for c in value]


def _bad(c):
    if c is None:
        return Clause("", "", "")
    raise ValueError(f"json: cannot unmarshal {type(c).__name__} into extractedClause")


def parse_reply(content: str) -> list[Clause]:
    """extractClausesFromDocument after the call: the envelope when it parses
    AND is non-empty, otherwise a bare array, otherwise a failed attempt."""
    cleaned = extract_json_value(content)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise AppError(f"failed to parse extracted clauses: {e}")
    try:
        env = _as_envelope(value)
        if env:
            return env
    except ValueError:
        pass
    try:
        return _as_array(value)
    except ValueError as e:
        raise AppError(f"failed to parse extracted clauses: {e}")


def reply_content(raw: str) -> str:
    """Accept either the model's text or a whole chat-completions response.
    For the latter, apply postChatCompletion's checks first."""
    try:
        resp = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if not (isinstance(resp, dict) and "choices" in resp):
        return raw
    if not resp["choices"]:
        raise AppError("RunPod returned no choices")
    choice = resp["choices"][0]
    if choice.get("finish_reason") == "length":
        used = resp.get("usage", {}).get("completion_tokens")
        raise AppError(f"RunPod truncated the reply at the {MAX_OUTPUT_TOKENS}-token output "
                       f"budget ({used} completion tokens used)")
    return choice["message"]["content"]


def normalize_clause_name(name: str) -> str:
    """Lowercase, keep Unicode letters, decimal digits and spaces, collapse spaces."""
    kept = "".join(r for r in name.strip().lower()
                   if r.isalpha() or unicodedata.category(r) == "Nd" or r.isspace())
    return " ".join(kept.split())


def finalize(clauses: list[Clause]) -> tuple[list[Clause], list[tuple[Clause, str]]]:
    """finalizeClauses. Returns (kept, dropped-with-reason)."""
    seen: set[str] = set()
    kept, dropped = [], []
    for c in clauses:
        if len(c.clause_text.strip().split()) < MIN_CLAUSE_WORDS:
            dropped.append((c, f"clause_text under {MIN_CLAUSE_WORDS} words"))
            continue
        key = normalize_clause_name(c.pasal)
        if key in seen:
            dropped.append((c, "pasal already seen"))
            continue
        seen.add(key)
        kept.append(c)
    return kept, dropped


# --------------------------------------------------------------------- CLI

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--out", type=Path, help="write request.json and user_message.txt here")
    ap.add_argument("--response", type=Path,
                    help="a reply to run through steps 5-7: the model's text, or a full "
                         "chat-completions response JSON")
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args()

    system = system_prompt()
    print(f"\n  app             {APP}")
    print(f"  pdf             {args.pdf.name}")

    text = document_text(args.pdf)
    print(f"  1-2 text        {len(text):,} chars after pdftotext -layout + keepIndonesianOnly")
    doc, available = check_fits(text, system)
    print(f"  3   fits        {doc:,} of {available:,} tokens (app estimate) — one call")

    body = request_body(text, system, args.model)
    print(f"  4   request     POST {ENDPOINT}")
    print(f"                  model {body['model']}, max_tokens {body['max_tokens']:,}, "
          f"response_format json_object")
    print(f"                  system {len(system):,} chars, user {len(body['messages'][1]['content']):,} chars")
    print(f"                  NOT SENT — this tool never calls the API")

    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "request.json").write_text(
            json.dumps(body, ensure_ascii=False, indent=2), "utf-8")
        (args.out / "user_message.txt").write_text(body["messages"][1]["content"], "utf-8")
        print(f"\n  wrote {args.out / 'request.json'}")
        print(f"        {args.out / 'user_message.txt'}")

    if args.response:
        content = reply_content(args.response.read_text("utf-8"))
        parsed = parse_reply(content)
        kept, dropped = finalize(parsed)
        print(f"\n  5-6 reply       {len(parsed)} clauses parsed")
        print(f"  7   finalize    {len(kept)} kept, {len(dropped)} dropped")
        for c, why in dropped:
            print(f"        - {c.pasal[:60]:<62} {why}")


if __name__ == "__main__":
    try:
        main()
    except AppError as e:
        sys.exit(f"\n  app error  {e}\n")
