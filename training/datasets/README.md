# Datasets

Training data lives here as JSONL, one JSON object per line, in the chat format
the base model expects.

**Rule: no raw client documents in git.** Bank contracts, statements, and anything
under NDA stay out of this repo. Push datasets to a **private** Hugging Face dataset
repo under `scalejade/` and record the repo name plus revision in the training config.
What lives here is the schema, the build script, and a small redacted sample.

```
training/datasets/
  <task-name>/
    README.md          # where the data came from, how many rows, how it was built
    build.py           # raw -> jsonl, deterministic and re-runnable
    sample.jsonl       # ~10 redacted rows so a reviewer can see the shape
```

Every dataset needs a fixed train/eval split committed by row ID, not a random
seed at load time. A split that moves between runs makes every comparison meaningless.
