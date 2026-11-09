#!/usr/bin/env python3
"""guard_worker — the RainbowOMMA guard as a long-lived helper process, one per Hermes profile.

    python3 -I guard_worker.py      (started by guard_hook; identity in the environment: RAINBOW_AGENT, RAINBOW_HOME,
                                     BROWSER_OWNER_REGISTRY)

One JSON request per line on stdin, one JSON answer per line on stdout:
    {"id": 1, "event": {"tool_name": "terminal", "tool_input": {"command": "pkill Chrome"}}}
    {"id": 1, "why": "pkill matches processes by pattern …", "kind": "block"}      kind: block | send | none
    {"id": 2, "paused": true}                                                       for {"id": 2, "ask": "paused"}

The guard decides whose call it is from its environment. A Hermes gateway can serve several profiles in one process, so
the plugin never puts an agent's identity into Hermes's own environment: each profile's guard lives here, in a process
of its own. An error while judging is a refusal.
"""
import importlib.machinery
import importlib.util
import json
import os
import sys

VENDOR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "vendor")


def load_guard():
    sys.path.insert(0, VENDOR)
    loader = importlib.machinery.SourceFileLoader("rainbowomma_vendored_guard", os.path.join(VENDOR, "rainbowomma-guard.py"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def answer(guard, req):
    rid = req.get("id")
    if req.get("ask") == "paused":
        try:
            return {"id": rid, "paused": bool(guard.is_paused())}
        except Exception:
            return {"id": rid, "paused": False}
    event = req.get("event") if isinstance(req.get("event"), dict) else {}
    try:
        why, _command = guard.judge(event)
    except Exception as exc:                          # can't tell → no
        why = f"{guard.WHY['guard-error']} ({type(exc).__name__})"
    if not why:
        return {"id": rid, "why": None, "kind": "none"}
    return {"id": rid, "why": why, "kind": "send" if why == guard.WHY.get("send") else "block"}


def main():
    guard = load_guard()
    sys.stdout.write(json.dumps({"ready": True}) + "\n")
    sys.stdout.flush()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            out = answer(guard, req if isinstance(req, dict) else {})
        except Exception as exc:
            out = {"id": None, "why": f"the guard could not read the request ({type(exc).__name__})", "kind": "block"}
        sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
