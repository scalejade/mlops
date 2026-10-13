# Troubleshooting

Every failure we have hit on this stack, the symptom you will see, and the fix.
Most of these cost real H200 time the first time. Back to the [index](README.md).

## Creating pods and endpoints

### `POST /pods -> 400` … `dataCenterIds/items/enum`

**Cause.** RunPod's REST API only accepts a fixed list of datacenters for pods and
endpoints, and it lags the datacenters that exist. `US-CO-1` holds network volumes
but is rejected for both.

**Fix.** Use a datacenter from the API's list (`curl -s
https://rest.runpod.io/v1/openapi.json`, `PodCreateInput.dataCenterIds`). For a pod
on a network volume, `pod.py` no longer sends the pin at all — the volume decides
the region — and only uses it to check the volume matches.

### No instances available

`create pod: There are no instances currently available` (HTTP 500). The GPU was
listed as "Low" stock and someone took it. Nothing was created; nothing bills.

**Fix.** Retry later, or pick another datacenter. Stock per datacenter:

```bash
.venv/bin/python - <<'PY'
import sys; sys.path.insert(0, "training/scripts"); import pod
pod.load_dotenv()
d = pod.graphql('query { dataCenters { id storageSupport gpuAvailability { gpuTypeId stockStatus } } }')
for dc in d["dataCenters"]:
    for g in dc["gpuAvailability"] or []:
        if g["gpuTypeId"] == "NVIDIA H200" and g.get("stockStatus"):
            print(dc["id"], g["stockStatus"], "volumes" if dc["storageSupport"] else "no volumes")
PY
```

Training has no region pin, so this mostly bites serving and the loader (fixed to
the volume's datacenter).

### A stopped pod will not start again

A stopped volume-disk pod is tied to its physical machine. If that machine's GPU was
rented by someone else, `pod-start` fails or comes up without a GPU. **Fix:**
`make pod-delete` and `make pod-up` — and prefer delete over stop at the end of a run.

## On the training pod

### `HF_TOKEN is not set` although the pod was created with it

**Cause.** RunPod writes the pod's env to PID 1 and `/etc/rp_environment`, and only
an interactive shell's `.bashrc` sources that file. `make` runs everything over
non-interactive ssh.

**Fix (in place).** `run.sh` and `prepare.sh` source `/etc/rp_environment` first. If
you run something by hand over `ssh host 'cmd'`, do the same:
`set -a; . /etc/rp_environment; set +a`.

### `error: externally-managed-environment` from pip

**Cause.** The image's Python is Ubuntu 24.04's system Python 3.12, marked
EXTERNALLY-MANAGED (PEP 668), and torch lives in it.

**Fix (in place).** `bootstrap.sh`, `prepare.sh` and both `boot.sh` scripts export
`PIP_BREAK_SYSTEM_PACKAGES=1`. The container disk is thrown away with the pod, so
installing beside torch is intended.

### `prepare.sh` dies on `/workspace/mlops/.env: line 40: AAAAC3…: No such file`

**Cause.** Someone copied the laptop's root `.env` onto the pod. `prepare.sh`
sources `$REPO/.env` if present, and an unquoted `SSH_PUBLIC_KEY=ssh-ed25519 AAAA…`
line runs `AAAA…` as a command.

**Fix.** Delete it: `rm /workspace/mlops/.env`. It also put the account-wide
`RUNPOD_API_KEY` on the pod. The pod gets everything it needs from its chart's
`.env` at creation — never copy a `.env` onto a pod.

### Fast kernels do not install

`The fast path is not available … Falling back to torch implementation` during
training, after `!!  build failed` in `prepare.log`.

**What happened (2026-10-12).**

1. `pip install flash-linear-attention causal-conv1d` in one call: `causal-conv1d`'s
   isolated build pulled torch 2.14/CUDA 13 against the image's CUDA 12.8 toolkit and
   failed — and, being one call, `flash-linear-attention` was not installed either.
2. Installing them separately with `--no-build-isolation` and torch pinned got both
   in, but current `flash-linear-attention` imports `torchao` 0.18, which needs
   **torch ≥ 2.11**; with it installed, **transformers can no longer import the
   Qwen3.5 model at all**. Pinning `torchao==0.13` got past that into an
   `fla-core` / `flash-linear-attention` version clash.

**Current state.** `prepare.sh` keeps the original single call, which fails
*safely*: training runs on the slower fallback. Do not ship a partial fix — a
half-installed `fla` breaks model loading.

**Real fix (not done).** Move the training image to a torch ≥ 2.11 build, then
install the kernels normally. Test that on a cheap GPU, not an H200. Even on the
fallback, training is ~10 s per row; the cost is mostly in generation (quality check).

### `make train` refuses: uncommitted files

The pod runs `origin/<branch>`. `make train` refuses while `training/`,
`preparation/` or the `Makefile` have changes that are not pushed. Commit and push;
other uncommitted files are only warned about.

### `ssh-agent: no key loaded — the pod cannot clone from GitHub`

`ssh-add` (the key resets on every Mac restart). To load it automatically:
`AddKeysToAgent yes` + `IdentityFile ~/.ssh/id_ed25519` under `Host github.com` in
`~/.ssh/config`.

## Serving

### A worker crash-loops right after enabling LoRA

`MAX_CPU_LORAS=0` with `ENABLE_LORA=true`: vLLM requires `max_cpu_loras ≥
max_loras`. `deploy.py` now sets both to 1 whenever `adapter:` is set, and `plan`
fails on the combination.

### Cold starts download the model again although the volume is filled

The worker asked for a different revision than the loader pulled — usually an
unpinned `MODEL_REVISION` (resolves `main`) or an endpoint's `ADAPTER_REVISION`
not matching its entry in `BOOT_ADAPTERS`. Compare `models/<model>/model.config`,
`runpod/pbbi-serverless-<task>/.env` and `runpod/pbbi-loader/.env`; `cat
/workspace/loader.done` (via a loader pod) shows what is actually on the volume.

### Requests return HTTP 200 with content missing

`finish_reason: "length"` — the reply hit `max_tokens`. It is a failure, not a
success; callers must raise. Keep `max_tokens` ≥ the measured need (17,258) and the
context window large enough for prompt + output.

## Billing hygiene

- `make pod-status` / `python runpod/deploy.py list` show what is live and what it costs.
- A training pod bills from `pod-up` until `pod-delete`, idle or not.
- The volume bills continuously; `python runpod/deploy.py delete pbbi-volumes` stops
  it and destroys everything on it (re-fill with `make volume-fill`).
- Interactive confirmations (`pod-delete`, `deploy.py delete`) read from stdin;
  scripts pipe the name in, e.g. `echo pbbi-volumes | python runpod/deploy.py delete pbbi-volumes`.
