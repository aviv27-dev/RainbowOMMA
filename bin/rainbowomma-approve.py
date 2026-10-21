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
import contextlib
import fcntl
import hashlib
import json
import os
import re
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
MAX_COMMAND = 600            # longer is refused, never cut: the human sees all of what runs
MAX_WHY = 200
NAME_RE = re.compile(r"[a-z][a-z0-9-]{1,30}")
ASK = None                   # tests replace it: (agent, why, command) -> True/False. No environment variable can answer.


def store():
    root = Path(os.path.expanduser(os.environ.get("RAINBOW_HOME") or str(Path.home() / ".rainbowomma")))
    return root / "state" / "approvals.json"


def key(command, agent=""):
    """the same key for the command the agent asked about (its words) and the shell line the guard sees — and only
    for the agent that asked"""
    if isinstance(command, str):
        try:
            command = shlex.split(command)
        except ValueError:
            command = command.split()
    return hashlib.sha256("\0".join([agent or "", *command]).encode()).hexdigest()


def pending_file():
    return store().with_name("approval-pending.json")


def pending():
    """an approval dialog is up — no agent may click or type until the human answered it"""
    try:
        return time.time() - pending_file().stat().st_mtime < DIALOG_S + 30
    except OSError:
        return False


@contextlib.contextmanager
def locked():
    """one reader-writer at a time: two guards must never both use one Allow-once"""
    store().parent.mkdir(parents=True, exist_ok=True)
    with open(store().with_suffix(".lock"), "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _load():
    try:
        d = json.loads(store().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    now = time.time()
    return {k: v for k, v in d.items() if float(v.get("until") or 0) > now}


def _save(d):
    f = store()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f".{f.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, f)


def consume(command, agent=""):
    """→ the approval for exactly this command, asked by this agent (and it is used up), or None"""
    with locked():
        d = _load()
        rec = d.pop(key(command, agent), None)
        if rec:
            _save(d)
    return rec


def clean(text, limit):
    """one line, no control characters: nothing can push the command out of the human's sight"""
    return re.sub(r"[\x00-\x1f\x7f]+", " ", str(text)).strip()[:limit]


def ask_human(agent, why, command):
    """→ True (allow once) · False (deny, or no answer in time)"""
    if ASK:
        return ASK(agent, why, command)
    text = t("ap.dialog", agent=agent, why=why, command=shlex.join(command))
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
    me = (os.environ.get("RAINBOW_AGENT") or "").strip().lower()
    if not NAME_RE.fullmatch(agent) or agent == "human" or (me and agent != me):
        print(json.dumps({"status": "refused", "why": f"--agent must be your own agent name ({me or 'a-z, 0-9, -'})"}, ensure_ascii=False))
        return 2
    if len(shlex.join(command)) > MAX_COMMAND:
        print(json.dumps({"status": "refused", "why": f"the command is longer than {MAX_COMMAND} characters — the human must "
                                                      "be able to read all of it; send a shorter one"}, ensure_ascii=False))
        return 2
    a.why = clean(a.why, MAX_WHY)
    ok = ask_human(agent, a.why, command)
    rainbow_receipts.write("approve", "ask", agent, agent, "approved" if ok else "refused", why=a.why, command=cmd)
    if not ok:
        print(json.dumps({"status": "refused", "why": t("ap.refused")}, ensure_ascii=False))
        return 2
    with locked():
        d = _load()
        d[key(command, me)] = {"agent": agent, "command": cmd[:MAX_COMMAND], "until": time.time() + VALID_S}
        _save(d)
    print(json.dumps({"status": "approved", "validSeconds": VALID_S, "next": t("ap.next")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
