#!/usr/bin/env python3
"""
Rent, watch and stop the H200 training pod, from your laptop.

    python training/scripts/pod.py gpus [h200]     # real GPU type ids on the account
    python training/scripts/pod.py plan            # validate + price, sends nothing
    python training/scripts/pod.py apply           # create (or update) the pod
    python training/scripts/pod.py status          # what is live, and the ssh command
    python training/scripts/pod.py ssh-target      # "root@<ip> <port>", for the Makefile
    python training/scripts/pod.py stop            # stop billing (network volume: deletes the pod)
    python training/scripts/pod.py start           # resume (volume-disk pods only)
    python training/scripts/pod.py delete [--yes]  # tear down, disk and all

Config is a runpod/<chart>/ directory (chart.yaml + values.yaml), next to the
volume and endpoint charts it shares storage with. pbbi-training by default;
`--chart <name>` picks another, which is how `make pod-up <chart>` reaches it.
Same idea as runpod/deploy.py — nothing is created by clicking around the
console, because a pod made there exists nowhere in git.

This is deliberately separate from runpod/deploy.py: that tool's `pod` kind is
shaped for serving (it renders a `vllm serve` command and preflights engine args).
A training pod runs nothing on boot but sshd; the work is started by hand.

A chart's values.yaml has either a `gpu:` block (pbbi-training, the H200) or a
`cpu:` block (pbbi-loader, which only downloads models onto pbbi-volumes for the
serving endpoint, so it has no reason to rent a GPU).

Only dependency is PyYAML.  pip install pyyaml
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required:  pip install pyyaml")

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DEFAULT_CHART = "pbbi-training"
CHART = REPO / "runpod" / DEFAULT_CHART   # --chart replaces it

API = "https://rest.runpod.io/v1"
# REST v1 has no GPU catalogue — /gpuTypes 400s with "that path does not exist in
# the specification". The old GraphQL API is the only place the ids and live prices
# are readable, so `gpus` is the one command that talks to it.
GRAPHQL = "https://api.runpod.io/graphql"
VAR = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")
SECRET_KEYS = {"HF_TOKEN", "RUNPOD_API_KEY", "WANDB_API_KEY"}


class Fail(Exception):
    """A problem the user needs to fix. Printed without a traceback."""


def c(text: str, code: str) -> str:
    return text if not sys.stdout.isatty() else f"\033[{code}m{text}\033[0m"


def info(msg: str) -> None:
    print(f"  {msg}")


def ok(msg: str) -> None:
    print(f"  {c('ok', '32')}  {msg}")


def warn(msg: str) -> None:
    print(f"  {c('warn', '33')}  {msg}")


def mask(key: str, value) -> str:
    value = str(value)
    if key in SECRET_KEYS and value:
        return value[:6] + "…" + value[-4:] if len(value) > 12 else "…"
    return value


# ------------------------------------------------------------------- config

def read_env_file(path: Path) -> dict[str, str]:
    """KEY=VALUE lines into a dict. Missing file -> empty dict."""
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip("'\"")
    return env


def load_dotenv() -> None:
    """Load the root .env into os.environ. Values already in the environment win.

    It holds this laptop's credentials — RUNPOD_API_KEY — and nothing the pod gets.
    The pod's secrets live in runpod/<chart>/.env; see expand().
    """
    path = REPO / ".env"
    if not path.exists():
        raise Fail(".env not found. Copy .env.example to .env and set RUNPOD_API_KEY.")
    for key, value in read_env_file(path).items():
        os.environ.setdefault(key, value)


# runpod/<chart>/.env, read by load_config(). The only source expand() consults.
SECRETS: dict[str, str] = {}


def chart_env_path() -> str:
    return f"runpod/{CHART.name}/.env"


def expand(obj):
    """
    Recursively replace ${VAR} with the value from the chart's own .env — not the
    root .env, not the shell — so the pod only ever gets the secrets put next to it.

    ${VAR}          required — a missing value is a hard failure.
    ${VAR:-}        optional — falls back to the default (empty here), and an env
                    entry that resolves to empty is dropped rather than sent as "".
    """
    if isinstance(obj, str):
        def sub(m):
            name, default = m.group(1), m.group(2)
            value = SECRETS.get(name)
            if value:
                return value
            if default is not None:
                return default
            raise Fail(f"${{{name}}} is referenced in {CHART.name}/values.yaml but not set in "
                       f"{chart_env_path()}\n    cp {chart_env_path()}.example {chart_env_path()}")
        return VAR.sub(sub, obj)
    if isinstance(obj, dict):
        return {k: expand(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [expand(v) for v in obj]
    return obj


def load_config() -> dict:
    """values.yaml, with the chart's name, description and dependencies on top.

    The pod's name is the chart's name: it is how the pod is found again, and the
    chart directory is what makes it unique among everything on the account.
    """
    chart_path, values_path = CHART / "chart.yaml", CHART / "values.yaml"
    for path in (chart_path, values_path):
        if not path.exists():
            raise Fail(f"{path.relative_to(REPO)} not found")
    chart = yaml.safe_load(chart_path.read_text()) or {}
    if chart.get("kind") != "pod":
        raise Fail(f"{chart_path.relative_to(REPO)} has kind={chart.get('kind')!r}, expected pod")
    cfg = yaml.safe_load(values_path.read_text()) or {}
    cfg["name"] = chart.get("name") or CHART.name
    cfg["description"] = chart.get("description")
    cfg["dependencies"] = chart.get("dependencies") or []
    SECRETS.clear()
    SECRETS.update(read_env_file(CHART / ".env"))
    return cfg


def compute(cfg: dict) -> tuple[str, dict]:
    """("GPU", gpu block) or ("CPU", cpu block). Exactly one of the two is set."""
    if cfg.get("cpu") and cfg.get("gpu"):
        raise Fail(f"{CHART.name}/values.yaml has both gpu: and cpu: — a pod is one or the other")
    return ("CPU", cfg["cpu"]) if cfg.get("cpu") else ("GPU", cfg.get("gpu") or {})


def on_network_volume(cfg: dict) -> bool:
    return cfg.get("disk", {}).get("type") == "network_volume"


def volume_dependency(cfg: dict) -> str | None:
    return next((d["name"] for d in cfg.get("dependencies") or []
                 if d.get("kind") == "volume"), None)


# ---------------------------------------------------------------------- api

def api(method: str, path: str, body: dict | None = None):
    key = os.environ.get("RUNPOD_API_KEY")
    if not key:
        raise Fail("RUNPOD_API_KEY is not set in .env")
    req = urllib.request.Request(
        API + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            # Cloudflare 403s (error 1010) on urllib's default User-Agent.
            "User-Agent": "scalejade-mlops/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:600]
        raise Fail(f"RunPod {method} {path} -> {e.code}\n    {detail}")
    except urllib.error.URLError as e:
        raise Fail(f"cannot reach RunPod: {e.reason}")


def graphql(query: str) -> dict:
    key = os.environ.get("RUNPOD_API_KEY")
    if not key:
        raise Fail("RUNPOD_API_KEY is not set in .env")
    req = urllib.request.Request(
        f"{GRAPHQL}?api_key={key}",
        method="POST",
        data=json.dumps({"query": query}).encode(),
        # Cloudflare 403s (error 1010) on urllib's default User-Agent. curl gets
        # through, so send something that looks like a client.
        headers={"Content-Type": "application/json", "User-Agent": "scalejade-mlops/1.0"},
    )
    try:
        with urllib.request.urlopen(req) as r:
            body = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise Fail(f"RunPod GraphQL -> {e.code}\n    {e.read().decode()[:400]}")
    except urllib.error.URLError as e:
        raise Fail(f"cannot reach RunPod: {e.reason}")
    if body.get("errors"):
        raise Fail(f"RunPod GraphQL: {body['errors'][0].get('message')}")
    return body["data"]


def find_pod(name: str) -> dict | None:
    pods = api("GET", "/pods")
    pods = pods.get("data", pods) if isinstance(pods, dict) else pods
    for p in pods or []:
        if p.get("name") == name:
            return p
    return None


# ------------------------------------------------------------------ payload

HF_URL = re.compile(r"^https?://huggingface\.co/([^/\s]+/[^/\s]+?)(?:/tree/([^/\s]+))?/?$")


def boot_ref(cfg: dict, key: str = "model") -> tuple[str, str] | None:
    """values.yaml boot.<key> / boot.<key>_revision -> (repo id, revision), or None.

    key is "model" (boot.model / boot.revision). Takes a repo id (scalejade/x) or its huggingface.co URL,
    as copied from the browser; a /tree/<rev> URL also supplies the revision. Empty
    means nothing to pull. Both may be ${VAR}s from the chart's .env.
    """
    boot = expand(cfg.get("boot") or {})
    rev_key = "revision" if key == "model" else f"{key}_revision"
    repo = str(boot.get(key) or "").strip()
    revision = str(boot.get(rev_key) or "").strip()
    if not repo:
        return None
    m = HF_URL.match(repo)
    if m:
        repo, revision = m.group(1), revision or (m.group(2) or "")
    if repo.count("/") != 1:
        raise Fail(f"boot.{key}={repo!r} — expected <org>/<name> or a huggingface.co URL")
    if not revision:
        warn(f"boot.{rev_key} is empty — pulling {repo} @ main, which moves. Pin a sha or tag.")
        revision = "main"
    return repo, revision


def boot_adapters(cfg: dict) -> list[tuple[str, str]]:
    """values.yaml boot.adapters -> [(repo id, revision), ...].

    One string, "repo@revision" entries separated by commas (BOOT_ADAPTERS in the
    chart's .env), so one `make volume-fill` puts every endpoint's adapter on the
    volume. Each entry must carry its revision: an unpinned adapter is exactly what
    makes a worker download again on its cold start.
    """
    raw = str(expand((cfg.get("boot") or {}).get("adapters") or "")).strip()
    out = []
    for entry in filter(None, (e.strip() for e in raw.split(","))):
        repo, _, rev = entry.partition("@")
        if repo.count("/") != 1 or not rev:
            raise Fail(f"boot.adapters entry {entry!r} — expected <org>/<name>@<tag or sha>")
        out.append((repo, rev))
    return out


def check_on_hub(model: str, revision: str, what: str = "boot model") -> None:
    """Resolve the repo and revision with the pod's own HF_TOKEN, before anything bills.

    A typo here would otherwise surface as a 404 in the boot log of a running H200.
    """
    req = urllib.request.Request(
        f"https://huggingface.co/api/models/{model}/revision/{revision}?blobs=true",
        headers={"User-Agent": "scalejade-mlops/1.0",
                 **({"Authorization": f"Bearer {SECRETS['HF_TOKEN']}"} if SECRETS.get("HF_TOKEN") else {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            info_ = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 404):
            raise Fail(f"{what}: {model} @ {revision} is not readable with the HF_TOKEN in "
                       f"{chart_env_path()} (HTTP {e.code}) — wrong name, wrong revision, or "
                       f"the token has no access to it")
        warn(f"could not check {model} on the Hub (HTTP {e.code}) — the pod will try anyway")
        return
    except urllib.error.URLError as e:
        warn(f"could not reach the Hub to check {model} ({e.reason}) — the pod will try anyway")
        return
    size = sum((f.get("size") or 0) for f in info_.get("siblings") or []) / 1e9
    ok(f"{what} {model} @ {str(info_.get('sha'))[:12]} on the Hub, {size:.1f} GB")


def boot_command(cfg: dict) -> tuple[list[str], dict[str, str]] | None:
    """values.yaml `boot:` -> (dockerStartCmd, env), or None when there is no boot block.

    The script ships inside the start command, base64 so its newlines and quotes
    survive the API untouched, and runs as the container's CMD — so it must end by
    exec'ing the image's own /start.sh, or the pod comes up without sshd. It is sent
    even with no model, so an existing pod's start command is replaced rather than
    left pulling the previous one; with no BOOT_MODEL it pulls nothing.
    """
    boot = cfg.get("boot")
    if not boot:
        return None
    script = CHART / boot.get("script", "boot.sh")
    if not script.exists():
        raise Fail(f"boot.script: {script.relative_to(REPO)} not found")
    encoded = base64.b64encode(script.read_bytes()).decode()
    cmd = ["bash", "-c", f"echo {encoded} | base64 -d > /boot.sh && exec bash /boot.sh"]
    env = {}
    model, adapters = boot_ref(cfg, "model"), boot_adapters(cfg)
    if model:
        env.update(BOOT_MODEL=model[0], BOOT_REVISION=model[1])
    if adapters:
        env["BOOT_ADAPTERS"] = ",".join(f"{r}@{v}" for r, v in adapters)
    return cmd, env


def build_payload(cfg: dict, deps: dict) -> dict:
    kind, block = compute(cfg)
    block = expand(block)
    disk = cfg.get("disk", {})
    container = expand(cfg.get("container", {}))

    payload = {
        "name": cfg["name"],
        "imageName": container["image"],
        "computeType": kind,
        "cloudType": block.get("cloudType", "SECURE"),
        **({"cpuFlavorIds": list(block["flavors"]),
            "cpuFlavorPriority": "availability",
            "vcpuCount": int(block.get("vcpus", 2))} if kind == "CPU" else
           {"gpuTypeIds": [block["type"]],
            "gpuCount": int(block.get("count", 1))}),
        "containerDiskInGb": int(disk.get("container_gb", 100)),
        "volumeMountPath": disk.get("mount_path", "/workspace"),
        "ports": container.get("ports", ["22/tcp", "8888/http"]),
        # env values must be strings — YAML turns 0.9 into a float and RunPod 400s.
        # Empty values are dropped: RunPod keeps them, and an empty HF_TOKEN on the
        # pod fails as a 401 on a private repo rather than as a missing variable.
        "env": {k: str(v) for k, v in (container.get("env") or {}).items() if str(v) != ""},
    }
    # On a network volume the volume decides the region: RunPod places the pod in
    # its datacenter, and resolve_volume() has already checked the pin agrees. The
    # pin is not sent, because REST v1's dataCenterIds enum lags the datacenters
    # volumes exist in — US-CO-1 holds volumes but is a 400 on POST /pods.
    if block.get("dataCenterIds") and disk.get("type") != "network_volume":
        payload["dataCenterIds"] = block["dataCenterIds"]
        payload["dataCenterPriority"] = "custom"

    # train.py turns this into the cost/ panels on W&B. Informational only: the
    # real bill is RunPod's, and this is the rate values.yaml was last checked at.
    if cfg.get("cost", {}).get("usd_per_hour"):
        payload["env"]["POD_USD_PER_HOUR"] = str(cfg["cost"]["usd_per_hour"])

    boot = boot_command(cfg)
    if boot:
        payload["dockerStartCmd"], boot_env = boot
        payload["env"].update(boot_env)

    if not payload["env"].get("PUBLIC_KEY"):
        warn(f"SSH_PUBLIC_KEY is not in {chart_env_path()} — you will not be able to ssh into the pod")
    if not payload["env"].get("HF_TOKEN"):
        warn(f"HF_TOKEN is not in {chart_env_path()} — private scalejade/ repos will 401 on the pod")

    if disk.get("type") == "network_volume":
        payload["networkVolumeId"] = deps["volume"]
    else:
        payload["volumeInGb"] = int(disk.get("volume_gb", 200))
    return payload


def resolve_volume(cfg: dict) -> dict:
    """The chart's volume dependency is referenced by name; the id is looked up on the account."""
    if not on_network_volume(cfg):
        return {}
    name = volume_dependency(cfg)
    if not name:
        raise Fail("disk.type is network_volume but chart.yaml declares no volume dependency")
    vols = api("GET", "/networkvolumes")
    vols = vols.get("data", vols) if isinstance(vols, dict) else vols
    for v in vols or []:
        if v.get("name") == name:
            ok(f"network volume '{name}' -> {v['id']}  ({v.get('dataCenterId')})")
            region = (compute(cfg)[1].get("dataCenterIds") or [None])[0]
            if region and v.get("dataCenterId") != region:
                raise Fail(
                    f"volume '{name}' is in {v.get('dataCenterId')} but the pod asks for "
                    f"{region}. Network volumes are region-local and will not attach. "
                    f"Pin the pod to {v.get('dataCenterId')} in values.yaml, or (a GPU "
                    f"pod with no H200 there) use disk.type: volume_disk."
                )
            return {"volume": v["id"]}
    raise Fail(
        f"network volume '{name}' does not exist on this account.\n"
        f"    Create it first:  python runpod/deploy.py apply {name}"
    )


def preflight(cfg: dict) -> None:
    kind, gpu = compute(cfg)
    disk = cfg.get("disk", {})
    problems: list[str] = []

    if kind == "CPU":
        if not gpu.get("flavors"):
            problems.append("cpu.flavors is required — e.g. [cpu3c, cpu5c] (REST v1 cpuFlavorIds)")
    elif not gpu.get("type"):
        problems.append("gpu.type is required — run `pod.py gpus h200` for the real id")
    elif int(gpu.get("count", 1)) != 1:
        problems.append(
            f"gpu.count={gpu.get('count')}. Unsloth is single-GPU: extra GPUs sit idle "
            f"and still bill. Use one H200, or move to Axolotl/TRL+FSDP."
        )
    if disk.get("type") not in ("volume_disk", "network_volume"):
        problems.append(f"disk.type={disk.get('type')!r} must be volume_disk or network_volume")
    if on_network_volume(cfg):
        if not volume_dependency(cfg):
            problems.append("disk.type is network_volume but chart.yaml declares no volume "
                            "dependency — there is no volume to attach")
        if gpu.get("cloudType", "SECURE") != "SECURE":
            problems.append(f"cloudType={gpu.get('cloudType')} cannot attach a network "
                            f"volume — they exist on Secure Cloud only")
        if not gpu.get("dataCenterIds"):
            problems.append("a network volume pod must pin dataCenterIds to the volume's "
                            "datacenter, or RunPod may place it where the volume cannot attach")
    if not gpu.get("dataCenterIds"):
        info("no dataCenterIds pin — the pod goes wherever there is capacity")
    if disk.get("type") == "volume_disk":
        info("disk.type is volume_disk — the disk dies with the pod. `make pod-delete` when "
             "done (a stopped pod still bills its disk); the adapter is on the Hub by then.")
    if int(disk.get("volume_gb", 0) or 0) < 150 and disk.get("type") == "volume_disk":
        warn(f"volume_gb={disk.get('volume_gb')} — a bf16 30B checkpoint alone is ~60 GB "
             f"before optimizer state and checkpoints.")

    if problems:
        raise Fail("preflight failed:\n" + "\n".join(f"    - {p}" for p in problems))
    ok("preflight passed")


# ----------------------------------------------------------------- commands

def cmd_gpus(filter_: str | None) -> None:
    data = graphql(
        "query { gpuTypes { id displayName memoryInGb secureCloud communityCloud "
        "securePrice communityPrice lowestPrice(input:{gpuCount:1}) { stockStatus } } }"
    )
    rows = [
        g for g in data["gpuTypes"]
        if not filter_ or filter_.lower() in (g["id"] + g["displayName"]).lower()
    ]
    if not rows:
        raise Fail(f"no GPU type matches {filter_!r}")

    print(f"\n  {'id (gpu.type in values.yaml)':<32} {'name':<12} {'vram':>6} "
          f"{'secure':>8} {'commty':>8}  stock")
    for g in sorted(rows, key=lambda g: g["memoryInGb"]):
        stock = (g.get("lowestPrice") or {}).get("stockStatus") or "-"
        print(f"  {g['id']:<32} {g['displayName']:<12} {str(g['memoryInGb']) + ' GB':>6} "
              f"{'$' + str(g['securePrice']):>8} {'$' + str(g['communityPrice']):>8}  {stock}")
    print("\n  gpu.type takes the id on the left, exactly. gpu.cloudType picks which\n"
          "  price you pay: SECURE, or COMMUNITY (cheaper, interruptible).\n")


def cmd_plan(apply: bool = False) -> None:
    cfg = load_config()
    print(f"\n{c('pod', '1')}  {cfg['name']}")
    if cfg.get("description"):
        info(cfg["description"])
    print()
    preflight(cfg)
    deps = resolve_volume(cfg)
    payload = build_payload(cfg, deps)

    print()
    for key in ("imageName", "computeType", "gpuTypeIds", "gpuCount", "cpuFlavorIds",
                "vcpuCount", "containerDiskInGb", "volumeInGb", "networkVolumeId",
                "volumeMountPath", "dataCenterIds"):
        if key in payload:
            info(f"{key:<20} {payload[key]}")
    for k, v in payload["env"].items():
        info(f"env {k:<16} {mask(k, v)}")

    if payload["env"].get("BOOT_MODEL"):
        info(f"{'boot':<20} pulls {payload['env']['BOOT_MODEL']} @ "
             f"{payload['env']['BOOT_REVISION'][:12]} into /workspace/hf, in the background")
        check_on_hub(payload["env"]["BOOT_MODEL"], payload["env"]["BOOT_REVISION"])
        for repo, rev in boot_adapters(cfg):
            info(f"{'boot':<20} and {repo} @ {rev} into /workspace/adapters/{repo.split('/')[1]}/{rev}")
            check_on_hub(repo, rev, what="boot adapter")
    elif payload.get("dockerStartCmd"):
        info(f"{'boot':<20} boot.model is empty — no model is pulled")

    price = cfg.get("cost", {}).get("usd_per_hour")
    if price:
        info(f"{'price':<20} ${price}/hr while RUNNING — a pod bills idle too "
             f"(${float(price) * 24:.0f}/day)")

    if not apply:
        print(f"\n  plan only — nothing sent. Apply with:  make pod-up {CHART.name}\n")
        return

    live = find_pod(cfg["name"])
    if live:
        api("PATCH", f"/pods/{live['id']}", {
            "imageName": payload["imageName"],
            "env": payload["env"],
            "ports": payload["ports"],
            **({"dockerStartCmd": payload["dockerStartCmd"]} if "dockerStartCmd" in payload else {}),
        })
        ok(f"pod updated  {live['id']}  (image, env, ports, boot — GPU and disk are fixed at creation)")
        pid = live["id"]
    else:
        pid = api("POST", "/pods", payload)["id"]
        ok(f"pod created  {pid}")

    print(f"\n  pod    {pid}")
    print( "  ssh    RunPod prints the exact command (it embeds a per-pod user hash):")
    print(f"         console -> Pods -> {cfg['name']} -> Connect -> SSH,")
    print( "         or `python training/scripts/pod.py status` once it is RUNNING")
    if payload["env"].get("BOOT_MODEL"):
        print( "  boot   the base model is downloading into /workspace/hf in the background.")
        print(f"         watch it: make pod-ssh {CHART.name}, then tail -f /workspace/boot-model.log")
    if payload["computeType"] == "CPU":
        print( "  then   make volume-fill waits for the download and deletes this pod")
        print(f"  stop   make pod-delete {CHART.name}   # if you created it by hand\n")
        return
    print( "  then   make train   (it waits for the boot download)")
    print(f"  stop   make pod-delete {CHART.name}   # when the adapter is on the Hub; billing "
          f"continues until you do\n")


def cmd_status() -> None:
    cfg = load_config()
    live = find_pod(cfg["name"])
    if not live:
        sys.exit(f"\n  pod '{cfg['name']}' is not on this account\n")
    print()
    for key in ("id", "desiredStatus", "lastStatusChange", "machineId", "gpuCount",
                "costPerHr", "volumeInGb", "networkVolumeId", "imageName"):
        if live.get(key) is not None:
            info(f"{key:<20} {live[key]}")
    for key in ("publicIp", "portMappings", "sshCommand"):
        if live.get(key):
            info(f"{key:<20} {live[key]}")
    info(f"{'connect':<20} console -> Pods -> {cfg['name']} -> Connect (SSH over the "
         f"exposed 22/tcp port, using SSH_PUBLIC_KEY from {chart_env_path()})")
    print()


def cmd_ssh_target() -> None:
    """
    Print "root@<publicIp> <port>" for the pod's exposed 22/tcp, and nothing else,
    so the Makefile can ssh/scp without anyone copying an address by hand. Fails
    (non-zero, message on stderr) when the pod is missing, not running, or has
    no public ssh port yet -- right after `apply` it can take a minute to appear.
    """
    cfg = load_config()
    live = find_pod(cfg["name"])
    if not live:
        raise Fail(f"pod '{cfg['name']}' is not on this account — make pod-up {CHART.name} first")
    if live.get("desiredStatus") != "RUNNING":
        raise Fail(f"pod '{cfg['name']}' is {live.get('desiredStatus')} — make pod-start first")
    ip, ports = live.get("publicIp"), live.get("portMappings") or {}
    port = ports.get("22") or ports.get(22)
    if not ip or not port:
        raise Fail(f"pod '{cfg['name']}' has no public ssh port yet "
                   f"(publicIp={ip!r}, portMappings={ports!r}). Wait a minute and retry; "
                   f"if it persists, check values.yaml exposes 22/tcp.")
    print(f"root@{ip} {port}")


def cmd_power(action: str) -> None:
    cfg = load_config()
    if on_network_volume(cfg):
        if action == "start":
            raise Fail("a pod on a network volume is deleted, not stopped, so there is "
                       f"nothing to start. Create a fresh one:  make pod-up {CHART.name}")
        # RunPod cannot stop a pod with a network volume attached; the only way to end
        # GPU billing is to delete it. Nothing is lost that matters: /workspace is the
        # volume, and it outlives the pod.
        info("this pod is on a network volume, which RunPod cannot stop — deleting it is")
        info("how GPU billing ends. /workspace stays on the volume.")
        cmd_delete()
        return
    live = find_pod(cfg["name"])
    if not live:
        raise Fail(f"pod '{cfg['name']}' is not on this account")
    api("POST", f"/pods/{live['id']}/{action}")
    ok(f"pod {live['id']} {action}ped" if action == "stop" else f"pod {live['id']} started")
    if action == "stop":
        info("GPU billing has stopped. The disk still bills until the pod is deleted.")


def cmd_delete(yes: bool = False) -> None:
    cfg = load_config()
    live = find_pod(cfg["name"])
    if not live:
        raise Fail(f"pod '{cfg['name']}' is not on this account")
    if on_network_volume(cfg):
        info(f"/workspace (base, checkpoints, adapters, logs) stays on '{volume_dependency(cfg)}'.")
        info("the container disk goes: pip deps reinstall on the next pod.")
        if live.get("desiredStatus") == "RUNNING":
            warn("if training is still running it is killed with the pod — make train-logs first.")
    else:
        warn("this deletes the pod AND its disk. Adapters not pushed to the Hub are lost.")
    if not yes and input(f"  type the pod name to confirm [{cfg['name']}]: ").strip() != cfg["name"]:
        sys.exit("  aborted")
    api("DELETE", f"/pods/{live['id']}")
    ok(f"pod {live['id']} deleted")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chart", default=DEFAULT_CHART,
                    help="chart directory under runpod/ (default: %(default)s)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gpus", help="list GPU type ids")
    g.add_argument("filter", nargs="?", help="substring, e.g. h200")
    sub.add_parser("plan", help="validate + price, send nothing")
    sub.add_parser("apply", help="create or update the pod")
    sub.add_parser("status", help="what is live")
    sub.add_parser("ssh-target", help='print "root@<ip> <port>" for scripts')
    sub.add_parser("stop", help="stop billing, keep the disk (on a network volume: delete)")
    sub.add_parser("start", help="resume a stopped volume-disk pod")
    d = sub.add_parser("delete", help="tear down, disk and all")
    d.add_argument("--yes", action="store_true",
                   help="no confirmation prompt (make volume-fill, after the download is verified)")
    args = ap.parse_args()

    global CHART
    CHART = REPO / "runpod" / args.chart

    load_dotenv()
    if args.cmd == "gpus":
        cmd_gpus(args.filter)
    elif args.cmd == "plan":
        cmd_plan(apply=False)
    elif args.cmd == "apply":
        cmd_plan(apply=True)
    elif args.cmd == "status":
        cmd_status()
    elif args.cmd == "ssh-target":
        cmd_ssh_target()
    elif args.cmd in ("stop", "start"):
        cmd_power(args.cmd)
    elif args.cmd == "delete":
        cmd_delete(yes=args.yes)


if __name__ == "__main__":
    try:
        main()
    except Fail as e:
        sys.exit(f"\n  {c('error', '31')}  {e}\n")
    except KeyboardInterrupt:
        sys.exit("\n  aborted\n")
