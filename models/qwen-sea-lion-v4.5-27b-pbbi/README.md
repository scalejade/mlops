# qwen-sea-lion-v4.5-27b-pbbi

Hub repo: <https://huggingface.co/scalejade/qwen-sea-lion-v4.5-27b-pbbi> (private)

Cloned from [`scalejade/qwen-sea-lion-v4.5-27b-it`](https://huggingface.co/scalejade/qwen-sea-lion-v4.5-27b-it) at revision
`main` (commit `81d9102bab84b46085cc0f8539efe578d33e29da`) on 2026-09-12.

No weights are stored in this directory — the clone lives on the Hub. This file
is the local record of it.

## Contents

| File | Size |
| --- | --- |
| `model-00013-of-00015.safetensors` | 4.00 GB |
| `model-00007-of-00015.safetensors` | 3.99 GB |
| `model-00001-of-00015.safetensors` | 3.97 GB |
| `model-00014-of-00015.safetensors` | 3.94 GB |
| `model-00002-of-00015.safetensors` | 3.92 GB |
| `model-00009-of-00015.safetensors` | 3.92 GB |
| `model-00011-of-00015.safetensors` | 3.92 GB |
| `model-00012-of-00015.safetensors` | 3.92 GB |
| `model-00003-of-00015.safetensors` | 3.92 GB |
| `model-00004-of-00015.safetensors` | 3.92 GB |
| `model-00010-of-00015.safetensors` | 3.92 GB |
| `model-00005-of-00015.safetensors` | 3.92 GB |
| `model-00006-of-00015.safetensors` | 3.90 GB |
| `model-00008-of-00015.safetensors` | 3.88 GB |
| `model-00015-of-00015.safetensors` | 508.7 MB |
| `tokenizer.json` | 12.8 MB |
| `vocab.json` | 6.7 MB |
| `merges.txt` | 3.4 MB |
| `Qwen-SEA-LION-v4.5.png` | 1.7 MB |
| `SEA-HELM_20_May_2026_200B-ver2.png` | 297.2 KB |
| `model.safetensors.index.json` | 112.2 KB |
| `README.md` | 23.4 KB |
| `tokenizer_config.json` | 16.7 KB |
| `LICENSE` | 11.3 KB |
| `chat_template.jinja` | 7.8 KB |
| `config.json` | 4.3 KB |
| `.gitattributes` | 1.9 KB |
| `preprocessor_config.json` | 390 B |
| `video_preprocessor_config.json` | 385 B |
| `generation_config.json` | 202 B |
| `configuration.json` | 51 B |
| **Total** | **55.59 GB** |

## Reproduce

```bash
./scripts/clone_model.py scalejade/qwen-sea-lion-v4.5-27b-it qwen-sea-lion-v4.5-27b-pbbi
```

## Pull the weights onto a machine

```bash
MODELS_DIR=/runpod-volume/models ./scripts/download_model.sh scalejade/qwen-sea-lion-v4.5-27b-pbbi qwen-sea-lion-v4.5-27b-pbbi
```
