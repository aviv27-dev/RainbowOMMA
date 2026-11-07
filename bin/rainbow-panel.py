#!/usr/bin/env python3
"""rainbow-panel — RainbowOMMA's control window: every browser on the shared Mac in one place.

The human's own Chrome and each agent's, with open / close / bring to front, its color and its name, and a form to add an
agent. The actions are the desktop icons' (desk-browser.sh, one line back), the state is browser-owner's, the agents are
browsers.json — changed only through browser-owner's own validation, so a bad row is refused and the file stays as it was.

A standard-library HTTP server on 127.0.0.1 only, with a random key per launch: every /api call must carry it (X-Panel-Key) and
come with the panel's own Host, so no web page in any browser on this Mac can drive it. It exits by itself a minute after the
window stops asking. The window is rainbow-panel.js (a native AppKit window with a web view — no browser profile is opened).

    rainbow-panel.py [--port 8790]        prints {"url": ...} once listening
    rainbow-panel.sh                      what an icon runs: starts this, then opens the window
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from rainbow_i18n import M, direction, lang, t  # noqa: E402

DESK = Path(os.environ.get("RAINBOW_DESK") or HERE / "desk-browser.sh")
HUMAN_CHROME = HERE / "human-chrome.sh"
CHROME_EXE = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
HUMAN_COLOR = "#B0BEC5"                     # the human's default color (browser-owner human-theme, the Dock group)
IDLE_EXIT = 60
_spec = importlib.util.spec_from_file_location("browser_owner", HERE / "browser-owner.py")
bo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bo)

KEY = secrets.token_urlsafe(24)
LAST = [time.time()]
LOCK = threading.Lock()
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
VIEW_KEYS = ("agent", "label", "color", "port", "status", "up", "offByHuman", "offAt", "lastStop", "lastStart", "managedBy")


def human_running(rows):
    """the human's own Chrome: the Chrome executable itself (no helper), no DevTools port or pipe, not headless, and either no
    --user-data-dir or the default personal one — the same rule as human-chrome.sh"""
    personal = str(bo.PERSONAL[0])
    for _pid, _ppid, cmd in rows:
        if not cmd.startswith(CHROME_EXE) or " --type=" in cmd or "--headless" in cmd or "--remote-debugging-" in cmd:
            continue
        if "--user-data-dir=" in cmd and f"--user-data-dir={personal}" not in cmd:
            continue
        return True
    return False


def human():
    """the human's row: their name and color from $RAINBOW_HOME/human.json (as the Dock group shows them), else the defaults"""
    try:
        h = json.loads((bo.SHARED / "human.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        h = {}
    label = str(h.get("label") or "").strip()[:40] or t("bo.human_label")
    return {"label": label, "color": h["color"] if HEX.match(str(h.get("color") or "")) else HUMAN_COLOR}


def texts():
    """the window's words, in the panel's language"""
    return {k[len("panel."):]: t(k) for k in M if k.startswith("panel.")}


def state():
    rows = bo.processes()
    agents = []
    for a in bo.registry().values():
        v = bo.view(a, rows=rows)
        agents.append({k: v.get(k) for k in VIEW_KEYS})
    used = {a["port"] for a in agents}
    return {"human": dict(human(), running=human_running(rows)),
            "agents": agents, "nextPort": next((p for p in range(9222, 9300) if p not in used), None)}


def act(action, who):
    if action not in ("open", "close", "front") or not (who == "human" or bo.NAME_RE.match(who or "")):
        return {"ok": False, "line": t("panel.unknown_action")}
    if action == "front":
        if who == "human":
            r = subprocess.run([str(HUMAN_CHROME)], capture_output=True, text=True, timeout=30)
            return {"ok": r.returncode == 0, "line": t("panel.human_front_ok") if r.returncode == 0 else t("panel.failed")}
        r = subprocess.run([str(HERE / "browser-owner"), "front", who], capture_output=True, text=True, timeout=30)
        return {"ok": r.returncode == 0, "line": t("panel.front_ok") if r.returncode == 0 else t("panel.front_failed")}
    r = subprocess.run(["bash", str(DESK), action, who], capture_output=True, text=True, timeout=120)
    line = ((r.stdout if r.returncode == 0 else r.stderr) or r.stdout or "").strip().splitlines()[-1:] or [t("panel.no_answer")]
    return {"ok": r.returncode == 0, "line": line[0]}


def write_registry(mutate):
    """change browsers.json through browser-owner's own validation: a bad row is refused and the file is left untouched"""
    path = Path(bo.REGISTRY)
    raw = json.loads(path.read_text(encoding="utf-8"))
    mutate(raw["agents"])
    text = json.dumps(raw, ensure_ascii=False, indent=1) + "\n"
    check = path.with_name(f".{path.stem}.panel-check.json")
    check.write_text(text, encoding="utf-8")
    try:
        bo.registry(check)
    finally:
        check.unlink(missing_ok=True)
    bo.atomic_write(path, text)


def set_style(who, color=None, label=None):
    if color is not None and not HEX.match(color):
        return {"ok": False, "line": t("panel.bad_color")}
    if label is not None:
        label = label.strip()[:30]
        if not label:
            return {"ok": False, "line": t("panel.empty_label")}
    if who == "human":
        return {"ok": False, "line": t("panel.human_fixed")}

    def m(agents):
        if who not in agents:
            raise ValueError(t("panel.not_registered"))
        if color:
            agents[who]["color"] = color
        if label:
            agents[who]["label"] = label
    try:
        write_registry(m)
    except Exception as exc:
        return {"ok": False, "line": f"✗ {exc}"[:200]}
    return {"ok": True, "line": t("panel.saved")}


def add_agent(name, label, color):
    name = (name or "").strip().lower()
    if not bo.NAME_RE.match(name) or name == "human" or name.startswith("human-"):
        return {"ok": False, "line": t("panel.bad_name")}
    if not HEX.match(color or ""):
        return {"ok": False, "line": t("panel.bad_color")}
    st = state()
    if not st["nextPort"]:
        return {"ok": False, "line": t("panel.no_port")}

    def m(agents):
        if name in agents:
            raise ValueError(t("panel.exists"))
        agents[name] = {"label": (label or name).strip()[:30] or name, "port": st["nextPort"],
                        "profile": f"~/agents/{name}-profile", "color": color}
    try:
        write_registry(m)
    except Exception as exc:
        return {"ok": False, "line": f"✗ {exc}"[:200]}
    return {"ok": True, "line": t("panel.added", port=st["nextPort"])}


def page():
    """the window's page, in the panel's language and direction"""
    html = (HERE / "rainbow-panel.html").read_text(encoding="utf-8")
    return (html.replace("__LANG__", lang()).replace("__DIR__", direction())
                .replace("/*RAINBOW_TEXT*/null", json.dumps(texts(), ensure_ascii=False).replace("</", "<\\/"))).encode()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _ok(self):
        LAST[0] = time.time()
        host_ok = self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"
        return host_ok and secrets.compare_digest(self.headers.get("X-Panel-Key") or "", KEY)

    def do_GET(self):
        LAST[0] = time.time()
        if self.path.split("?")[0] == "/":
            return self._send(200, page(), "text/html; charset=utf-8")
        if self.path == "/api/state":
            if not self._ok():
                return self._send(403, {"error": "forbidden"})
            try:
                return self._send(200, state())
            except Exception as exc:
                return self._send(500, {"error": f"{type(exc).__name__}: {exc}"[:200]})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._ok():
            return self._send(403, {"error": "forbidden"})
        try:
            b = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 10000)) or b"{}")
        except ValueError:
            return self._send(400, {"error": "bad json"})
        with LOCK:
            if self.path == "/api/act":
                return self._send(200, act(b.get("action"), b.get("who")))
            if self.path == "/api/style":
                return self._send(200, set_style(b.get("who"), b.get("color"), b.get("label")))
            if self.path == "/api/agent":
                return self._send(200, add_agent(b.get("name"), b.get("label"), b.get("color")))
        self._send(404, {"error": "not found"})


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8790)
    a = ap.parse_args(argv)
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    print(json.dumps({"url": f"http://127.0.0.1:{a.port}/#{KEY}", "title": t("panel.title")}, ensure_ascii=False), flush=True)

    def reaper():
        while True:
            time.sleep(5)
            if time.time() - LAST[0] > IDLE_EXIT:
                os._exit(0)
    threading.Thread(target=reaper, daemon=True).start()
    srv.serve_forever()


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.realpath(__file__))); __import__("rainbow_help").handle(__file__)   # --help: one shape, never acts
    sys.exit(main())
