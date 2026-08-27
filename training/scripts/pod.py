#!/usr/bin/env python3
"""
Rent, watch and stop the H200 training pod, from your laptop.

    python training/scripts/pod.py gpus [h200]     # real GPU type ids on the account
    python training/scripts/pod.py plan            # validate + price, sends nothing
    python training/scripts/pod.py apply           # create (or update) the pod
    python training/scripts/pod.py status          # what is live, and the ssh command
    python training/scripts/pod.py stop            # stop billing, keep the disk
    python training/scripts/pod.py start           # resume
    python training/scripts/pod.py delete          # tear down, disk and all

Config is training/pod.yaml. Same idea as runpod/deploy.py — nothing is created by
clicking around the console, because a pod made there exists nowhere in git.

This is deliberately separate from runpod/deploy.py: that tool's `pod` kind is
shaped for serving (it renders a `vllm serve` command and preflights engine args).
A training pod runs nothing on boot but sshd; the work is started by hand.

Only dependency is PyYAML.  pip install pyyaml
"""

from __future__ import annotations

import argparse
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
CONFIG = HERE.parent / "pod.yaml"

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

def load_dotenv() -> None:
    """Load .env into os.environ. Values already in the environment win."""
    path = REPO / ".env"
    if not path.exists():
        raise Fail(".env not found. Copy .env.example to .env and fill it in.")
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def expand(obj):
    """
    Recursively replace ${VAR} with the value from the environment.

    ${VAR}          required — a missing value is a hard failure.
    ${VAR:-}        optional — falls back to the default (empty here), and an env
                    entry that resolves to empty is dropped rather than sent as "".
    """
    if isinstance(obj, str):
        def sub(m):
            name, default = m.group(1), m.group(2)
            value = os.environ.get(name)
            if value:
                return value
            if default is not None:
                return default
            raise Fail(f"${{{name}}} is referenced in pod.yaml but not set in .env")
        return VAR.sub(sub, obj)
    if isinstance(obj, dict):
        return {k: expand(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [expand(v) for v in obj]
    return obj


def load_config() -> dict:
    if not CONFIG.exists():
        raise Fail(f"{CONFIG} not found")
    cfg = yaml.safe_load(CONFIG.read_text()) or {}
    if not cfg.get("name"):
        raise Fail("pod.yaml needs a `name` — it is how the pod is found again")
    return cfg


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

def build_payload(cfg: dict, deps: dict) -> dict:
    gpu = expand(cfg.get("gpu", {}))
    disk = cfg.get("disk", {})
    container = expand(cfg.get("container", {}))

    payload = {
        "name": cfg["name"],
        "imageName": container["image"],
        "computeType": "GPU",
        "cloudType": gpu.get("cloudType", "SECURE"),
        "gpuTypeIds": [gpu["type"]],
        "gpuCount": int(gpu.get("count", 1)),
        "containerDiskInGb": int(disk.get("container_gb", 100)),
        "volumeMountPath": disk.get("mount_path", "/workspace"),
        "ports": container.get("ports", ["22/tcp", "8888/http"]),
        # env values must be strings — YAML turns 0.9 into a float and RunPod 400s.
        # Empty values are dropped: RunPod keeps them, and an empty HF_TOKEN on the
        # pod fails as a 401 on a private repo rather than as a missing variable.
        "env": {k: str(v) for k, v in (container.get("env") or {}).items() if str(v) != ""},
    }
    if gpu.get("dataCenterIds"):
        payload["dataCenterIds"] = gpu["dataCenterIds"]
        payload["dataCenterPriority"] = "custom"

    if not payload["env"].get("PUBLIC_KEY"):
        warn("SSH_PUBLIC_KEY is not in .env — you will not be able to ssh into the pod")
    if not payload["env"].get("HF_TOKEN"):
        warn("HF_TOKEN is not in .env — private scalejade/ repos will 401 on the pod")

    if disk.get("type") == "network_volume":
        payload["networkVolumeId"] = deps["volume"]
    else:
        payload["volumeInGb"] = int(disk.get("volume_gb", 200))
    return payload


def resolve_volume(cfg: dict) -> dict:
    """A network volume is referenced by name; the id is looked up on the account."""
    if cfg.get("disk", {}).get("type") != "network_volume":
        return {}
    name = cfg["disk"].get("volume_name")
    if not name:
        raise Fail("disk.type is network_volume but disk.volume_name is not set")
    vols = api("GET", "/networkvolumes")
    vols = vols.get("data", vols) if isinstance(vols, dict) else vols
    for v in vols or []:
        if v.get("name") == name:
            ok(f"network volume '{name}' -> {v['id']}  ({v.get('dataCenterId')})")
            region = (cfg.get("gpu", {}).get("dataCenterIds") or [None])[0]
            if region and v.get("dataCenterId") != region:
                raise Fail(
                    f"volume '{name}' is in {v.get('dataCenterId')} but the pod asks for "
                    f"{region}. Network volumes are region-local and will not attach. "
                    f"Either move the pod to {v.get('dataCenterId')} — if H200s are "
                    f"available there — or use disk.type: volume_disk."
                )
            return {"volume": v["id"]}
    raise Fail(
        f"network volume '{name}' does not exist on this account.\n"
        f"    Create it first:  python runpod/deploy.py apply {name}"
    )


def preflight(cfg: dict) -> None:
    gpu, disk = cfg.get("gpu", {}), cfg.get("disk", {})
    problems: list[str] = []

    if not gpu.get("type"):
        problems.append("gpu.type is required — run `pod.py gpus h200` for the real id")
    if int(gpu.get("count", 1)) != 1:
        problems.append(
            f"gpu.count={gpu.get('count')}. Unsloth is single-GPU: extra GPUs sit idle "
            f"and still bill. Use one H200, or move to Axolotl/TRL+FSDP."
        )
    if disk.get("type") not in ("volume_disk", "network_volume"):
        problems.append(f"disk.type={disk.get('type')!r} must be volume_disk or network_volume")
    if not gpu.get("dataCenterIds"):
        warn("no gpu.dataCenterIds — you get whatever region has capacity")
    if disk.get("type") == "volume_disk":
        warn("disk.type is volume_disk — the disk dies with the pod. STOP the pod when "
             "idle, never delete it, or the next run re-downloads the base model.")
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

    print(f"\n  {'id (put this in pod.yaml)':<32} {'name':<12} {'vram':>6} "
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
    for key in ("imageName", "gpuTypeIds", "gpuCount", "containerDiskInGb",
                "volumeInGb", "networkVolumeId", "volumeMountPath", "dataCenterIds"):
        if key in payload:
            info(f"{key:<20} {payload[key]}")
    for k, v in payload["env"].items():
        info(f"env {k:<16} {mask(k, v)}")

    price = cfg.get("cost", {}).get("usd_per_hour")
    if price:
        info(f"{'price':<20} ${price}/hr while RUNNING — a pod bills idle too "
             f"(${float(price) * 24:.0f}/day)")

    if not apply:
        print("\n  plan only — nothing sent. Apply with:  python training/scripts/pod.py apply\n")
        return

    live = find_pod(cfg["name"])
    if live:
        api("PATCH", f"/pods/{live['id']}", {
            "imageName": payload["imageName"],
            "env": payload["env"],
            "ports": payload["ports"],
        })
        ok(f"pod updated  {live['id']}  (image, env, ports — GPU and disk are fixed at creation)")
        pid = live["id"]
    else:
        pid = api("POST", "/pods", payload)["id"]
        ok(f"pod created  {pid}")

    print(f"\n  pod    {pid}")
    print( "  ssh    RunPod prints the exact command (it embeds a per-pod user hash):")
    print(f"         console -> Pods -> {cfg['name']} -> Connect -> SSH,")
    print( "         or `python training/scripts/pod.py status` once it is RUNNING")
    print( "  then   bash training/scripts/bootstrap.sh   # on the pod")
    print(f"  stop   python training/scripts/pod.py stop     # billing continues until you do\n")


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
         f"exposed 22/tcp port, using SSH_PUBLIC_KEY from .env)")
    print()


def cmd_power(action: str) -> None:
    cfg = load_config()
    live = find_pod(cfg["name"])
    if not live:
        raise Fail(f"pod '{cfg['name']}' is not on this account")
    api("POST", f"/pods/{live['id']}/{action}")
    ok(f"pod {live['id']} {action}ped" if action == "stop" else f"pod {live['id']} started")
    if action == "stop":
        info("GPU billing has stopped. The disk still bills until the pod is deleted.")


def cmd_delete() -> None:
    cfg = load_config()
    live = find_pod(cfg["name"])
    if not live:
        raise Fail(f"pod '{cfg['name']}' is not on this account")
    warn("this deletes the pod AND its disk. Adapters not pushed to the Hub are lost.")
    if input(f"  type the pod name to confirm [{cfg['name']}]: ").strip() != cfg["name"]:
        sys.exit("  aborted")
    api("DELETE", f"/pods/{live['id']}")
    ok(f"pod {live['id']} deleted")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gpus", help="list GPU type ids")
    g.add_argument("filter", nargs="?", help="substring, e.g. h200")
    sub.add_parser("plan", help="validate + price, send nothing")
    sub.add_parser("apply", help="create or update the pod")
    sub.add_parser("status", help="what is live")
    sub.add_parser("stop", help="stop billing, keep the disk")
    sub.add_parser("start", help="resume")
    sub.add_parser("delete", help="tear down, disk and all")
    args = ap.parse_args()

    load_dotenv()
    if args.cmd == "gpus":
        cmd_gpus(args.filter)
    elif args.cmd == "plan":
        cmd_plan(apply=False)
    elif args.cmd == "apply":
        cmd_plan(apply=True)
    elif args.cmd == "status":
        cmd_status()
    elif args.cmd in ("stop", "start"):
        cmd_power(args.cmd)
    elif args.cmd == "delete":
        cmd_delete()


if __name__ == "__main__":
    try:
        main()
    except Fail as e:
        sys.exit(f"\n  {c('error', '31')}  {e}\n")
    except KeyboardInterrupt:
        sys.exit("\n  aborted\n")
