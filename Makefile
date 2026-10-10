# Fine-tuning, driven from the laptop. Data is built here; the GPU work runs on a
# rented RunPod H200, reached over ssh. `make` (or `make help`) prints the whole
# workflow, every target, the settings, and what is ready on this laptop.
#
#   make setup              once: .venv with the laptop-side deps
#   make data               preparation/raw/  ->  preparation/data/*.jsonl
#   make pod-up             rent the H200 (billing starts)
#   make train              push code + data, pull the base model, start training
#   make train-logs         follow it
#   make pod-stop           stop billing — do not forget this one
#
# Every pod target finds the pod by name (training/pod.yaml) through the RunPod
# API, so no address is ever copied by hand. Override anything on the command
# line:  make train CONFIG=training/configs/<other>.yaml

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

CONFIG   ?= training/configs/pbbi-extraction-2026-10-10.yaml
PY       ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
BRANCH   ?= $(shell git rev-parse --abbrev-ref HEAD)
REPO_URL ?= $(shell git remote get-url origin)

REMOTE      := /workspace/mlops
REMOTE_DATA := $(REMOTE)/preparation/data
POD         := $(PY) training/scripts/pod.py
SSH_OPTS    := -A -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30 -o LogLevel=ERROR

# The base model and its pinned sha, read from the config so the pod caches
# exactly what train.py will load.
BASE     = $(shell $(PY) -c "import yaml;print(yaml.safe_load(open('$(CONFIG)'))['model']['base'])")
REVISION = $(shell $(PY) -c "import yaml;print(yaml.safe_load(open('$(CONFIG)'))['model'].get('revision','main'))")

# "root@<ip> <port>" -> HOST, PORT for the recipe that uses it.
POD_ADDR = t=$$($(POD) ssh-target) || exit 1; set -- $$t; HOST=$$1; PORT=$$2
# .env into the environment, for the targets that need HF_TOKEN locally.
DOTENV   = if [ -f .env ]; then set -a; . ./.env; set +a; fi

.PHONY: help setup data test \
        pod-gpus pod-plan pod-up pod-status pod-ssh pod-start pod-stop pod-delete \
        train train-push-code train-push-data train-pull-model train-check \
        train-run train-logs train-kill

help:  ## this guide: workflow, targets, settings, and what is ready
	@bash training/scripts/help.sh "$(firstword $(MAKEFILE_LIST))" "$(CONFIG)" "$(BRANCH)" "$(PY)"

# ---------------------------------------------------------------- laptop
##@ On this laptop  (free)

setup:  ## once: create .venv with the laptop-side deps (build, tests, pod.py)
	python3 -m venv .venv
	.venv/bin/pip install -q -r preparation/requirements.txt
	@command -v pdftotext >/dev/null || echo "  !! install pdftotext:  brew install poppler"
	@echo "  ready — targets use .venv/bin/python from now on"

data:  ## build preparation/data/ from preparation/raw/ (exact token counts)
	@$(DOTENV); $(PY) preparation/build.py --tokenizer "$(BASE)@$(REVISION)"

test:  ## offline tests of the local copy of the app's extraction call
	$(PY) -m unittest preparation/test_app_request.py

# ------------------------------------------------------------------- pod
##@ The pod  (billed while it runs — pod-stop when done)

pod-gpus:  ## live H200 type ids and prices
	$(POD) gpus h200

pod-plan:  ## validate training/pod.yaml and show the price; creates nothing
	$(POD) plan

pod-up:  ## create the pod — BILLING STARTS
	$(POD) apply

pod-status:  ## what is running, its address and its cost
	$(POD) status

pod-ssh:  ## open a shell on the pod
	@$(POD_ADDR); ssh -t $(SSH_OPTS) -p "$$PORT" "$$HOST" "cd $(REMOTE) 2>/dev/null; exec bash -l"

pod-start:  ## resume a stopped pod (its disk and cached model are still there)
	$(POD) start

pod-stop:  ## STOP GPU BILLING — keeps the disk, so the next run skips setup
	$(POD) stop

pod-delete:  ## delete the pod and its disk (asks first)
	$(POD) delete

# ----------------------------------------------------------------- train
##@ Training on the pod  (run from this laptop)

train: train-push-code train-push-data train-pull-model train-run  ## everything: code, data, base model, start training
	@echo
	@echo "  training started on the pod.  make train-logs  to follow,  make pod-stop  when it has pushed."

train-push-code:  ## put this branch on the pod (must be pushed to GitHub first)
	@git fetch -q origin "$(BRANCH)" || { echo "  !! $(BRANCH) is not on origin — git push -u origin $(BRANCH)"; exit 1; }
	@if [ "$$(git rev-parse HEAD)" != "$$(git rev-parse "origin/$(BRANCH)")" ]; then \
	  echo "  !! local $(BRANCH) differs from origin/$(BRANCH) — the pod would get the old code. git push first."; exit 1; fi
	@dirty=$$(git status --porcelain -- training preparation Makefile); if [ -n "$$dirty" ]; then \
	  echo "  !! the pod runs origin/$(BRANCH) @ $$(git rev-parse --short HEAD), which lacks these (commit + push first):"; \
	  echo "$$dirty" | sed 's/^/       /'; exit 1; fi
	@if [ -n "$$(git status --porcelain --untracked-files=no)" ]; then \
	  echo "  ?? other uncommitted changes stay on the laptop (not needed on the pod)"; fi
	@$(POD_ADDR); ssh $(SSH_OPTS) -p "$$PORT" "$$HOST" '\
	  set -e; export GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=accept-new"; \
	  mkdir -p $(REMOTE) && cd $(REMOTE); \
	  [ -d .git ] || { git init -q && git remote add origin $(REPO_URL); }; \
	  git fetch -q origin $(BRANCH) && git checkout -q -f -B $(BRANCH) FETCH_HEAD; \
	  echo "  pod code   $$(git log -1 --format="%h %s")"'

train-push-data:  ## copy preparation/data/{train,eval}.jsonl to the pod (test.jsonl stays here)
	@[ -f preparation/data/train.jsonl ] || { echo "  !! no preparation/data/train.jsonl — mark folders 'Split : Train' and make data"; exit 1; }
	@$(POD_ADDR); files=preparation/data/train.jsonl; \
	  [ -f preparation/data/eval.jsonl ] && files="$$files preparation/data/eval.jsonl"; \
	  ssh $(SSH_OPTS) -p "$$PORT" "$$HOST" "mkdir -p $(REMOTE_DATA)"; \
	  scp -q $(SSH_OPTS) -P "$$PORT" $$files "$$HOST:$(REMOTE_DATA)/"; \
	  echo "  pod data   $$files"

train-pull-model:  ## install deps and download the config's base model onto the pod volume (~25 min once)
	@echo "  base       $(BASE) @ $(REVISION)"
	@$(POD_ADDR); ssh $(SSH_OPTS) -p "$$PORT" "$$HOST" '\
	  set -e; cd $(REMOTE); \
	  flags="--model $(BASE) --revision $(REVISION)"; \
	  if [ -f /workspace/versions.txt ]; then flags="--skip-deps $$flags"; else flags="--fast-kernels $$flags"; fi; \
	  setsid nohup bash training/scripts/prepare.sh $$flags > /workspace/prepare.log 2>&1 < /dev/null & pid=$$!; \
	  echo "  prepare.sh $$flags   (log /workspace/prepare.log — safe to disconnect)"; \
	  tail -n +1 --pid=$$pid -f /workspace/prepare.log; \
	  if wait $$pid; then echo "  pod ready  base cached on /workspace"; \
	  else echo "  !! prepare.sh failed — see above, or /workspace/prepare.log on the pod"; exit 1; fi'

train-check:  ## on the pod: validate config + data and dry-run (loads the model, trains nothing)
	@$(POD_ADDR); ssh -t $(SSH_OPTS) -p "$$PORT" "$$HOST" "cd $(REMOTE) && bash training/run.sh $(CONFIG) --check"

train-run:  ## on the pod: start training in the background (survives disconnect)
	@$(POD_ADDR); ssh $(SSH_OPTS) -p "$$PORT" "$$HOST" '\
	  set -e; cd $(REMOTE); \
	  if pgrep -f "[t]raining/scripts/train.py" >/dev/null; then echo "  !! training is already running — make train-logs"; exit 1; fi; \
	  setsid nohup bash training/run.sh $(CONFIG) > /workspace/run.log 2>&1 < /dev/null & \
	  echo "  started    run.sh $(CONFIG)  (pid $$!)"; \
	  echo "  logs       /workspace/run.log (checks, dry run)  /workspace/train.log (training)"'

train-logs:  ## follow the run on the pod (Ctrl-C stops watching, not training)
	@$(POD_ADDR); ssh -t $(SSH_OPTS) -p "$$PORT" "$$HOST" \
	  "touch /workspace/run.log /workspace/train.log; tail -n 50 -F /workspace/run.log /workspace/train.log"

train-kill:  ## stop a running training on the pod (the pod itself keeps billing)
	@$(POD_ADDR); ssh $(SSH_OPTS) -p "$$PORT" "$$HOST" \
	  'pkill -f "[t]raining/scripts/train.py" && echo "  training stopped" || echo "  nothing running"; pkill -f "[t]raining/run.sh" || true'
