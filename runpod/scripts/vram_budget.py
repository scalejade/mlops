#!/usr/bin/env python3
"""
VRAM budget for serving a model with vLLM. Answers "which GPU, and how much context".

    python runpod/scripts/vram_budget.py --model qwen-sea-lion-v4.5-27b-it

Model shapes are recorded below from each model's config.json. Verify a new model with:

    python -c "import json,urllib.request as u; \
      print(json.load(u.urlopen('https://huggingface.co/<repo>/raw/main/config.json')))"
"""

from __future__ import annotations
import argparse

GB = 1024 ** 3

MODELS = {
    # Qwen3.5 hybrid attention: only 1 in every `full_attention_interval` layers keeps
    # a growing KV cache. The linear-attention layers hold a fixed-size state instead,
    # which is why a 262k window is affordable at all.
    "qwen-sea-lion-v4.5-27b-it": {
        "weights_gb": 55.59,          # measured: 15 safetensors shards on the Hub
        "layers": 64,
        "full_attention_interval": 4,  # -> 16 full-attention layers
        "kv_heads": 4,
        "head_dim": 256,
        "native_context": 262144,
        "arch": "Qwen3_5ForConditionalGeneration (hybrid attention, multimodal)",
    },
    "qwen-sea-lion-v4-32b-it": {
        "weights_gb": 65.5,
        "layers": 64,
        "full_attention_interval": 1,  # every layer is full attention
        "kv_heads": 8,
        "head_dim": 128,
        "native_context": 40960,
        "arch": "Qwen3ForCausalLM",
    },
}

GPUS = [
    ("RTX PRO 6000",  96, 2.09),
    ("H100 NVL",      94, 3.19),
    ("H100 SXM",      80, 3.29),
    ("H200",         141, 4.59),
    ("B200",         180, 6.79),
]

OVERHEAD_GB = 4.0     # activations, CUDA graphs, NCCL buffers, fragmentation


def kv_bytes_per_token(m: dict, kv_dtype_bytes: int) -> int:
    full_layers = m["layers"] // m["full_attention_interval"]
    return 2 * full_layers * m["kv_heads"] * m["head_dim"] * kv_dtype_bytes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen-sea-lion-v4.5-27b-it", choices=list(MODELS))
    ap.add_argument("--kv-dtype", default="fp8", choices=["fp8", "bf16"])
    ap.add_argument("--util", type=float, default=0.90, help="GPU_MEMORY_UTILIZATION")
    args = ap.parse_args()

    m = MODELS[args.model]
    kv_bytes = kv_bytes_per_token(m, 1 if args.kv_dtype == "fp8" else 2)
    full_layers = m["layers"] // m["full_attention_interval"]

    print(f"\n  model          {args.model}")
    print(f"  architecture   {m['arch']}")
    print(f"  weights        {m['weights_gb']:.1f} GB (bf16)")
    print(f"  full-attn      {full_layers} of {m['layers']} layers keep a KV cache")
    print(f"  KV per token   {kv_bytes / 1024:.0f} KiB  ({args.kv_dtype})")
    print(f"  overhead       {OVERHEAD_GB:.1f} GB assumed\n")

    contexts = [40960, 65536, 131072, 163840, 262144]
    seqs = [1, 2, 4, 8]

    print(f"  {'context':>9} | " + " | ".join(f"{n} seq".rjust(9) for n in seqs) + "   (total VRAM GB)")
    print("  " + "-" * (11 + len(seqs) * 12))
    rows = {}
    for ctx in contexts:
        if ctx > m["native_context"]:
            continue
        cells = []
        for n in seqs:
            total = m["weights_gb"] + (kv_bytes * ctx * n) / GB + OVERHEAD_GB
            cells.append(total)
            rows[(ctx, n)] = total
        print(f"  {ctx:>9,} | " + " | ".join(f"{v:9.1f}" for v in cells))

    print(f"\n  usable VRAM at GPU_MEMORY_UTILIZATION={args.util}:")
    for name, vram, price in GPUS:
        print(f"    {name:<14} {vram:>4} GB -> {vram * args.util:6.1f} GB usable   ${price}/hr")

    print("\n  largest workable (context, concurrency) per GPU:")
    for name, vram, price in GPUS:
        usable = vram * args.util
        best = [(ctx, n) for (ctx, n), v in rows.items() if v <= usable]
        if not best:
            print(f"    {name:<14} does not fit this model at bf16 weights")
            continue
        max_ctx = max(c for c, _ in best)
        max_n = max(n for c, n in best if c == max_ctx)
        print(f"    {name:<14} {max_ctx:>7,} tokens x {max_n} concurrent   "
              f"({rows[(max_ctx, max_n)]:.1f} / {usable:.1f} GB)")
    print()


if __name__ == "__main__":
    main()
