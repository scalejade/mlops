#!/usr/bin/env bash
# Prepare a fresh H200 pod for training. Run once per pod, on the pod:
#
#   bash training/scripts/bootstrap.sh
#
# Idempotent — safe to re-run after `pod.py stop` / `pod.py start`, which is the
# normal case: the container filesystem is rebuilt, /workspace is not.

set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "==> repo       $REPO"
echo "==> workspace  $WORKSPACE"

# --- sanity: is this actually the GPU we are paying for? ---------------------
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
GPUS=$(nvidia-smi --list-gpus | wc -l)
if [ "$GPUS" -gt 1 ]; then
  echo "!!  $GPUS GPUs visible. Unsloth uses one. The rest idle and still bill."
fi

# --- caches on the volume, not the container disk ----------------------------
# The container disk is wiped on stop/start; /workspace survives. A base model
# cached in the wrong place is re-downloaded every restart.
export HF_HOME="${HF_HOME:-$WORKSPACE/hf}"
export HUGGINGFACE_HUB_CACHE="${HUGGINGFACE_HUB_CACHE:-$HF_HOME/hub}"
export HF_HUB_ENABLE_HF_TRANSFER=1
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"
export TOKENIZERS_PARALLELISM=false
mkdir -p "$HUGGINGFACE_HUB_CACHE" "$WORKSPACE/adapters"

# Make it stick for every later shell, including the one you ssh back into.
grep -q "HUGGINGFACE_HUB_CACHE" ~/.bashrc 2>/dev/null || cat >> ~/.bashrc <<RC
export HF_HOME=$HF_HOME
export HUGGINGFACE_HUB_CACHE=$HUGGINGFACE_HUB_CACHE
export HF_HUB_ENABLE_HF_TRANSFER=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export TOKENIZERS_PARALLELISM=false
RC

# --- dependencies ------------------------------------------------------------
# torch stays exactly as the image shipped it. Everything else installs against it.
echo "==> torch (from the image, not reinstalled)"
python -c "import torch; print(torch.__version__, 'cuda', torch.version.cuda)"

pip install --upgrade pip -q
pip install -q -r "$REPO/training/requirements.txt"

# --- record what this pod actually has ---------------------------------------
# The config records the intent; this records the reality. Both are needed to
# reproduce a run, and only one of them is in git.
{
  date -u +"%Y-%m-%dT%H:%M:%SZ"
  nvidia-smi --query-gpu=name,driver_version --format=csv,noheader
  python - <<'PY'
import torch, importlib
print("torch", torch.__version__, "cuda", torch.version.cuda)
for pkg in ("unsloth", "transformers", "trl", "peft", "datasets", "bitsandbytes"):
    try:
        print(pkg, importlib.import_module(pkg).__version__)
    except Exception as e:
        print(pkg, "MISSING", e)
PY
} | tee "$WORKSPACE/versions.txt"

# --- credentials -------------------------------------------------------------
# hf_auth.py rather than login(): HF_TOKEN already takes precedence over a stored
# credential, and login() raises a 30-line traceback on a bad token. A rejected
# token is fatal — everything after this authenticates with it — but an unset one
# (exit 2) is only a warning, since public repos still work.
set +e
python "$REPO/training/scripts/hf_auth.py"
AUTH=$?
set -e
[ "$AUTH" -eq 1 ] && exit 1
[ -n "${WANDB_API_KEY:-}" ] || echo "!!  WANDB_API_KEY not set — the run will not be tracked"

cat <<'DONE'

==> ready

    python training/scripts/test.py            # smoke-test the stack first, ~5 min

    python training/scripts/train.py training/configs/<task>-<date>.yaml --dry-run
    nohup python training/scripts/train.py training/configs/<task>-<date>.yaml \
          > /workspace/train.log 2>&1 &
    tail -f /workspace/train.log

    ssh drops kill a foreground run. Use nohup, tmux, or screen.
    When it is done:  python training/scripts/pod.py stop   (from your laptop)

DONE
