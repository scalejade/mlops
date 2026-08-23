#!/usr/bin/env bash
# Clone a Hugging Face model into models/<TARGET_MODEL>.
#
# Usage:
#   ./scripts/download_model.sh                          # uses SOURCE_MODEL/TARGET_MODEL from .env
#   ./scripts/download_model.sh <source_repo> <local_name>
#
# Env overrides: SOURCE_REVISION, MODELS_DIR, FORCE=1 (skip the disk-space check)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

SOURCE_MODEL="${1:-${SOURCE_MODEL:-}}"
TARGET_MODEL="${2:-${TARGET_MODEL:-}}"
SOURCE_REVISION="${SOURCE_REVISION:-main}"
MODELS_DIR="${MODELS_DIR:-models}"
[[ "$MODELS_DIR" = /* ]] || MODELS_DIR="$REPO_ROOT/$MODELS_DIR"

if [[ -z "$SOURCE_MODEL" || -z "$TARGET_MODEL" ]]; then
  echo "error: SOURCE_MODEL and TARGET_MODEL must be set (in .env or as arguments)" >&2
  exit 1
fi
if [[ -z "${HF_TOKEN:-}" ]]; then
  echo "error: HF_TOKEN is not set — add it to .env" >&2
  exit 1
fi

# Weights go in a weights/ subdir so they never clobber the model's README.md.
TARGET_DIR="$MODELS_DIR/$TARGET_MODEL/weights"

echo "source : $SOURCE_MODEL@$SOURCE_REVISION"
echo "target : $TARGET_DIR"

# --- disk-space check -------------------------------------------------------
NEEDED_BYTES="$(
  HF_TOKEN="$HF_TOKEN" SOURCE_MODEL="$SOURCE_MODEL" SOURCE_REVISION="$SOURCE_REVISION" \
  python3 - <<'PY'
import os
from huggingface_hub import HfApi

info = HfApi(token=os.environ["HF_TOKEN"]).model_info(
    os.environ["SOURCE_MODEL"],
    revision=os.environ["SOURCE_REVISION"],
    files_metadata=True,
)
print(sum((s.lfs.size if s.lfs else (s.size or 0)) for s in info.siblings))
PY
)"

mkdir -p "$TARGET_DIR"
AVAIL_BYTES=$(( $(df -k "$TARGET_DIR" | awk 'NR==2 {print $4}') * 1024 ))

printf 'size   : %.2f GB needed, %.2f GB free\n' \
  "$(echo "$NEEDED_BYTES" | awk '{print $1/1e9}')" \
  "$(echo "$AVAIL_BYTES" | awk '{print $1/1e9}')"

# Require the download size plus a 5 GB headroom margin.
if [[ "${FORCE:-0}" != "1" ]] && (( AVAIL_BYTES < NEEDED_BYTES + 5000000000 )); then
  echo "error: not enough free disk space (want download size + 5 GB headroom). Re-run with FORCE=1 to override." >&2
  exit 1
fi

# --- download ---------------------------------------------------------------
# --local-dir writes straight into the target, no duplicate copy in ~/.cache.
HF_TOKEN="$HF_TOKEN" HF_HUB_ENABLE_HF_TRANSFER="${HF_HUB_ENABLE_HF_TRANSFER:-0}" \
  hf download "$SOURCE_MODEL" \
    --revision "$SOURCE_REVISION" \
    --local-dir "$TARGET_DIR"

# Record where this snapshot came from.
cat > "$TARGET_DIR/MODEL_ORIGIN.json" <<EOF
{
  "local_name": "$TARGET_MODEL",
  "source_repo": "$SOURCE_MODEL",
  "revision": "$SOURCE_REVISION",
  "downloaded_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

echo "done: $TARGET_DIR"
