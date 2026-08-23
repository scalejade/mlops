# Requests

Ready-to-send RunPod payloads, generated from the `=== MODEL / SYSTEM PROMPT / USER
MESSAGE ===` files in `scratch/`.

**These files embed client documents. They are gitignored.** Regenerate them instead
of committing them.

## Generate

```bash
pip install transformers

# Against the current 40,960-token endpoint (splits automatically if needed)
python runpod/scripts/build_request.py "scratch/[jago] - req - extraction.txt"

# Against a long-context model
python runpod/scripts/build_request.py "scratch/[jago] - req - extraction.txt" \
    --model scalejade/qwen-sea-lion-v4.5-27b-it --context 262144
```

It counts tokens with the real Qwen3 tokenizer (the base of every SEA-LION v4 model),
including chat-template overhead, then budgets for generation before it writes anything.
If input + estimated output exceeds the window it splits the document on section
boundaries and writes one request per chunk, plus a manifest with the full budget.

The output estimate uses a ratio measured from our own BCA run: 10,280 document tokens
produced 17,258 output tokens, so extraction output ≈ **1.68× the document**. Verbatim
copying plus JSON scaffolding makes output larger than input, which is exactly why
budgeting on input alone silently loses clauses.

## Send

```bash
python runpod/scripts/send_request.py runpod/requests/jago-req-extraction-*.json \
    --endpoint-id $RUNPOD_ENDPOINT_ID
```

Sends each request, checks `finish_reason` on every response, merges the `clauses`
arrays, and exits non-zero if anything truncated or came back as invalid JSON.

## Truncation

A response that hits `max_tokens` returns **HTTP 200** with `finish_reason: "length"`
and a JSON body cut off mid-object. Nothing raises. This is how we lost roughly seven
clauses per document on the BCA run.

Both scripts treat it as a hard failure. Any caller you write must do the same:

```python
if resp.choices[0].finish_reason == "length":
    raise RuntimeError("output truncated — clauses are missing")
```

## Chunked runs

When a document is split, each chunk is extracted independently. Two consequences:

- **Header-less clauses restart numbering per chunk** (system prompt rule 1.3.1).
  Re-number across the merged set before handing anything to the legal team.
- **Cross-chunk parent/child inheritance is lost** (rule 7). Splitting on section
  boundaries keeps parents with their children, which is why `build_request.py` splits
  on roman-numeral headers rather than at a fixed token offset.

Chunking is a workaround for a context window that is too small. The real fix is a
long-context model.
