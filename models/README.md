# Models

One directory per model we host on `huggingface.co/scalejade`.

```
models/<model-name>/
  README.md        # the HF model card — this file IS what gets pushed to the Hub
  model.config     # vLLM engine args used when serving this model
  weights/         # gitignored. Local snapshot only; the Hub is the real home.
```

**Weights are never committed.** `models/**/weights/` is gitignored. Pull them with
`scripts/download_model.sh`, push them to the Hub with `scripts/clone_model.py`.

**`model.config` must not contain secrets.** `HF_TOKEN` is written as `${HF_TOKEN}`
and injected from `.env` at deploy time.

Adding a model: create the directory, write the card, write `model.config`, add an
entry to `registry/models.yaml`, then evaluate it before it reaches an endpoint.
