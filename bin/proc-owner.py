#!/usr/bin/env python3
"""proc-owner — whose process this is on a shared Mac, and stopping only your own.

    proc-owner whose PID                       {"agent": "alpha" | "human", "via": "env" | "browser" | "ancestor" | "none"}
    proc-owner kill PID --by WHO [--force]     stops it only if it is WHO's (the human may stop any); --force: KILL after 5 s
    proc-owner list AGENT                      the agent's processes, and the ports they listen on
    proc-owner reap AGENT [--session ID] [--dry-run]   after a session: the agent's orphaned servers stop (only that
                                               session's with --session), its unused port leases go back

An agent's processes are known by RAINBOW_AGENT=<name> in their environment (set it where the agent starts — see
docs/AGENTS.md — every child inherits it), by an ancestor that carries it, or by being part of the agent's Chrome
(browser-owner's tree). Everything else is the human's. Exit codes: 0 ok · 2 refused · 1 failure. One JSON answer.
"""
from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))   # -I drops the script's folder; the message catalog lives beside it
import rainbow_receipts  # noqa: E402
from rainbow_i18n import t  # noqa: E402


def _load(name, file):
    loader = importlib.machinery.SourceFileLoader(name, str(HERE / file))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


PO = _load("rainbow_port_owner", "port-owner.py")
BO = PO.BO                                  # one registry for all three owners
MARK = re.compile(r"(?:^|\s)RAINBOW_AGENT=([a-z][a-z0-9-]{0,30})(?=\s|$)")
SESSION = re.compile(r"(?:^|\s)RAINBOW_SESSION=([A-Za-z0-9._-]{1,64})(?=\s|$)")
PROCESSES = None                            # tests replace it: () -> [(pid, ppid, cmd)]
MARKERS = None                              # tests replace it: () -> {pid: agent}
SESSIONS = None                             # tests replace it: () -> {pid: session id}
KILL = None                                 # tests replace it: (pid, sig) -> None
ALIVE = None                                # tests replace it: (pid) -> bool


def processes():
    return PROCESSES() if PROCESSES else BO.processes()


def _env_tags():
    """({pid: agent}, {pid: session}) from every process environment that carries RAINBOW_AGENT / RAINBOW_SESSION
    (same user only — that is every agent here)"""
    agents, sessions = {}, {}
    proc = Path("/proc")
    if proc.is_dir():                       # Linux
        for d in proc.iterdir():
            if d.name.isdigit():
                try:
                    env = dict(kv.decode(errors="replace").split("=", 1) for kv in (d / "environ").read_bytes().split(b"\0") if b"=" in kv)
                except OSError:
                    continue
                if env.get("RAINBOW_AGENT"):
                    agents[int(d.name)] = env["RAINBOW_AGENT"].strip().lower()
                if env.get("RAINBOW_SESSION"):
                    sessions[int(d.name)] = env["RAINBOW_SESSION"].strip()
        return agents, sessions
    try:                                    # macOS: ps -E appends the environment to the command
        out = subprocess.run(["ps", "-axEww", "-o", "pid=,command="], capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return agents, sessions
    for line in out.splitlines():
        pid, _, rest = line.strip().partition(" ")
        if not pid.isdigit():
            continue
        m, s = MARK.search(rest), SESSION.search(rest)
        if m:
            agents[int(pid)] = m.group(1)
        if s:
            sessions[int(pid)] = s.group(1)
    return agents, sessions


def markers():
    return MARKERS() if MARKERS else _env_tags()[0]


def sessions():
    return SESSIONS() if SESSIONS else _env_tags()[1]


def ownership(reg=None, rows=None, marks=None):
    """→ (rows, {pid: (agent, via)}) for every process"""
    reg = registry() if reg is None else reg
    rows = processes() if rows is None else rows
    marks = markers() if marks is None else marks
    parent = {pid: ppid for pid, ppid, _ in rows}
    browser = {}
    for name, a in reg.items():
        for pid in BO.tree_of(a, rows)[1]:
            browser[pid] = name
    own = {}
    for pid, _, _ in rows:
        if marks.get(pid) in reg:
            own[pid] = (marks[pid], "env")
        elif pid in browser:
            own[pid] = (browser[pid], "browser")
        else:
            seen, p = set(), parent.get(pid)
            while p and p not in seen and p != 1:
                seen.add(p)
                if marks.get(p) in reg:
                    own[pid] = (marks[p], "ancestor")
                    break
                p = parent.get(p)
            else:
                own[pid] = ("human", "none")
    return rows, own


def registry():
    return BO.registry(PO.REGISTRY)


def cmd_whose(pid):
    rows, own = ownership()
    cmd = next((c for p, _, c in rows if p == pid), None)
    if cmd is None:
        return 1, {"status": "failed", "why": t("pc.no_process", pid=pid)}
    agent, via = own[pid]
    return 0, {"pid": pid, "agent": agent, "via": via, "cmd": cmd[:200]}


def alive(pid):
    return ALIVE(pid) if ALIVE else BO.alive(pid)


def send(pid, sig):
    (KILL or os.kill)(pid, sig)


def cmd_kill(pid, by, force=False):
    if pid <= 1 or pid == os.getpid():
        return 2, {"status": "refused", "why": t("pc.protected", pid=pid)}
    code, who = cmd_whose(pid)
    if code:
        return code, who
    if by != "human" and who["agent"] != by:
        return 2, {"status": "refused", "why": t("pc.not_yours", pid=pid, owner=who["agent"], via=who["via"], by=by)}
    try:
        send(pid, signal.SIGTERM)
        if force:
            deadline = time.time() + 5
            while time.time() < deadline and alive(pid):
                time.sleep(0.25)
            if alive(pid):
                send(pid, signal.SIGKILL)
    except OSError as exc:
        return 1, {"status": "failed", "why": f"{type(exc).__name__}: {exc}"[:200]}
    return 0, {"status": "stopped", "pid": pid, "agent": who["agent"]}


def ports_by_pid():
    got = {}
    for port, who in PO.listeners().items():
        m = re.search(r"\(pid (\d+)\)", who)
        if m:
            got.setdefault(int(m.group(1)), []).append(port)
    return got


def cmd_list(agent):
    reg = registry()
    if agent not in reg:
        return 1, {"status": "failed", "why": t("bo.unknown_agent", agent=repr(agent), names=", ".join(reg))}
    rows, own = ownership(reg)
    ports = ports_by_pid()
    mine = [{"pid": p, "ppid": pp, "via": own[p][1], "cmd": c[:160], "ports": sorted(ports.get(p, []))}
            for p, pp, c in rows if own[p][0] == agent]
    return 0, {"agent": agent, "processes": mine}


def cmd_reap(agent, dry=False, session=None):
    """the agent's servers left behind (re-parented to launchd and listening on a port) stop; its idle port leases go back.
    Never its Chrome (browser-owner's), never the caller's own ancestors (the agent that runs this hook)."""
    reg = registry()
    if agent not in reg:
        return 1, {"status": "failed", "why": t("bo.unknown_agent", agent=repr(agent), names=", ".join(reg))}
    rows, own = ownership(reg)
    parent = {p: pp for p, pp, _ in rows}
    mine_up, p = set(), os.getpid()
    while p and p not in mine_up:
        mine_up.add(p)
        p = parent.get(p)
    ports = ports_by_pid()
    tags = sessions() if session else {}
    orphans = [p for p, pp, _ in rows if own[p][0] == agent and own[p][1] != "browser" and pp == 1 and p in ports and p not in mine_up
               and (not session or tags.get(p) == session)]
    stopped = []
    if not dry:
        for p in orphans:
            try:
                send(p, signal.SIGTERM)
                stopped.append(p)
            except OSError:
                pass
    still = {port for p, ps in ports.items() if p not in stopped for port in ps}
    with PO.locked() as st:
        idle = [x for x in st.leases if x["agent"] == agent and x["port"] not in still]
        if not dry:
            st.leases = [x for x in st.leases if x not in idle]
            st.save()
    if dry:
        return 0, {"status": "would-reap", "processes": orphans, "leases": [x["port"] for x in idle]}
    return 0, {"status": "reaped", "processes": stopped, "released": [x["port"] for x in idle]}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="proc-owner")
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("whose"); w.add_argument("pid", type=int)
    k = sub.add_parser("kill"); k.add_argument("pid", type=int); k.add_argument("--by", required=True); k.add_argument("--force", action="store_true")
    li = sub.add_parser("list"); li.add_argument("agent")
    r = sub.add_parser("reap"); r.add_argument("agent"); r.add_argument("--session"); r.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "whose":
            code, out = cmd_whose(a.pid)
        elif a.cmd == "kill":
            code, out = cmd_kill(a.pid, a.by.strip().lower(), a.force)
        elif a.cmd == "list":
            code, out = cmd_list(a.agent.strip().lower())
        else:
            code, out = cmd_reap(a.agent.strip().lower(), a.dry_run, (a.session or "").strip() or None)
    except FileNotFoundError:
        code, out = 1, {"status": "failed", "why": t("bo.no_registry", path=PO.REGISTRY or BO.REGISTRY)}
    except Exception as exc:   # one JSON answer, always
        code, out = 1, {"status": "failed", "why": f"{type(exc).__name__}: {exc}"[:200]}
    if a.cmd == "kill":
        rainbow_receipts.write("proc-owner", "kill", out.get("agent"), a.by.strip().lower(), out.get("status"), pid=a.pid, why=out.get("why"))
    elif a.cmd == "reap" and not a.dry_run and (out.get("processes") or out.get("released")):
        rainbow_receipts.write("proc-owner", "reap", a.agent.strip().lower(), "session-end", out.get("status"),
                               pids=out.get("processes"), ports=out.get("released"))
    print(json.dumps(out, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
