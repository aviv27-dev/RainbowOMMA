#!/usr/bin/env python3
"""rainbowomma-approve — the human says yes (or no) before an agent sends something that can't be taken back.

    rainbowomma-approve ask --agent NAME --why "TEXT" -- COMMAND …   a dialog shows the human exactly what will be sent;
                                                                    "Allow once" lets that exact command run once, within 5 min
    rainbowomma-approve list                                       the approvals waiting to be used

The guardrail refuses sending through Messages or Mail (AppleScript `send`, a new outgoing message) unless this exact
command was approved; using an approval consumes it. Exit codes: 0 approved · 2 refused (or no answer) · 1 failure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))   # -I drops the script's folder; the message catalog lives beside it
import rainbow_receipts  # noqa: E402
from rainbow_i18n import t  # noqa: E402

VALID_S = 300
DIALOG_S = 120


def store():
    root = Path(os.path.expanduser(os.environ.get("RAINBOW_HOME") or str(Path.home() / ".rainbowomma")))
    return root / "state" / "approvals.json"


def key(command):
    """the same key for the command the agent asked about (its words) and the shell line the guard sees"""
    if isinstance(command, str):
        try:
            command = shlex.split(command)
        except ValueError:
            command = command.split()
    return hashlib.sha256("\0".join(command).encode()).hexdigest()


def pending_file():
    return store().with_name("approval-pending.json")


def pending():
    """an approval dialog is up — no agent may click or type until the human answered it"""
    try:
        return time.time() - pending_file().stat().st_mtime < DIALOG_S + 30
    except OSError:
        return False


def _load():
    try:
        d = json.loads(store().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    now = time.time()
    return {k: v for k, v in d.items() if float(v.get("until") or 0) > now}


def _save(d):
    store().parent.mkdir(parents=True, exist_ok=True)
    store().write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def consume(command):
    """→ the approval for exactly this command (and it is used up), or None"""
    d = _load()
    rec = d.pop(key(command), None)
    if rec:
        _save(d)
    return rec


def ask_human(agent, why, command):
    """→ True (allow once) · False (deny, or no answer in time)"""
    if os.environ.get("RAINBOW_TEST_APPROVE"):
        return os.environ["RAINBOW_TEST_APPROVE"] == "yes"
    text = t("ap.dialog", agent=agent, why=why, command=" ".join(command)[:600])
    script = (f'display dialog {json.dumps(text)} with title "RainbowOMMA" buttons {{{json.dumps(t("ap.deny"))}, '
              f'{json.dumps(t("ap.allow"))}}} default button {json.dumps(t("ap.deny"))} with icon caution giving up after {DIALOG_S}')
    pending_file().parent.mkdir(parents=True, exist_ok=True)
    pending_file().write_text(json.dumps({"agent": agent}), encoding="utf-8")
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=DIALOG_S + 10)
    except Exception:
        return False
    finally:
        try:
            pending_file().unlink()
        except OSError:
            pass
    return r.returncode == 0 and t("ap.allow") in r.stdout and "gave up:true" not in r.stdout


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    command = []
    if "--" in argv:
        i = argv.index("--")
        argv, command = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser(prog="rainbowomma-approve")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a_ = sub.add_parser("ask"); a_.add_argument("--agent", required=True); a_.add_argument("--why", default="")
    sub.add_parser("list")
    a = ap.parse_args(argv)
    if a.cmd == "list":
        print(json.dumps({"approvals": list(_load().values())}, ensure_ascii=False))
        return 0
    cmd = " ".join(command).strip()
    if not command:
        print(json.dumps({"status": "failed", "why": "usage: rainbowomma-approve ask --agent NAME --why TEXT -- COMMAND …"}))
        return 1
    agent = a.agent.strip().lower()
    ok = ask_human(agent, a.why, command)
    rainbow_receipts.write("approve", "ask", agent, agent, "approved" if ok else "refused", why=a.why, command=cmd)
    if not ok:
        print(json.dumps({"status": "refused", "why": t("ap.refused")}, ensure_ascii=False))
        return 2
    d = _load()
    d[key(command)] = {"agent": agent, "command": cmd[:300], "until": time.time() + VALID_S}
    _save(d)
    print(json.dumps({"status": "approved", "validSeconds": VALID_S, "next": t("ap.next")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
