# Datasets

**Rule: no raw client documents in git.** Bank contracts, statements, and anything
under NDA stay out of this repo. Push the dataset to a **private** Hugging Face
dataset repo under `scalejade/` and record the repo name plus the commit sha in the
training config. What lives here is the schema, the build script, and a small
redacted sample.

```
training/datasets/
  <task-name>/
    README.md          where the data came from, how many rows, how it was built
    build.py           raw -> jsonl, deterministic and re-runnable
    sample.jsonl       ~10 redacted rows, so a reviewer can see the shape
```

## Format

JSONL, one object per line, one conversation per line. `train.py` expects exactly
one column, `messages`:

```json
{"messages": [
  {"role": "system", "content": "You extract clauses from Indonesian loan agreements."},
  {"role": "user", "content": "<document text>"},
  {"role": "assistant", "content": "{\"clauses\": [...]}"}
]}
```

The base model's own chat template renders it; the config never hardcodes special
tokens. With `train_on_responses_only: true` (the default) loss is computed on the
assistant turns only — training on the prompt teaches the model to predict our own
instructions back at us.

For structured output, make the assistant turn the exact string the caller must be
able to parse — same key order, same escaping, nothing before or after it. The model
reproduces what it is shown, formatting quirks included.

## Thinking blocks (Qwen-SEA-LION v4.5)

This base is a reasoning model, and its chat template rewrites every assistant turn.
Rendered from the repo's own `chat_template.jinja` on 2026-08-25, a row with **no**
`<think>` in it comes out as:

```
<|im_start|>system\nYou extract clauses.<|im_end|>
<|im_start|>user\n<DOC><|im_end|>
<|im_start|>assistant\n<think>\n\n</think>\n\n{"clauses": []}<|im_end|>
```

The empty `<think>` block is inserted for you. That is the behaviour you want for
extraction: the serving prompt ends at `<|im_start|>assistant\n<think>\n`, and the
model has been trained to close the block immediately and go straight to the JSON.

If a row *does* contain `<think>…</think>` in the assistant content, the template
pulls the reasoning out and keeps it — but only on the final assistant turn; earlier
turns in the same conversation are re-rendered with their reasoning stripped.

Decide this once, per dataset, and write it in the dataset README:

- **No reasoning in the data** — the model learns to answer directly. Then the
  endpoint should send `enable_thinking: false`, or accept an empty think block in
  every response and strip it.
- **Reasoning in the data** — the model learns to think first, which costs output
  tokens and pushes toward the `finish_reason: "length"` trap. Raise `max_tokens`
  accordingly and count the reasoning in your budget.

Mixing the two in one dataset teaches the model that thinking is optional and it
will decide on its own, per request. That is the worst of the three.

## Splits

Commit a fixed train/eval split **by row id**, never a random seed at load time. A
split that moves between runs makes every comparison between runs meaningless.

The eval split here is for watching the loss curve, and that is all it is for. It is
not the quality gate — that is `eval/`, against a human-verified golden set. A better
eval loss is not evidence that the product improved.

## Length

`train.py` prints the max and p95 token length of every split against
`model.max_seq_length`, and says how many rows will be truncated. Truncation happens
mid-example and silently: the model is trained on a document whose answer was cut
off. Either raise the window or drop those rows — do not ignore the warning.
