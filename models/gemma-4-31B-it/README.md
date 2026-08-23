# gemma-4-31B-it-baseline

Hub repo: <https://huggingface.co/scalejade/gemma-4-31B-it-baseline> (private)

Cloned from [`google/gemma-4-31B-it-qat-w4a16-ct`](https://huggingface.co/google/gemma-4-31B-it-qat-w4a16-ct) at revision
`main` (commit `52f3f65bc7a02d555763bc923bd1d9094898219d`) on 2026-08-16.

No weights are stored in this directory — the clone lives on the Hub. This file
is the local record of it.

## Contents

| File | Size |
| --- | --- |
| `model.safetensors` | 23.27 GB |
| `tokenizer.json` | 32.2 MB |
| `README.md` | 29.4 KB |
| `config.json` | 18.7 KB |
| `chat_template.jinja` | 18.7 KB |
| `tokenizer_config.json` | 3.7 KB |
| `processor_config.json` | 1.7 KB |
| `.gitattributes` | 1.6 KB |
| `generation_config.json` | 208 B |
| **Total** | **23.30 GB** |

## Reproduce

```bash
./scripts/clone_model.py google/gemma-4-31B-it-qat-w4a16-ct gemma-4-31B-it-baseline
```

## Pull the weights onto a machine

```bash
MODELS_DIR=/runpod-volume/models ./scripts/download_model.sh scalejade/gemma-4-31B-it-baseline gemma-4-31B-it-baseline
```
