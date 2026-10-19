#!/usr/bin/env python3
"""rainbowomma-pause — the human's stop button for every agent at once.

    rainbowomma-pause on | off | toggle | status

While paused, the guardrail refuses every command and tool call it sees ("the human paused all agents") and the cursor
proxy holds computer-use actions, then answers them with an error. Nothing is killed; resuming lets everything go on.
One JSON answer. The menu-bar item (install.sh --with-menubar) toggles it, with a keyboard shortcut.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # -I drops the script's folder
import rainbow_receipts  # noqa: E402


def flag():
    root = Path(os.path.expanduser(os.environ.get("RAINBOW_HOME") or str(Path.home() / ".rainbowomma")))
    return root / "state" / "paused.json"


def paused():
    """→ the pause record ({"at": …}) or None"""
    try:
        return json.loads(flag().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def set_paused(on):
    f = flag()
    if on:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}), encoding="utf-8")
    else:
        try:
            f.unlink()
        except OSError:
            pass
    rainbow_receipts.write("pause", "on" if on else "off", None, "human", "paused" if on else "running")
    return paused()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    what = (argv or ["status"])[0]
    if what not in ("on", "off", "toggle", "status"):
        print(json.dumps({"status": "failed", "why": "usage: rainbowomma-pause on|off|toggle|status"}))
        return 1
    rec = paused()
    if what != "status":
        rec = set_paused(what == "on" or (what == "toggle" and not rec))
    print(json.dumps({"status": "paused" if rec else "running", **({"since": rec.get("at")} if rec else {})}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
