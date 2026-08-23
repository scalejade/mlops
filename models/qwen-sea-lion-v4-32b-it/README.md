---
language:
- en
- zh
- vi
- id
- th
- fil
- ta
- ms
- km
- lo
- my
base_model:
- Qwen/Qwen3-32B
- aisingapore/Qwen-SEA-LION-v4-32B-IT
base_model_relation: finetune
library_name: transformers
pipeline_tag: text-generation
license: mit
tags:
- southeast-asia
- sea-lion
- qwen3
- instruction-tuned
- multilingual
---

# Qwen-SEA-LION-v4-32B-IT

A 32B-parameter instruction-tuned large language model for Southeast Asian languages, hosted by **Scalejade** as a redistribution of AI Singapore's [`aisingapore/Qwen-SEA-LION-v4-32B-IT`](https://huggingface.co/aisingapore/Qwen-SEA-LION-v4-32B-IT). All model weights, training work, and evaluation were produced by the SEA-LION team at AI Singapore; this repository exists to make the model conveniently available inside the Scalejade workspace and to standardize how we consume it in downstream MLOps pipelines.

## Overview

Qwen-SEA-LION-v4-32B-IT is built on top of [Qwen3-32B](https://huggingface.co/Qwen/Qwen3-32B) and specialized for the Southeast Asian region. It was continue-pretrained on roughly **100B tokens** sampled from the SEA-Pile v2 corpus across seven SEA languages — Burmese, Indonesian, Malay, Filipino, Tamil, Thai, and Vietnamese — and then post-trained on approximately **8M high-quality instruction pairs** to produce the final instruct model. It supports a **32,768-token** native context window and inherits Qwen3's optional thinking mode (`enable_thinking=True`).

The model is intended for research and commercial use on SEA-language workloads: multilingual assistants, translation, retrieval-augmented generation over regional content, summarization, classification, and instruction-following tasks where a stronger SEA-language foundation matters.

## Model Details

| Field | Value |
|---|---|
| Architecture | Decoder-only Transformer (Qwen3) |
| Parameters | ~32B |
| Context length | 32,768 tokens |
| Tokenizer | Qwen3-32B default |
| Languages | Burmese, English, Indonesian, Khmer, Lao, Malay, Mandarin, Tagalog, Tamil, Thai, Vietnamese |
| Base model | [Qwen/Qwen3-32B](https://huggingface.co/Qwen/Qwen3-32B) |
| Upstream release | [aisingapore/Qwen-SEA-LION-v4-32B-IT](https://huggingface.co/aisingapore/Qwen-SEA-LION-v4-32B-IT) |
| License | MIT |
| Hosted by | [Scalejade](https://huggingface.co/scalejade) |
| Original developer | AI Products Pillar, AI Singapore |

Related upstream variants (quantized): [`Qwen-SEA-LION-v4-32B-IT-8BIT`](https://huggingface.co/aisingapore/Qwen-SEA-LION-v4-32B-IT-8BIT), [`Qwen-SEA-LION-v4-32B-IT-4BIT`](https://huggingface.co/aisingapore/Qwen-SEA-LION-v4-32B-IT-4BIT).

## Intended Use

Recommended: multilingual chat and instruction-following across SEA languages, translation between English and SEA languages, summarization, extractive/abstractive QA, cultural-context tasks, and as a starting point for domain-specific fine-tunes.

Not recommended without additional work: any application requiring hard safety guarantees, medical or legal advice, or use cases where hallucination has material consequences. The model **has not been safety-aligned**. Teams deploying it must add their own safety fine-tuning, content filtering, and evaluation.

## How to Use

```python
from transformers import AutoModelForCausalLM, AutoTokenizer

model_name = "scalejade/qwen-sea-lion-v4-32b-it"

tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(
    model_name,
    torch_dtype="auto",
    device_map="auto",
)

messages = [
    {"role": "user", "content": "Tuliskan puisi singkat tentang senja di Jakarta."},
]
text = tokenizer.apply_chat_template(
    messages,
    tokenize=False,
    add_generation_prompt=True,
    enable_thinking=False,  # set True to enable Qwen3 thinking mode
)
inputs = tokenizer([text], return_tensors="pt").to(model.device)
generated = model.generate(**inputs, max_new_tokens=1024)
print(tokenizer.decode(generated[0][inputs.input_ids.shape[-1]:], skip_special_tokens=True))
```

Thinking-mode parsing follows the upstream convention: after generation, split on the thinking end-of-block token (`151668`) to separate reasoning from the final answer.

## Training

Upstream training was performed by AI Singapore. Continue-pretraining used ~100B tokens drawn from SEA-Pile v2 spanning seven SEA languages, followed by instruction fine-tuning on ~8M OSS and synthetic instruction pairs, with model merging as part of the post-training pipeline. No additional training has been performed by Scalejade on the weights hosted here — this repository is a redistribution.

## Evaluation

The upstream model was evaluated on the [SEA-HELM benchmark](https://arxiv.org/abs/2502.14301) across general-language tasks (QA, sentiment, toxicity, translation both directions, abstractive summarization, causal reasoning, NLI, LINDSEA, Kalahi, Global MMLU Lite) as well as SEA-IFEval (instruction-following) and SEA-MTBench (multi-turn chat, judged by `gpt-4.1-2025-04-14`). Evaluation was zero-shot with native-language prompts, averaged across 8 seeds. Live results: [leaderboard.sea-lion.ai](https://leaderboard.sea-lion.ai/).

## Limitations

Like any LLM this model can hallucinate, produce factually incorrect content, or generate text that is inconsistent across turns. It has not been tested against adversarial prompting and has not undergone safety alignment. Performance in the eleven listed languages is uneven — the strongest results are in the seven SEA languages that were part of continued pretraining. Users are responsible for validating outputs before acting on them.

## License

MIT — see [https://mit-license.org/](https://mit-license.org/). Same terms as the upstream release.

## Attribution

All credit for the model itself belongs to the SEA-LION team at AI Singapore. If you use this model in research or production, please cite the upstream project and follow AI Singapore's attribution guidance at [sea-lion.ai](https://sea-lion.ai/).

For questions about the underlying model or the SEA-LION project, contact the original authors at [sealion@aisingapore.org](mailto:sealion@aisingapore.org). For questions about this Scalejade-hosted mirror, contact the Scalejade team.

## Acknowledgements

The SEA-LION project is supported by the National Research Foundation Singapore and the Infocomm Media Development Authority (IMDA) under Singapore's National Large Language Model Funding Initiative. Scalejade thanks the AI Singapore team for open-sourcing this work.
