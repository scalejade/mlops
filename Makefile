# Fine-tuning, driven from the laptop. Data is built here; the GPU work runs on a
# rented RunPod H200, reached over ssh. `make` (or `make help`) prints the whole
# workflow, every target, the settings, and what is ready on this laptop.
#
#   make setup              once: .venv with the laptop-side deps
#   make data               preparation/raw/  ->  preparation/data/*.jsonl
#   make pod-up pbbi-training   rent the H200 (billing starts). The chart is required:
#                           pod-up creates billable things, so it never guesses which
#   make train              push code + data, pull the base model, start training
#   make train-logs         follow it
#   make pod-stop pbbi-training   stop billing — do not forget this one (deletes the
#                           pod; /workspace lives on the pbbi-volumes network volume)
#
# Every pod target finds its resource by name (runpod/<chart>) through the RunPod
# API, so no address is ever copied by hand. Override anything on the command
# line:  make train CONFIG=training/configs/<other>.yaml

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

CONFIG   ?= training/configs/pbbi-extraction.yaml
PY       ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
BRANCH   ?= $(shell git rev-parse --abbrev-ref HEAD)
REPO_URL ?= $(shell git remote get-url origin)

REMOTE      := /workspace/mlops
REMOTE_DATA := $(REMOTE)/preparation/data
DEPLOY      := $(PY) runpod/deploy.py
SSH_OPTS    := -A -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30 -o LogLevel=ERROR

# The base model and its pinned sha, read from the config so the pod caches
# exactly what train.py will load.
BASE     = $(shell $(PY) -c "import yaml;print(yaml.safe_load(open('$(CONFIG)'))['model']['base'])")
REVISION = $(shell $(PY) -c "import yaml;print(yaml.safe_load(open('$(CONFIG)'))['model'].get('revision','main'))")

# The chart a pod-* target acts on: the word after it, so `make pod-up pbbi-serverles`
# names runpod/pbbi-serverles. CHART=<name> works too. Without one it is the training
# pod, which is also the only chart the train-* targets ever use — except for the
# targets that create or tear down (pod-up, pod-down, pod-stop, pod-delete), which
# refuse to guess (CHART_GIVEN is empty then).
POD_GOALS   := pod-plan pod-up pod-down pod-status pod-ssh pod-start pod-stop pod-delete
CHART_GIVEN := $(filter command line,$(origin CHART))
CHART       ?= pbbi-training
ifneq ($(filter $(POD_GOALS),$(firstword $(MAKECMDGOALS))),)
  CHART_ARGS := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
  ifneq ($(word 2,$(CHART_ARGS)),)
    $(error one chart at a time: make $(firstword $(MAKECMDGOALS)) <chart>, got "$(CHART_ARGS)")
  endif
  ifneq ($(CHART_ARGS),)
    CHART       := $(CHART_ARGS)
    CHART_GIVEN := yes
    # The chart name is a goal too, as far as make is concerned. Make it a no-op.
    $(eval $(CHART_ARGS):;@:)
  endif
endif
POD := $(PY) training/scripts/pod.py --chart $(CHART)

# A pod chart without an engine block is a training pod: pod.py drives it. Every
# other chart (serverless, volume, a serving pod) is deploy.py's. Same verbs in
# both tools, so a target only has to name the verb.
IS_TRAINING_POD = import sys, yaml, pathlib; d = pathlib.Path(sys.argv[1]); \
  c = yaml.safe_load((d / 'chart.yaml').read_text()) or {}; \
  v = yaml.safe_load((d / 'values.yaml').read_text()) or {}; \
  sys.exit(0 if c.get('kind') == 'pod' and not v.get('engine') else 1)
define chart_do
	@[ -f runpod/$(CHART)/chart.yaml ] || { echo "  !! no chart runpod/$(CHART)/ — charts: $$(ls runpod/*/chart.yaml | cut -d/ -f2 | xargs)"; exit 1; }
	@if $(PY) -c "$(IS_TRAINING_POD)" runpod/$(CHART); then $(POD) $(1); else $(DEPLOY) $(1) $(CHART); fi
endef

# chart_do, but only for a chart named on the command line. $(if) picks the recipe
# when make expands it, before any shell runs: an `exit` inside a recipe line would
# end that line only, and make would go on to the next one — the action.
define chart_refuse
	@echo "  !! $@ needs a chart — nothing was sent to RunPod. Pick one:"
	@for c in $$(ls runpod/*/chart.yaml | cut -d/ -f2); do echo "       make $@ $$c"; done
endef
chart_do_named = $(if $(CHART_GIVEN),$(call chart_do,$(1)),$(chart_refuse))

# "root@<ip> <port>" -> HOST, PORT for the recipe that uses it.
POD_ADDR = t=$$($(POD) ssh-target) || exit 1; set -- $$t; HOST=$$1; PORT=$$2
# .env into the environment, for the targets that need HF_TOKEN locally.
DOTENV   = if [ -f .env ]; then set -a; . ./.env; set +a; fi

.PHONY: help setup data test wandb-example \
        pod-gpus pod-plan pod-up pod-down pod-status pod-ssh pod-start pod-stop pod-delete \
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

wandb-example:  ## log a SIMULATED training run to W&B (<project>-example), no GPU
	$(PY) training/scripts/wandb_example.py $(CONFIG)

# ------------------------------------------------------------------- pod
##@ RunPod  (make pod-<verb> <chart> — a runpod/ directory; only plan/status/ssh/start default to pbbi-training)

pod-gpus:  ## live H200 type ids and prices
	$(POD) gpus h200

pod-plan:  ## validate the chart and show the price; creates nothing
	$(call chart_do,plan)

pod-up:  ## make pod-up <chart>: create or update it — BILLING STARTS for a pod
	$(call chart_do_named,apply)

pod-down:  ## make pod-down <chart>: the opposite of pod-up — stops a pod's billing
	$(call chart_do_named,stop)

pod-status:  ## what is live, its address and its cost
	$(call chart_do,status)

pod-ssh:  ## open a shell on a pod
	@$(POD_ADDR); ssh -t $(SSH_OPTS) -p "$$PORT" "$$HOST" "cd $(REMOTE) 2>/dev/null; exec bash -l"

pod-start:  ## resume a stopped volume-disk pod (a network-volume pod is recreated with pod-up)
	$(call chart_do,start)

pod-stop:  ## make pod-stop <chart>: STOP GPU BILLING — a network-volume pod is deleted; /workspace stays
	$(call chart_do_named,stop)

pod-delete:  ## make pod-delete <chart>: tear its resource down (asks first)
	$(call chart_do_named,delete)

# ----------------------------------------------------------------- train
##@ Training on the pod  (run from this laptop)

train: train-push-code train-push-data train-pull-model train-run  ## everything: code, data, base model, start training
	@echo
	@echo "  training started on the pod.  make train-logs  to follow,  make pod-stop pbbi-training  when it has pushed."

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

train-push-data:  ## copy preparation/data/{train,eval}.jsonl + build-report.json to the pod (test.jsonl stays here)
	@[ -f preparation/data/train.jsonl ] || { echo "  !! no preparation/data/train.jsonl — mark folders 'Split : Train' and make data"; exit 1; }
	@# build-report.json names each row's document and annotation tags, for the
	@# per-document eval metrics and the run fingerprint. It quotes section headings
	@# from the contracts (not clause text), so it gets the same NDA care as the JSONL.
	@$(POD_ADDR); files=preparation/data/train.jsonl; \
	  [ -f preparation/data/eval.jsonl ] && files="$$files preparation/data/eval.jsonl"; \
	  [ -f preparation/data/build-report.json ] && files="$$files preparation/data/build-report.json"; \
	  ssh $(SSH_OPTS) -p "$$PORT" "$$HOST" "mkdir -p $(REMOTE_DATA)"; \
	  scp -q $(SSH_OPTS) -P "$$PORT" $$files "$$HOST:$(REMOTE_DATA)/"; \
	  echo "  pod data   $$files"

train-pull-model:  ## install deps and download the config's base model onto the volume (~25 min once)
	@echo "  base       $(BASE) @ $(REVISION)"
	@$(POD_ADDR); ssh $(SSH_OPTS) -p "$$PORT" "$$HOST" '\
	  set -e; cd $(REMOTE); \
	  flags="--model $(BASE) --revision $(REVISION)"; \
	  if python3 -c "import importlib.util as u, sys; sys.exit(0 if u.find_spec(\"unsloth\") else 1)"; \
	    then flags="--skip-deps $$flags"; else flags="--fast-kernels $$flags"; fi; \
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
