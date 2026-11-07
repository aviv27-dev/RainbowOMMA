#!/usr/bin/env python3
"""rainbowomma-doctor — is everything RainbowOMMA needs in place on this Mac? Changes nothing.

    rainbowomma-doctor            one line per check: ✓ ok · ✗ needed and missing (with the fix) · – optional and missing
    rainbowomma-doctor --json     the same as one JSON answer
    rainbowomma-doctor logs [--since 2026-11-01] [-n 200]   every log RainbowOMMA writes, as one timeline
    rainbowomma-doctor status [--json]   the running system: agents, presence, ports, Office, recent errors — each problem with its fix

Exit codes: 0 everything needed is in place · 1 something needed is missing.
"""
from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))   # -I drops the script's folder; the message catalog lives beside it
from rainbow_i18n import t  # noqa: E402

MAC = sys.platform == "darwin"


def _load(name, file):
    loader = importlib.machinery.SourceFileLoader(name, str(HERE / file))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def check(name, ok, detail="", fix="", needed=True):
    return {"check": name, "ok": bool(ok), "needed": needed, "detail": detail, "fix": "" if ok else fix}


def osa_ok(script):
    """→ True ok · False refused (no permission) · None could not tell"""
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
    except Exception:
        return None
    if r.returncode == 0:
        return True
    return False if "-1743" in (r.stderr or "") or "not allowed" in (r.stderr or "").lower() else None


def run_checks(launch_agents=None):
    out = [check(t("dr.python"), sys.version_info >= (3, 9), sys.version.split()[0], t("dr.python_fix"))]
    bo = _load("rainbow_browser_owner", "browser-owner.py")
    try:
        reg = bo.registry()
        out.append(check(t("dr.registry"), True, t("dr.agents", n=len(reg), names=", ".join(reg))))
    except FileNotFoundError:
        reg = {}
        out.append(check(t("dr.registry"), False, str(bo.REGISTRY), t("bo.no_registry", path=bo.REGISTRY)))
    except Exception as exc:
        reg = {}
        out.append(check(t("dr.registry"), False, f"{type(exc).__name__}: {exc}"[:200], t("dr.registry_fix")))
    for app in sorted({a["chrome_app"] for a in reg.values() if not a.get("managedBy")}):
        out.append(check(t("dr.chrome", app=Path(app).name), not MAC or Path(app).exists(), app, t("dr.chrome_fix", app=Path(app).name)))
    root = bo.SHARED
    try:
        (root / "logs").mkdir(parents=True, exist_ok=True)
        probe = root / "logs" / ".doctor"
        probe.write_text("ok"); probe.unlink()
        out.append(check(t("dr.state"), True, str(root)))
    except OSError as exc:
        out.append(check(t("dr.state"), False, f"{root}: {exc}", t("dr.state_fix", path=root)))
    try:
        iv = json.loads((root / "installed-version").read_text())
        out.append(check(t("dr.version"), bool(iv.get("version")), f'{iv.get("version")} ({iv.get("source")}, {iv.get("at")})',
                         t("dr.version_fix"), needed=False))
    except (OSError, ValueError, AttributeError):
        out.append(check(t("dr.version"), False, str(root / "installed-version"), t("dr.version_fix"), needed=False))
    for tool in ("browser-owner", "office-owner", "port-owner", "proc-owner", "rainbowomma-guard", "rainbow_i18n.py"):
        out.append(check(t("dr.tool", tool=tool), (HERE / tool).exists(), str(HERE / tool), t("dr.tool_fix")))
    if MAC:
        ok = osa_ok('tell application "System Events" to get name of first process whose frontmost is true')
        out.append(check(t("dr.system_events"), ok is not False, "" if ok else t("dr.unknown") if ok is None else "-1743",
                         t("dr.system_events_fix")))
        hid = subprocess.run(["ioreg", "-c", "IOHIDSystem", "-d", "4"], capture_output=True, text=True).stdout if shutil.which("ioreg") else ""
        out.append(check(t("dr.hid"), "HIDIdleTime" in hid, "", t("dr.hid_fix"), needed=False))
    else:
        out.append(check(t("dr.macos"), False, sys.platform, t("dr.macos_fix"), needed=False))
    for app in ("Microsoft Word", "Microsoft Excel"):
        out.append(check(t("dr.app", app=app), Path(f"/Applications/{app}.app").exists(), "", t("dr.app_fix", app=app), needed=False))
    cua = os.environ.get("CUA_DRIVER") or ("/Applications/CuaDriver.app/Contents/MacOS/cua-driver"
                                          if Path("/Applications/CuaDriver.app").exists() else shutil.which("cua-driver"))
    out.append(check(t("dr.cua"), bool(cua), cua or "", t("dr.cua_fix"), needed=False))
    la = Path(launch_agents or os.path.expanduser("~/Library/LaunchAgents"))
    for label, flag in (("com.rainbowomma.agent-office-sweep", "--with-sweep"), ("com.rainbowomma.heal", "--with-heal")):
        out.append(check(t("dr.job", label=label), (la / f"{label}.plist").exists(), "", t("dr.job_fix", flag=flag), needed=False))
    guard_users = [f for f in ("~/.claude/settings.json", "~/.codex/hooks.json", "~/.gemini/settings.json", "~/.cursor/hooks.json")
                   if "rainbowomma-guard" in _read(f)]
    out.append(check(t("dr.guard"), bool(guard_users), ", ".join(guard_users), t("dr.guard_fix"), needed=False))
    return out


def _read(path):
    try:
        return Path(os.path.expanduser(path)).read_text(encoding="utf-8")
    except OSError:
        return ""


def _json(*argv, timeout=30):
    """one tool's JSON answer (the last line it prints), or {} — the status screen asks the tools, it never guesses"""
    try:
        r = subprocess.run([str(HERE / argv[0]), *argv[1:]], capture_output=True, text=True, timeout=timeout)
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return {}


def _ago_min(iso):
    import time
    try:
        return int((time.time() - time.mktime(time.strptime(str(iso)[:19], "%Y-%m-%dT%H:%M:%S"))) // 60)
    except (ValueError, TypeError):
        return None


BAD_STATUS = ("refused", "failed", "blocked", "busy", "blocked-by-dialog")


def status():
    """the running system on one screen: → {"agents", "ports", "presence", "office", "errors", "problems"}; each problem
    has a fix. Read-only: it only asks the tools."""
    problems = []
    listing = _json("browser-owner", "list").get("agents", [])
    agents = []
    fixes = {"hung": "browser-owner recover {a} --by {a}", "blocked": "port-owner who {port}  (something else answers on its port)",
             "profile-busy": "a Chrome outside the owner uses its profile — close it, then browser-owner start {a} --by {a}"}
    for v in listing:
        a, st = v.get("agent"), v.get("status")
        quiet = _ago_min(v.get("idleSince")) if st == "up" else None
        row = {"agent": a, "status": st, "cdp": v.get("cdp", "port"), "port": v.get("port"), "color": v.get("color"),
               "themePending": v.get("themePending", False), "offByHuman": v.get("offByHuman", False),
               "idle": f"{quiet}/{v['idleMinutes']} min" if quiet is not None and v.get("idleMinutes") else None}
        agents.append(row)
        if st in fixes:
            problems.append({"what": f"{a}: browser {st}", "fix": fixes[st].format(a=a, port=v.get("port"))})
        if row["themePending"]:
            problems.append({"what": f"{a}: its colors are missing while its browser is open",
                             "fix": f"stop and start it when it suits you (browser-owner stop {a} --by human; desk icon to open)"})
    ports = _json("port-owner", "list")
    presence = _json("browser-owner", "presence")
    office = _json("office-owner", "apps").get("apps", {})
    root = Path(os.path.expanduser(os.environ.get("RAINBOW_HOME") or str(Path.home() / ".rainbowomma")))
    try:
        temps = json.loads((root / "state" / "doc_leases").parent.joinpath("office_temps.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        temps = []
    if temps:
        problems.append({"what": f"{len(temps)} temp cop{'y' if len(temps) == 1 else 'ies'} left open in Office by failed conversions",
                         "fix": "office-owner sweep  (closes them, then quits an idle Office it launched)"})
    import rainbow_receipts
    recent = [r for r in rainbow_receipts.read(n=400) if r.get("status") in BAD_STATUS and (_ago_min(r.get("at")) or 0) <= 24 * 60]
    if any(r.get("status") == "blocked-by-dialog" for r in recent[-5:]):
        problems.append({"what": "Word showed a dialog that blocked a conversion", "fix": "close the dialog in Word (or quit Word), then retry"})
    return {"agents": agents, "ports": {"leases": len(ports.get("leases", [])), "byAgent": {
                n: sum(1 for x in ports.get("leases", []) if x.get("agent") == n) for n in ports.get("ranges", {})}},
            "presence": presence, "office": {k: {"launchedBy": v.get("launchedBy"), "running": v.get("running"),
                                                 "inflight": v.get("inflight")} for k, v in office.items()},
            "officeTemps": len(temps), "errors": [{k: r.get(k) for k in ("at", "tool", "action", "agent", "status", "why")} for r in recent[-5:]],
            "errors24h": len(recent), "problems": problems}


def print_status(s):
    print("Agents")
    for a in s["agents"] or [{"agent": "—", "status": "no agents (browsers.json)"}]:
        extra = " · ".join(x for x in (a.get("cdp") == "pipe" and "pipe", a.get("idle") and f"idle {a['idle']}",
                                       a.get("offByHuman") and "closed by the human", a.get("themePending") and "colors missing") if x)
        print(f"  {a['agent']:<10} {a['status']:<14} {extra}")
    pr = s["presence"] or {}
    print(f"Presence   {'here' if pr.get('present') else 'away' if pr else 'unknown'} ({pr.get('why', '—')})")
    print(f"Ports      {s['ports']['leases']} leased" + "".join(f" · {n} {c}" for n, c in s["ports"]["byAgent"].items() if c))
    print("Office     " + (", ".join(f"{k} {'running' if v['running'] else 'not running'} ({v['launchedBy'] or '—'})"
                                     for k, v in s["office"].items()) or "nothing launched by office-owner")
          + (f" · {s['officeTemps']} temp copies left" if s["officeTemps"] else ""))
    print(f"Errors     {s['errors24h']} in the last 24 h")
    for e in s["errors"]:
        print(f"  {str(e.get('at'))[11:16]} {e.get('agent') or '—'}: {e.get('tool')} {e.get('action')} → {e.get('status')}"
              + (f" — {str(e.get('why'))[:90]}" if e.get("why") else ""))
    if s["problems"]:
        print("Needs attention")
        for p in s["problems"]:
            print(f"  ✗ {p['what']}\n    → {p['fix']}")
    else:
        print("Nothing needs attention.")


TS = re.compile(r"^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\]\s?(.*)$")


def log_files():
    """every log RainbowOMMA writes: $RAINBOW_HOME/logs, and an agent's own `log` when browsers.json puts it elsewhere"""
    root = Path(os.path.expanduser(os.environ.get("RAINBOW_HOME") or str(Path.home() / ".rainbowomma")))
    files = sorted((root / "logs").glob("*.log")) if (root / "logs").is_dir() else []
    try:
        reg = json.loads(Path(os.environ.get("BROWSER_OWNER_REGISTRY") or HERE / "browsers.json").read_text(encoding="utf-8"))
        for row in (reg.get("agents") or {}).values():
            if isinstance(row, dict) and isinstance(row.get("log"), str):
                f = Path(os.path.expanduser(row["log"]))
                if f.is_file() and f not in files:
                    files.append(f)
    except (OSError, ValueError, AttributeError):
        pass
    return files


def merged_logs(since="", n=200):
    """→ [(time, file, line)] from every log, oldest first: "[YYYY-mm-dd HH:MM:SS] …" lines and JSON lines with "at";
    a line without a time (an old job's stdout) can't be placed, and is counted, not shown"""
    got, untimed = [], 0
    for f in log_files():
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for ln in lines:
            m = TS.match(ln)
            if m:
                when, text = m.group(1).replace(" ", "T"), m.group(2)
            elif ln.startswith("{"):
                try:
                    d = json.loads(ln)
                    when, text = str(d.get("at") or "")[:19], ln
                except ValueError:
                    when = ""
            else:
                when = ""
            if not when:
                untimed += bool(ln.strip())
                continue
            if when >= since:
                got.append((when, f.name, text))
    got.sort(key=lambda x: x[0])
    return got[-n:] if n else got, untimed


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["status"]:                   # rainbowomma-doctor status [--json]: the running system on one screen
        sys.path.insert(0, str(HERE))
        st = status()
        if "--json" in argv:
            print(json.dumps({"status": "attention" if st["problems"] else "ok", **st}, ensure_ascii=False))
        else:
            print_status(st)
        return 1 if st["problems"] else 0
    if argv[:1] == ["logs"]:                     # rainbowomma-doctor logs [--since 2026-11-01] [-n 200]
        lp = argparse.ArgumentParser(prog="rainbowomma-doctor logs")
        lp.add_argument("--since", default=""); lp.add_argument("-n", type=int, default=200)
        la = lp.parse_args(argv[1:])
        rows, untimed = merged_logs(la.since.replace(" ", "T"), la.n)
        for when, name, text in rows:
            print(f"{when}  {name}  {text}")
        if untimed:
            print(f"({untimed} lines without a time were left out)")
        return 0
    ap = argparse.ArgumentParser(prog="rainbowomma-doctor")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    checks = run_checks()
    bad = [c for c in checks if c["needed"] and not c["ok"]]
    if a.json:
        print(json.dumps({"status": "problems" if bad else "ok", "checks": checks}, ensure_ascii=False))
    else:
        for c in checks:
            mark = "✓" if c["ok"] else ("✗" if c["needed"] else "–")
            line = f"{mark} {c['check']}" + (f" — {c['detail']}" if c["detail"] else "")
            print(line + (f"\n    → {c['fix']}" if c["fix"] else ""))
        print(t("dr.summary_bad", n=len(bad)) if bad else t("dr.summary_ok"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.realpath(__file__))); __import__("rainbow_help").handle(__file__)   # --help: one shape, never acts
    sys.exit(main())
