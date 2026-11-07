#!/usr/bin/env python3
"""rainbowomma-browser — a BROWSER= launcher for agents: an address an agent's framework opens (a sign-in, an OAuth or
device-code page) goes to that agent's OWN browser, never the human's.

    BROWSER=~/bin/rainbowomma-browser      in the agent's environment (as-agent sets RAINBOW_AGENT; see docs/AGENTS.md)

Python's webbrowser.open, and most frameworks, run $BROWSER with the address. This runs `browser-owner open
$RAINBOW_AGENT <url>`. It never hands the address on to another browser: when it can't open it, it says why on stderr
and still exits 0, because a failure would make webbrowser.open fall back to the human's default browser.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main(argv=None):
    urls = [u for u in (sys.argv[1:] if argv is None else argv) if u.strip()]
    me = (os.environ.get("RAINBOW_AGENT") or "").strip().lower()
    if not me:
        print("rainbowomma-browser: no agent name (RAINBOW_AGENT) — not opening anything; start the agent with as-agent", file=sys.stderr)
        return 0
    for u in urls:
        r = subprocess.run([str(HERE / "browser-owner"), "open", me, u, "--by", me], capture_output=True, text=True, timeout=90)
        if r.returncode:
            print(f"rainbowomma-browser: {me}'s browser didn't open it: {(r.stdout or r.stderr).strip()[:300]}\n"
                  f"  open it yourself: browser-owner open {me} {u}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
