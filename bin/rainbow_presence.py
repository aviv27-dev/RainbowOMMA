"""rainbow_presence — is the human at the Mac? One answer for every tool that has to decide (the guard, browser-owner,
the cursor proxy, screen-owner), instead of a copy each.

    idle_seconds()    seconds since the last keyboard or mouse input (HIDIdleTime) — a remote screen-sharing session's
                      input counts too — or None when it can't be read
    screen_locked()   the console session's screen is locked, or None when unknown
    presence()        {"present": True|False, "why": "…"} — in doubt, PRESENT: a wrong "absent" would take the focus
                      from someone typing. (The sensitive-sites rule reads idle_seconds() itself and treats unknown as
                      absent — each caller decides what "can't tell" means for it.)

RAINBOW_TEST_IDLE_S fakes the idle time in tests; RAINBOW_HUMAN_PRESENT_S (default 120) is how recent input counts as here.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

IDLE = None                      # tests replace it: () -> seconds or None
LOCKED = None                    # tests replace it: () -> True / False / None


def idle_seconds():
    if IDLE:
        return IDLE()
    if os.environ.get("RAINBOW_TEST_IDLE_S"):
        return float(os.environ["RAINBOW_TEST_IDLE_S"])
    if sys.platform != "darwin":
        return None
    try:
        out = subprocess.run(["ioreg", "-c", "IOHIDSystem", "-d", "4"], capture_output=True, text=True, timeout=3).stdout
        m = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', out)
        return int(m.group(1)) / 1e9 if m else None
    except Exception:
        return None


def screen_locked():
    if LOCKED:
        return LOCKED()
    if sys.platform != "darwin":
        return None
    try:
        out = subprocess.run(["ioreg", "-n", "Root", "-d", "1"], capture_output=True, text=True, timeout=3).stdout
        if "CGSSessionScreenIsLocked" not in out:
            return False if "IOConsoleUsers" in out else None
        return bool(re.search(r'"CGSSessionScreenIsLocked"\s*=\s*Yes', out))
    except Exception:
        return None


def presence():
    limit = float(os.environ.get("RAINBOW_HUMAN_PRESENT_S") or 120)
    if screen_locked():
        return {"present": False, "why": "screen locked"}
    idle = idle_seconds()
    if idle is None:
        return {"present": True, "why": "unknown — counted as present"}
    if idle < limit:
        return {"present": True, "why": f"input {int(idle)} s ago"}
    return {"present": False, "why": f"no input for {int(idle)} s"}
