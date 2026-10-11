#!/usr/bin/env bash
# One entry point for a training run, meant to be executed ON THE POD.
#
#   bash training/run.sh training/configs/pbbi-extraction-2026-10-10.yaml
#   bash training/run.sh <config> --check     # validate and stop, train nothing
#
# It does, in order: check the config and its data exist, prepare the pod if it
# has not been prepared, dry-run to print token lengths, then train in the
# background with the log on disk so an ssh drop does not kill the run.
#
# It deliberately does NOT create or stop the pod. Renting and releasing an H200
# is a billing decision and stays an explicit command you type from your laptop:
#   python training/scripts/pod.py apply   /   python training/scripts/pod.py stop
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="${1:-}"
MODE="${2:-run}"
LOG="${TRAIN_LOG:-/workspace/train.log}"

die() { printf '\n  error  %s\n\n' "$*" >&2; exit 1; }
say() { printf '  %s\n' "$*"; }

[ -n "$CONFIG" ] || die "usage: bash training/run.sh <config.yaml> [--check]"
[ -f "$REPO/$CONFIG" ] || [ -f "$CONFIG" ] || die "config not found: $CONFIG"
CONFIG_ABS="$(cd "$(dirname "$REPO/$CONFIG")" 2>/dev/null && pwd)/$(basename "$CONFIG")"
[ -f "$CONFIG_ABS" ] || CONFIG_ABS="$CONFIG"

printf '\nconfig\n'
say "$CONFIG"

# --- the data has to be there before anything expensive happens --------------
# train.py would also catch this, but only after loading 55 GB of weights onto
# the GPU, which is ~15 minutes and a few dollars into the run.
printf '\ndata\n'
python3 - "$CONFIG_ABS" "$REPO" <<'PY'
import sys, yaml, pathlib
cfg = yaml.safe_load(open(sys.argv[1])); repo = pathlib.Path(sys.argv[2])
data = cfg.get("data", {})
if data.get("hub_repo"):
    print(f"  hub_repo        {data['hub_repo']} @ {data.get('revision','main')}")
    sys.exit(0)
missing = []
for which in ("train", "eval"):
    ref = data.get(which)
    if not ref:
        print(f"  {which:<15} not set")
        continue
    p = pathlib.Path(ref)
    p = p if p.is_absolute() else repo / p
    if p.exists():
        n = sum(1 for _ in p.open(encoding="utf-8"))
        print(f"  {which:<15} {n:>5} rows   {p}")
    else:
        print(f"  {which:<15} MISSING     {p}")
        missing.append(which)
if missing:
    # train.py would find this only after loading the 55 GB base onto the GPU.
    sys.exit(f"\n  error  data.{' and data.'.join(missing)} set in the config but the file "
             f"is missing.\n"
             "         Build it:  python preparation/build.py  (needs a folder with\n"
             "         'Split : Train' / 'Split : Validation' in its annotation.txt),\n"
             "         then copy it here. Or remove data.eval from the config to train\n"
             "         without an eval loss.\n")
PY

# --- prepare the pod once ----------------------------------------------------
# The base comes from the config, not prepare.sh's default: a different repo or
# sha here means the 55 GB download lands in the cache for nothing, and train.py
# then pulls the real base mid-run.
read -r BASE REVISION < <(python3 - "$CONFIG_ABS" <<'PY'
import sys, yaml
m = yaml.safe_load(open(sys.argv[1]))["model"]
print(m["base"], m.get("revision", "main"))
PY
)
printf '\nprepare\n'
# Ask the interpreter, not versions.txt: that file is on /workspace, which outlives
# the container (stop/start, or a new pod on the same network volume), while the
# pip packages it describes live on the container disk and do not.
if ! python3 -c "import importlib.util as u, sys; sys.exit(0 if u.find_spec('unsloth') else 1)"; then
  say "deps not installed in this container — running prepare.sh (deps + $BASE, ~25 min)"
  bash "$REPO/training/scripts/prepare.sh" --fast-kernels --model "$BASE" --revision "$REVISION"
else
  # Deps are there; make sure THIS config's base is too (a no-op when cached).
  say "deps already installed — checking $BASE @ ${REVISION:0:12} is cached"
  bash "$REPO/training/scripts/prepare.sh" --skip-deps --model "$BASE" --revision "$REVISION"
fi

# --- dry run: shapes and token lengths, nothing trained ----------------------
printf '\ndry run\n'
python3 "$REPO/training/scripts/train.py" "$CONFIG_ABS" --dry-run

if [ "$MODE" = "--check" ]; then
  printf '\nchecked only — nothing trained\n\n'
  exit 0
fi

# --- train -------------------------------------------------------------------
printf '\ntrain\n'
say "log: $LOG"
nohup python3 "$REPO/training/scripts/train.py" "$CONFIG_ABS" > "$LOG" 2>&1 &
PID=$!
say "pid: $PID   (tail -f $LOG)"
say ""
say "when it finishes, from your LAPTOP:  python training/scripts/pod.py stop"
say "the pod bills while running, idle or not."
wait $PID
