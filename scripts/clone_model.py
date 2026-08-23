#!/usr/bin/env python3
"""Clone a Hugging Face model into our namespace, Hub-side.

The duplication happens on Hugging Face's servers, so the weights never travel
through the machine running this script. Locally we only keep
``models/<target>/README.md`` as the record of what was cloned.

Usage::

    ./scripts/clone_model.py                                  # defaults from .env
    ./scripts/clone_model.py google/gemma-4-31B-it-qat-w4a16-ct gemma-4-31B-it-baseline
    ./scripts/clone_model.py --visibility public
    ./scripts/clone_model.py --readme-only                    # refresh the README, no clone

Requires: pip install huggingface_hub
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from huggingface_hub import HfApi
from huggingface_hub.utils import HfHubHTTPError, RepositoryNotFoundError

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_env(path: Path) -> None:
    """Minimal .env loader. Existing environment variables win."""
    if not path.is_file():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def human_size(num_bytes: int) -> str:
    for limit, unit, digits in ((1e9, "GB", 2), (1e6, "MB", 1), (1e3, "KB", 1)):
        if num_bytes >= limit:
            return f"{num_bytes / limit:.{digits}f} {unit}"
    return f"{num_bytes} B"


def file_sizes(api: HfApi, repo_id: str, revision: str) -> list[tuple[str, int]]:
    info = api.model_info(repo_id, revision=revision, files_metadata=True)
    return sorted(
        ((s.rfilename, (s.lfs.size if s.lfs else s.size) or 0) for s in info.siblings),
        key=lambda pair: -pair[1],
    )


def write_readme(
    target_dir: Path,
    *,
    source: str,
    source_revision: str,
    source_sha: str,
    target: str,
    visibility: str,
    files: list[tuple[str, int]],
) -> Path:
    total = sum(size for _, size in files)
    rows = "\n".join(f"| `{name}` | {human_size(size)} |" for name, size in files)
    readme = target_dir / "README.md"
    readme.parent.mkdir(parents=True, exist_ok=True)
    readme.write_text(
        f"""# {target_dir.name}

Hub repo: <https://huggingface.co/{target}> ({visibility})

Cloned from [`{source}`](https://huggingface.co/{source}) at revision
`{source_revision}` (commit `{source_sha}`) on {datetime.now(timezone.utc):%Y-%m-%d}.

No weights are stored in this directory — the clone lives on the Hub. This file
is the local record of it.

## Contents

| File | Size |
| --- | --- |
{rows}
| **Total** | **{human_size(total)}** |

## Reproduce

```bash
./scripts/clone_model.py {source} {target_dir.name}
```

## Pull the weights onto a machine

```bash
MODELS_DIR=/runpod-volume/models ./scripts/download_model.sh {target} {target_dir.name}
```
"""
    )
    return readme


def main() -> int:
    load_env(REPO_ROOT / ".env")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", nargs="?", default=os.environ.get("SOURCE_MODEL"),
                        help="source repo on the Hub, e.g. google/gemma-4-31B-it-qat-w4a16-ct")
    parser.add_argument("target", nargs="?", default=os.environ.get("TARGET_MODEL"),
                        help="our name for it, without the namespace, e.g. gemma-4-31B-it-baseline")
    parser.add_argument("--namespace", default=os.environ.get("HF_NAMESPACE"),
                        help="Hub namespace to clone into (default: HF_NAMESPACE)")
    parser.add_argument("--revision", default=os.environ.get("SOURCE_REVISION", "main"))
    parser.add_argument("--visibility", choices=("private", "public"),
                        default=os.environ.get("VISIBILITY", "private"))
    parser.add_argument("--models-dir", default=os.environ.get("MODELS_DIR", "models"),
                        help="where the per-model README goes (default: models)")
    parser.add_argument("--readme-only", action="store_true",
                        help="skip the clone, just rewrite the local README")
    args = parser.parse_args()

    missing = [n for n, v in (("SOURCE_MODEL", args.source),
                              ("TARGET_MODEL", args.target),
                              ("HF_NAMESPACE", args.namespace)) if not v]
    if missing:
        parser.error(f"missing {', '.join(missing)} — set it in .env or pass it as an argument")

    token = os.environ.get("HF_TOKEN")
    if not token:
        parser.error("HF_TOKEN is not set — add it to .env")

    if "/" in args.target:
        parser.error(f"target should not include a namespace (got '{args.target}'); "
                     f"pass '{args.target.split('/')[-1]}' and use --namespace")

    target_repo = f"{args.namespace}/{args.target}"
    models_dir = Path(args.models_dir)
    if not models_dir.is_absolute():
        models_dir = REPO_ROOT / models_dir
    target_dir = models_dir / args.target

    api = HfApi(token=token)

    print(f"source : {args.source}@{args.revision}")
    print(f"target : {target_repo} ({args.visibility})")

    if args.readme_only:
        print("clone  : skipped (--readme-only)")
    else:
        try:
            api.model_info(target_repo)
        except RepositoryNotFoundError:
            pass
        else:
            print(f"error  : {target_repo} already exists — delete it first or pick another name",
                  file=sys.stderr)
            return 1

        try:
            url = api.duplicate_repo(
                from_id=args.source,
                to_id=target_repo,
                repo_type="model",
                private=args.visibility == "private",
            )
        except HfHubHTTPError as exc:
            print(f"error  : duplication failed — {exc}", file=sys.stderr)
            return 1
        print(f"clone  : {url}")

    source_sha = api.model_info(args.source, revision=args.revision).sha
    files = file_sizes(api, target_repo, "main")
    readme = write_readme(
        target_dir,
        source=args.source,
        source_revision=args.revision,
        source_sha=source_sha,
        target=target_repo,
        visibility=args.visibility,
        files=files,
    )
    print(f"readme : {readme.relative_to(REPO_ROOT)}")
    print(f"size   : {human_size(sum(size for _, size in files))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
