#!/usr/bin/env bash
# One command to take a freshly created pod to "ready to train", on the pod:
#
#   bash training/scripts/prepare.sh
#
# Three things have to be true before training/scripts/test.py can run, and each
# one fails differently and expensively:
#
#   1. dependencies         -> delegated to bootstrap.sh (caches, pip, versions.txt)
#   2. the version intersection actually holds after pip resolved everything
#   3. the 55.56 GB base is in /workspace/hf, pulled as its own resumable step
#
# Idempotent, and safe to re-run after `pod.py stop` / `pod.py start` -- the
# container disk is rebuilt each time, /workspace is not, so step 3 is skipped on
# every run after the first.
#
#   --skip-deps     dependencies are already installed (skips bootstrap.sh)
#   --skip-model    do not download the base (versions and env only)
#   --test          run training/scripts/test.py at the end
#   --model REPO    default scalejade/qwen-sea-lion-v4.5-27b-it
#   --revision SHA  default the sha pinned in configs/example-lora.yaml

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORKSPACE="${WORKSPACE:-/workspace}"

# Kept in sync with configs/example-lora.yaml and scripts/test.py. A base model
# that moves under a run makes the run unreproducible, so the sha is pinned here
# too rather than resolved to whatever main happens to be today.
MODEL="scalejade/qwen-sea-lion-v4.5-27b-it"
REVISION="81d9102bab84b46085cc0f8539efe578d33e29da"
MODEL_GB=56          # 15 shards, 55.56 GB bf16, verified 2026-08-25
SKIP_DEPS=0
SKIP_MODEL=0
RUN_TEST=0

while [ $# -gt 0 ]; do
  case "$1" in
    --skip-deps)  SKIP_DEPS=1 ;;
    --skip-model) SKIP_MODEL=1 ;;
    --test)       RUN_TEST=1 ;;
    --model)      MODEL="$2"; shift ;;
    --revision)   REVISION="$2"; shift ;;
    -h|--help)    awk 'NR>1 && /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' \
                    "${BASH_SOURCE[0]}"; exit 0 ;;
    *)            echo "unknown flag: $1  (--help)" >&2; exit 2 ;;
  esac
  shift
done

fail() { echo; echo "!!  $*" >&2; exit 1; }

# --- credentials -------------------------------------------------------------
# On a pod created by pod.py these are already in the environment. Sourcing .env
# covers the other case: a pod made by hand, or a shell that lost them.
if [ -f "$REPO/.env" ]; then
  set -a; . "$REPO/.env"; set +a
  echo "==> loaded $REPO/.env"
fi

# --- preflight ---------------------------------------------------------------
# Everything below is cheap and everything below is a reason to stop before pip
# spends five minutes and the download spends fifteen.
echo "==> preflight"

command -v python >/dev/null || fail "no python on PATH"
python - <<'PY' || exit 1
import sys
if sys.version_info < (3, 10):
    raise SystemExit(f"!!  python {sys.version.split()[0]}; unsloth needs >=3.10")
print(f"    python     {sys.version.split()[0]}")
PY

if command -v nvidia-smi >/dev/null; then
  nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader \
    | sed 's/^/    gpu        /'
  GPUS=$(nvidia-smi --list-gpus | wc -l)
  [ "$GPUS" -gt 1 ] && echo "!!  $GPUS GPUs visible. Unsloth uses one; the rest idle and still bill."
else
  fail "no nvidia-smi. This runs ON the pod, not on your laptop."
fi

[ -d "$WORKSPACE" ] || fail "$WORKSPACE does not exist. The volume is not mounted -- \
anything cached now dies with the container disk on the next stop/start."

# The base alone is ~56 GB and pip's wheels are several more. Running the volume
# out of space mid-download leaves a half-written cache that fails at load time.
FREE_GB=$(df -Pk "$WORKSPACE" | awk 'NR==2 {print int($4/1024/1024)}')
echo "    disk       ${FREE_GB} GB free on $WORKSPACE"
if [ "$SKIP_MODEL" -eq 0 ] && [ "$FREE_GB" -lt "$((MODEL_GB + 20))" ]; then
  fail "need ~$((MODEL_GB + 20)) GB free for the base plus checkpoints, have ${FREE_GB} GB. \
Raise disk.volume_gb in training/pod.yaml (it is 300 by default) or clear $WORKSPACE/hf."
fi

# The whole point of doing this in preflight: a bad token 401s the 56 GB download
# and every push, and finding out here costs seconds instead of after pip.
set +e
python "$REPO/training/scripts/hf_auth.py" | sed 's/^/    /'
AUTH=${PIPESTATUS[0]}
set -e
[ "$AUTH" -eq 1 ] && fail "fix HF_TOKEN and re-run. Nothing has been installed or \
downloaded yet."

# --- 1. dependencies ---------------------------------------------------------
# bootstrap.sh owns this: caches on the volume, pip against the image's torch,
# versions.txt, hf login. Duplicating any of it here is how the two drift apart.
if [ "$SKIP_DEPS" -eq 0 ]; then
  echo
  echo "==> dependencies (training/scripts/bootstrap.sh)"
  bash "$REPO/training/scripts/bootstrap.sh"
else
  echo "==> dependencies skipped (--skip-deps)"
fi

export HF_HOME="${HF_HOME:-$WORKSPACE/hf}"
export HUGGINGFACE_HUB_CACHE="${HUGGINGFACE_HUB_CACHE:-$HF_HOME/hub}"
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"

# HF_HUB_ENABLE_HF_TRANSFER=1 with hf_transfer missing does not fall back — it
# raises, mid-download. pod.yaml sets the variable for every shell on the pod, so
# turn it off here rather than let a 56 GB pull die on an accelerator we do not
# have. (hub 1.x dropped the [hf_transfer] extra; requirements.txt asks for the
# package directly, but this pod may predate that.)
if python -c "import hf_transfer" 2>/dev/null; then
  export HF_HUB_ENABLE_HF_TRANSFER=1
else
  echo "!!  hf_transfer not installed -- downloading without it (slower, but it works)"
  unset HF_HUB_ENABLE_HF_TRANSFER
fi
export TOKENIZERS_PARALLELISM=false

# --- 2. verify the intersection actually holds -------------------------------
# pip exits 0 having resolved a combination that dies at import: `pip install
# unsloth` alone pulls transformers 5.15 and trl 1.10, both outside what Unsloth
# supports. Check it here, where the fix is one command, not inside train.py an
# hour later.
echo
echo "==> verify"
python - <<'PY' || fail "dependency versions are wrong. Fix:  pip install -r training/requirements.txt"
import importlib
from packaging.version import Version

BOUNDS = {                      # (min inclusive, max inclusive, why)
    "transformers": ("5.2.0", "5.5.0", "below 5.2.0 AutoConfig cannot read model_type qwen3_5"),
    "trl":          ("0.18.2", "0.24.0", "trl 1.x is not supported by this Unsloth"),
    "peft":         ("0.18.0", None, None),
    "datasets":     ("3.4.1", None, None),
}
bad = []
for pkg in ("torch", "unsloth", "unsloth_zoo", *BOUNDS):
    try:
        v = getattr(importlib.import_module(pkg), "__version__", "?")
    except Exception as e:
        bad.append(f"{pkg}: not importable ({type(e).__name__}: {e})")
        continue
    lo, hi, why = BOUNDS.get(pkg, (None, None, None))
    flag = ""
    if lo and Version(v) < Version(lo):
        bad.append(f"{pkg} {v} < {lo}" + (f" -- {why}" if why else "")); flag = "  <-- too old"
    elif hi and Version(v) > Version(hi):
        bad.append(f"{pkg} {v} > {hi}" + (f" -- {why}" if why else "")); flag = "  <-- too new"
    print(f"    {pkg:<14} {v}{flag}")

try:
    import torch
    print(f"    cuda           {torch.version.cuda}  available={torch.cuda.is_available()}")
    if not torch.cuda.is_available():
        bad.append("torch cannot see the GPU -- the wheel does not match the driver. "
                   "Do not reinstall torch; use the image's.")
    elif not torch.cuda.is_bf16_supported():
        bad.append("this GPU has no bf16. Qwen3.5's gated-deltanet layers NaN in fp16.")

    # Import order matters and is easy to get wrong: unsloth patches transformers
    # and trl, so it has to be imported before either of them.
    from unsloth import FastModel  # noqa: F401
    print("    unsloth imports cleanly (Triton kernels for gated-deltanet included)")
except Exception as e:
    bad.append(f"import failed: {type(e).__name__}: {e}")

if bad:
    print("\n!!  " + "\n!!  ".join(bad))
    raise SystemExit(1)
PY

# --- 3. the base model -------------------------------------------------------
# Its own step on purpose: 56 GB over the wire, and a download that dies inside
# test.py or train.py wastes the model load with it. hf_transfer + resume means
# a re-run costs nothing once the shards are there.
if [ "$SKIP_MODEL" -eq 1 ]; then
  echo
  echo "==> base model skipped (--skip-model)"
else
  echo
  echo "==> base model  $MODEL @ ${REVISION:0:8}"
  if MODEL="$MODEL" REVISION="$REVISION" python - <<'PY'
import os
from huggingface_hub import snapshot_download
try:
    p = snapshot_download(os.environ["MODEL"], revision=os.environ["REVISION"],
                          local_files_only=True)
    print(f"    already cached: {p}")
except Exception:
    raise SystemExit(1)
PY
  then
    echo "    nothing to download"
  else
    HF="huggingface-cli"; command -v hf >/dev/null && HF="hf"
    echo "    pulling ~${MODEL_GB} GB into $HUGGINGFACE_HUB_CACHE (resumable, ~15 min)"
    ok=0
    for attempt in 1 2 3; do
      # Hub transfers drop on long pulls. Each retry resumes from the shards
      # already on disk, so attempt 3 is cheap even when attempt 1 died at 90%.
      if "$HF" download "$MODEL" --revision "$REVISION"; then ok=1; break; fi
      echo "!!  download attempt $attempt failed, retrying (it resumes)"
      sleep 10
    done
    [ "$ok" -eq 1 ] || fail "could not download $MODEL after 3 attempts. \
Check HF_TOKEN has access, then re-run -- the shards already on disk are kept."
  fi
  du -sh "$HF_HOME" 2>/dev/null | sed 's/^/    cache      /'
fi

# --- done --------------------------------------------------------------------
echo
echo "==> ready"
if [ "$RUN_TEST" -eq 1 ]; then
  echo
  exec python "$REPO/training/scripts/test.py"
fi
cat <<'DONE'

    python training/scripts/test.py            # smoke-test the stack, ~5 min
    python training/scripts/train.py training/configs/<task>-<date>.yaml --dry-run
    nohup python training/scripts/train.py training/configs/<task>-<date>.yaml \
          > /workspace/train.log 2>&1 &

    The pod bills from create to `pod.py stop`, idle or not.

DONE
