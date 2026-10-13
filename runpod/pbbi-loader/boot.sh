#!/usr/bin/env bash
# pbbi-loader boot: the pod's start command. Fills pbbi-volumes for serving.
#
# pod.py sends this file as the pod's dockerStartCmd and sets, from values.yaml:
#   BOOT_MODEL / BOOT_REVISION                  -> /workspace/hf (the HF cache vLLM reads)
#   BOOT_ADAPTERS  "repo@rev,repo@rev"          -> /workspace/adapters/<repo>/<rev>, each
#
# /workspace is pbbi-volumes; the endpoint sees it as /runpod-volume. The adapter
# path is a plain directory, not the HF cache, because vLLM's --lora-modules takes
# a path, and a path pinned by revision cannot drift the way "main" can.
#
#   /workspace/loader.log     what it did, appended per boot (on the volume)
#   /workspace/loader.done    "<model>@<rev> <adapters>" once everything is verified
#   /workspace/loader.failed  the reason, if not
#
# Both markers are removed BEFORE /start.sh brings up sshd, so `make volume-fill`
# can never read a marker left by an earlier boot. Nothing here may stop
# /start.sh: the download runs in a background subshell.

LOG=/workspace/loader.log
DONE=/workspace/loader.done
FAILED=/workspace/loader.failed

mkdir -p /workspace "${HF_HOME:-/workspace/hf}" /workspace/adapters 2>/dev/null
rm -f "$DONE" "$FAILED"

(
  set -uo pipefail
  stamp() { echo "$(date -u +%FT%TZ)  $*"; }
  fail()  { stamp "FAILED: $*"; echo "$*" > "$FAILED"; exit 1; }
  stamp "loader  ${BOOT_MODEL:-?} @ ${BOOT_REVISION:-?}  +  adapters: ${BOOT_ADAPTERS:-(none)}"
  [ -n "${BOOT_MODEL:-}" ] && [ -n "${BOOT_REVISION:-}" ] || fail "BOOT_MODEL / BOOT_REVISION not set"
  [ -n "${HF_TOKEN:-}" ] || fail "no HF_TOKEN (runpod/pbbi-loader/.env) — the private repos would 401"

  # Progress bars are carriage-return redraws: over 56 GB they fill the log.
  export HF_HUB_DISABLE_PROGRESS_BARS=1 PIP_DISABLE_PIP_VERSION_CHECK=1
  export PIP_BREAK_SYSTEM_PACKAGES=1   # Ubuntu 24.04 system python, PEP 668
  python3 -c "import huggingface_hub" 2>/dev/null \
    || pip install -q "huggingface_hub>=0.34.0" || fail "pip install huggingface_hub"
  python3 -c "import hf_transfer" 2>/dev/null \
    || pip install -q "hf_transfer>=0.1.6" || unset HF_HUB_ENABLE_HF_TRANSFER

  # Resumable: each attempt keeps the files already on the volume.
  python3 - <<'PY' || fail "download or verification failed — see the lines above"
import os, sys, time
from pathlib import Path
from huggingface_hub import snapshot_download

def pull(what, **kw):
    for attempt in (1, 2, 3):
        try:
            path = snapshot_download(**kw)
            print(f"    {what:<8} {path}", flush=True)
            return Path(path)
        except Exception as e:
            print(f"    {what} attempt {attempt} failed: {type(e).__name__}: {e}", flush=True)
            time.sleep(15)
    sys.exit(1)

base = pull("base", repo_id=os.environ["BOOT_MODEL"], revision=os.environ["BOOT_REVISION"])
shards = list(base.glob("*.safetensors"))
if not shards or not (base / "config.json").exists():
    sys.exit(f"    base at {base} has no config.json or no *.safetensors")
print(f"    base     {len(shards)} shards, {sum(s.stat().st_size for s in shards) / 1e9:.1f} GB", flush=True)

for entry in filter(None, os.environ.get("BOOT_ADAPTERS", "").split(",")):
    repo, _, rev = entry.strip().partition("@")
    target = Path("/workspace/adapters") / repo.split("/")[1] / rev
    pull("adapter", repo_id=repo, revision=rev, local_dir=str(target))
    for f in ("adapter_config.json", "adapter_model.safetensors"):
        if not (target / f).exists():
            sys.exit(f"    adapter at {target} is missing {f}")
    print(f"    adapter  {target}  (vLLM: /runpod-volume/adapters/{repo.split('/')[1]}/{rev})", flush=True)
PY
  echo "${BOOT_MODEL}@${BOOT_REVISION} ${BOOT_ADAPTERS:-}" > "$DONE"
  du -sh "${HF_HOME:-/workspace/hf}" /workspace/adapters 2>/dev/null | sed 's/^/    size  /'
  stamp "done"
) >> "$LOG" 2>&1 &

exec /start.sh
