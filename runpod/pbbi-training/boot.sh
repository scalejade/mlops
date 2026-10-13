#!/usr/bin/env bash
# pbbi-training boot: the pod's start command, on every start of every pod.
#
# Pulls a model into /workspace/hf — the pod's own disk — in the
# BACKGROUND, then hands over to the image's own /start.sh, so sshd and jupyter
# come up at once instead of after tens of GB. On a volume that already has the
# model, the pull is a quick check and nothing is downloaded.
#
# pod.py sends this file as the pod's dockerStartCmd and sets BOOT_MODEL and
# BOOT_REVISION from values.yaml (boot.model, boot.revision). With boot.model
# empty, BOOT_MODEL is unset and nothing is pulled.
#
#   /workspace/boot-model.log    what it did, appended per boot
#   /workspace/boot-model.done   "<model>@<revision>" once that one is complete
#   /tmp/boot-model.pid          while it runs. On the container disk, not the
#                                volume: a pid from a previous pod means nothing.
#
# Nothing here may stop /start.sh from running: no `set -e` out here, and the
# download lives in a subshell. A boot that fails to download still gives you
# ssh, and `make train` downloads it the usual way.

LOG=/workspace/boot-model.log
DONE=/workspace/boot-model.done

mkdir -p /workspace "${HF_HOME:-/workspace/hf}" 2>/dev/null

(
  set -uo pipefail
  stamp() { echo "$(date -u +%FT%TZ)  $*"; }
  stamp "boot download  ${BOOT_MODEL:-?} @ ${BOOT_REVISION:-?}"
  if [ -z "${BOOT_MODEL:-}" ] || [ -z "${BOOT_REVISION:-}" ]; then
    stamp "boot.model is empty — nothing to pull"; exit 0
  fi
  if [ -z "${HF_TOKEN:-}" ]; then
    stamp "no HF_TOKEN (runpod/pbbi-training/.env) — the private repo would 401. Skipped."; exit 1
  fi

  # Progress bars are carriage-return redraws: over 56 GB they would fill the log
  # with megabytes of one line. The per-attempt result is what is worth keeping.
  export HF_HUB_DISABLE_PROGRESS_BARS=1 PIP_DISABLE_PIP_VERSION_CHECK=1
  export PIP_BREAK_SYSTEM_PACKAGES=1   # Ubuntu 24.04 system python, PEP 668

  # The image has no huggingface_hub. Same bounds as training/requirements.txt,
  # so bootstrap.sh finds them already satisfied. hf_transfer is optional: with
  # HF_HUB_ENABLE_HF_TRANSFER=1 and no package, the hub raises mid-download.
  python -c "import huggingface_hub" 2>/dev/null \
    || pip install -q "huggingface_hub>=0.34.0" || { stamp "pip install failed"; exit 1; }
  python -c "import hf_transfer" 2>/dev/null \
    || pip install -q "hf_transfer>=0.1.6" || unset HF_HUB_ENABLE_HF_TRANSFER

  # Resumable: each attempt keeps the shards already on the volume.
  python - <<'PY' || { stamp "FAILED — make train will retry it"; exit 1; }
import os, time
from huggingface_hub import snapshot_download

model, rev = os.environ["BOOT_MODEL"], os.environ["BOOT_REVISION"]
for attempt in (1, 2, 3):
    try:
        print("    cached at", snapshot_download(model, revision=rev), flush=True)
        break
    except Exception as e:
        print(f"    attempt {attempt} failed: {type(e).__name__}: {e}", flush=True)
        time.sleep(10)
else:
    raise SystemExit(1)
PY
  echo "${BOOT_MODEL}@${BOOT_REVISION}" > "$DONE"
  du -sh "${HF_HOME:-/workspace/hf}" 2>/dev/null | sed 's/^/    cache  /'
  stamp "done"
) >> "$LOG" 2>&1 &
echo $! > /tmp/boot-model.pid

exec /start.sh
