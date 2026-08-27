#!/usr/bin/env python3
"""
Check that HF_TOKEN is real, and say what it can reach.

    python training/scripts/hf_auth.py            # exit 0 ok, 1 rejected, 2 unset

Called by prepare.sh (in preflight, before pip spends five minutes) and by
bootstrap.sh (which also runs on its own). A bad token is worth catching here
because everything after it -- the 56 GB download, a private mirror, --push --
fails on the same 401, but by then it has cost real time.

There is no login step: HF_TOKEN takes precedence over a stored `hf auth login`,
so writing the token to disk as well only creates a second thing to get stale.
"""

from __future__ import annotations

import os
import sys

ORG = "scalejade"


def main() -> int:
    token = os.environ.get("HF_TOKEN")
    if not token:
        print("!!  HF_TOKEN is not set -- private scalejade/ repos will 401 and "
              "--push cannot work")
        return 2

    try:
        from huggingface_hub import HfApi
        me = HfApi(token=token).whoami()
    except ImportError:
        print("!!  huggingface_hub is not installed yet; skipping the token check")
        return 0
    except Exception as e:  # noqa: BLE001 -- 401, DNS, proxy all land here
        first = str(e).splitlines()[0]
        print(f"!!  the Hub rejected HF_TOKEN: {type(e).__name__}: {first}")
        print("!!  mint a new one at https://huggingface.co/settings/tokens (write "
              f"scope, with {ORG} org access) and put it in .env")
        print("!!  a token in the pod's environment came from .env at pod.py apply "
              "time -- fixing .env on your laptop does not update a running pod; "
              "export it in the shell, or recreate the pod")
        return 1

    orgs = [o.get("name") for o in me.get("orgs", [])]
    role = (me.get("auth", {}).get("accessToken", {}) or {}).get("role", "?")
    print(f"==> hf auth ok: {me.get('name')}  (token role: {role})"
          + (f"  orgs: {', '.join(orgs)}" if orgs else ""))

    if ORG not in orgs and me.get("name") != ORG:
        print(f"!!  this token has no {ORG} membership. The base model and any "
              f"--push to {ORG}/... will 401.")
    elif role == "read":
        print("!!  read-only token: downloads work, --push does not")
    return 0


if __name__ == "__main__":
    sys.exit(main())
