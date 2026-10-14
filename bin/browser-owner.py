#!/usr/bin/env python3
"""browser-owner — the ONE owner of every agent's Chrome on a shared Mac.

    browser-owner list | names | status AGENT | start AGENT [--by WHO] | stop AGENT --by human [--allow-reopen]
    browser-owner idle-stop AGENT --by WHO | recover AGENT [--by WHO] | human-theme

Agents are rows in browsers.json beside this file. See docs/DESIGN.md for every status word and rule.
Exit codes: 0 ok · 2 refused · 1 failure. One JSON answer, always.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HOME = Path.home()
HERE = Path(__file__).resolve().parent
REGISTRY = Path(os.environ.get("BROWSER_OWNER_REGISTRY") or HERE / "browsers.json")
SHARED = HOME / ".rainbowomma"
CHROME_APP = "/Applications/Google Chrome.app"
CHROME_BIN = "Google Chrome.app/Contents/MacOS/Google Chrome"
STALE_FLAG_AFTER = 120
NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,30}$")


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def expand(p):
    return str(Path(os.path.expanduser(str(p))))


PERSONAL = [HOME / "Library" / "Application Support" / n for n in
            ("Google/Chrome", "Google/Chrome Beta", "Google/Chrome Canary", "Chromium", "BraveSoftware")]


def canon(p):
    return os.path.realpath(expand(p))


def registry(path=None):
    raw = json.loads(Path(path or REGISTRY).read_text(encoding="utf-8"))["agents"]
    out, ports, profiles, states = {}, {}, {}, {}
    for name, r in raw.items():
        if not NAME_RE.match(name):
            raise ValueError(f"bad agent name: {name!r}")
        miss = [k for k in ("label", "port", "profile", "color") if not r.get(k)]
        if miss:
            raise ValueError(f"{name}: missing {', '.join(miss)}")
        port = int(r["port"])
        if not 9222 <= port <= 9299:
            raise ValueError(f"{name}: port {port} outside 9222–9299")
        if port in ports:
            raise ValueError(f"{name}: port {port} already belongs to {ports[port]}")
        ports[port] = name
        if not re.match(r"^#[0-9A-Fa-f]{6}$", r.get("color", "")):
            raise ValueError(f"{name}: color must be #RRGGBB")
        a = dict(r, name=name, port=port, profile=canon(r["profile"]))
        if " " in a["profile"]:
            raise ValueError(f"{name}: profile path must not contain spaces (process matching splits on them)")
        if any(a["profile"] == os.path.realpath(str(pp)) or a["profile"].startswith(os.path.realpath(str(pp)) + os.sep) for pp in PERSONAL):
            raise ValueError(f"{name}: {a['profile']} is a personal Chrome profile — never an agent's")
        if a["profile"] in profiles:
            raise ValueError(f"{name}: profile already belongs to {profiles[a['profile']]}")
        profiles[a["profile"]] = name
        a["state"] = canon(r.get("state") or SHARED / "browsers" / f"{name}.json")
        if a["state"] in states:
            raise ValueError(f"{name}: state file already belongs to {states[a['state']]}")
        states[a["state"]] = name
        a["log"] = expand(r.get("log") or SHARED / "logs" / "browser-owner.log")
        a["lock"] = str(Path(a["state"]).with_suffix(".lock"))
        if r.get("launcher"):
            a["launcher"] = expand(r["launcher"])
        if r.get("managedBy"):
            a["managedBy"] = expand(r["managedBy"])
        if r.get("idleMinutes") is not None:
            a["idleMinutes"] = int(r["idleMinutes"])
        a["port_re"] = re.compile(rf"(?:^|\s)--remote-debugging-port={port}(?:\s|$)")
        a["dir_re"] = re.compile(r"(?:^|\s)--user-data-dir=" + re.escape(a["profile"]) + r"(?:\s|$)")
        out[name] = a
    return out


def log(a, msg):
    try:
        p = Path(a["log"])
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {a['name']}: {msg}\n")
    except OSError:
        pass


def load(a):
    try:
        return json.loads(Path(a["state"]).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save(a, st):
    atomic_write(a["state"], json.dumps(st, ensure_ascii=False, indent=1))


def healthy(a, timeout=2.0):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{a['port']}/json/version", timeout=timeout) as r:
            json.loads(r.read())
        return True
    except Exception:
        return False


def processes():
    out = subprocess.run(["ps", "-axo", "pid=,ppid=,command="], capture_output=True, text=True, check=True).stdout
    rows = []
    for line in out.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) == 3:
            try:
                rows.append((int(parts[0]), int(parts[1]), parts[2]))
            except ValueError:
                pass
    return rows


def is_root(a, cmd):
    return CHROME_BIN in cmd and " --type=" not in cmd and bool(a["port_re"].search(cmd)) and bool(a["dir_re"].search(cmd))


def profile_users(a, rows):
    return [pid for pid, _, cmd in rows if CHROME_BIN in cmd and " --type=" not in cmd and a["dir_re"].search(cmd) and not a["port_re"].search(cmd)]


def listener(a):
    """who LISTENS on the agent's port (lsof) — named when the port answers and it is not the agent's browser"""
    try:
        out = subprocess.run(["lsof", "-nP", f"-iTCP:{a['port']}", "-sTCP:LISTEN", "-Fpc"], capture_output=True, text=True, timeout=5).stdout
        pid = next((l[1:] for l in out.splitlines() if l.startswith("p")), "")
        cmd = next((l[1:] for l in out.splitlines() if l.startswith("c")), "")
        return f"{cmd} (pid {pid})" if pid else ""
    except Exception:
        return ""


def foreign_roots(a, rows):
    """Chromes on this agent's port with ANOTHER profile — someone launched a browser outside the owner"""
    return [pid for pid, _, cmd in rows if CHROME_BIN in cmd and " --type=" not in cmd and a["port_re"].search(cmd) and not a["dir_re"].search(cmd)]


def tree_of(a, rows):
    roots = [pid for pid, _, cmd in rows if is_root(a, cmd)]
    tree = set(roots)
    changed = True
    while changed:
        changed = False
        for pid, ppid, _ in rows:
            if ppid in tree and pid not in tree:
                tree.add(pid)
                changed = True
    return roots, tree


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def terminate_tree(tree, grace=8.0):
    for pid in sorted(tree, reverse=True):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    deadline = time.time() + grace
    while time.time() < deadline and any(alive(p) for p in tree):
        time.sleep(0.25)
    left = [p for p in tree if alive(p)]
    for pid in left:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    return left


def really_down(a, probes=3, timeout=10.0, spread=30.0):
    for i in range(probes):
        if healthy(a, timeout=timeout):
            return False
        if i < probes - 1:
            time.sleep(spread / (probes - 1))
    return True


def last_exit_type(a):
    try:
        return (json.loads((Path(a["profile"]) / "Default" / "Preferences").read_text(encoding="utf-8")).get("profile") or {}).get("exit_type")
    except (OSError, ValueError):
        return None


CLEAN_QUIT_HOLD = 2 * 3600


def boot_time():
    try:
        out = subprocess.run(["sysctl", "-n", "kern.boottime"], capture_output=True, text=True, timeout=5).stdout
        return float(re.search(r"sec = (\d+)", out).group(1))
    except Exception:
        return None


def quit_by_person(a, now=None, st=None):
    now = now or time.time()
    if last_exit_type(a) != "Normal":
        return False
    try:
        m = (Path(a["profile"]) / "Default" / "Preferences").stat().st_mtime
    except OSError:
        return False
    b = boot_time()
    if b is None or m < b or now - m > CLEAN_QUIT_HOLD:
        return False
    # a close the OWNER made (stop / idle-stop / a theme install) also leaves "Normal" — that is not a person's ⌘Q
    ls = (st or load(a)).get("lastStop") or {}
    try:
        stopped = time.mktime(time.strptime(str(ls.get("at", ""))[:19], "%Y-%m-%dT%H:%M:%S"))
    except ValueError:
        stopped = 0
    return not (stopped and -5 <= m - stopped <= 180)


def chrome_color(hex_rgb):
    """#RRGGBB → the signed 32-bit ARGB integer Chrome stores (opaque)"""
    v = 0xFF000000 | int(hex_rgb[1:], 16)
    return v - (1 << 32) if v >= (1 << 31) else v


def display_name(a):
    return f"{a['label']} — סוכן · לא לגעת"


def paint(a, themed=False):
    """Write the profile's name and color into Chrome's own files — ONLY while the browser is down (Chrome rewrites them on exit).
    Merges into what is there; a file Chrome left unreadable is left alone (never replaced with a blank one).
    → list of the files changed"""
    prof = Path(a["profile"])
    color, name, changed = chrome_color(a["color"]), display_name(a), []

    def merge(path, fn):
        path = Path(path)
        st0 = None
        if path.exists():
            try:
                st0 = path.stat()
                d = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return
        else:
            d = {}
        before = json.dumps(d, sort_keys=True)
        fn(d)
        if json.dumps(d, sort_keys=True) != before:
            atomic_write(path, json.dumps(d, ensure_ascii=False))
            if st0:
                os.utime(path, (st0.st_atime, st0.st_mtime))
            changed.append(str(path))

    def prefs(d):
        d.setdefault("profile", {})["name"] = name
        if themed:
            return                 # the installed theme paints the frame — the profile color must not replace it
        th = d.setdefault("browser", {}).setdefault("theme", {})
        th.update({"user_color": color, "user_color2": color, "color_variant": 1, "color_variant2": 1, "is_grayscale": False})
        d.setdefault("extensions", {}).setdefault("theme", {})["id"] = "user_color_theme_id"
        av = d.get("account_values", {}).get("browser", {}).get("theme")
        if isinstance(av, dict):
            av.update({"user_color": color, "user_color2": color})

    def local_state(d):
        ic = d.setdefault("profile", {}).setdefault("info_cache", {}).setdefault("Default", {})
        ic.update({"name": name, "is_using_default_name": False, "profile_highlight_color": color,
                   "default_avatar_fill_color": color, "default_avatar_stroke_color": color})

    merge(prof / "Default" / "Preferences", prefs)
    merge(prof / "Local State", local_state)
    return changed


THEMES = SHARED / "themes"
THEME_VERSION = "2"            # bump to rebuild every agent's theme (2: the name only on the free left part of the frame)
FRAME_JS = HERE / "theme-frame.js"


def rgb(hex_rgb):
    v = int(hex_rgb[1:], 16)
    return [(v >> 16) & 255, (v >> 8) & 255, v & 255]


def theme_key(a):
    return f"{THEME_VERSION}:{a['color'].upper()}:{a['label']}"


def build_theme(a, text=None, title=None):
    base = rgb(a["color"])
    light = (0.299 * base[0] + 0.587 * base[1] + 0.114 * base[2]) / 255 > 0.65
    frame = base if light else [int(c * 0.82) for c in base]
    inactive = [int(c * 0.9) for c in base] if light else [int(c * 0.7) for c in base]
    tint = [int(c + (255 - c) * 0.78) for c in base]
    ink = [int(c * 0.35) for c in base]
    d = THEMES / a["name"]
    d.mkdir(parents=True, exist_ok=True)
    manifest = {"manifest_version": 3, "name": title or f"סוכן: {a['label']}", "version": f"{THEME_VERSION}.{int(time.time()) % 100000}",
                "description": "browser-owner — the agent's browser theme (RainbowOMMA)",
                "theme": {"images": {}, "colors": {
                    "frame": frame, "frame_inactive": inactive, "frame_incognito": frame, "toolbar": tint,
                    "tab_text": ink, "tab_background_text": ink if light else [255, 255, 255],
                    "tab_background_text_inactive": ink if light else [235, 235, 235],
                    "bookmark_text": ink, "toolbar_button_icon": ink, "omnibox_background": [255, 255, 255], "omnibox_text": [20, 20, 20],
                    "ntp_background": tint, "ntp_text": ink}}}
    try:
        r = subprocess.run(["osascript", "-l", "JavaScript", str(FRAME_JS), str(d / "frame.png"), text or f"{a['label']} · סוכן · לא לגעת",
                            *map(str, frame), "dark" if light else "light"],
                           capture_output=True, text=True, timeout=30)
        if r.returncode == 0 and (d / "frame.png").exists():
            manifest["theme"]["images"] = {"theme_frame": "frame.png", "theme_frame_inactive": "frame.png"}
    except Exception:
        pass                       # a theme without the written name is still a solid color
    atomic_write(d / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1))
    return d


def theme_saved(a):
    """the theme extension Chrome has recorded as the profile's theme (a real extension id, not the built-in user color)"""
    try:
        d = json.loads((Path(a["profile"]) / "Default" / "Preferences").read_text(encoding="utf-8"))
        tid = (d.get("extensions", {}).get("theme") or {}).get("id") or ""
        return tid if re.fullmatch(r"[a-p]{32}", tid) else ""
    except (OSError, ValueError):
        return ""


def install_theme(a, folder, timeout=25.0):
    """Chrome with NO window on the agent's profile, a DevTools pipe, Extensions.loadUnpacked → the theme's id, then that instance
    (our own child, nothing else) is closed. → (ok, id_or_reason)"""
    r1, w1 = os.pipe(); r2, w2 = os.pipe()
    r1, w1, r2, w2 = [os.dup(x) for x in (r1, w1, r2, w2)]    # above 3/4, so the dup2 below cannot clobber them

    def child():
        os.dup2(r1, 3); os.dup2(w2, 4); os.setsid()
    chrome = str(Path(CHROME_APP) / "Contents" / "MacOS" / "Google Chrome")
    p = subprocess.Popen([chrome, f"--user-data-dir={a['profile']}", "--remote-debugging-pipe", "--enable-unsafe-extension-debugging",
                          "--no-startup-window", "--no-first-run", "--no-default-browser-check"],
                         preexec_fn=child, close_fds=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.close(r1); os.close(w2)
    ans = b""
    try:
        os.write(w1, (json.dumps({"id": 1, "method": "Extensions.loadUnpacked", "params": {"path": str(folder)}}) + "\0").encode())
        import select
        t0 = time.time()
        while time.time() - t0 < timeout and b"\0" not in ans:
            rd, _, _ = select.select([r2], [], [], 1.0)
            if rd:
                chunk = os.read(r2, 65536)
                if not chunk:
                    break
                ans += chunk
        if b'"result"' in ans:
            t1 = time.time()
            while time.time() - t1 < 10 and not theme_saved(a):
                time.sleep(0.5)
            time.sleep(1.0)
    except OSError as exc:
        ans = json.dumps({"error": {"message": str(exc)}}).encode()
    finally:
        for fd in (w1, r2):
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            p.terminate(); p.wait(timeout=15)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
    try:
        msg = json.loads(ans.split(b"\0")[0].decode() or "{}")
    except ValueError:
        msg = {}
    if msg.get("result", {}).get("id"):
        if theme_saved(a) != msg["result"]["id"]:
            return False, "Chrome loaded the theme but did not save it in the profile"
        return True, msg["result"]["id"]
    return False, (msg.get("error") or {}).get("message") or "no answer from Chrome"


def ensure_theme(a, st):
    """install (or rebuild) the agent's theme when it is missing or its color/name changed — only while its browser is down.
    A failure is recorded and the start goes on with the profile color (never blocks the agent)."""
    if st.get("theme") == theme_key(a):
        return "kept"
    try:
        ok, res = install_theme(a, build_theme(a))
    except Exception as exc:
        ok, res = False, f"{type(exc).__name__}: {exc}"[:160]
    st["lastStop"] = {"at": now_iso(), "by": "theme-install", "pids": 1}
    if ok:
        st.update({"theme": theme_key(a), "themeId": res, "themeAt": now_iso()})
        st.pop("themeError", None)
        log(a, f"theme installed ({a['color']})")
        return "installed"
    st["themeError"] = str(res)[:200]
    log(a, f"theme NOT installed: {res}")
    return "failed"


def chrome_args(a):
    port = a["port"]
    return [f"--user-data-dir={a['profile']}", f"--remote-debugging-port={port}",
            f"--remote-allow-origins=http://127.0.0.1:{port},http://localhost:{port}",
            "--disable-background-timer-throttling", "--disable-renderer-backgrounding", "--disable-backgrounding-occluded-windows",
            "--disable-features=OptimizationGuideOnDeviceModel", "--no-first-run", "--no-default-browser-check",
            "--restore-last-session", "--hide-crash-restore-bubble", f"--window-name={a['label']}-CDP"]


def launch(a):
    if a.get("launcher"):
        if not Path(a["launcher"]).exists():
            return 1, f"המפעיל חסר: {a['launcher']}"
        env = dict(os.environ, **{a.get("launcherEnv") or "BROWSER_OWNER_LAUNCH": "1"})
        r = subprocess.run(["bash", a["launcher"]], capture_output=True, text=True, timeout=60, env=env, start_new_session=True)
        return r.returncode, (r.stdout or r.stderr or "").strip()
    Path(a["profile"]).mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["open", "-g", "-n", "-a", CHROME_APP, "--args", *chrome_args(a)], capture_output=True, text=True,
                       timeout=30, start_new_session=True)
    if r.returncode != 0:
        return r.returncode, (r.stderr or "open failed").strip()
    for _ in range(25):
        if healthy(a):
            return 0, f"CDP up on {a['port']}"
        time.sleep(1)
    return 1, f"Chrome נפתח אבל פורט {a['port']} לא ענה"


FOCUS_NO_PERMISSION = "no-permission"


def front_pid():
    try:
        r = subprocess.run(["osascript", "-e", 'tell application "System Events" to get unix id of first process whose frontmost is true'],
                           capture_output=True, text=True, timeout=5)
        if r.returncode != 0 and "-1743" in (r.stderr or ""):
            return FOCUS_NO_PERMISSION
        return int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip().isdigit() else None
    except Exception:
        return None


def set_front(pid):
    try:
        r = subprocess.run(["osascript", "-e", f'tell application "System Events" to set frontmost of (first process whose unix id is {int(pid)}) to true'],
                           capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def give_focus_back(a, before, wait=4.0):
    if before is None:
        return "unknown"
    if before == FOCUS_NO_PERMISSION:
        return FOCUS_NO_PERMISSION
    deadline = time.time() + wait
    while time.time() < deadline:
        now = front_pid()
        if now in (None, FOCUS_NO_PERMISSION):
            return "unknown" if now is None else FOCUS_NO_PERMISSION
        _, tree = tree_of(a, processes())
        if now in tree and before not in tree:
            return "restored" if set_front(before) and front_pid() == before else "lost"
        if now != before:
            return "user-moved"
        time.sleep(0.5)
    return "kept"


def view(a, st=None, rows=None):
    """the read-only picture of one agent's browser"""
    rows = processes() if rows is None else rows
    st = load(a) if st is None else st
    roots, tree = tree_of(a, rows)
    up = healthy(a)
    foreign = foreign_roots(a, rows)
    busy = profile_users(a, rows)
    if up and not roots:
        status = "blocked"
    elif up:
        status = "up"
    elif busy:
        status = "profile-busy"
    else:
        status = "hung" if roots else "down"
    return {"agent": a["name"], "label": a["label"], "color": a["color"], "port": a["port"], "status": status, "up": status == "up",
            "roots": roots, "processes": len(tree), "foreignRoots": foreign, "profileBusy": busy, "offByHuman": bool(st.get("offByHuman")),
            "offAt": st.get("offAt"), "lastExitType": last_exit_type(a), "lastStart": st.get("lastStart"),
            "lastStop": st.get("lastStop"), "managedBy": a.get("managedBy")}


def reconcile(a, st, v):
    if not st.get("offByHuman") or v["status"] != "up":
        return st
    try:
        off = time.mktime(time.strptime(st.get("offAt", "")[:19], "%Y-%m-%dT%H:%M:%S"))
    except ValueError:
        off = 0
    if time.time() - off < STALE_FLAG_AFTER:
        return st
    st["offByHuman"] = False
    st["reconciledAt"] = now_iso()
    save(a, st)
    log(a, "offByHuman cleared — its browser is up (opened outside the owner)")
    return st


def blocked(v, a=None):
    who = (f"pid {v['foreignRoots']}" if v.get("foreignRoots") else "") or (listener(a) if a else "") or "תהליך לא מזוהה"
    return 1, {"status": "blocked", "why": f"פורט {v['port']} עונה, אבל לא מהדפדפן של {v['label']} ({who}); לא נוגעים. האדם צריך לסגור אותו"}


def profile_busy(v):
    return 1, {"status": "profile-busy", "why": f"הפרופיל של {v['label']} פתוח ב-Chrome אחר בלי פורט השליטה (pid {v['profileBusy']}) — "
               f"לא צובעים ולא פותחים; האדם צריך לסגור אותו"}


def do_start(a, by):
    st = load(a)
    v = view(a, st)
    if v["status"] == "blocked":
        return blocked(v, a)
    if v["status"] == "profile-busy":
        return profile_busy(v)
    st = reconcile(a, st, v)
    if st.get("offByHuman") and by != "human":
        return 2, {"status": "refused", "why": f"האדם סגר את הדפדפן של {a['label']} ב-{st.get('offAt')} — נפתח רק כשהאדם פותח"}
    if by == "human" and st.get("offByHuman"):
        st["offByHuman"] = False
        save(a, st)
    if v["status"] == "up":
        return 0, {"status": "already-up"}
    if v["status"] == "hung":
        return 1, {"status": "hung", "why": f"Chrome של {a['label']} רץ (pid {v['roots']}) אבל לא עונה — recover, לא start"}
    if by != "human" and quit_by_person(a, st=st):
        return 2, {"status": "closed-by-person", "why": f"הדפדפן של {a['label']} נסגר ביציאה רגילה (⌘Q) בשעתיים האחרונות — לא נפתח אוטומטית; "
                   "האדם פותח, או שהסוכן מבקש זאת"}
    theme = ensure_theme(a, st) if not a.get("noTheme") else "off"
    painted = paint(a, themed=theme in ("installed", "kept"))
    before = front_pid() if by != "human" else None
    rc, text = launch(a)
    ok = rc == 0 and healthy(a, timeout=5)
    focus = give_focus_back(a, before) if ok and by != "human" else "human"
    st["lastStart"] = {"at": now_iso(), "by": by, "ok": ok, "out": text[:200], "painted": len(painted), "focus": focus, "theme": theme}
    save(a, st)
    log(a, f"start by {by}: {'ok' if ok else 'FAILED'} {text[:200]}")
    return (0 if ok else 1), {"status": "started" if ok else "failed", "detail": text[:200]}


def do_stop(a, by, allow_reopen=False):
    if by != "human":
        return 2, {"status": "refused", "why": f"רק האדם סוגר את הדפדפן של {a['label']} (stop --by human). סוכן שצריך התאוששות — recover"}
    rows = processes()
    roots, tree = tree_of(a, rows)
    st = load(a)
    st.update({"offByHuman": not allow_reopen, "offAt": None if allow_reopen else now_iso(),
               "lastStop": {"at": now_iso(), "by": by, "pids": len(tree), **({"allowReopen": True} if allow_reopen else {})}})
    save(a, st)
    left = terminate_tree(tree) if tree else []
    log(a, f"stop by {by}: {len(tree)} processes, {len(left)} needed KILL")
    return 0, {"status": "stopped", "processes": len(tree), "killed": len(left)}


def do_idle_stop(a, by):
    if not a.get("idleMinutes"):
        return 2, {"status": "refused", "why": f"לדפדפן של {a['label']} אין סגירה בחוסר פעילות (idleMinutes) — רק האדם סוגר (stop --by human)"}
    rows = processes()
    roots, tree = tree_of(a, rows)
    if not tree:
        return 0, {"status": "not-running"}
    st = load(a)
    st["lastStop"] = {"at": now_iso(), "by": by, "pids": len(tree), "idle": True}
    save(a, st)
    left = terminate_tree(tree)
    log(a, f"idle-stop by {by}: {len(tree)} processes, {len(left)} needed KILL")
    return 0, {"status": "stopped", "processes": len(tree), "killed": len(left), "idle": True}


def do_recover(a, by):
    st = load(a)
    rows = processes()
    v = view(a, st, rows)
    if v["status"] == "blocked":
        return blocked(v, a)
    if v["status"] == "profile-busy":
        return profile_busy(v)
    st = reconcile(a, st, v)
    if st.get("offByHuman") and by != "human":
        return 2, {"status": "refused", "why": f"האדם סגר את הדפדפן של {a['label']} ב-{st.get('offAt')}"}
    if v["status"] == "up":
        return 0, {"status": "healthy"}
    roots, tree = tree_of(a, rows)
    if len(roots) > 1:
        return 1, {"status": "failed", "why": f"יותר משורש אחד של הדפדפן של {a['label']}: {roots} — לא נוגעים"}
    if tree and by != "human":
        if not really_down(a):
            return 0, {"status": "healthy", "why": "ענה בבדיקה החוזרת — לא נסגר"}
        if healthy(a, timeout=5):
            return 0, {"status": "healthy", "why": "ענה ממש לפני הסגירה — לא נסגר"}
    if tree:
        roots2, tree2 = tree_of(a, processes())
        if roots2 != roots:
            return 1, {"status": "failed", "why": f"התהליכים השתנו בזמן הבדיקה ({roots} → {roots2}) — לא סוגרים; לנסות שוב"}
        tree = tree2
    left = terminate_tree(tree) if tree else []
    if tree:
        log(a, f"recover by {by}: closed a hung browser ({len(tree)} processes, {len(left)} KILL)")
        time.sleep(1)
    return do_start(a, by)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="browser-owner")
    ap.add_argument("cmd", choices=["list", "names", "status", "start", "stop", "idle-stop", "recover", "human-theme"])
    ap.add_argument("agent", nargs="?")
    ap.add_argument("--by", default="agent", help="human | keepalive | host | <agent name>")
    ap.add_argument("--allow-reopen", action="store_true", help="stop: the human closes it now, the agents may open it again")
    a = ap.parse_args(argv)
    try:
        reg = registry()
    except Exception as exc:
        print(json.dumps({"status": "failed", "why": f"registry: {type(exc).__name__}: {exc}"[:300]}, ensure_ascii=False))
        return 1
    if a.cmd == "human-theme":
        d = build_theme({"name": "human-human", "label": "האדם", "color": "#B0BEC5"}, text="האדם · HUMAN · ניתן להשתמש", title="האדם · HUMAN")
        print(json.dumps({"status": "built", "folder": str(d)}, ensure_ascii=False))
        return 0
    if a.cmd == "names":
        # plain words for shell callers (kill-chrome --all): the agents this owner may stop — no JSON parsing in bash
        print(" ".join(n for n, x in reg.items() if not x.get("managedBy")))
        return 0
    if a.cmd == "list" or (a.cmd == "status" and not a.agent):
        try:
            rows = processes()
            print(json.dumps({"agents": [view(x, rows=rows) for x in reg.values()]}, ensure_ascii=False))
            return 0
        except Exception as exc:
            print(json.dumps({"status": "failed", "why": f"{type(exc).__name__}: {exc}"[:200]}, ensure_ascii=False))
            return 1
    ag = reg.get((a.agent or "").strip().lower())
    if not ag:
        print(json.dumps({"status": "failed", "why": f"סוכן לא רשום: {a.agent!r} — רשומים: {', '.join(reg)}"}, ensure_ascii=False))
        return 1
    if a.cmd == "status":
        print(json.dumps(view(ag), ensure_ascii=False))
        return 0
    if ag.get("managedBy"):
        print(json.dumps({"status": "refused", "why": f"הדפדפן של {ag['label']} מנוהל על ידי {ag['managedBy']} — כאן רק דיווח"}, ensure_ascii=False))
        return 2
    Path(ag["lock"]).parent.mkdir(parents=True, exist_ok=True)
    with open(ag["lock"], "w") as lk:
        try:
            fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print(json.dumps({"status": "busy", "why": "פעולה אחרת על הדפדפן הזה רצה עכשיו"}, ensure_ascii=False))
            return 1
        fn = {"start": do_start, "stop": do_stop, "idle-stop": do_idle_stop, "recover": do_recover}[a.cmd]
        try:
            code, out = fn(ag, a.by.strip().lower(), a.allow_reopen) if a.cmd == "stop" else fn(ag, a.by.strip().lower())
        except Exception as exc:   # one JSON answer, always
            code, out = 1, {"status": "failed", "why": f"{type(exc).__name__}: {exc}"[:200]}
    print(json.dumps(out, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
