#!/usr/bin/env python3
"""
Send request JSON(s) to a RunPod pod or serverless endpoint and merge the results.

    python runpod/scripts/send_request.py runpod/requests/jago-extraction-SINGLE-262k.json --pod-id x3mi36g0033lqq
    python runpod/scripts/send_request.py runpod/requests/jago-extraction-*-of-06.json --pod-id x3mi36g0033lqq
    python runpod/scripts/send_request.py <file> --base-url https://host/v1 --api-key sk-...

Streams by default. That is not a cosmetic choice: a pod's public URL sits behind
Cloudflare, which kills any request whose response has not STARTED within 120 seconds
(HTTP 524). At ~43 tokens/s a 100k-token extraction takes ~40 minutes, so a
non-streaming call can never return. Streaming keeps bytes flowing and the timeout
never fires. The engine finishes the work either way — without streaming you simply
never see the answer, and pay for it anyway.

Every response is checked for truncation. `finish_reason == "length"` means the model
ran out of room mid-answer: clauses go missing with no error anywhere.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent

HEADERS = {
    "Content-Type": "application/json",
    # Cloudflare rejects the default "Python-urllib/3.x" agent with 403 / code 1010.
    "User-Agent": "curl/8.7.1",
    "Accept": "application/json",
}


def load_dotenv() -> None:
    path = REPO / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def open_stream(url: str, key: str, payload: dict, timeout: int):
    req = urllib.request.Request(
        url,
        method="POST",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={**HEADERS, "Authorization": f"Bearer {key}"},
    )
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:600]
        hint = ""
        if e.code == 524:
            hint = ("\n  Cloudflare's 120s timeout. Use streaming (the default here) "
                    "or reach the pod over SSH / a TCP port instead of the HTTP proxy.")
        elif e.code == 403 and "1010" in body:
            hint = "\n  Cloudflare blocked the client signature. Check the User-Agent header."
        sys.exit(f"  HTTP {e.code}: {body}{hint}")
    except urllib.error.URLError as e:
        sys.exit(f"  could not reach the server: {e.reason}")


def stream_completion(url: str, key: str, payload: dict, timeout: int) -> tuple[str, str, dict]:
    """Return (content, finish_reason, usage). Prints progress as tokens arrive."""
    payload = {**payload, "stream": True, "stream_options": {"include_usage": True}}
    parts: list[str] = []
    finish_reason = None
    usage: dict = {}
    n_chunks = 0
    t0 = time.time()
    last_print = 0.0

    with open_stream(url, key, payload, timeout) as resp:
        for raw in resp:
            line = raw.decode("utf-8").strip()
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue

            if obj.get("usage"):
                usage = obj["usage"]
            for choice in obj.get("choices") or []:
                piece = (choice.get("delta") or {}).get("content")
                if piece:
                    parts.append(piece)
                    n_chunks += 1
                if choice.get("finish_reason"):
                    finish_reason = choice["finish_reason"]

            now = time.time()
            if now - last_print >= 5:
                el = now - t0
                print(f"\r      {n_chunks:,} tokens  {el/60:5.1f} min  "
                      f"{n_chunks/max(el,1):5.1f} tok/s", end="", flush=True)
                last_print = now

    el = time.time() - t0
    print(f"\r      {n_chunks:,} tokens  {el/60:5.1f} min  "
          f"{n_chunks/max(el,1):5.1f} tok/s")
    return "".join(parts), finish_reason, usage


def post_once(url: str, key: str, payload: dict, timeout: int) -> tuple[str, str, dict]:
    with open_stream(url, key, {**payload, "stream": False}, timeout) as resp:
        obj = json.loads(resp.read().decode())
    choice = obj["choices"][0]
    return choice["message"]["content"], choice.get("finish_reason"), obj.get("usage", {})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("requests", nargs="+", type=Path)
    ap.add_argument("--pod-id", default=os.environ.get("RUNPOD_POD_ID"),
                    help="pod id -> https://<id>-8000.proxy.runpod.net/v1")
    ap.add_argument("--endpoint-id", default=os.environ.get("RUNPOD_ENDPOINT_ID"),
                    help="serverless endpoint id -> https://api.runpod.ai/v2/<id>/openai/v1")
    ap.add_argument("--base-url", default=os.environ.get("POD_URL"),
                    help="full base URL ending in /v1; overrides the two above")
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--no-stream", action="store_true",
                    help="single non-streaming call. Will hit Cloudflare's 120s cap on a pod.")
    ap.add_argument("--timeout", type=int, default=7200)
    ap.add_argument("--out", type=Path, default=Path("runpod/requests/merged.json"))
    args = ap.parse_args()

    load_dotenv()

    # Pods and serverless endpoints are different products: different URL shape,
    # different key. Pods sit behind the public proxy guarded by VLLM_API_KEY;
    # serverless sits behind the RunPod API and uses RUNPOD_API_KEY.
    if args.base_url:
        base = args.base_url.rstrip("/")
        key = args.api_key or os.environ.get("VLLM_API_KEY") or os.environ.get("RUNPOD_API_KEY")
    elif args.pod_id:
        base = f"https://{args.pod_id}-8000.proxy.runpod.net/v1"
        key = args.api_key or os.environ.get("VLLM_API_KEY")
    elif args.endpoint_id:
        base = f"https://api.runpod.ai/v2/{args.endpoint_id}/openai/v1"
        key = args.api_key or os.environ.get("RUNPOD_API_KEY")
    else:
        sys.exit("pass --pod-id, --endpoint-id, or --base-url")
    if not key:
        sys.exit("no API key: pass --api-key, or set VLLM_API_KEY (pod) / RUNPOD_API_KEY (serverless)")

    url = f"{base}/chat/completions"
    files = sorted(f for f in args.requests if "manifest" not in f.name)
    print(f"\n  POST {url}")
    print(f"  {len(files)} request(s), {'non-streaming' if args.no_stream else 'streaming'}")

    all_clauses: list[dict] = []
    total_in = total_out = 0
    failures: list[str] = []

    for i, f in enumerate(files, 1):
        payload = json.loads(f.read_text(encoding="utf-8"))
        print(f"\n  [{i}/{len(files)}] {f.name}  max_tokens={payload['max_tokens']:,}")

        send = post_once if args.no_stream else stream_completion
        content, reason, usage = send(url, key, payload, args.timeout)

        n_in = usage.get("prompt_tokens", 0)
        n_out = usage.get("completion_tokens", 0)
        total_in += n_in
        total_out += n_out
        print(f"      in={n_in:,}  out={n_out:,}  finish_reason={reason}")

        # Always keep the raw text — a long generation is expensive to redo.
        raw_path = f.parent / f"{f.stem}.raw.txt"
        raw_path.write_text(content, encoding="utf-8")

        if reason == "length":
            failures.append(f"{f.name}: TRUNCATED at {n_out:,} tokens (max_tokens={payload['max_tokens']:,})")
            print(f"      TRUNCATED — output incomplete, clauses are missing. raw -> {raw_path.name}")
            continue

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            failures.append(f"{f.name}: response is not valid JSON ({e})")
            print(f"      not valid JSON — raw output kept at {raw_path.name}")
            continue

        clauses = parsed.get("clauses", [])
        all_clauses.extend(clauses)
        print(f"      {len(clauses)} clauses")

    print(f"\n  total  in={total_in:,}  out={total_out:,}  clauses={len(all_clauses)}")

    if all_clauses:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({"clauses": all_clauses}, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        print(f"  merged -> {args.out}")

    if failures:
        print("\n  FAILURES")
        for msg in failures:
            print(f"    - {msg}")
        print("\n  The merged output is INCOMPLETE. Do not hand it to the legal team.")
        sys.exit(1)

    if len(files) > 1:
        print("\n  NOTE: clauses were extracted per chunk. Header-less clauses are numbered\n"
              "        within their chunk (system prompt rule 1.3.1) — re-number across the\n"
              "        merged set before use.")


if __name__ == "__main__":
    main()
