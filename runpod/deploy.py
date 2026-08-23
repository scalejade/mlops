#!/usr/bin/env python3
"""
Deploy a Scalejade model to RunPod Serverless from your laptop.

    python runpod/deploy.py plan   pjp-clause-extraction    # show what would change
    python runpod/deploy.py apply  pjp-clause-extraction    # create or update
    python runpod/deploy.py status pjp-clause-extraction    # what is live now
    python runpod/deploy.py delete pjp-clause-extraction    # tear down
    python runpod/deploy.py list                            # all endpoints on the account

Reads:
    runpod/endpoints/<name>.yaml    hardware, scaling, storage
    models/<model>/model.config     vLLM engine args -> template env
    .env                            RUNPOD_API_KEY, HF_TOKEN, RUNPOD_NETWORK_VOLUME_ID

Idempotent: it looks up the template and endpoint by name and PATCHes them if
they already exist. Running apply twice is safe.

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

REPO = Path(__file__).resolve().parent.parent
API = "https://rest.runpod.io/v1"
VAR = re.compile(r"\$\{([A-Z0-9_]+)\}")

# Keys in model.config that are secrets — masked in output, never printed.
SECRET_KEYS = {"HF_TOKEN", "RUNPOD_API_KEY", "WANDB_API_KEY"}


# --------------------------------------------------------------------------- io

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


def mask(key: str, value: str) -> str:
    if key in SECRET_KEYS and value:
        return value[:6] + "…" + value[-4:] if len(value) > 12 else "…"
    return value


# ---------------------------------------------------------------------- config

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
    """Recursively replace ${VAR} with the value from the environment."""
    if isinstance(obj, str):
        def sub(m):
            name = m.group(1)
            value = os.environ.get(name)
            if value is None or value == "":
                raise Fail(f"${{{name}}} is referenced in config but not set in .env")
            return value
        return VAR.sub(sub, obj)
    if isinstance(obj, dict):
        return {k: expand(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [expand(v) for v in obj]
    return obj


def load_endpoint_config(name: str) -> dict:
    path = REPO / "runpod" / "endpoints" / f"{name}.yaml"
    if not path.exists():
        available = sorted(
            p.stem for p in (REPO / "runpod" / "endpoints").glob("*.yaml")
            if not p.stem.startswith("_")
        )
        raise Fail(f"no config at {path.relative_to(REPO)}\n  available: {', '.join(available) or '(none)'}")
    cfg = yaml.safe_load(path.read_text())
    cfg.setdefault("name", name)
    return cfg


def load_model_config(model: str) -> dict:
    """Parse models/<model>/model.config (KEY=VALUE) into the template env dict."""
    path = REPO / "models" / model / "model.config"
    if not path.exists():
        raise Fail(f"no engine config at {path.relative_to(REPO)}")
    env: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        # Strip trailing inline comments, but only when clearly separated,
        # so a '#' inside a real value survives.
        value = re.split(r"\s+#", value, maxsplit=1)[0].strip().strip("'\"")
        env[key.strip()] = value
    return env


# ------------------------------------------------------------------- preflight

def preflight(cfg: dict, env: dict) -> None:
    """Catch the failures we have already paid for once. Raises on anything fatal."""
    ep = cfg.get("endpoint", {})
    problems: list[str] = []

    tp = int(env.get("TENSOR_PARALLEL_SIZE", 1) or 1)
    gpus = int(ep.get("gpuCount", 1) or 1)
    if tp != gpus:
        problems.append(
            f"TENSOR_PARALLEL_SIZE={tp} but gpuCount={gpus}. These must match, or the "
            f"worker dies with 'DP adjusted local rank N is out of bounds for {gpus} devices'."
        )

    max_len = int(env.get("MAX_MODEL_LEN", 0) or 0)
    if max_len <= 0:
        problems.append(
            "MAX_MODEL_LEN is empty or 0. vLLM >=0.27 rejects 0 instead of treating it "
            "as auto, and the worker will not boot."
        )

    if not ep.get("networkVolumeId"):
        problems.append(
            "networkVolumeId is not set. Without a network volume every worker "
            "re-downloads the checkpoint: ~2h cold start instead of ~26s."
        )

    if not ep.get("dataCenterIds"):
        warn("dataCenterIds is unset — workers may spread across regions and get throttled.")

    if ep.get("workersMax", 1) and int(ep.get("workersMax", 1)) > 1 and not ep.get("networkVolumeId"):
        warn("workersMax > 1 without a shared volume multiplies download cost per worker.")

    # max_tokens has to fit inside the context window alongside the prompt.
    max_tokens = int(cfg.get("request_defaults", {}).get("max_tokens", 0) or 0)
    if max_tokens and max_len and max_tokens >= max_len:
        problems.append(
            f"request_defaults.max_tokens={max_tokens} leaves no room for the prompt "
            f"inside MAX_MODEL_LEN={max_len}."
        )
    if max_tokens and max_len and max_tokens < 0.3 * max_len:
        warn(
            f"max_tokens={max_tokens} is small relative to MAX_MODEL_LEN={max_len}. "
            "Truncated responses return HTTP 200 with content silently missing — "
            "check finish_reason on every call."
        )

    if problems:
        raise Fail("preflight failed:\n" + "\n".join(f"    - {p}" for p in problems))
    ok("preflight passed")


# ------------------------------------------------------------------------- api

def api(method: str, path: str, body: dict | None = None) -> dict | list:
    key = os.environ.get("RUNPOD_API_KEY")
    if not key:
        raise Fail("RUNPOD_API_KEY is not set in .env")
    req = urllib.request.Request(
        f"{API}{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:600]
        if e.code == 401:
            raise Fail("RunPod rejected the API key (401). Check RUNPOD_API_KEY in .env.")
        raise Fail(f"RunPod API {method} {path} -> {e.code}\n    {detail}")
    except urllib.error.URLError as e:
        raise Fail(f"could not reach RunPod: {e.reason}")


def find_by_name(collection: str, name: str) -> dict | None:
    items = api("GET", f"/{collection}")
    if isinstance(items, dict):
        items = items.get(collection) or items.get("data") or []
    return next((i for i in items if i.get("name") == name), None)


# -------------------------------------------------------------------- commands

def build_payloads(cfg: dict) -> tuple[dict, dict, dict]:
    """Return (template_payload, endpoint_payload, engine_env)."""
    model = cfg.get("model")
    if not model:
        raise Fail("config is missing 'model'")

    engine_env = load_model_config(model)
    engine_env = expand(engine_env)

    tpl = expand(cfg.get("template", {}))
    template_payload = {
        "name": cfg["name"],
        "imageName": tpl.get("imageName"),
        "isServerless": True,
        "containerDiskInGb": tpl.get("containerDiskInGb", 20),
        "volumeMountPath": tpl.get("volumeMountPath", "/runpod-volume"),
        "env": engine_env,
    }
    if not template_payload["imageName"]:
        raise Fail("template.imageName is required — pin the vLLM worker image explicitly")

    endpoint_payload = expand(cfg.get("endpoint", {}))
    endpoint_payload["name"] = cfg["name"]

    return template_payload, endpoint_payload, engine_env


def cmd_plan(name: str, apply: bool = False) -> None:
    cfg = load_endpoint_config(name)
    template_payload, endpoint_payload, engine_env = build_payloads(cfg)

    print(f"\n{c('endpoint', '1')}  {cfg['name']}")
    print(f"{c('model', '1')}     {cfg['model']}" + (f"  + adapter {cfg['adapter']}" if cfg.get("adapter") else ""))
    print(f"{c('image', '1')}     {template_payload['imageName']}\n")

    preflight(cfg, engine_env)

    print(f"\n  {c('hardware', '1')}")
    for k in ("gpuTypeIds", "gpuCount", "workersMin", "workersMax", "idleTimeout",
              "scalerType", "scalerValue", "executionTimeoutMs", "dataCenterIds",
              "networkVolumeId", "flashboot"):
        if k in endpoint_payload:
            info(f"{k:<20} {endpoint_payload[k]}")

    print(f"\n  {c('engine env', '1')}  ({len(engine_env)} vars from models/{cfg['model']}/model.config)")
    for k in ("MODEL_NAME", "MAX_MODEL_LEN", "TENSOR_PARALLEL_SIZE", "GPU_MEMORY_UTILIZATION",
              "KV_CACHE_DTYPE", "ENABLE_PREFIX_CACHING", "MAX_NUM_SEQS", "HF_TOKEN"):
        if k in engine_env:
            info(f"{k:<24} {mask(k, engine_env[k])}")

    if not apply:
        print(f"\n  {c('dry run', '33')} — nothing sent. Re-run with 'apply' to deploy.\n")
        return

    print(f"\n  {c('applying', '1')}")
    existing_tpl = find_by_name("templates", cfg["name"])
    if existing_tpl:
        tid = existing_tpl["id"]
        api("PATCH", f"/templates/{tid}", template_payload)
        ok(f"template updated  {tid}")
    else:
        created = api("POST", "/templates", template_payload)
        tid = created["id"]
        ok(f"template created  {tid}")

    endpoint_payload["templateId"] = tid

    existing_ep = find_by_name("endpoints", cfg["name"])
    if existing_ep:
        eid = existing_ep["id"]
        api("PATCH", f"/endpoints/{eid}", endpoint_payload)
        ok(f"endpoint updated  {eid}")
    else:
        created = api("POST", "/endpoints", endpoint_payload)
        eid = created["id"]
        ok(f"endpoint created  {eid}")

    print(f"\n  url   https://api.runpod.ai/v2/{eid}/openai/v1")
    print(f"  id    {eid}")
    print(f"\n  {c('next', '1')}  update registry/deployments.yaml with endpoint_id: {eid}")
    print(f"        then smoke-test a FULL-LENGTH document and confirm finish_reason == 'stop'\n")


def cmd_status(name: str) -> None:
    cfg = load_endpoint_config(name)
    ep = find_by_name("endpoints", cfg["name"])
    if not ep:
        raise Fail(f"'{cfg['name']}' is not deployed on this account")
    eid = ep["id"]
    detail = api("GET", f"/endpoints/{eid}")
    print(f"\n{c(cfg['name'], '1')}  {eid}")
    for k in ("templateId", "gpuTypeIds", "gpuCount", "workersMin", "workersMax",
              "idleTimeout", "networkVolumeId", "dataCenterIds"):
        if k in detail:
            info(f"{k:<18} {detail[k]}")
    print(f"\n  url   https://api.runpod.ai/v2/{eid}/openai/v1\n")


def cmd_list() -> None:
    items = api("GET", "/endpoints")
    if isinstance(items, dict):
        items = items.get("endpoints") or items.get("data") or []
    if not items:
        print("\n  no endpoints on this account\n")
        return
    print()
    for e in items:
        print(f"  {e.get('id','?'):<16} {e.get('name','?')}")
    print()


def cmd_delete(name: str) -> None:
    cfg = load_endpoint_config(name)
    ep = find_by_name("endpoints", cfg["name"])
    if not ep:
        raise Fail(f"'{cfg['name']}' is not deployed")
    confirm = input(f"  delete endpoint '{cfg['name']}' ({ep['id']})? type the name to confirm: ")
    if confirm.strip() != cfg["name"]:
        raise Fail("aborted")
    api("DELETE", f"/endpoints/{ep['id']}")
    ok(f"deleted {ep['id']}")
    warn("the template and network volume were left in place — remove them by hand if unused")


def main() -> None:
    p = argparse.ArgumentParser(description="Deploy Scalejade models to RunPod Serverless.")
    sub = p.add_subparsers(dest="cmd", required=True)
    for cmd in ("plan", "apply", "status", "delete"):
        s = sub.add_parser(cmd)
        s.add_argument("endpoint", help="name of a file in runpod/endpoints/ without .yaml")
    sub.add_parser("list")

    args = p.parse_args()
    try:
        load_dotenv()
        if args.cmd == "plan":
            cmd_plan(args.endpoint, apply=False)
        elif args.cmd == "apply":
            cmd_plan(args.endpoint, apply=True)
        elif args.cmd == "status":
            cmd_status(args.endpoint)
        elif args.cmd == "delete":
            cmd_delete(args.endpoint)
        elif args.cmd == "list":
            cmd_list()
    except Fail as e:
        print(f"\n  {c('error', '31')}  {e}\n", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
