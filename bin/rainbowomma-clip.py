#!/usr/bin/env python3
"""rainbowomma-clip — a clipboard of its own for every agent, so no agent overwrites (or reads) the human's.

    echo text | rainbowomma-clip copy AGENT [--name N]     keep it
    rainbowomma-clip paste AGENT [--name N]                print it back
    rainbowomma-clip clear AGENT                           forget them all

The system clipboard is the human's: with RAINBOW_AGENT set, the guardrail refuses pbcopy, pbpaste and AppleScript's
"the clipboard", and points here. Each agent's clips are files only its user can read ($RAINBOW_HOME/state/clip/AGENT).
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path


def folder(agent):
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,30}", agent):
        raise SystemExit("rainbowomma-clip: bad agent name")
    root = Path(os.path.expanduser(os.environ.get("RAINBOW_HOME") or str(Path.home() / ".rainbowomma")))
    return root / "state" / "clip" / agent


def main(argv=None):
    ap = argparse.ArgumentParser(prog="rainbowomma-clip")
    ap.add_argument("cmd", choices=["copy", "paste", "clear"]); ap.add_argument("agent"); ap.add_argument("--name", default="default")
    a = ap.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", a.name):
        print("rainbowomma-clip: bad clip name", file=sys.stderr)
        return 2
    d = folder(a.agent.strip().lower())
    if a.cmd == "clear":
        shutil.rmtree(d, ignore_errors=True)
        return 0
    f = d / a.name
    if a.cmd == "copy":
        d.mkdir(parents=True, exist_ok=True)
        os.chmod(d, 0o700)
        data = sys.stdin.buffer.read()
        fd = os.open(str(f), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        return 0
    try:
        sys.stdout.buffer.write(f.read_bytes())
    except OSError:
        print(f"rainbowomma-clip: nothing copied as {a.name}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
