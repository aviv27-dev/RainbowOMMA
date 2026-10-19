#!/usr/bin/env python3
"""agent-office / office-owner — the ONE owner of the shared Office/PDF apps an AI agent touches.

    office-owner open|close|renew --agent NAME <file> · office-owner pdf --agent NAME <file.docx> [--out file.pdf] [--force]
    office-owner sweep [--max-age-h 3] [--dry-run] · office-owner list · office-owner apps

A document is closed only if the agent leased it, nobody had it open before, and the app says it is saved (checked in the
same AppleScript that closes it). `pdf` converts through the real Word, on a uniquely named temp copy closed by name, so
parallel conversions never touch the human's documents. An app is quit only if office-owner itself launched it, after
10 idle minutes with no documents open — an app that was already running is the human's and is never quit.
Exit codes: 0 done · 3 left open · 1 failure.
"""
from __future__ import annotations

import argparse
import fcntl
import shutil
import json
import tempfile
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # -I drops the script's folder; the message catalog lives beside it
from rainbow_i18n import t  # noqa: E402

ROOT = Path(os.path.expanduser(os.environ.get("RAINBOW_HOME") or str(Path.home() / ".rainbowomma")))   # logs, state, work folder
LEASES = ROOT / "state" / "doc_leases"
LOG = ROOT / "logs" / "agent-office.log"
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
APPS_STATE = LEASES.parent / "office_apps.json"     # app → {launchedBy, pid, launchedAt, lastActivity}
INFLIGHT = LEASES.parent / "office_inflight"         # one file per running conversion: {app, pid}
IDLE_QUIT_S = 600
PDF_TIMEOUT_S = 100
WORD_DIR = Path(os.environ.get("OFFICE_WORD_DIR") or (ROOT / "word-convert"))
APP_BIN = {"word": "/Microsoft Word.app/Contents/MacOS/", "excel": "/Microsoft Excel.app/Contents/MacOS/",
           "acrobat": "/Adobe Acrobat.app/Contents/MacOS/", "preview": "/Preview.app/Contents/MacOS/"}
PGREP = None   # tests replace it: (app) -> pid | None


def log(msg):
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except OSError:
        pass


def osa(script, timeout=None):
    """→ (code, stdout) — or, on a failure, (code, the reason osascript gave); a hang (a dialog, a permission prompt) is a
    failure, never an answer"""
    if RUN:
        return RUN(script)
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout or TIMEOUT_S)
        if r.returncode:                       # the reason is on stderr (e.g. "Microsoft Word got an error: …") — say it
            return r.returncode, ((r.stderr or "").strip() or (r.stdout or "").strip())
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
        return 1, {"status": "failed", "why": t("ao.no_file", path=p)}
    app = app or EXT_APP.get(p.suffix.lower())
    if app not in APPS:
        return 1, {"status": "failed", "why": t("ao.bad_app")}
    was = app_pid(app)                       # running before we open → the human's; recorded only once the open worked
    before = open_paths(app)
    shared = before is None or any(x in before for x in forms(path))
    if not RUN:
        r = subprocess.run(["open", "-g", "-a", APPS[app][0], str(p)], capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return 1, {"status": "failed", "why": (r.stderr or "open failed").strip()[:200]}
    note_use(app, "office-owner/" + agent, was)
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
        return 1, {"status": "failed", "why": t("ao.no_lease")}
    results = [_close_lease(d, "by agent") for d in ds]
    res = next((r for r in results if r not in ("closed", "gone")), results[-1])     # one left open → say so
    return (0 if res in ("closed", "gone") else 3), {"status": res, **({"results": results} if len(results) > 1 else {})}


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


# ── office-owner: who launched each app, Word→PDF, quitting what the owner launched ──────────────────────────────────────────
def app_pid(app):
    """the app's main process id, or None"""
    if PGREP:
        return PGREP(app)
    try:
        out = subprocess.run(["pgrep", "-f", APP_BIN[app]], capture_output=True, text=True, timeout=5).stdout.split()
        return int(out[0]) if out else None
    except Exception:
        return None


def apps_state():
    try:
        return json.loads(APPS_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_apps_state(st):
    APPS_STATE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".office_apps.", suffix=".tmp", dir=str(APPS_STATE.parent))
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(st, ensure_ascii=False, indent=1))
    os.replace(tmp, APPS_STATE)


_UNSET = object()
CLAIM_S = 300      # a record with no pid may adopt the app's pid only this soon after the owner's own launch


def note_use(app, by, was=_UNSET):
    """was: the app's pid before the owner launched anything (None = not running) — by default, read now"""
    st = apps_state()
    rec = st.get(app) or {}
    pid = app_pid(app)
    if (pid if was is _UNSET else was) is None:
        rec = {"launchedBy": by, "launchedAt": time.time(), "pid": pid}
    elif not rec or (rec.get("pid") and rec["pid"] != pid):
        rec = {"launchedBy": "human", "seenAt": time.time(), "pid": pid}
    rec["lastActivity"] = time.time()
    st[app] = rec
    save_apps_state(st)
    return rec


def claimable(rec):
    return time.time() - float(rec.get("launchedAt") or 0) < CLAIM_S


def touch(app):
    st = apps_state()
    rec = st.get(app)
    if rec is None:
        return
    rec["lastActivity"] = time.time()
    if rec.get("pid") is None and rec.get("launchedBy") != "human" and claimable(rec):
        rec["pid"] = app_pid(app)
    st[app] = rec
    save_apps_state(st)


class inflight:
    """one file per running conversion — the sweep never quits an app with work in flight (dead pids are ignored)"""

    def __init__(self, app):
        self.app = app

    def __enter__(self):
        INFLIGHT.mkdir(parents=True, exist_ok=True)
        self.f = INFLIGHT / f"{os.getpid()}-{uuid.uuid4().hex[:8]}.json"
        self.f.write_text(json.dumps({"app": self.app, "pid": os.getpid(), "at": time.time()}), encoding="utf-8")
        return self

    def __exit__(self, *exc):
        try:
            self.f.unlink()
        except OSError:
            pass


def inflight_for(app):
    n = 0
    for f in INFLIGHT.glob("*.json") if INFLIGHT.exists() else []:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            os.kill(int(d["pid"]), 0)
            n += d.get("app") == app
        except (OSError, ValueError, KeyError):
            try:
                f.unlink()                 # a dead converter's record
            except OSError:
                pass
    return n


def cmd_pdf(agent, src, out=None, force=False):
    p = Path(norm(src))
    if not p.exists():
        return 1, {"status": "failed", "why": t("ao.no_file", path=p)}
    ext = p.suffix.lower()
    if ext not in (".doc", ".docx", ".rtf"):
        return 1, {"status": "failed", "why": t("ao.pdf_types")}
    dest = Path(norm(out)) if out else p.with_suffix(".pdf")
    if dest.suffix.lower() != ".pdf" or dest.resolve() == p.resolve():
        return 1, {"status": "failed", "why": t("ao.pdf_out")}
    if dest.exists() and not force:          # never silently replace a PDF someone already has
        return 1, {"status": "failed", "why": t("ao.pdf_exists", path=dest)}
    WORD_DIR.mkdir(parents=True, exist_ok=True)
    base = "ofc-pdf-" + uuid.uuid4().hex[:12]
    tmp, tmp_pdf = WORD_DIR / (base + ext), WORD_DIR / (base + ".pdf")
    shutil.copy2(p, tmp)
    with leases_lock():
        note_use("word", "office-owner/" + agent)
    names = [tmp.name, tmp_pdf.name]
    close_mine = (f'repeat with x in (documents as list)\ntry\nset n to name of x\nif n is {q(names[0])} or n is {q(names[1])} '
                  f'then close x saving no\nend try\nend repeat')
    script = (f'with timeout of {PDF_TIMEOUT_S - 10} seconds\ntell application "Microsoft Word"\nlaunch\nopen (POSIX file {q(str(tmp))})\n'
              f'set d to document {q(tmp.name)}\nsave as d file name {q(str(tmp_pdf))} file format format PDF\n{close_mine}\n'
              f'end tell\nend timeout')
    try:
        with inflight("word"):
            code, msg = osa(script, PDF_TIMEOUT_S)
            ok = tmp_pdf.exists() and tmp_pdf.stat().st_size > 0
            if not ok:
                osa(f'with timeout of 15 seconds\ntell application "Microsoft Word"\n{close_mine}\nend tell\nend timeout')
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
    with leases_lock():
        touch("word")
    if not ok:
        try:
            tmp_pdf.unlink()
        except OSError:
            pass
        log(f"pdf FAILED {agent} {p} ({msg[:120]})")
        return 1, {"status": "failed", "why": t("ao.pdf_failed", detail=msg.strip()[:160] or f"exit {code}")}
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(tmp_pdf), str(dest))
    log(f"pdf {agent} {p} -> {dest}")
    return 0, {"status": "converted", "pdf": str(dest), "renderer": "Microsoft Word"}


def idle_quit(dry=False):
    """quit an app ONLY if the owner launched it (the same process), idle ≥ 10 min, no lease or conversion on it, no documents"""
    out, st = [], apps_state()
    for app, rec in list(st.items()):
        pid = app_pid(app)
        if pid is None:
            st.pop(app, None)                      # not running any more — forget it
            continue
        if rec.get("launchedBy") == "human" or (rec.get("pid") and rec["pid"] != pid):
            if rec.get("pid") and rec["pid"] != pid:
                st[app] = {"launchedBy": "human", "seenAt": time.time(), "pid": pid}
            continue
        if rec.get("pid") is None:
            if not claimable(rec):                 # no pid of ours was ever seen: whoever runs it now, it is not ours
                st[app] = {"launchedBy": "human", "seenAt": time.time(), "pid": pid}
                continue
            rec["pid"] = pid
        if time.time() - float(rec.get("lastActivity") or 0) < IDLE_QUIT_S:
            continue
        if inflight_for(app) or any(d["app"] == app for d in leases()):
            continue
        if dry:
            out.append({"app": app, "would": "quit if it has no documents"})
            continue
        name, coll = APPS[app][0], APPS[app][1]
        code, res = osa(f'with timeout of 15 seconds\ntell application {q(name)}\nif (count of {coll}) is 0 then\nquit\nreturn "quit"\n'
                        f'end if\nreturn "busy " & (count of {coll})\nend tell\nend timeout')
        res = res.strip() if code == 0 else "unknown"
        if res == "quit":
            st.pop(app, None)
            log(f"quit {app} — launched by {rec.get('launchedBy')}, idle {int((time.time() - float(rec.get('lastActivity') or 0)) / 60)} min, no documents")
        out.append({"app": app, "result": res})
    save_apps_state(st)
    return out


def cmd_sweep(max_age_h=3.0, dry=False):
    now, report = time.time(), []
    ls = leases()
    if not dry:
        ls, dropped = drop_closed(ls)
        report += [{"path": d["path"], "agent": d["agent"], "app": d["app"], "result": "dropped"} for d in dropped]
    for d in ls:
        age_h = (now - float(d.get("openedAt") or now)) / 3600
        if age_h < max_age_h:
            touch(d["app"])                 # a live lease keeps its app "in use"
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
    apps = idle_quit(dry)
    return 0, {"status": "swept", "items": report, "apps": apps}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="agent-office")
    sub = ap.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("open"); o.add_argument("--agent", required=True); o.add_argument("--app"); o.add_argument("file")
    c = sub.add_parser("close"); c.add_argument("--agent", required=True); c.add_argument("file")
    r = sub.add_parser("renew"); r.add_argument("--agent", required=True); r.add_argument("file")
    s = sub.add_parser("sweep"); s.add_argument("--max-age-h", type=float, default=3.0); s.add_argument("--dry-run", action="store_true")
    sub.add_parser("list")
    pd = sub.add_parser("pdf"); pd.add_argument("--agent", required=True); pd.add_argument("--out"); pd.add_argument("--force", action="store_true"); pd.add_argument("file")
    sub.add_parser("apps")
    a = ap.parse_args(argv)
    if a.cmd == "pdf":                      # NOT under the leases lock: conversions run in parallel (each its own copy)
        try:
            code, out = cmd_pdf(a.agent.strip().lower(), a.file, a.out, a.force)
        except Exception as exc:
            code, out = 1, {"status": "failed", "why": f"{type(exc).__name__}: {exc}"[:200]}
        print(json.dumps(out, ensure_ascii=False))
        return code
    try:
        with leases_lock():
            if a.cmd == "apps":
                st = apps_state()
                code, out = 0, {"apps": {k: dict(v, running=app_pid(k) is not None, inflight=inflight_for(k)) for k, v in st.items()}}
            elif a.cmd == "open":
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
