#!/usr/bin/env python3
"""aimanac — operator CLI for an AiMANAC backend deployment.

Commands
  status        Is the server claimed? + health + first-owner claim mode.
  show-code     Print the owner BOOTSTRAP_SETUP_CODE from the container (lockout recovery).
  rotate-code   Regenerate the owner setup code, then print it (--confirm to write).
  init          Claim the first owner (display name [+ setup code]).
  update        Volume-SAFE image update (compose pull + up -d; refuses `-v`).

The lockout class (2026-06-23): a `docker compose down -v` wiped /app/data/.env.generated,
silently re-minting the JWT keys + owner setup code, locking the owner out. `update` here is
the volume-preserving path; `show-code` / `rotate-code` are the manual recovery, productized.

Stdlib only — no runtime dependencies.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

DEFAULT_URL = os.environ.get("AIMANAC_URL", "http://127.0.0.1:8080")
DEFAULT_CONTAINER = os.environ.get("AIMANAC_CONTAINER", "aimanac-magus-rs")
ENV_FILE = "/app/data/.env.generated"
SETUP_CODE_KEY = "BOOTSTRAP_SETUP_CODE"


def _http(method, url, body=None, timeout=10):
    """Returns (status_code, parsed_json). status_code 0 == unreachable."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method, headers={"content-type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"error": raw}
    except Exception as e:
        return 0, {"error": str(e)}


def _docker(args):
    return subprocess.run(["docker", *args], capture_output=True, text=True)


def _emit(obj, as_json):
    if as_json:
        print(json.dumps(obj, indent=2))
    else:
        for k, v in obj.items():
            print(f"{k}: {v}")


def cmd_status(a):
    code, st = _http("GET", f"{a.url}/api/v1/bootstrap/status")
    hcode, _ = _http("GET", f"{a.url}/health")
    out = {
        "backend": a.url,
        "reachable": code != 0,
        "claimed": st.get("claimed") if code == 200 else None,
        "firstOwnerClaimMode": st.get("firstOwnerClaimMode") if code == 200 else None,
        "health": "up" if (hcode and hcode < 500) else "down",
        "status_http": code,
    }
    if code != 200 and "error" in st:
        out["error"] = st["error"]
    _emit(out, a.json)
    return 0 if code == 200 else 1


def cmd_show_code(a):
    r = _docker(["exec", a.container, "sh", "-c", f"cat {ENV_FILE}"])
    if r.returncode != 0:
        _emit({"error": f"docker exec failed: {r.stderr.strip()}", "container": a.container}, a.json)
        return 1
    code = None
    for line in r.stdout.splitlines():
        if line.startswith(SETUP_CODE_KEY + "="):
            code = line.split("=", 1)[1].strip()
            break
    if not code:
        _emit({"error": f"{SETUP_CODE_KEY} not found in {ENV_FILE}", "container": a.container}, a.json)
        return 1
    _emit({"container": a.container, "setupCode": code}, a.json)
    return 0


def cmd_rotate_code(a):
    if not a.confirm:
        _emit(
            {
                "action": "rotate-code",
                "container": a.container,
                "preview": "drops BOOTSTRAP_SETUP_CODE from the env file + restarts so the backend re-mints it; re-run with --confirm",
            },
            a.json,
        )
        return 0
    edit = (
        f"grep -v '^{SETUP_CODE_KEY}=' {ENV_FILE} > {ENV_FILE}.tmp "
        f"&& mv {ENV_FILE}.tmp {ENV_FILE}"
    )
    r = _docker(["exec", a.container, "sh", "-c", edit])
    if r.returncode != 0:
        _emit({"error": f"could not edit env file: {r.stderr.strip()}"}, a.json)
        return 1
    rr = _docker(["restart", a.container])
    if rr.returncode != 0:
        _emit({"error": f"restart failed: {rr.stderr.strip()}"}, a.json)
        return 1
    time.sleep(3)  # let the backend boot + re-mint
    return cmd_show_code(a)


def cmd_init(a):
    body = {"displayName": a.name}
    if a.setup_code:
        body["setupCode"] = a.setup_code
    code, resp = _http("POST", f"{a.url}/api/v1/bootstrap/claim", body)
    if code == 200:
        _emit({"status_http": code, "userId": resp.get("userId"), "role": resp.get("role")}, a.json)
        return 0
    _emit({"status_http": code, "error": resp}, a.json)
    return 1


def cmd_update(a):
    # Volume-SAFE by construction: only `compose pull` + `compose up -d`, which
    # recreate containers on the new image while PRESERVING named volumes. It
    # never runs `down` (let alone `down -v`), so the lockout class cannot recur.
    base = ["compose"] + (["-f", a.compose_file] if a.compose_file else [])
    svc = [a.service] if a.service else []
    if not a.confirm:
        _emit(
            {
                "action": "update",
                "compose_file": a.compose_file or "(default)",
                "service": a.service or "(all)",
                "preview": "docker compose pull + up -d (volumes preserved); re-run with --confirm",
            },
            a.json,
        )
        return 0
    p = _docker(base + ["pull", *svc])
    if p.returncode != 0:
        _emit({"error": f"pull failed: {p.stderr.strip()}"}, a.json)
        return 1
    u = _docker(base + ["up", "-d", *svc])
    if u.returncode != 0:
        _emit({"error": f"up failed: {u.stderr.strip()}"}, a.json)
        return 1
    _emit({"action": "update", "result": "pulled + recreated (volumes preserved)", "service": a.service or "all"}, a.json)
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="aimanac", description="Operator CLI for an AiMANAC backend.")
    p.add_argument("--url", default=DEFAULT_URL, help=f"backend base URL (default {DEFAULT_URL})")
    p.add_argument("--container", default=DEFAULT_CONTAINER, help=f"docker container (default {DEFAULT_CONTAINER})")
    p.add_argument("--json", action="store_true", help="machine-readable JSON output")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="claimed? + health + claim mode").set_defaults(fn=cmd_status)
    sub.add_parser("show-code", help="print the owner setup code (lockout recovery)").set_defaults(fn=cmd_show_code)

    rc = sub.add_parser("rotate-code", help="regenerate the owner setup code")
    rc.add_argument("--confirm", action="store_true")
    rc.set_defaults(fn=cmd_rotate_code)

    ini = sub.add_parser("init", help="claim the first owner")
    ini.add_argument("name", help="owner display name")
    ini.add_argument("--setup-code", dest="setup_code", help="required for public claims")
    ini.set_defaults(fn=cmd_init)

    up = sub.add_parser("update", help="volume-safe image update")
    up.add_argument("--compose-file", dest="compose_file")
    up.add_argument("--service")
    up.add_argument("--confirm", action="store_true")
    up.set_defaults(fn=cmd_update)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
