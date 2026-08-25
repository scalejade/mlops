#!/usr/bin/env python3
"""
Deploy Scalejade services to RunPod from your laptop.

Every service is a chart: a directory under runpod/ holding chart.yaml (what it
is) and values.yaml (how it is configured). Three kinds, all at the same level:

    runpod/
      deploy.py
      pbbi-volumes/      kind: volume
      pbbi-serverles/    kind: serverless

    python runpod/deploy.py list                     # charts on disk vs what is live
    python runpod/deploy.py plan   <service>         # validate + show, sends nothing
    python runpod/deploy.py apply  <service>         # create or update
    python runpod/deploy.py status <service>         # what is actually live
    python runpod/deploy.py delete <service>         # tear down (asks for confirmation)
    python runpod/deploy.py stop   <service>         # pods only — stop billing, keep disk
    python runpod/deploy.py start  <service>         # pods only — resume

Idempotent. Every kind is looked up by name and PATCHed if it already exists, so
running apply twice does not create duplicates. Always run plan first.

Also reads:
    models/<model>/model.config     vLLM engine args (serverless only)
    .env                            RUNPOD_API_KEY, HF_TOKEN, VLLM_API_KEY, ...

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
REPO = HERE.parent

# RunPod REST v1. Deprecated, retires 2026-11-15. v2 is NOT a drop-in replacement
# (nested request bodies, /endpoints -> /serverless, list responses wrapped in an
# object, RFC 9457 errors), so migration is a deliberate change, not a URL swap.
# Everything version-specific is in api(), find_by_name(), and the KINDS table.
API = "https://rest.runpod.io/v1"

VAR = re.compile(r"\$\{([A-Z0-9_]+)\}")

# Masked in all output. Never printed, never logged.
SECRET_KEYS = {"HF_TOKEN", "RUNPOD_API_KEY", "WANDB_API_KEY", "VLLM_API_KEY"}

# kind -> REST collection it lives in.
KINDS = {
    "volume": "networkvolumes",
    "serverless": "endpoints",
    "pod": "pods",
}


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


def mask(key: str, value) -> str:
    value = str(value)
    if key in SECRET_KEYS and value:
        return value[:6] + "…" + value[-4:] if len(value) > 12 else "…"
    return value


# ---------------------------------------------------------------------- charts

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


def chart_dirs() -> list[Path]:
    """Every directory under runpod/ that holds a chart.yaml."""
    return sorted(p.parent for p in HERE.glob("*/chart.yaml"))


def load_chart(name: str) -> dict:
    """Load <name>/chart.yaml + <name>/values.yaml into one dict.

    values stays UNEXPANDED here — expansion happens per-payload so that a plan
    for one service does not fail on a ${VAR} another service needs.
    """
    root = HERE / name
    chart_path = root / "chart.yaml"
    if not chart_path.exists():
        available = ", ".join(d.name for d in chart_dirs()) or "(none)"
        raise Fail(f"no chart at {chart_path.relative_to(REPO)}\n  available: {available}")

    chart = yaml.safe_load(chart_path.read_text()) or {}
    values_path = root / "values.yaml"
    if not values_path.exists():
        raise Fail(f"{name}/chart.yaml exists but {name}/values.yaml is missing")
    values = yaml.safe_load(values_path.read_text()) or {}

    kind = chart.get("kind")
    if kind not in KINDS:
        raise Fail(
            f"{name}/chart.yaml has kind={kind!r}. Must be one of: {', '.join(KINDS)}"
        )
    chart.setdefault("name", name)
    if chart["name"] != name:
        raise Fail(
            f"{name}/chart.yaml declares name={chart['name']!r} but lives in "
            f"directory {name!r}. The directory is the service name — make them match."
        )
    chart["values"] = values
    return chart


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
        # Strip trailing inline comments, but only when clearly separated, so a
        # '#' inside a real value survives.
        value = re.split(r"\s+#", value, maxsplit=1)[0].strip().strip("'\"")
        env[key.strip()] = value
    return env


def resolve_dependencies(chart: dict) -> dict[str, str]:
    """Look each declared dependency up on the account. Returns {name: live id}.

    A dependency that is not deployed is fatal — applying a serverless endpoint
    without its volume is how you get a 2-hour cold start instead of 26 seconds.
    """
    resolved: dict[str, str] = {}
    for dep in chart.get("dependencies") or []:
        dep_name, dep_kind = dep.get("name"), dep.get("kind")
        if dep_kind not in KINDS:
            raise Fail(f"dependency {dep_name!r} has unknown kind {dep_kind!r}")
        live = find_by_name(KINDS[dep_kind], dep_name)
        if not live:
            raise Fail(
                f"dependency {dep_kind} '{dep_name}' is not deployed on this account.\n"
                f"    Apply it first:  python runpod/deploy.py apply {dep_name}"
            )
        resolved[dep_name] = live["id"]
        ok(f"dependency {dep_kind} '{dep_name}' -> {live['id']}")
    return resolved


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


# ------------------------------------------------------------------- preflight

def preflight_volume(chart: dict) -> None:
    vol = chart["values"].get("volume", {})
    problems = []
    size = int(vol.get("size", 0) or 0)
    if size <= 0:
        problems.append("volume.size must be a positive integer (GB)")
    if size > 4000:
        problems.append(f"volume.size={size} exceeds RunPod's 4000 GB maximum")
    if not vol.get("dataCenterId"):
        problems.append(
            "volume.dataCenterId is required. A network volume is region-local — "
            "anything that mounts it must be pinned to the same region."
        )

    live = find_by_name("networkvolumes", chart["name"])
    if live and size and int(live.get("size", 0) or 0) > size:
        problems.append(
            f"volume.size={size} is smaller than the live volume "
            f"({live['size']} GB). Network volumes can grow but never shrink."
        )

    if problems:
        raise Fail("preflight failed:\n" + "\n".join(f"    - {p}" for p in problems))
    ok("preflight passed")


def preflight_serverless(chart: dict, env: dict, deps: dict[str, str]) -> None:
    """Catch the failures we have already paid for once."""
    ep = chart["values"].get("endpoint", {})
    problems: list[str] = []

    tp = int(env.get("TENSOR_PARALLEL_SIZE", 1) or 1)
    gpus = int(ep.get("gpuCount", 1) or 1)
    if tp != gpus:
        problems.append(
            f"TENSOR_PARALLEL_SIZE={tp} but gpuCount={gpus}. These must match, or the "
            f"worker dies with 'DP adjusted local rank N is out of bounds for {gpus} devices'. "
            f"Note gpuCount is GPUs PER WORKER; workersMax is the replica count."
        )

    max_len = int(env.get("MAX_MODEL_LEN", 0) or 0)
    if max_len <= 0:
        problems.append(
            "MAX_MODEL_LEN is empty or 0. vLLM >=0.27 rejects 0 instead of treating it "
            "as auto, and the worker will not boot."
        )

    if not deps and not ep.get("networkVolumeId"):
        problems.append(
            "no network volume. Declare a volume dependency in chart.yaml — without a "
            "shared volume every worker re-downloads the checkpoint: ~2h cold start "
            "instead of ~26s."
        )

    if not ep.get("dataCenterIds"):
        warn("dataCenterIds is unset — workers may spread across regions and get throttled.")

    # A volume in one region cannot attach to a worker in another.
    for dep in chart.get("dependencies") or []:
        if dep.get("kind") != "volume":
            continue
        try:
            dep_values = load_chart(dep["name"])["values"].get("volume", {})
        except Fail:
            continue
        dep_dc = dep_values.get("dataCenterId")
        ep_dcs = ep.get("dataCenterIds") or []
        if dep_dc and ep_dcs and dep_dc not in ep_dcs:
            problems.append(
                f"volume '{dep['name']}' is in {dep_dc} but this endpoint is pinned to "
                f"{ep_dcs}. A network volume cannot attach across regions."
            )

    # max_tokens has to fit inside the context window alongside the prompt.
    max_tokens = int(chart["values"].get("request_defaults", {}).get("max_tokens", 0) or 0)
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


def preflight_pod(chart: dict) -> None:
    v = chart["values"]
    gpu, disk, eng = v.get("gpu", {}), v.get("disk", {}), v.get("engine", {})
    problems: list[str] = []

    tp = int(eng.get("tensor_parallel_size", 1) or 1)
    count = int(gpu.get("count", 1) or 1)
    if tp != count:
        problems.append(
            f"engine.tensor_parallel_size={tp} but gpu.count={count}. These must match, "
            f"or the worker dies with 'DP adjusted local rank N is out of bounds'."
        )

    max_len = int(eng.get("max_model_len", 0) or 0)
    if max_len <= 0:
        problems.append(
            "engine.max_model_len is empty or 0. vLLM >=0.27 rejects 0 rather than "
            "reading it as auto, and the engine will not boot."
        )

    if not gpu.get("type"):
        problems.append("gpu.type is required")

    disk_type = disk.get("type")
    if disk_type not in ("volume_disk", "network_volume"):
        problems.append(
            f"disk.type={disk_type!r} must be 'volume_disk' or 'network_volume'"
        )
    if disk_type == "network_volume" and not any(
        d.get("kind") == "volume" for d in chart.get("dependencies") or []
    ):
        problems.append(
            "disk.type is network_volume but no volume dependency is declared in "
            "chart.yaml. deploy.py has no volume to attach."
        )
    if disk_type == "volume_disk":
        warn(
            "disk.type is volume_disk — the disk is deleted with the pod. STOP the pod, "
            "never delete it, or the next run re-downloads the whole checkpoint."
        )

    # The workload has to fit in the window, or clauses go missing at HTTP 200.
    peak = int(v.get("workload", {}).get("peak_context_needed", 0) or 0)
    if peak and max_len and peak > max_len:
        problems.append(
            f"workload.peak_context_needed={peak:,} exceeds engine.max_model_len="
            f"{max_len:,}. The request cannot be served in one call."
        )
    elif peak and max_len:
        margin = max_len - peak
        if margin < 0.05 * max_len:
            warn(f"only {margin:,} tokens of margin above the peak workload — tight.")

    # 55.6 GB of weights leaves too little room for KV cache below 80 GB.
    vram = int(gpu.get("vram_gb", 0) or 0)
    if vram and vram <= 80:
        warn(
            f"gpu.vram_gb={vram} — at or below 80 GB the weights leave too little room "
            "for a useful KV cache at this context length."
        )

    if problems:
        raise Fail("preflight failed:\n" + "\n".join(f"    - {p}" for p in problems))
    ok("preflight passed")


# -------------------------------------------------------------------- payloads

def build_volume_payload(chart: dict) -> dict:
    vol = expand(chart["values"].get("volume", {}))
    return {
        "name": chart["name"],
        "size": int(vol["size"]),
        "dataCenterId": vol["dataCenterId"],
    }


def build_serverless_payloads(chart: dict, deps: dict[str, str]) -> tuple[dict, dict, dict]:
    """Return (template_payload, endpoint_payload, engine_env)."""
    values = chart["values"]
    model = values.get("model")
    if not model:
        raise Fail("values.yaml is missing 'model'")

    engine_env = expand(load_model_config(model))

    tpl = expand(values.get("template", {}))
    if not tpl.get("imageName"):
        raise Fail("template.imageName is required — pin the vLLM worker image explicitly")
    template_payload = {
        "name": chart["name"],
        "imageName": tpl["imageName"],
        "isServerless": True,
        "containerDiskInGb": tpl.get("containerDiskInGb", 20),
        "volumeMountPath": tpl.get("volumeMountPath", "/runpod-volume"),
        "env": engine_env,
    }

    endpoint_payload = expand(values.get("endpoint", {}))
    endpoint_payload["name"] = chart["name"]

    # Dependency wins over anything hardcoded — the declared graph is the truth.
    for dep in chart.get("dependencies") or []:
        if dep.get("kind") == "volume":
            endpoint_payload["networkVolumeId"] = deps[dep["name"]]

    return template_payload, endpoint_payload, engine_env


def build_serve_args(chart: dict) -> list[str]:
    """Render engine values into vLLM serve arguments.

    This is the ONLY place serve arguments are produced. There is deliberately no
    start-vllm.sh alongside it: two hand-maintained copies of these flags drift,
    and then the config lies about what is actually running.
    """
    v = chart["values"]
    eng = v.get("engine", {})
    args = [v["model"]]

    flags = {
        "--served-model-name": eng.get("served_model_name") or v["model"],
        "--host": "0.0.0.0",
        "--port": "8000",
        "--dtype": eng.get("dtype", "auto"),
        "--max-model-len": eng.get("max_model_len"),
        "--max-num-seqs": eng.get("max_num_seqs"),
        "--gpu-memory-utilization": eng.get("gpu_memory_utilization"),
        "--kv-cache-dtype": eng.get("kv_cache_dtype"),
        "--tensor-parallel-size": eng.get("tensor_parallel_size"),
        "--max-num-batched-tokens": eng.get("max_num_batched_tokens"),
        "--gdn-prefill-backend": eng.get("gdn_prefill_backend"),
    }
    for flag, value in flags.items():
        if value is not None:
            args += [flag, str(value)]

    # Boolean flags: vLLM takes the presence of the flag, not a value.
    for key, flag in (
        ("enable_prefix_caching", "--enable-prefix-caching"),
        ("enable_chunked_prefill", "--enable-chunked-prefill"),
        ("trust_remote_code", "--trust-remote-code"),
    ):
        if eng.get(key):
            args.append(flag)

    return args


def build_pod_payload(chart: dict, deps: dict[str, str]) -> dict:
    v = chart["values"]
    gpu = expand(v.get("gpu", {}))
    disk = v.get("disk", {})
    container = expand(v.get("container", {}))

    payload = {
        "name": chart["name"],
        "imageName": container["image"],
        "computeType": "GPU",
        "cloudType": gpu.get("cloudType", "SECURE"),
        "gpuTypeIds": [gpu["type"]],
        "gpuCount": int(gpu.get("count", 1)),
        "containerDiskInGb": int(disk.get("container_gb", 50)),
        "volumeMountPath": disk.get("mount_path", "/workspace"),
        "ports": container.get("ports", ["8000/http", "22/tcp"]),
        # env values must be strings — YAML turns 0.90 into a float and RunPod 400s.
        "env": {k: str(x) for k, x in (container.get("env") or {}).items()},
        # The vllm/vllm-openai image has `vllm serve` as its ENTRYPOINT, so this is
        # arguments only, starting with the model name.
        "dockerStartCmd": build_serve_args(chart),
    }

    if gpu.get("dataCenterIds"):
        payload["dataCenterIds"] = gpu["dataCenterIds"]
        payload["dataCenterPriority"] = "custom"

    if disk.get("type") == "network_volume":
        for dep in chart.get("dependencies") or []:
            if dep.get("kind") == "volume":
                payload["networkVolumeId"] = deps[dep["name"]]
    else:
        payload["volumeInGb"] = int(disk.get("volume_gb", 20))

    return payload


# -------------------------------------------------------------------- commands

def cmd_plan(name: str, apply: bool = False) -> None:
    chart = load_chart(name)
    kind = chart["kind"]

    print(f"\n{c(kind, '1')}  {chart['name']}  v{chart.get('version', '?')}")
    if chart.get("description"):
        print(f"  {chart['description']}")
    print()

    # Resolved on plan too: an unapplied dependency is a fatal config error and
    # should surface in the dry run, not on first apply.
    deps = resolve_dependencies(chart) if chart.get("dependencies") else {}

    if kind == "volume":
        preflight_volume(chart)
        payload = build_volume_payload(chart)
        print(f"\n  {c('volume', '1')}")
        for k, val in payload.items():
            info(f"{k:<20} {val}")
        cost = chart["values"].get("cost", {})
        if cost.get("usd_per_gb_month"):
            monthly = payload["size"] * float(cost["usd_per_gb_month"])
            info(f"{'est. cost':<20} ${monthly:.2f}/mo, billed continuously")

    elif kind == "serverless":
        template_payload, endpoint_payload, engine_env = build_serverless_payloads(chart, deps)
        print(f"  {c('model', '1')}     {chart['values']['model']}"
              + (f"  + adapter {chart['values']['adapter']}" if chart["values"].get("adapter") else ""))
        print(f"  {c('image', '1')}     {template_payload['imageName']}\n")
        preflight_serverless(chart, engine_env, deps)
        print(f"\n  {c('hardware', '1')}")
        for k in ("gpuTypeIds", "gpuCount", "workersMin", "workersMax", "idleTimeout",
                  "scalerType", "scalerValue", "executionTimeoutMs", "dataCenterIds",
                  "networkVolumeId", "flashboot"):
            if k in endpoint_payload:
                info(f"{k:<20} {endpoint_payload[k]}")
        print(f"\n  {c('engine env', '1')}  ({len(engine_env)} vars from "
              f"models/{chart['values']['model']}/model.config)")
        for k in ("MODEL_NAME", "MAX_MODEL_LEN", "TENSOR_PARALLEL_SIZE", "GPU_MEMORY_UTILIZATION",
                  "KV_CACHE_DTYPE", "ENABLE_PREFIX_CACHING", "MAX_NUM_SEQS", "HF_TOKEN"):
            if k in engine_env:
                info(f"{k:<24} {mask(k, engine_env[k])}")

    elif kind == "pod":
        preflight_pod(chart)
        payload = build_pod_payload(chart, deps)
        print(f"\n  {c('hardware', '1')}")
        for k in ("imageName", "gpuTypeIds", "gpuCount", "cloudType", "dataCenterIds",
                  "containerDiskInGb", "volumeInGb", "networkVolumeId", "volumeMountPath", "ports"):
            if k in payload:
                info(f"{k:<20} {payload[k]}")
        price = chart["values"].get("gpu", {}).get("price_per_hour_usd")
        if price:
            info(f"{'price':<20} ${price}/hr while RUNNING — a pod bills when idle")
        print(f"\n  {c('env', '1')}")
        for k, val in payload["env"].items():
            info(f"{k:<24} {mask(k, val)}")
        print(f"\n  {c('vllm serve', '1')}")
        print("    " + " ".join(payload["dockerStartCmd"]))

    if not apply:
        print(f"\n  {c('dry run', '33')} — nothing sent. Re-run with 'apply' to deploy.\n")
        return

    print(f"\n  {c('applying', '1')}")
    if kind == "volume":
        apply_volume(chart, payload)
    elif kind == "serverless":
        apply_serverless(chart, template_payload, endpoint_payload)
    elif kind == "pod":
        apply_pod(chart, payload)


def apply_volume(chart: dict, payload: dict) -> None:
    live = find_by_name("networkvolumes", chart["name"])
    if live:
        # Only size is mutable, and only upward.
        api("PATCH", f"/networkvolumes/{live['id']}", {"size": payload["size"]})
        ok(f"volume updated  {live['id']}")
        vid = live["id"]
    else:
        created = api("POST", "/networkvolumes", payload)
        vid = created["id"]
        ok(f"volume created  {vid}")
    print(f"\n  id    {vid}")
    print(f"\n  {c('next', '1')}  apply anything that declares this as a dependency\n")


def apply_serverless(chart: dict, template_payload: dict, endpoint_payload: dict) -> None:
    existing_tpl = find_by_name("templates", chart["name"])
    if existing_tpl:
        tid = existing_tpl["id"]
        api("PATCH", f"/templates/{tid}", template_payload)
        ok(f"template updated  {tid}")
    else:
        tid = api("POST", "/templates", template_payload)["id"]
        ok(f"template created  {tid}")

    endpoint_payload["templateId"] = tid

    existing_ep = find_by_name("endpoints", chart["name"])
    if existing_ep:
        eid = existing_ep["id"]
        api("PATCH", f"/endpoints/{eid}", endpoint_payload)
        ok(f"endpoint updated  {eid}")
    else:
        eid = api("POST", "/endpoints", endpoint_payload)["id"]
        ok(f"endpoint created  {eid}")

    print(f"\n  url   https://api.runpod.ai/v2/{eid}/openai/v1")
    print(f"  id    {eid}")
    print(f"\n  {c('next', '1')}  update registry/deployments.yaml with endpoint_id: {eid}")
    print("        then smoke-test a FULL-LENGTH document and confirm finish_reason == 'stop'\n")


def apply_pod(chart: dict, payload: dict) -> None:
    live = find_by_name("pods", chart["name"])
    if live:
        pid = live["id"]
        # A pod's GPU, disk and region are fixed at creation. Only the container
        # side is patchable, so say plainly what was NOT applied rather than
        # reporting success for a change that did not happen.
        patch = {k: payload[k] for k in ("imageName", "env", "dockerStartCmd", "ports")
                 if k in payload}
        api("PATCH", f"/pods/{pid}", patch)
        ok(f"pod updated  {pid}  (image, env, start command, ports)")
        warn("gpu, disk and region are fixed at creation — delete and recreate to change them")
    else:
        pid = api("POST", "/pods", payload)["id"]
        ok(f"pod created  {pid}")

    print(f"\n  url   https://{pid}-8000.proxy.runpod.net/v1")
    print(f"  id    {pid}")
    print(f"\n  {c('next', '1')}  watch the logs. First start downloads the checkpoint —")
    print("        expect 10-20 min. Ready when you see 'Application startup complete'")
    print("        and /v1/models answers. Then: deploy.py stop pbbi when you are done —")
    print("        a pod bills by the second whether or not it is serving.\n")


def cmd_status(name: str) -> None:
    chart = load_chart(name)
    collection = KINDS[chart["kind"]]
    live = find_by_name(collection, chart["name"])
    if not live:
        raise Fail(f"{chart['kind']} '{chart['name']}' is not deployed on this account")
    rid = live["id"]
    detail = api("GET", f"/{collection}/{rid}")
    print(f"\n{c(chart['name'], '1')}  {chart['kind']}  {rid}")

    fields = {
        "volume": ("size", "dataCenterId"),
        "serverless": ("templateId", "gpuTypeIds", "gpuCount", "workersMin", "workersMax",
                       "idleTimeout", "networkVolumeId", "dataCenterIds"),
        "pod": ("desiredStatus", "imageName", "gpuCount", "costPerHr", "machineId",
                "containerDiskInGb", "volumeInGb", "networkVolumeId", "lastStartedAt"),
    }[chart["kind"]]
    for k in fields:
        if k in detail:
            info(f"{k:<18} {detail[k]}")

    if chart["kind"] == "serverless":
        print(f"\n  url   https://api.runpod.ai/v2/{rid}/openai/v1")
    elif chart["kind"] == "pod":
        print(f"\n  url   https://{rid}-8000.proxy.runpod.net/v1")
        if detail.get("desiredStatus") == "RUNNING" and detail.get("costPerHr"):
            warn(f"RUNNING — billing at ${detail['costPerHr']}/hr")
    print()


def cmd_list() -> None:
    """Charts on disk, and whether each one is live."""
    charts = chart_dirs()
    if not charts:
        print("\n  no charts in runpod/\n")
        return

    # One GET per collection, not one per chart.
    cache: dict[str, list] = {}
    for collection in KINDS.values():
        try:
            items = api("GET", f"/{collection}")
            if isinstance(items, dict):
                items = items.get(collection) or items.get("data") or []
            cache[collection] = items
        except Fail:
            cache[collection] = []

    print(f"\n  {'SERVICE':<26} {'KIND':<12} {'ID':<18} STATUS")
    for d in charts:
        try:
            chart = load_chart(d.name)
        except Fail as e:
            print(f"  {d.name:<26} {c('invalid', '31'):<12} {e}")
            continue
        kind = chart["kind"]
        live = next((i for i in cache[KINDS[kind]] if i.get("name") == chart["name"]), None)
        if live:
            status = live.get("desiredStatus") or "live"
            print(f"  {chart['name']:<26} {kind:<12} {live['id']:<18} {c(status, '32')}")
        else:
            print(f"  {chart['name']:<26} {kind:<12} {'-':<18} {c('not deployed', '33')}")
    print()


def cmd_delete(name: str) -> None:
    chart = load_chart(name)
    kind, collection = chart["kind"], KINDS[chart["kind"]]
    live = find_by_name(collection, chart["name"])
    if not live:
        raise Fail(f"{kind} '{chart['name']}' is not deployed")

    if kind == "pod" and chart["values"].get("disk", {}).get("type") == "volume_disk":
        warn("this pod uses a volume disk — deleting it DELETES the checkpoint with it.")
        warn("if you only want billing to stop, use 'stop' instead.")
    if kind == "volume":
        warn("deleting a network volume destroys its contents for every service that mounts it.")

    confirm = input(f"  delete {kind} '{chart['name']}' ({live['id']})? type the name to confirm: ")
    if confirm.strip() != chart["name"]:
        raise Fail("aborted")
    api("DELETE", f"/{collection}/{live['id']}")
    ok(f"deleted {live['id']}")
    if kind == "serverless":
        warn("the template and network volume were left in place — remove them by hand if unused")


def cmd_pod_action(name: str, action: str) -> None:
    chart = load_chart(name)
    if chart["kind"] != "pod":
        raise Fail(f"'{action}' applies to pods only; '{chart['name']}' is a {chart['kind']}")
    live = find_by_name("pods", chart["name"])
    if not live:
        raise Fail(f"pod '{chart['name']}' is not deployed")
    api("POST", f"/pods/{live['id']}/{action}")
    ok(f"pod {action} sent  {live['id']}")
    if action == "stop":
        info("billing stops. The volume disk survives — do not delete the pod.")


def main() -> None:
    p = argparse.ArgumentParser(description="Deploy Scalejade services to RunPod.")
    sub = p.add_subparsers(dest="cmd", required=True)
    for cmd, helptext in (
        ("plan", "validate and show, send nothing"),
        ("apply", "create or update"),
        ("status", "what is live now"),
        ("delete", "tear down"),
        ("stop", "pods only: stop billing, keep the disk"),
        ("start", "pods only: resume a stopped pod"),
    ):
        s = sub.add_parser(cmd, help=helptext)
        s.add_argument("service", help="name of a chart directory under runpod/")
    sub.add_parser("list", help="charts on disk vs what is live")

    args = p.parse_args()
    try:
        load_dotenv()
        if args.cmd == "plan":
            cmd_plan(args.service, apply=False)
        elif args.cmd == "apply":
            cmd_plan(args.service, apply=True)
        elif args.cmd == "status":
            cmd_status(args.service)
        elif args.cmd == "delete":
            cmd_delete(args.service)
        elif args.cmd in ("stop", "start"):
            cmd_pod_action(args.service, args.cmd)
        elif args.cmd == "list":
            cmd_list()
    except Fail as e:
        print(f"\n  {c('error', '31')}  {e}\n", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
