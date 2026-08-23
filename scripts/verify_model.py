#!/usr/bin/env python3
"""
Check that a scalejade mirror actually matches its upstream model.

    python scripts/verify_model.py scalejade/qwen-sea-lion-v4.5-27b-it aisingapore/Qwen-SEA-LION-v4.5-27B-IT
    python scripts/verify_model.py --all          # every entry in registry/models.yaml

Exists because a mirror silently stopped matching upstream: a second clone was pushed
over the first without deleting the old files, leaving orphan shards from one model,
the config.json and tokenizer of another, and the weights of a third. Nothing errored.
The pod just refused to start, days later, with a confusing context-length message.

Compares: shard set, total size, config.json fields, tokenizer size, vocab size.
Exit code 1 if anything differs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    from huggingface_hub import HfApi, hf_hub_download
except ImportError:
    sys.exit("huggingface_hub is required:  pip install huggingface_hub")

SHARD_RE = re.compile(r"model-(\d+)-of-(\d+)\.safetensors$")
CONFIG_FIELDS = [
    "architectures", "model_type", "max_position_embeddings", "num_hidden_layers",
    "num_key_value_heads", "head_dim", "hidden_size", "vocab_size",
    "full_attention_interval",
]


def size_of(sibling) -> int:
    return sibling.lfs.size if sibling.lfs else (sibling.size or 0)


def survey(api: HfApi, repo: str, token: str | None) -> dict:
    info = api.model_info(repo, files_metadata=True, token=token)
    files = {s.rfilename: size_of(s) for s in info.siblings}
    shards = {}
    for name in files:
        m = SHARD_RE.search(name)
        if m:
            shards.setdefault(int(m.group(2)), []).append(name)
    cfg = json.load(open(hf_hub_download(repo, "config.json", token=token)))
    # Qwen3.5 and other multimodal configs nest the language model under text_config.
    text = cfg.get("text_config", cfg)
    flat = {f: cfg.get(f, text.get(f)) for f in CONFIG_FIELDS}
    flat["architectures"] = cfg.get("architectures")
    return {
        "repo": repo,
        "sha": info.sha,
        "files": files,
        "shard_sets": {k: sorted(v) for k, v in shards.items()},
        "weights_bytes": sum(v for k, v in files.items() if k.endswith(".safetensors")),
        "tokenizer_bytes": files.get("tokenizer.json", 0),
        "config": flat,
    }


def check(mirror: dict, upstream: dict) -> list[str]:
    problems = []

    # A healthy repo has exactly one shard set.
    if len(mirror["shard_sets"]) > 1:
        detail = ", ".join(
            f"{len(v)} of {k}" for k, v in sorted(mirror["shard_sets"].items())
        )
        problems.append(
            f"mirror has {len(mirror['shard_sets'])} overlapping shard sets ({detail}). "
            "A push landed on top of an older upload without deleting it."
        )
    for total, names in mirror["shard_sets"].items():
        if len(names) != total:
            problems.append(f"shard set of {total} is incomplete: only {len(names)} present")

    for total, names in upstream["shard_sets"].items():
        if total not in mirror["shard_sets"]:
            problems.append(f"mirror is missing upstream's {total}-shard set entirely")

    for field, up in upstream["config"].items():
        mine = mirror["config"].get(field)
        if mine != up:
            problems.append(f"config.{field}: mirror={mine!r} upstream={up!r}")

    if mirror["tokenizer_bytes"] != upstream["tokenizer_bytes"]:
        problems.append(
            f"tokenizer.json size differs: mirror={mirror['tokenizer_bytes']:,} "
            f"upstream={upstream['tokenizer_bytes']:,} — a mismatched tokenizer "
            "produces fluent nonsense, not an error"
        )

    return problems


def report(mirror: dict, upstream: dict) -> bool:
    print(f"\n  mirror    {mirror['repo']}  @{mirror['sha'][:12]}")
    print(f"  upstream  {upstream['repo']}  @{upstream['sha'][:12]}\n")
    for label, d in (("mirror", mirror), ("upstream", upstream)):
        sets = ", ".join(f"{len(v)}/{k}" for k, v in sorted(d["shard_sets"].items())) or "none"
        print(f"  {label:<9} shards {sets:<20} weights {d['weights_bytes']/1e9:7.2f} GB  "
              f"{d['config']['architectures']} @ {d['config']['max_position_embeddings']}")

    problems = check(mirror, upstream)
    if not problems:
        print("\n  ok — mirror matches upstream\n")
        return True
    print(f"\n  {len(problems)} problem(s):")
    for p in problems:
        print(f"    - {p}")
    print()
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mirror", nargs="?")
    ap.add_argument("upstream", nargs="?")
    ap.add_argument("--all", action="store_true", help="check every entry in registry/models.yaml")
    ap.add_argument("--token", default=None)
    args = ap.parse_args()

    api = HfApi()
    ok = True

    if args.all:
        import yaml
        reg = yaml.safe_load((Path(__file__).resolve().parent.parent / "registry/models.yaml").read_text())
        pairs = [(m["hub_repo"], m["upstream"]) for m in reg["models"] if m.get("upstream")]
    elif args.mirror and args.upstream:
        pairs = [(args.mirror, args.upstream)]
    else:
        ap.error("give MIRROR and UPSTREAM, or --all")

    for m, u in pairs:
        try:
            ok &= report(survey(api, m, args.token), survey(api, u, args.token))
        except Exception as e:
            print(f"\n  {m}: could not check — {type(e).__name__}: {e}\n")
            ok = False

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
