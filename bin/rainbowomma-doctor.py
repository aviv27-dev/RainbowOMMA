#!/usr/bin/env python3
"""rainbowomma-doctor — is everything RainbowOMMA needs in place on this Mac? Changes nothing.

    rainbowomma-doctor            one line per check: ✓ ok · ✗ needed and missing (with the fix) · – optional and missing
    rainbowomma-doctor --json     the same as one JSON answer

Exit codes: 0 everything needed is in place · 1 something needed is missing.
"""
from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
import json
import os
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


def main(argv=None):
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
    sys.exit(main())
