#!/usr/bin/env python3
"""
Score a deployed extraction model: send labelled rows to a live endpoint exactly as
the app does, parse the replies as the app does, and count the clauses it got right.

    python preparation/evaluate.py --target pbbi-eval --dry-run          # what would be sent
    python preparation/evaluate.py --target pbbi-eval                    # every model it serves
    python preparation/evaluate.py --target pbbi-serverless-extraction --model pbbi-clause-extraction
    python preparation/evaluate.py --target openai                       # gpt-4.1-mini on OpenAI
    python preparation/evaluate.py --url https://<pod>-8000.proxy.runpod.net/v1 \\
                                   --api-key-env VLLM_API_KEY --data preparation/data/eval.jsonl
    python preparation/evaluate.py --check                               # labels vs labels, offline

TARGETS -- a chart under runpod/, looked up by name on the RunPod account
    pod         (pbbi-eval)                    https://<id>-8000.proxy.runpod.net/v1
                                               key: VLLM_API_KEY in runpod/<chart>/.env
    serverless  (pbbi-serverless-extraction)   https://api.runpod.ai/v2/<id>/openai/v1
                                               key: RUNPOD_API_KEY in the root .env
    hosted      (openai)                       https://api.openai.com/v1
                                               key: OPENAI_API_KEY in the root .env
                                               model gpt-4.1-mini, max_tokens 32,768 unless
                                               --model / --max-tokens say otherwise
    --url / --api-key-env reach anything else that speaks OpenAI chat completions.

MODELS
    Default: every name GET /models lists -- on pbbi-eval that is the base AND each
    adapter, so one run compares them on the same pod, the adapter the only variable.
    --model (repeatable) restricts it. Each row goes to each model.

THE REQUEST IS THE APP'S (app_request.request_body): the row's system prompt and
"DOCUMENT:\\n" + text, max_tokens 65,536, response_format json_object, no
temperature. Only stream: true is added, so a 20-minute reply cannot hit a proxy
timeout. --temperature adds a temperature (e.g. 0, greedy) to test a change to
the app's request; without it none is sent, so vLLM applies the model's
generation_config defaults (temperature 1.0). A reply cut at max_tokens (finish_reason "length") is a failure, as in
the app: valid=False, 0 clauses. OpenAI refuses max_tokens above the model's own
output cap (32,768 for gpt-4.1-mini), so the openai target sends that instead, and
a document whose answer is longer ends "length". A 429 or a 5xx is retried, up to
4 times.

SCORING IS TRAINING'S (preparation/score.py): parse_reply + finalize on both the
reply and Legal's labels, then clauses matched one-to-one at >= 0.8 word overlap.
Labels are first scored against themselves; anything under 100% stops the run.

DATA defaults to preparation/data/test.jsonl -- whole documents, never trained on:
the gate before a deploy. eval.jsonl is the validation split (seen as eval loss
during training, never as gradient).

OUTPUT: a table here, and under --out (default preparation/data/scores/<UTC time>/,
gitignored like all of preparation/data): report.json, and every raw reply in
replies/ -- they quote the client contract, so they stay off git.

Costs nothing itself, but every request is GPU time on the target: a whole
document is ~30k output tokens, ~20 min at the ~25 tok/s measured on pbbi-eval.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import app_request as app  # noqa: E402
import score  # noqa: E402

DEFAULT_DATA = HERE / "data" / "test.jsonl"
TIMEOUT_S = 1800          # per socket read: covers a serverless cold start + a 64k prefill
USER_AGENT = "scalejade-mlops-evaluate/1.0"   # Cloudflare 403s urllib's default
RETRY_STATUS = {429, 500, 502, 503}           # a rate limit or a passing overload: nothing generated
RETRIES = 4

# Hosted APIs, reached directly rather than through a runpod/ chart. The key comes
# from the root .env. max_tokens is the API's own output cap: OpenAI rejects the
# app's 65,536 outright, rather than stopping at its cap.
HOSTED = {
    "openai": {"url": "https://api.openai.com/v1", "key": "OPENAI_API_KEY",
               "model": "gpt-4.1-mini", "max_tokens": 32_768},
}


class Fail(Exception):
    pass


# ------------------------------------------------------------------ target

def resolve_target(chart_name: str) -> tuple[str, str]:
    """A runpod/ chart name -> (base URL, API key), from what is live on the account.
    A HOSTED name -> its URL and the key from the root .env."""
    sys.path.insert(0, str(REPO / "runpod"))
    import deploy
    if chart_name in HOSTED:
        hosted = HOSTED[chart_name]
        if (REPO / ".env").exists():
            deploy.load_dotenv()
        key = os.environ.get(hosted["key"], "")
        if not key:
            raise Fail(f"{hosted['key']} is not set — add it to the root .env (see .env.example)")
        return hosted["url"], key
    try:
        deploy.load_dotenv()
        chart = deploy.load_chart(chart_name)
        live = deploy.find_by_name(deploy.KINDS[chart["kind"]], chart["name"])
    except deploy.Fail as e:
        raise Fail(str(e))
    if not live:
        raise Fail(f"{chart['kind']} '{chart_name}' is not deployed on this account — "
                   f"python runpod/deploy.py apply {chart_name}")
    if chart["kind"] == "serverless":
        return f"https://api.runpod.ai/v2/{live['id']}/openai/v1", os.environ["RUNPOD_API_KEY"]
    if chart["kind"] == "pod":
        key = chart["secrets"].get("VLLM_API_KEY", "")
        if not key:
            raise Fail(f"VLLM_API_KEY is not in runpod/{chart_name}/.env")
        return f"https://{live['id']}-8000.proxy.runpod.net/v1", key
    raise Fail(f"'{chart_name}' is a {chart['kind']}, not something that serves a model")


def http(method: str, url: str, key: str, body: dict | None = None, timeout: int = 60):
    req = urllib.request.Request(
        url, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "User-Agent": USER_AGENT})
    return urllib.request.urlopen(req, timeout=timeout)


def list_models(base: str, key: str) -> list[str]:
    try:
        with http("GET", f"{base}/models", key) as r:
            return [m["id"] for m in json.loads(r.read()).get("data", [])]
    except urllib.error.HTTPError as e:
        raise Fail(f"GET {base}/models -> {e.code}: {e.read().decode()[:300]}")
    except urllib.error.URLError as e:
        raise Fail(f"could not reach {base}: {e.reason}")


# ---------------------------------------------------------------- requests

def stream_completion(base: str, key: str, body: dict) -> dict:
    """POST a streaming chat completion; return the reply and how it ended.
    Reads server-sent events: `data: {chunk}` lines, then `data: [DONE]`."""
    body = {**body, "stream": True, "stream_options": {"include_usage": True}}
    started = time.time()
    first = None
    parts: list[str] = []
    finish, usage, chunks = None, {}, 0
    with http("POST", f"{base}/chat/completions", key, body, timeout=TIMEOUT_S) as r:
        for raw in r:
            line = raw.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            chunk = json.loads(data)
            if chunk.get("usage"):
                usage = chunk["usage"]
            for choice in chunk.get("choices") or []:
                text = (choice.get("delta") or {}).get("content")
                if text:
                    if first is None:
                        first = time.time()
                    parts.append(text)
                    chunks += 1
                if choice.get("finish_reason"):
                    finish = choice["finish_reason"]
    ended = time.time()
    tokens = usage.get("completion_tokens") or chunks
    gen = ended - (first or ended)
    return {"content": "".join(parts), "finish": finish or "?", "output_tokens": tokens,
            "seconds": round(ended - started, 1),
            "first_token_s": round((first or ended) - started, 1),
            "tok_per_s": round(tokens / gen, 1) if gen > 0 else 0.0}


def retry_wait(e: urllib.error.HTTPError, attempt: int) -> float:
    """The server's Retry-After when it sends one, else 15 s, 30 s, 60 s, ..."""
    try:
        return max(0.0, float(e.headers.get("Retry-After", "")))
    except (TypeError, ValueError):
        return 15.0 * 2 ** attempt


def run_one(base: str, key: str, model: str, i: int, row: dict, max_tokens: int,
            temperature: float | None = None) -> dict:
    msgs = row["messages"]
    document = msgs[1]["content"].removeprefix(app.DOCUMENT_PREFIX)
    body = app.request_body(document, msgs[0]["content"], model)
    body["max_tokens"] = max_tokens
    if temperature is not None:   # not the app's request: it sends none
        body["temperature"] = temperature
    base_result = {"model": model, "row": i}
    for attempt in range(RETRIES + 1):
        try:
            reply = stream_completion(base, key, body)
            break
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:300]
            # insufficient_quota is a 429 too, but waiting does not add credit.
            if e.code in RETRY_STATUS and attempt < RETRIES and "insufficient_quota" not in detail:
                wait = retry_wait(e, attempt)
                print(f"    {model[:30]:<30} row {i:<3} HTTP {e.code}, retry in {wait:.0f}s")
                time.sleep(wait)
                continue
            return base_result | {"error": f"HTTP {e.code}: {detail}"}
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
            return base_result | {"error": f"{type(e).__name__}: {e}"}
    # postChatCompletion: a reply cut at max_tokens is an error, not a reply.
    content = reply["content"] if reply["finish"] != "length" else ""
    return base_result | reply | {"finished": reply["finish"] == "stop"} | \
        score.score_reply(content, msgs[2]["content"])


# -------------------------------------------------------------------- data

def load_rows(path: Path) -> list[dict]:
    if not path.exists():
        raise Fail(f"{path} not found — python preparation/build.py builds it")
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def row_docs(path: Path, n: int) -> list[str]:
    """Document name per row, from build-report.json beside the data (train/eval/test)."""
    try:
        report = json.loads((path.parent / "build-report.json").read_text("utf-8"))
        meta = report[path.stem]["meta"]
        return [m.get("doc", f"row {i}") for i, m in enumerate(meta)][:n] + \
            [f"row {i}" for i in range(len(meta), n)]
    except (OSError, KeyError, ValueError):
        return [f"row {i}" for i in range(n)]


def parse_rows(spec: str | None, n: int) -> list[int]:
    if not spec:
        return list(range(n))
    out: list[int] = []
    for part in spec.split(","):
        lo, _, hi = part.partition("-")
        out.extend(range(int(lo), int(hi or lo) + 1))
    bad = [i for i in out if not 0 <= i < n]
    if bad:
        raise Fail(f"--rows {spec}: the data has rows 0-{n - 1}")
    return out


def self_check(rows: list[dict], picked: list[int]) -> None:
    """Legal's labels scored against themselves must match 100%, or the scorer is broken."""
    for i in picked:
        labels = rows[i]["messages"][2]["content"]
        try:
            r = score.score_reply(labels, labels)
        except app.AppError as e:
            raise Fail(f"row {i}: the labels do not parse ({e}) — nothing was sent")
        if not (r["json_valid"] and r["matched"] == r["labelled"] == r["predicted"]):
            raise Fail(f"row {i}: labels vs themselves matched {r['matched']}/{r['labelled']} "
                       f"— the scorer or the row is broken; nothing was sent")


# --------------------------------------------------------------------- CLI

def pct(x: float) -> str:
    return f"{x:.3f}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    where = ap.add_mutually_exclusive_group()
    where.add_argument("--target", help="a runpod/ chart: pbbi-eval, pbbi-serverless-extraction, ...; "
                                        f"or a hosted API: {', '.join(HOSTED)}")
    where.add_argument("--url", help="an OpenAI-compatible base URL, ending in /v1")
    where.add_argument("--check", action="store_true",
                       help="score the labels against themselves and stop; no network")
    ap.add_argument("--api-key-env", default="VLLM_API_KEY",
                    help="with --url: the environment variable holding the key")
    ap.add_argument("--model", action="append",
                    help="a served model name (repeatable); default every one GET /models lists")
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA)
    ap.add_argument("--rows", help="e.g. 0 or 0,2-3; default all")
    ap.add_argument("--parallel", type=int, default=2,
                    help="requests in flight (default 2 = pbbi-eval's max_num_seqs)")
    ap.add_argument("--max-tokens", type=int,
                    help=f"default {app.MAX_OUTPUT_TOKENS:,}, the app's own; "
                         "a hosted API's output cap for a hosted --target")
    ap.add_argument("--temperature", type=float,
                    help="add a temperature to the request (0 = greedy); default none, as the app")
    ap.add_argument("--out", type=Path, help="default preparation/data/scores/<UTC time>/")
    ap.add_argument("--dry-run", action="store_true", help="resolve and list; send nothing")
    args = ap.parse_args()
    # A hosted API lists every model it has: without --model, every row would go to all of them.
    hosted = HOSTED.get(args.target, {})
    args.model = args.model or ([hosted["model"]] if hosted else None)
    args.max_tokens = args.max_tokens or hosted.get("max_tokens") or app.MAX_OUTPUT_TOKENS

    rows = load_rows(args.data)
    picked = parse_rows(args.rows, len(rows))
    docs = row_docs(args.data, len(rows))
    print(f"\n  data       {args.data.relative_to(REPO) if args.data.is_relative_to(REPO) else args.data}"
          f"   rows {','.join(map(str, picked))} of {len(rows)}")
    for i in picked:
        if rows[i]["messages"][0]["content"] != app.system_prompt():
            print(f"  !!  row {i}: system prompt differs from prompts/extraction_system.md "
                  f"— rebuild the data, or the request is not the app's")

    self_check(rows, picked)
    print(f"  scorer     labels vs themselves: 100% on every row")
    if args.check:
        for i in picked:
            r = score.score_reply(rows[i]["messages"][2]["content"], rows[i]["messages"][2]["content"])
            print(f"    row {i:<3} {docs[i][:44]:<44} {r['labelled']} clauses")
        return
    if not (args.target or args.url):
        raise Fail("say where: --target <chart>, --url <base>, or --check")

    if args.target:
        base, key = resolve_target(args.target)
    else:
        base = args.url.rstrip("/")
        key = os.environ.get(args.api_key_env, "")
        if not key:
            raise Fail(f"${args.api_key_env} is not set")
    print(f"  endpoint   {base}")
    if args.dry_run:
        # Not even GET /models: on a serverless endpoint any request can wake a worker.
        print(f"  models     {', '.join(args.model) if args.model else 'every one GET /models lists'}")
        print(f"  requests   {len(args.model or ['?']) * len(picked)} "
              f"({len(picked)} row(s) per model), max_tokens {args.max_tokens:,}, "
              f"temperature {'none' if args.temperature is None else args.temperature}")
        print("\n  dry run — nothing sent to the endpoint\n")
        return

    served = list_models(base, key)
    models = args.model or served
    missing = [m for m in models if m not in served]
    if missing:
        raise Fail(f"not served there: {', '.join(missing)}   (served: {', '.join(served)})")
    print(f"  models     {', '.join(models)}")
    jobs = [(m, i) for m in models for i in picked]
    print(f"  requests   {len(jobs)}, {args.parallel} at a time, max_tokens {args.max_tokens:,}, "
          f"temperature {'none' if args.temperature is None else args.temperature}")

    out = args.out or HERE / "data" / "scores" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (out / "replies").mkdir(parents=True, exist_ok=True)
    print(f"  out        {out}\n")

    results: list[dict] = []

    def job(m: str, i: int) -> dict:
        r = run_one(base, key, m, i, rows[i], args.max_tokens, args.temperature)
        reply = r.pop("content", None)
        if reply is not None:
            (out / "replies" / f"{m.replace('/', '__')}__row{i}.txt").write_text(reply, "utf-8")
        if "error" in r:
            print(f"    {m[:30]:<30} row {i:<3} ERROR {r['error']}")
        else:
            print(f"    {m[:30]:<30} row {i:<3} {r['finish']:<6} valid={r['json_valid']!s:<5} "
                  f"matched {r['matched']}/{r['labelled']} (returned {r['predicted']})  "
                  f"{r['output_tokens']:,} tok  {r['tok_per_s']} tok/s  {r['seconds'] / 60:.1f} min")
        return r

    with ThreadPoolExecutor(max_workers=max(1, args.parallel)) as pool:
        results = list(pool.map(lambda mi: job(*mi), jobs))

    summary = {}
    print(f"\n  {'model':<40} {'recall':>7} {'precis':>7} {'f1':>7} {'count':>6} "
          f"{'valid':>6} {'done':>5} {'errors':>6}")
    for m in models:
        ok = [r for r in results if r["model"] == m and "error" not in r]
        errors = sum(1 for r in results if r["model"] == m and "error" in r)
        s = score.summarize(ok) if ok else {}
        s |= {"finished": sum(r["finished"] for r in ok) / len(ok) if ok else 0.0,
              "errors": errors}
        summary[m] = s
        print(f"  {m[:40]:<40} {pct(s.get('recall', 0)):>7} {pct(s.get('precision', 0)):>7} "
              f"{pct(s.get('f1', 0)):>7} {s.get('count_ratio', 0):>6.2f} "
              f"{s.get('json_valid', 0):>6.2f} {s['finished']:>5.2f} {errors:>6}")

    (out / "report.json").write_text(json.dumps({
        "endpoint": base, "target": args.target, "data": str(args.data), "rows": picked,
        "docs": {i: docs[i] for i in picked}, "max_tokens": args.max_tokens,
        "temperature": args.temperature,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": summary, "results": results,
    }, ensure_ascii=False, indent=2), "utf-8")
    print(f"\n  report     {out / 'report.json'}\n")
    if any("error" in r for r in results):
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Fail as e:
        sys.exit(f"\n  error  {e}\n")
    except KeyboardInterrupt:
        sys.exit(130)
