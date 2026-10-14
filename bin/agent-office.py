#!/usr/bin/env python3
"""agent-office — documents an AI agent opens in a SHARED Office/PDF app, and only those.

    agent-office open|close|renew --agent NAME <file> · agent-office sweep [--max-age-h 3] [--dry-run] · agent-office list

A document is closed only if the agent leased it, nobody had it open before, and the app says it is saved (checked in the
same AppleScript that closes it). Apps are never quit. Exit codes: 0 done · 3 left open · 1 failure.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import tempfile
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

LEASES = Path.home() / ".rainbowomma" / "state" / "doc_leases"
LOG = Path.home() / ".rainbowomma" / "logs" / "agent-office.log"
SEP = "␞"          # ␞ — never inside a file path, unlike ", "
APPS = {
    # AppleScript app name · collection · how to read a document's POSIX path · "is it safe to close" · close statement
    "word": ("Microsoft Word", "documents", "POSIX path of (full name of d as text)", "saved of d", "close d saving no"),
    "excel": ("Microsoft Excel", "workbooks", "POSIX path of (full name of d as text)", "saved of d", "close d saving no"),
    "acrobat": ("Adobe Acrobat", "documents", "POSIX path of (file alias of d)", "not (modified of d)", "close d saving no"),
    "preview": ("Preview", "documents", "path of d", "not (modified of d)", "close d saving no"),
}
EXT_APP = {".doc": "word", ".docx": "word", ".rtf": "word", ".xls": "excel", ".xlsx": "excel", ".csv": "excel", ".pdf": "acrobat"}
RUN = None   # tests replace it: (script) -> (code, stdout)
TIMEOUT_S = 20


def log(msg):
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except OSError:
        pass


def osa(script):
    """→ (code, stdout); a hang (a dialog, a permission prompt) is a failure, never an answer"""
    if RUN:
        return RUN(script)
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=TIMEOUT_S)
        return r.returncode, (r.stdout or "").strip()
    except subprocess.TimeoutExpired:
        return 124, ""


def q(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def norm(p):
    try:
        return os.path.realpath(os.path.expanduser(str(p)))
    except Exception:
        return str(p)


def running(app):
    code, out = osa(f'tell application "System Events" to (name of processes) contains {q(APPS[app][0])}')
    if code != 0:
        return None
    return out.strip() == "true"


def open_paths(app):
    """the POSIX paths of every open document · [] = the app is not running · None = could not tell (never "gone")"""
    r = running(app)
    if r is None:
        return None
    if not r:
        return []
    name, coll, path_of, _, _ = APPS[app]
    script = (f'with timeout of {TIMEOUT_S - 5} seconds\ntell application {q(name)}\nset out to {{}}\n'
              f'repeat with d in (every {coll[:-1]})\ntry\nset end of out to ({path_of})\non error\nset end of out to "?"\nend try\nend repeat\n'
              f'set AppleScript\'s text item delimiters to {q(SEP)}\nreturn ((count of out) as text) & {q(SEP)} & (out as text)\nend tell\nend timeout')
    code, out = osa(script)
    if code != 0:
        return None
    n, _, rest = out.partition(SEP)
    if not n.strip().isdigit():
        return None
    paths = rest.split(SEP) if int(n) else []
    if len(paths) != int(n) or any(p in ("?", "missing value", "") for p in paths):
        return None            # one document the app cannot place → the whole list is untrusted
    return sorted({f for p in paths for f in forms(p)})


def forms(path):
    """the spellings one file can have: as given (absolute) and resolved — /var vs /private/var, a symlinked folder"""
    a = os.path.abspath(os.path.expanduser(str(path)))
    return sorted({a, norm(a)})


def close_if_saved(app, paths):
    """ONE AppleScript: find the document at one of these spellings of ONE path; if exactly one and it is saved → close it.
    → closed|unsaved|ambiguous|gone|unknown"""
    r = running(app)
    if r is None:
        return "unknown"
    if not r:
        return "gone"
    name, coll, path_of, saved_expr, close_stmt = APPS[app]
    plist = "{" + ", ".join(q(p) for p in paths) + "}"
    script = (f'with timeout of {TIMEOUT_S - 5} seconds\ntell application {q(name)}\nset hits to {{}}\n'
              f'repeat with d in (every {coll[:-1]})\ntry\nif {plist} contains ({path_of}) then set end of hits to contents of d\nend try\nend repeat\n'
              f'if (count of hits) is 0 then return "gone"\nif (count of hits) > 1 then return "ambiguous"\nset d to item 1 of hits\n'
              f'if not ({saved_expr}) then return "unsaved"\n{close_stmt}\nreturn "closed"\nend tell\nend timeout')
    code, out = osa(script)
    return out.strip() if code == 0 and out.strip() in ("closed", "unsaved", "ambiguous", "gone") else "unknown"


def leases():
    out = []
    for f in sorted(LEASES.glob("*.json")) if LEASES.exists() else []:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            d["_file"] = str(f)
            out.append(d)
        except (OSError, ValueError):
            pass
    return out


def write_lease(d):
    f = Path(d["_file"]) if d.get("_file") else LEASES / f"{d['id']}.json"
    LEASES.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + f.name + ".", suffix=".tmp", dir=str(LEASES))
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({k: v for k, v in d.items() if k != "_file"}, ensure_ascii=False, indent=1))
    os.replace(tmp, f)


class leases_lock:

    def __enter__(self):
        LEASES.mkdir(parents=True, exist_ok=True)
        self.fh = open(LEASES / ".lock", "w")
        fcntl.flock(self.fh, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.fh, fcntl.LOCK_UN)
        self.fh.close()


def reread(d):
    """the lease as it is on disk NOW (None = gone)"""
    try:
        cur = json.loads(Path(d["_file"]).read_text(encoding="utf-8"))
        cur["_file"] = d["_file"]
        return cur
    except (OSError, ValueError):
        return None


def cmd_open(agent, path, app=None):
    p = Path(norm(path))
    if not p.exists():
        return 1, {"status": "failed", "why": f"אין קובץ: {p}"}
    app = app or EXT_APP.get(p.suffix.lower())
    if app not in APPS:
        return 1, {"status": "failed", "why": "אפליקציה לא נתמכת — word / excel / acrobat / preview"}
    before = open_paths(app)
    shared = before is None or any(x in before for x in forms(path))
    if not RUN:
        r = subprocess.run(["open", "-g", "-a", APPS[app][0], str(p)], capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return 1, {"status": "failed", "why": (r.stderr or "open failed").strip()[:200]}
    lease = {"id": uuid.uuid4().hex[:12], "agent": agent, "app": app, "path": str(p), "paths": forms(path), "name": p.name,
             "openedAt": time.time(), "shared": shared}
    write_lease(lease)
    log(f"open {agent} {app} {p}{' (shared — never auto-closed)' if shared else ''}")
    return 0, {"status": "opened", "lease": lease["id"], "shared": shared}


def _close_lease(d, reason):
    if d.get("shared"):
        return "shared"
    res = close_if_saved(d["app"], d.get("paths") or forms(d["path"]))
    if res in ("closed", "gone"):
        os.remove(d["_file"])
        if res == "closed":
            log(f"closed {d['agent']} {d['app']} {d['path']} ({reason})")
    return res


def mine(agent, path):
    fs = set(forms(path))
    return [d for d in leases() if d["agent"] == agent and fs & set(d.get("paths") or forms(d["path"]))]


def cmd_close(agent, path):
    ds = mine(agent, path)
    if not ds:
        return 1, {"status": "failed", "why": "אין חכירה של הסוכן הזה על המסמך הזה (לפי הנתיב המלא) — סוגרים רק מה שהסוכן פתח דרך agent-office"}
    res = [_close_lease(d, "by agent") for d in ds][-1]
    return (0 if res in ("closed", "gone") else 3), {"status": res}


def cmd_renew(agent, path):
    ds = mine(agent, path)
    for d in ds:
        d["openedAt"] = time.time()
        d.pop("warned", None)
        write_lease(d)
    return (0 if ds else 1), {"status": "renewed" if ds else "no-lease", "count": len(ds)}


def drop_closed(ls):
    kept, dropped, cache = [], [], {}
    for d in ls:
        app = d["app"]
        if time.time() - float(d.get("openedAt") or 0) < FRESH_S:
            kept.append(d)
            continue
        if app not in cache:
            cache[app] = open_paths(app)
        now_open = cache[app]
        if now_open is not None and not (set(d.get("paths") or forms(d["path"])) & set(now_open)):
            try:
                os.remove(d["_file"])
            except OSError:
                pass
            dropped.append(d)
            log(f"lease dropped — no longer open: {d['agent']} {d['app']} {d['path']}")
        else:
            kept.append(d)
    return kept, dropped


FRESH_S = 120


def cmd_sweep(max_age_h=3.0, dry=False):
    now, report = time.time(), []
    ls = leases()
    if not dry:
        ls, dropped = drop_closed(ls)
        report += [{"path": d["path"], "agent": d["agent"], "app": d["app"], "result": "dropped"} for d in dropped]
    for d in ls:
        age_h = (now - float(d.get("openedAt") or now)) / 3600
        if age_h < max_age_h:
            continue
        if dry:
            report.append({"path": d["path"], "agent": d["agent"], "app": d["app"], "ageH": round(age_h, 1), "would": "check"})
            continue
        d = reread(d)
        if not d or (now - float(d.get("openedAt") or now)) / 3600 < max_age_h:
            continue
        res = _close_lease(d, f"sweep, {age_h:.1f}h")
        if res in ("unsaved", "unknown", "ambiguous") and not d.get("warned"):
            d["warned"] = now
            write_lease(d)
            log(f"left open — {res}: {d['agent']} {d['app']} {d['path']} ({age_h:.1f}h)")
        report.append({"path": d["path"], "agent": d["agent"], "app": d["app"], "ageH": round(age_h, 1), "result": res})
    return 0, {"status": "swept", "items": report}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="agent-office")
    sub = ap.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("open"); o.add_argument("--agent", required=True); o.add_argument("--app"); o.add_argument("file")
    c = sub.add_parser("close"); c.add_argument("--agent", required=True); c.add_argument("file")
    r = sub.add_parser("renew"); r.add_argument("--agent", required=True); r.add_argument("file")
    s = sub.add_parser("sweep"); s.add_argument("--max-age-h", type=float, default=3.0); s.add_argument("--dry-run", action="store_true")
    sub.add_parser("list")
    a = ap.parse_args(argv)
    try:
        with leases_lock():
            if a.cmd == "open":
                code, out = cmd_open(a.agent.strip().lower(), a.file, a.app)
            elif a.cmd == "close":
                code, out = cmd_close(a.agent.strip().lower(), a.file)
            elif a.cmd == "renew":
                code, out = cmd_renew(a.agent.strip().lower(), a.file)
            elif a.cmd == "sweep":
                code, out = cmd_sweep(a.max_age_h, a.dry_run)
            else:
                code, out = 0, {"leases": [{k: v for k, v in d.items() if k != "_file"} for d in leases()]}
    except Exception as exc:
        code, out = 1, {"status": "failed", "why": f"{type(exc).__name__}: {exc}"[:200]}
    print(json.dumps(out, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
