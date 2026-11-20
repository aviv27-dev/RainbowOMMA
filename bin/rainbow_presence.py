"""rainbow_presence — is the human at the Mac? One answer for every tool that has to decide (the guard, browser-owner,
the cursor proxy, screen-owner), instead of a copy each.

    idle_seconds()    seconds since the last keyboard or mouse input (HIDIdleTime) — a remote screen-sharing session's
                      input counts too — or None when it can't be read
    screen_locked()   the console session's screen is locked, or None when unknown
    presence()        {"present": True|False, "why": "…"} — in doubt, PRESENT: a wrong "absent" would take the focus
                      from someone typing. (The sensitive-sites rule reads idle_seconds() itself and treats unknown as
                      absent — each caller decides what "can't tell" means for it.)

RAINBOW_TEST_IDLE_S fakes the idle time in tests; RAINBOW_HUMAN_PRESENT_S (default 120) is how recent input counts as here.

An AGENT's activity in its own browser, for idle-stop (#91): the last command it sent there (a navigation, code it ran,
a download …) — not a connection held open without commands. Written by whatever sees the command go by (cdp-broker in
pipe mode, the guard for a browser tool call), read by browser-owner:

    stamp_activity(agent, via)   record that the agent just sent a command (throttled: at most one write per 30 s)
    last_activity(agent)         {"at": epoch seconds, "via": "…"} or None
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

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


# ── an agent's last command in its own browser (#91) ──
ACTIVITY_WRITE_EVERY_S = 30
_last_write = {}

# CDP methods that are not the agent working: RainbowOMMA's own reads and housekeeping, and a client setting up its
# connection. Everything else an agent sends (Page.navigate, Runtime.evaluate, Input.*, Browser.setDownloadBehavior …) is.
NOT_ACTIVITY = re.compile(r"^(?:Target\.(?:getTargets|getTargetInfo|attachToTarget|detachFromTarget|setDiscoverTargets|"
                          r"setAutoAttach|closeTarget|activateTarget)|Browser\.(?:getVersion|getWindowForTarget|close)|SystemInfo\..*|"
                          r"Performance\..*|[A-Za-z]+\.(?:enable|disable))$")


def activity_path():
    root = os.environ.get("RAINBOW_HOME") or os.path.join(os.path.expanduser("~"), ".rainbowomma")
    return Path(os.path.expanduser(root)) / "state" / "browser-activity.json"


def counts_as_activity(method):
    return isinstance(method, str) and bool(method) and not NOT_ACTIVITY.match(method)


def stamp_activity(agent, via, now=None):
    """the agent just sent a command to its own browser. Never raises: a stamp that can't be written is skipped."""
    agent = str(agent or "").strip().lower()
    if not agent:
        return False
    now = time.time() if now is None else now
    if now - _last_write.get(agent, 0) < ACTIVITY_WRITE_EVERY_S:
        return False
    try:
        p = activity_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            d = d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            d = {}
        d[agent] = {"at": now, "via": str(via)[:80]}
        fd, tmp = tempfile.mkstemp(prefix=".browser-activity.", dir=str(p.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(d, fh)
        os.replace(tmp, p)
        _last_write[agent] = now
        return True
    except Exception:
        return False


def last_activity(agent):
    try:
        d = json.loads(activity_path().read_text(encoding="utf-8"))
        rec = d.get(str(agent).strip().lower()) if isinstance(d, dict) else None
        return rec if isinstance(rec, dict) and isinstance(rec.get("at"), (int, float)) else None
    except (OSError, ValueError):
        return None

