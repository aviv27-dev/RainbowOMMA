#!/usr/bin/env python3
"""sim-owner — an iOS Simulator of its own for every agent, so parallel builds never fight over one device.

    sim-owner lease AGENT [--device "iPhone 16"]     the agent's own simulator (created once as "rainbowomma-AGENT"), booted
    sim-owner who UDID                               whose simulator this is
    sim-owner release AGENT [--shutdown]             give it back (it stays installed for next time)
    sim-owner list                                   every agent's simulator

"Last Xcode wins" for a shared simulator, and `simctl … booted` means whichever device happens to be booted. With
RAINBOW_AGENT set, the guardrail refuses `xcrun simctl … booted`, and another agent's UDID or simulator name, in
simctl and xcodebuild -destination — use the UDID this lease gives you.
Exit codes: 0 ok · 2 refused · 1 failure. One JSON answer.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))   # -I drops the script's folder
import rainbow_receipts  # noqa: E402

PREFIX = "rainbowomma-"


def simctl(*args):
    """xcrun simctl … (RAINBOW_SIMCTL replaces it in tests) → (code, stdout)"""
    cmd = [os.environ["RAINBOW_SIMCTL"]] if os.environ.get("RAINBOW_SIMCTL") else ["xcrun", "simctl"]
    try:
        r = subprocess.run([*cmd, *args], capture_output=True, text=True, timeout=120)
        return r.returncode, (r.stdout or "").strip() or (r.stderr or "").strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, f"{type(exc).__name__}: {exc}"


def devices():
    """→ [{"name", "udid", "state", "runtime"}] for every simulator"""
    code, out = simctl("list", "devices", "--json")
    if code:
        raise RuntimeError(out[:200] or "xcrun simctl failed — is Xcode installed?")
    got = []
    for runtime, devs in json.loads(out).get("devices", {}).items():
        for d in devs:
            got.append({"name": d.get("name"), "udid": d.get("udid"), "state": d.get("state"), "runtime": runtime})
    return got


def owner_of(udid_or_name, devs=None):
    """→ the agent that owns this simulator (by its rainbowomma-AGENT name), or None"""
    key = str(udid_or_name).lower()                      # the guard sees lowercased command text
    for d in devs if devs is not None else devices():
        if key in (str(d["udid"]).lower(), str(d["name"]).lower()) and str(d["name"]).startswith(PREFIX):
            return d["name"][len(PREFIX):]
    return None


def cmd_lease(agent, device):
    devs = devices()
    mine = next((d for d in devs if d["name"] == PREFIX + agent), None)
    if not mine:
        code, out = simctl("create", PREFIX + agent, device)
        if code:
            return 1, {"status": "failed", "why": f"could not create a {device} simulator: {out[:200]}"}
        mine = {"name": PREFIX + agent, "udid": out.splitlines()[-1].strip(), "state": "Shutdown"}
    if mine.get("state") != "Booted":
        code, out = simctl("boot", mine["udid"])
        if code and "current state: Booted" not in out:
            return 1, {"status": "failed", "why": f"could not boot it: {out[:200]}", "udid": mine["udid"]}
    rainbow_receipts.write("sim-owner", "lease", agent, agent, "leased", udid=mine["udid"])
    return 0, {"status": "leased", "udid": mine["udid"], "name": mine["name"],
               "use": f"xcodebuild -destination 'id={mine['udid']}' · xcrun simctl <command> {mine['udid']}"}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="sim-owner")
    sub = ap.add_subparsers(dest="cmd", required=True)
    le = sub.add_parser("lease"); le.add_argument("agent"); le.add_argument("--device", default="iPhone 16")
    w = sub.add_parser("who"); w.add_argument("udid")
    r = sub.add_parser("release"); r.add_argument("agent"); r.add_argument("--shutdown", action="store_true")
    sub.add_parser("list")
    a = ap.parse_args(argv)
    if a.cmd in ("lease", "release") and rainbow_receipts.acting_as(a.agent):
        print(json.dumps({"status": "refused", "why": rainbow_receipts.acting_as(a.agent)}, ensure_ascii=False))
        return 2
    try:
        if a.cmd == "lease":
            code, out = cmd_lease(a.agent.strip().lower(), a.device)
        elif a.cmd == "who":
            code, out = 0, {"udid": a.udid, "agent": owner_of(a.udid) or "human"}
        elif a.cmd == "release":
            agent = a.agent.strip().lower()
            mine = next((d for d in devices() if d["name"] == PREFIX + agent), None)
            if mine and a.shutdown:
                simctl("shutdown", mine["udid"])
            rainbow_receipts.write("sim-owner", "release", agent, agent, "released")
            code, out = 0, {"status": "released", "udid": (mine or {}).get("udid")}
        else:
            code, out = 0, {"simulators": {d["name"][len(PREFIX):]: {"udid": d["udid"], "state": d["state"]}
                                           for d in devices() if str(d["name"]).startswith(PREFIX)}}
    except Exception as exc:   # one JSON answer, always
        code, out = 1, {"status": "failed", "why": f"{type(exc).__name__}: {exc}"[:200]}
    print(json.dumps(out, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
