#!/usr/bin/env python3
"""rainbow_receipts — one line per thing the owners did or refused, for the human to read back.

Every owner (browser-owner, port-owner, proc-owner, office-owner) and the guard append one JSON line to
$RAINBOW_HOME/logs/receipts.jsonl: when, which tool, what, for which agent, by whom, the status word, and a few details.
Read-only commands (list, status, who, whose) leave no receipt. A receipt that can't be written never stops the tool.

    receipts [--agent NAME] [--tool TOOL] [--since 2026-10-19T08:00] [-n 50]     the last receipts, oldest first
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
import time
from pathlib import Path

MAX_FIELD = 300


def path():
    root = Path(os.path.expanduser(os.environ.get("RAINBOW_HOME") or str(Path.home() / ".rainbowomma")))
    return root / "logs" / "receipts.jsonl"


def write(tool, action, agent=None, by=None, status=None, **detail):
    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "tool": tool, "action": action, "agent": agent, "by": by, "status": status}
    rec.update({k: (v[:MAX_FIELD] if isinstance(v, str) else v) for k, v in detail.items() if v not in (None, "", [], {})})
    try:
        p = path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fcntl.flock(fh, fcntl.LOCK_UN)
    except OSError:
        pass
    return rec


def read(agent=None, tool=None, since=None, n=50):
    try:
        lines = path().read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for ln in lines:
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if agent and r.get("agent") != agent:
            continue
        if tool and r.get("tool") != tool:
            continue
        if since and str(r.get("at", ""))[:len(since)] < since:
            continue
        out.append(r)
    return out[-n:] if n else out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="receipts")
    ap.add_argument("--agent"); ap.add_argument("--tool"); ap.add_argument("--since"); ap.add_argument("-n", type=int, default=50)
    a = ap.parse_args(argv)
    for r in read(a.agent, a.tool, a.since, a.n):
        print(json.dumps(r, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
