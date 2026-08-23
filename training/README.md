# Training — Unsloth

Fine-tuning runs on a single GPU with Unsloth (LoRA / QLoRA). Full fine-tuning
and multi-node are out of scope; if we need those, the move is Axolotl or TRL+FSDP,
not a bigger Unsloth run.

## Layout

| Path | What |
|---|---|
| `configs/` | One YAML per run. Committed. The config is the experiment record. |
| `datasets/` | Schema, build scripts, redacted samples. Real data goes to a private HF dataset repo. |
| `scripts/` | Training entrypoints. |
| `adapters/` | Local adapter output. Gitignored — the real copy goes to the Hub. |

## Workflow

1. Build the dataset, push to `scalejade/<name>` (private dataset repo). Record the revision.
2. Copy `configs/example-lora.yaml` to `configs/<task>-<date>.yaml` and edit.
3. Run the training entrypoint against that config. Do not edit hyperparameters
   at the command line — if it isn't in the config, it didn't happen.
4. Push the adapter to the Hub. Add the model to `registry/models.yaml`.
5. Run `eval/` against the adapter **before** it goes anywhere near an endpoint.
6. Only then update `registry/deployments.yaml` and deploy.

## Notes

- Unsloth is single-GPU. Plan VRAM around 4-bit base + LoRA, not the full-precision size.
- `max_seq_length` must match what the serving config uses. A model trained at 40960
  and served at 32768 will silently truncate.
- Set `random_state` and `seed`. Unseeded runs cannot be compared.
