#!/usr/bin/env python3
"""screen-owner — who may drive the screen (keyboard, mouse, the window in front) on a shared Mac.

    screen-owner take AGENT [--minutes M] [--wait S]   hold the screen for an agent that drives the foreground
    screen-owner release AGENT                         give it back
    screen-owner takeover [--minutes M]                the human takes the screen: every agent's GUI action waits
    screen-owner handback                              the human gives it back
    screen-owner who                                   who holds it now, and until when

One lease for the whole screen. The human always wins: a takeover holds every agent's GUI action (foreground or
background), and an agent can't take the screen while the human is typing. A foreground action without a lease takes
a short one by itself (the guard does it, 15 s, renewed by every action), so two agents never type into each other's
windows; background-capable drivers (Cua) don't need the screen, only the human's takeover stops them.
Exit codes: 0 ok · 2 refused · 1 failure. One JSON answer.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))   # -I drops the script's folder
import rainbow_receipts  # noqa: E402

AUTO_TTL_S = 15
IDLE = None                      # tests replace it: () -> seconds since the human's last input, or None


def root():
    return Path(os.path.expanduser(os.environ.get("RAINBOW_HOME") or str(Path.home() / ".rainbowomma")))


def state_file():
    return root() / "state" / "screen.json"


def human_idle_s():
    if IDLE:
        return IDLE()
    if os.environ.get("RAINBOW_TEST_IDLE_S"):
        return float(os.environ["RAINBOW_TEST_IDLE_S"])
    if sys.platform != "darwin":
        return None
    try:
        import re
        out = subprocess.run(["ioreg", "-c", "IOHIDSystem", "-d", "4"], capture_output=True, text=True, timeout=3).stdout
        m = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', out)
        return int(m.group(1)) / 1e9 if m else None
    except Exception:
        return None


def human_active():
    idle = human_idle_s()
    return idle is not None and idle < float(os.environ.get("RAINBOW_HUMAN_IDLE_S") or 5)


def holder(now=None):
    """→ the live lease {"holder", "until", "at", "auto"} or None"""
    try:
        d = json.loads(state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if d.get("holder") and float(d.get("until") or 0) > (now or time.time()) else None


class locked:
    def __enter__(self):
        state_file().parent.mkdir(parents=True, exist_ok=True)
        self.fh = open(state_file().with_suffix(".lock"), "w")
        fcntl.flock(self.fh, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.fh, fcntl.LOCK_UN)
        self.fh.close()


def _write(d):
    f = state_file()
    fd, tmp = tempfile.mkstemp(prefix=".screen.", suffix=".tmp", dir=str(f.parent))
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(d))
    os.replace(tmp, f)


def try_take(agent, seconds, auto=False):
    """→ (ok, the lease now in force). The human's takeover and another agent's live lease win; the same agent renews."""
    with locked():
        cur = holder()
        if cur and cur["holder"] != agent:
            return False, cur
        lease = {"holder": agent, "until": time.time() + seconds, "at": (cur or {}).get("at") or time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                 "auto": auto and (not cur or bool(cur.get("auto")))}
        _write(lease)
        return True, lease


def release(agent):
    with locked():
        cur = holder()
        if not cur or cur["holder"] != agent:
            return False
        _write({"holder": None, "until": 0})
        return True


def cmd_take(agent, minutes, wait):
    deadline = time.time() + wait
    while True:
        if human_active():
            why = {"status": "refused", "why": "the human is using the keyboard or mouse right now", "holder": "human"}
        else:
            ok, lease = try_take(agent, minutes * 60)
            if ok:
                rainbow_receipts.write("screen-owner", "take", agent, agent, "taken", minutes=minutes)
                return 0, {"status": "taken", "holder": agent, "until": int(lease["until"])}
            why = {"status": "refused", "why": f"the screen is held by {lease['holder']}", "holder": lease["holder"],
                   "until": int(lease["until"])}
        if time.time() >= deadline:
            return 2, why
        time.sleep(1.0)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="screen-owner")
    sub = ap.add_subparsers(dest="cmd", required=True)
    tk = sub.add_parser("take"); tk.add_argument("agent"); tk.add_argument("--minutes", type=float, default=5); tk.add_argument("--wait", type=float, default=0)
    rl = sub.add_parser("release"); rl.add_argument("agent")
    to = sub.add_parser("takeover"); to.add_argument("--minutes", type=float, default=30)
    sub.add_parser("handback")
    sub.add_parser("who")
    a = ap.parse_args(argv)
    if a.cmd == "take":
        code, out = cmd_take(a.agent.strip().lower(), a.minutes, a.wait)
    elif a.cmd == "release":
        ok = release(a.agent.strip().lower())
        code, out = (0, {"status": "released"}) if ok else (0, {"status": "not-held"})
    elif a.cmd == "takeover":
        with locked():                                  # the human never waits for an agent's lease
            _write({"holder": "human", "until": time.time() + a.minutes * 60, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
        rainbow_receipts.write("screen-owner", "takeover", None, "human", "human", minutes=a.minutes)
        code, out = 0, {"status": "human", "minutes": a.minutes}
    elif a.cmd == "handback":
        ok = release("human")
        rainbow_receipts.write("screen-owner", "handback", None, "human", "released" if ok else "not-held")
        code, out = 0, {"status": "released" if ok else "not-held"}
    else:
        cur = holder()
        code, out = 0, ({"holder": cur["holder"], "until": int(cur["until"]), "auto": bool(cur.get("auto"))} if cur else {"holder": None})
    if a.cmd == "release" and out["status"] == "released":
        rainbow_receipts.write("screen-owner", "release", a.agent.strip().lower(), a.agent.strip().lower(), "released")
    print(json.dumps(out, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
