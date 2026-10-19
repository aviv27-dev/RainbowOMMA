#!/usr/bin/env python3
"""port-owner — every agent's network ports on a shared Mac: a range per agent, leases inside it, the usual ports left to the human.

    port-owner lease AGENT [--name NAME] [--prefer PORT]     a free port of the agent's own, held for it
    port-owner env AGENT [--name NAME] [--var VAR ...]       the same, as shell words: eval "$(port-owner env alpha) npm run dev"
    port-owner who PORT                                      whose port this is, and who listens on it
    port-owner release AGENT [--name NAME | --all]           give a lease back
    port-owner list [AGENT]                                  the ranges and the leases

Each agent in browsers.json may set "ports": "41000-41099"; without it, it gets 41000 + 100 × (CDP port − 9222), 100 ports.
"humanPorts" (top level) lists the ports an agent never leases — by default 3000, 5173, 8000, 8080 and the other usual ones.
A lease nobody listens on is dropped after 10 minutes. Exit codes: 0 ok · 2 refused · 1 failure. One JSON answer (env: shell words).
"""
from __future__ import annotations

import argparse
import fcntl
import importlib.machinery
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))   # -I drops the script's folder; the message catalog lives beside it
import rainbow_receipts  # noqa: E402
from rainbow_i18n import t  # noqa: E402

LEASE_TTL_S = 600


def _owner_module():
    loader = importlib.machinery.SourceFileLoader("rainbow_browser_owner", str(HERE / "browser-owner.py"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


BO = _owner_module()                       # the registry (agents, their port ranges) is browser-owner's
STATE = BO.SHARED / "state" / "ports.json"
REGISTRY = None                            # tests point it at their own browsers.json
LISTENERS = None                           # tests replace it: () -> {port: "cmd (pid N)"}
BINDABLE = None                            # tests replace it: (port) -> bool


def registry():
    return BO.registry(REGISTRY)


def human_ports():
    return BO.human_ports(REGISTRY)


def rng(a):
    return f"{a['ports'][0]}-{a['ports'][1]}"


def listeners():
    """{port: "cmd (pid N)"} for every TCP port something listens on"""
    if LISTENERS:
        return LISTENERS()
    try:
        out = subprocess.run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-Fpcn"], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return {}
    got, pid, cmd = {}, "", ""
    for line in out.splitlines():
        if line.startswith("p"):
            pid = line[1:]
        elif line.startswith("c"):
            cmd = line[1:]
        elif line.startswith("n") and ":" in line:
            try:
                got.setdefault(int(line.rsplit(":", 1)[1]), f"{cmd} (pid {pid})")
            except ValueError:
                pass
    return got


def bindable(port):
    """nothing holds it: it binds on every interface"""
    if BINDABLE:
        return BINDABLE(port)
    for host in ("0.0.0.0", "127.0.0.1"):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind((host, port))
        except OSError:
            return False
        finally:
            s.close()
    return True


class locked:
    def __enter__(self):
        STATE.parent.mkdir(parents=True, exist_ok=True)
        self.fh = open(STATE.with_suffix(".lock"), "w")
        fcntl.flock(self.fh, fcntl.LOCK_EX)
        try:
            self.leases = json.loads(STATE.read_text(encoding="utf-8")).get("leases", [])
        except (OSError, ValueError):
            self.leases = []
        return self

    def save(self):
        fd, tmp = tempfile.mkstemp(prefix=".ports.", suffix=".tmp", dir=str(STATE.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"leases": self.leases}, ensure_ascii=False, indent=1))
        os.replace(tmp, STATE)

    def __exit__(self, *exc):
        fcntl.flock(self.fh, fcntl.LOCK_UN)
        self.fh.close()


def drop_stale(leases, listening, now=None):
    """a lease older than LEASE_TTL_S that nothing listens on was never used, or its server is gone"""
    now = now or time.time()
    return [x for x in leases if now - float(x.get("at") or 0) < LEASE_TTL_S or x["port"] in listening]


def leases_of(reg=None):
    """the live leases (read-only) — what the guard checks against"""
    try:
        return json.loads(STATE.read_text(encoding="utf-8")).get("leases", [])
    except (OSError, ValueError):
        return []


def owner_of(port, reg, leases, humans):
    """→ (owner, why): an agent by lease or range, else the human (kept for them, or simply nobody's)"""
    for x in leases:
        if x["port"] == port:
            return x["agent"], "lease"
    for name, a in reg.items():
        if a["ports"][0] <= port <= a["ports"][1]:
            return name, "range"
    return "human", "reserved" if port in humans else "unassigned"


def cmd_lease(agent, name="default", prefer=None):
    reg = registry()
    a = reg.get(agent)
    if not a:
        return 1, {"status": "failed", "why": t("bo.unknown_agent", agent=repr(agent), names=", ".join(reg))}
    humans = set(human_ports())
    lo, hi = a["ports"]
    with locked() as st:
        listening = listeners()
        st.leases = drop_stale(st.leases, listening)
        mine = next((x for x in st.leases if x["agent"] == agent and x["name"] == name), None)
        if mine and (prefer is None or mine["port"] == prefer):
            st.save()
            return 0, {"status": "leased", "port": mine["port"], "agent": agent, "name": name, "range": rng(a), "existing": True}
        taken = {x["port"] for x in st.leases if x is not mine}
        if prefer is not None:
            if prefer in humans:
                return 2, {"status": "refused", "why": t("po.human_port", port=prefer, agent=agent)}
            if not lo <= prefer <= hi:
                return 2, {"status": "refused", "why": t("po.not_yours", port=prefer, agent=agent, range=rng(a))}
            if prefer in taken or prefer in listening or not bindable(prefer):
                return 2, {"status": "refused", "why": t("po.taken", port=prefer, who=listening.get(prefer) or "a lease")}
            pick = prefer
        else:
            pick = next((p for p in range(lo, hi + 1)
                         if p not in humans and p not in taken and p not in listening and bindable(p)), None)
            if pick is None:
                return 1, {"status": "failed", "why": t("po.full", agent=agent, range=rng(a))}
        if mine:
            st.leases.remove(mine)
        st.leases.append({"port": pick, "agent": agent, "name": name, "at": time.time()})
        st.save()
    return 0, {"status": "leased", "port": pick, "agent": agent, "name": name, "range": rng(a)}


def cmd_release(agent, name=None, every=False):
    with locked() as st:
        keep = [x for x in st.leases if not (x["agent"] == agent and (every or x["name"] == (name or "default")))]
        n = len(st.leases) - len(keep)
        st.leases = keep
        st.save()
    return 0, {"status": "released", "count": n}


def cmd_who(port):
    reg = registry()
    with locked() as st:
        listening = listeners()
        st.leases = drop_stale(st.leases, listening)
        st.save()
        owner, why = owner_of(port, reg, st.leases, set(human_ports()))
        lease = next(({k: v for k, v in x.items()} for x in st.leases if x["port"] == port), None)
    return 0, {"port": port, "owner": owner, "why": why, "lease": lease, "listening": listening.get(port)}


def cmd_list(agent=None):
    reg = registry()
    with locked() as st:
        st.leases = drop_stale(st.leases, listeners())
        st.save()
        leases = [x for x in st.leases if not agent or x["agent"] == agent]
    return 0, {"ranges": {n: rng(a) for n, a in reg.items() if not agent or n == agent}, "humanPorts": human_ports(), "leases": leases}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="port-owner")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("lease", "env"):
        x = sub.add_parser(c); x.add_argument("agent"); x.add_argument("--name", default="default"); x.add_argument("--prefer", type=int)
        if c == "env":
            x.add_argument("--var", action="append", default=[], help="another variable to set to the same port (VITE_PORT …)")
    w = sub.add_parser("who"); w.add_argument("port", type=int)
    r = sub.add_parser("release"); r.add_argument("agent"); r.add_argument("--name"); r.add_argument("--all", action="store_true")
    li = sub.add_parser("list"); li.add_argument("agent", nargs="?")
    a = ap.parse_args(argv)
    agent = (getattr(a, "agent", None) or "").strip().lower() or None
    try:
        if a.cmd in ("lease", "env"):
            code, out = cmd_lease(agent, a.name, a.prefer)
        elif a.cmd == "release":
            code, out = cmd_release(agent, a.name, a.all)
        elif a.cmd == "who":
            code, out = cmd_who(a.port)
        else:
            code, out = cmd_list(agent)
    except FileNotFoundError:
        code, out = 1, {"status": "failed", "why": t("bo.no_registry", path=REGISTRY or BO.REGISTRY)}
    except Exception as exc:   # one JSON answer, always
        code, out = 1, {"status": "failed", "why": f"{type(exc).__name__}: {exc}"[:200]}
    if a.cmd in ("lease", "env", "release") and not out.get("existing"):
        rainbow_receipts.write("port-owner", "release" if a.cmd == "release" else "lease", agent, agent, out.get("status"),
                               port=out.get("port"), name=getattr(a, "name", None), why=out.get("why"))
    if a.cmd == "env":
        if code:
            print(json.dumps(out, ensure_ascii=False), file=sys.stderr)
        else:
            print(" ".join(f"{v}={out['port']}" for v in ["PORT", *[x.upper() for x in a.var]]))
        return code
    print(json.dumps(out, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
