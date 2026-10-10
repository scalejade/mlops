#!/usr/bin/env bash
# `make help`: the workflow, every target, the settings, and a status check of
# this laptop. Local only -- reads files, git refs and the ssh agent; sends
# nothing anywhere, so it is safe and instant to run any time.
#
#   bash training/scripts/help.sh <Makefile> <CONFIG> <BRANCH> <PY>

set -uo pipefail
MAKEFILE="$1"; CONFIG="$2"; BRANCH="$3"; PY="$4"
cd "$(dirname "$MAKEFILE")"

if [ -t 1 ]; then B=$'\e[1m'; D=$'\e[2m'; C=$'\e[36m'; G=$'\e[32m'; R=$'\e[31m'; Y=$'\e[33m'; N=$'\e[0m'
else B=; D=; C=; G=; R=; Y=; N=; fi
ok()   { printf "    ${G}✓${N} %-15s %s\n" "$1" "$2"; }
bad()  { printf "    ${R}✗${N} %-15s %s\n" "$1" "$2"; NEXT="${NEXT:-$3}"; }
warn() { printf "    ${Y}!${N} %-15s %s\n" "$1" "$2"; }
NEXT=""

cat <<EOF

${B}PBBI clause-extraction fine-tuning${N} — data is built on this laptop, training
runs on a rented RunPod H200 over ssh. Client documents never leave the laptop
except train.jsonl / eval.jsonl, copied to the pod for the run.

${B}FIRST TIME${N}
  1. cp .env.example .env      fill HF_TOKEN, RUNPOD_API_KEY, SSH_PUBLIC_KEY
                               (WANDB_API_KEY optional — no key, no experiment tracking)
  2. make setup                .venv with the laptop deps;  brew install poppler  (pdftotext)
  3. ssh-add                   your GitHub key in the ssh agent — the pod clones through it

${B}EACH RUN${N}
  1. preparation/raw/<folder>/   one folder per document: PDF + xlsx + annotation.txt
                                 with  Split : Train | Validation | Test
  2. make data                   build preparation/data/{train,eval,test}.jsonl
  3. git commit && git push      the pod runs origin/<branch>, not your working copy
  4. make pod-up                 rent the H200 — ${R}billing starts${N} (~\$4.59/hr)
  5. make train                  code + data to the pod, base model, start training
  6. make train-logs             follow it (Ctrl-C stops watching, not training)
  7. make pod-stop               ${R}stop billing${N} — as soon as the log says the adapter pushed
  then score the adapter on preparation/data/test.jsonl  (preparation/app_request.py)

  Data changed, pod already prepared:  make data train-push-data train-run
EOF

echo
echo "${B}TARGETS${N}"
awk -v C="$C" -v N="$N" -v B="$B" '
  /^##@ / { sub(/^##@ /, ""); printf "\n  %s%s%s\n", B, $0, N; next }
  /^[a-z][a-z-]*:.*## / {
    name = $0; sub(/:.*/, "", name)
    desc = $0; sub(/^[^#]*## /, "", desc)
    printf "    %s%-18s%s %s\n", C, name, N, desc
  }' "$MAKEFILE"

cat <<EOF

${B}SETTINGS${N}  ${D}override on the command line:  make <target> NAME=value${N}
    CONFIG   $CONFIG
    BRANCH   $BRANCH   ${D}(the pod checks out origin/$BRANCH)${N}
    PY       $PY
EOF

echo
echo "${B}STATUS${N}  ${D}this laptop only — nothing is sent anywhere${N}"

# secrets
if [ -f .env ]; then
  for k in HF_TOKEN RUNPOD_API_KEY SSH_PUBLIC_KEY; do
    v=$(grep -E "^$k=" .env | head -1 | cut -d= -f2-)
    if [ -n "$v" ]; then ok "$k" "set in .env"; else bad "$k" "empty or missing in .env" "fill $k in .env"; fi
  done
  v=$(grep -E "^WANDB_API_KEY=" .env | head -1 | cut -d= -f2-)
  [ -n "$v" ] && ok "WANDB_API_KEY" "set — runs are tracked" || warn "WANDB_API_KEY" "not set — training runs without experiment tracking"
else
  bad ".env" "missing" "cp .env.example .env, then fill it"
fi

# tools
if [ -x .venv/bin/python ]; then ok ".venv" "$(.venv/bin/python --version 2>&1)"
else bad ".venv" "missing — targets fall back to python3" "make setup"; fi
command -v pdftotext >/dev/null && ok "pdftotext" "$(command -v pdftotext)" \
  || bad "pdftotext" "missing — make data cannot read PDFs" "brew install poppler"
if ssh-add -l >/dev/null 2>&1; then ok "ssh-agent" "$(ssh-add -l 2>/dev/null | wc -l | tr -d ' ') key(s) loaded — forwarded to the pod for git"
else bad "ssh-agent" "no key loaded — the pod cannot clone from GitHub" "ssh-add"; fi

# documents
RAW=preparation/raw
if [ -d "$RAW" ]; then
  tr=0; va=0; te=0; badf=0
  for d in "$RAW"/*/; do
    [ -d "$d" ] || continue
    s=$(grep -E "^Split[[:space:]]*:" "$d/annotation.txt" 2>/dev/null | head -1 | cut -d: -f2 | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')
    case "$s" in train) tr=$((tr+1));; validation) va=$((va+1));; test) te=$((te+1));; *) badf=$((badf+1));; esac
  done
  line="Train $tr · Validation $va · Test $te"
  [ "$badf" -gt 0 ] && line="$line · ${R}$badf without a valid Split${N}"
  if [ "$tr" -gt 0 ] && [ "$badf" -eq 0 ]; then ok "raw/" "$line"
  elif [ "$tr" -eq 0 ]; then bad "raw/" "$line — nothing to train on" "mark folders 'Split : Train' in preparation/raw/*/annotation.txt"
  else bad "raw/" "$line" "fix annotation.txt in the folders without a valid Split"; fi
else
  bad "raw/" "preparation/raw/ missing" "create preparation/raw/<folder>/ per document"
fi

# built data
DATA=preparation/data
for f in train eval test; do
  p="$DATA/$f.jsonl"
  if [ -f "$p" ]; then
    n=$(wc -l < "$p" | tr -d ' ')
    stale=""; [ -n "$(find "$RAW" -newer "$p" -type f 2>/dev/null | head -1)" ] && stale=" ${Y}(raw/ changed since — make data)${N}"
    ok "$f.jsonl" "$n rows$stale"
  elif [ "$f" = train ]; then bad "$f.jsonl" "not built" "make data"
  else warn "$f.jsonl" "not built (optional)"; fi
done

# code on the pod = origin/BRANCH, compared against the last fetch (no network here)
dirty=$(git status --porcelain -- training preparation Makefile 2>/dev/null | wc -l | tr -d ' ')
if [ "$dirty" -gt 0 ]; then
  bad "git" "$dirty uncommitted file(s) in training/ preparation/ Makefile — the pod would not get them" "git add, commit and push"
elif ! git rev-parse -q --verify "origin/$BRANCH" >/dev/null; then
  bad "git" "origin/$BRANCH not known — never pushed?" "git push -u origin $BRANCH"
elif [ "$(git rev-parse HEAD)" != "$(git rev-parse "origin/$BRANCH")" ]; then
  bad "git" "$BRANCH differs from origin/$BRANCH (as of the last fetch)" "git push"
else
  ok "git" "$BRANCH @ $(git rev-parse --short HEAD) is pushed — what the pod will run"
fi

[ -f "$CONFIG" ] && ok "config" "$CONFIG" || bad "config" "$CONFIG not found" "check CONFIG="

echo
if [ -n "$NEXT" ]; then echo "  ${B}next:${N} $NEXT"
else echo "  ${B}next:${N} ready — make pod-up, then make train"; fi
echo
