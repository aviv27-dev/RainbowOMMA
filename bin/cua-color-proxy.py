#!/usr/bin/env python3
"""cua-color-proxy — any MCP agent's Cua Driver cursor in that agent's color.

Sits between an agent and `cua-driver mcp` (MCP over stdio) and passes every message through unchanged. Before the first
action on a session, it starts that session with the agent's cursor theme (com.rainbowomma.cursor.<agent>, built and
installed by tools/cursor-themes/build_cursor_themes.py) and selects the theme on it. The agent's code and prompt are not
involved, so it works the same for Claude Code, OpenClaw, OpenCode, Codex CLI, Cursor, or any other MCP client.

    cua-color-proxy --agent NAME [--theme ID] [--reduced-motion on|auto|off] [--driver PATH] [-- DRIVER ARGS…]

Register it wherever the client would run `cua-driver mcp`, e.g.
    claude mcp add-json --scope user cua-computer-use '{"command":"/Users/you/bin/cua-color-proxy","args":["--agent","alpha"]}'

Sessions (Cua Driver ≥ 0.21): a call without `session` uses the transport's implicit session, which ends after 5 idle
minutes or an explicit end_session; a call with a label uses that named session. Each is themed once — the implicit one
again after a long gap or an end. A label the agent ended is never touched again (start_session would revive it).
Nothing here can break the agent: a theme that fails to apply is logged and the agent's call goes through as it came.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

CUA_APP = "/Applications/CuaDriver.app/Contents/MacOS/cua-driver"
IMPLICIT = None                     # the key for the transport's implicit session
REFRESH_AFTER_S = float(os.environ.get("RAINBOW_CUA_IDLE_S") or 240)    # the driver drops an idle implicit session at 300 s
REPLY_TIMEOUT_S = 10.0
NOT_ACTIONS = {"end_session", "list_sessions", "get_session", "get_session_state"}
ROOT = Path(os.path.expanduser(os.environ.get("RAINBOW_HOME") or str(Path.home() / ".rainbowomma")))


def log(msg):
    try:
        p = ROOT / "logs" / "cua-color-proxy.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except OSError:
        pass


def driver_path(given=None):
    for c in (given, os.environ.get("CUA_DRIVER"), CUA_APP if os.path.exists(CUA_APP) else None, shutil.which("cua-driver")):
        if c:
            return c
    return None


class Proxy:
    def __init__(self, agent, theme, reduced_motion, argv, out=None):
        self.agent, self.theme, self.motion = agent, theme, reduced_motion
        self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0)
        self.out = out or sys.stdout.buffer
        self.ids = (f"rainbowomma-{n}" for n in itertools.count(1))
        self.waiting, self.replies = {}, {}
        self.cv = threading.Condition()
        self.themed = {}                # session key → monotonic time of its last action (themed once)
        self.ended = set()              # labels the agent ended — never revived

    # ── driver → agent ──
    def pump_driver(self):
        for line in iter(self.proc.stdout.readline, b""):
            msg = self._parse(line)
            rid = msg.get("id") if isinstance(msg, dict) else None
            if isinstance(rid, str) and rid.startswith("rainbowomma-") and ("result" in msg or "error" in msg):
                with self.cv:
                    if rid in self.waiting:
                        self.replies[rid] = msg
                        self.cv.notify_all()
                continue                # our own calls never reach the agent
            self.out.write(line if line.endswith(b"\n") else line + b"\n")
            self.out.flush()

    def call(self, name, arguments):
        """one tools/call of our own → its result, or None (logged)"""
        rid = next(self.ids)
        with self.cv:
            self.waiting[rid] = True
        self._send({"jsonrpc": "2.0", "id": rid, "method": "tools/call", "params": {"name": name, "arguments": arguments}})
        with self.cv:
            self.cv.wait_for(lambda: rid in self.replies, timeout=REPLY_TIMEOUT_S)
            self.waiting.pop(rid, None)
            reply = self.replies.pop(rid, None)
        res = (reply or {}).get("result")
        if not isinstance(res, dict) or res.get("isError") or "error" in (reply or {}):
            log(f"{self.agent}: {name} failed — {json.dumps((reply or {}).get('error') or res or 'no answer')[:300]}")
            return None
        return res

    def theme_session(self, label):
        args = {"cursor_theme": {"theme_id": self.theme, "reduced_motion": self.motion}}
        if label is not IMPLICIT:
            args["session"] = label
        res = self.call("start_session", args)
        sid = label
        if res:
            sid = (res.get("structuredContent") or {}).get("session") or sid
            if sid is IMPLICIT:
                try:
                    sid = json.loads(res["content"][0]["text"]).get("session")
                except (KeyError, IndexError, TypeError, ValueError):
                    sid = None
        if sid:
            if self.call("set_agent_cursor_theme", {"session": sid, "theme_id": self.theme, "reduced_motion": self.motion}):
                log(f"{self.agent}: session {sid} wears {self.theme}")

    # ── agent → driver ──
    def before(self, msg):
        if not isinstance(msg, dict) or msg.get("method") != "tools/call":
            return
        params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
        name = params.get("name")
        args = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        label = args.get("session") if isinstance(args.get("session"), str) and args.get("session") else IMPLICIT
        now = time.monotonic()
        if name == "end_session":
            if label is IMPLICIT:
                self.themed.pop(IMPLICIT, None)        # the next implicit session is a new one
            else:
                self.ended.add(label)
                self.themed.pop(label, None)
            return
        if name in NOT_ACTIONS:
            return
        if name == "start_session" and label is not IMPLICIT:
            self.ended.discard(label)                   # the agent revives it itself
            self.themed.pop(label, None)
        if label in self.ended:
            return
        last = self.themed.get(label)
        if last is None or (label is IMPLICIT and now - last > REFRESH_AFTER_S):
            try:
                self.theme_session(label)
            except Exception as exc:                     # never in the agent's way
                log(f"{self.agent}: theming failed — {type(exc).__name__}: {exc}")
        self.themed[label] = now

    def pump_agent(self, stdin):
        for line in iter(stdin.readline, b""):
            try:
                self.before(self._parse(line))
            except Exception as exc:                     # a message we can't read still reaches the driver
                log(f"{self.agent}: skipped theming for one message — {type(exc).__name__}: {exc}")
            self._send_raw(line)
        try:
            self.proc.stdin.close()
        except OSError:
            pass

    def _send(self, msg):
        self._send_raw((json.dumps(msg, separators=(",", ":")) + "\n").encode())

    def _send_raw(self, line):
        try:
            self.proc.stdin.write(line if line.endswith(b"\n") else line + b"\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, ValueError, OSError):
            pass

    @staticmethod
    def _parse(line):
        try:
            return json.loads(line)
        except ValueError:
            return None


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    extra = []
    if "--" in argv:
        i = argv.index("--")
        argv, extra = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser(prog="cua-color-proxy")
    ap.add_argument("--agent", required=True, help="the agent's name in browsers.json")
    ap.add_argument("--theme", help="cursor theme id (default: com.rainbowomma.cursor.<agent>)")
    ap.add_argument("--reduced-motion", default="on", choices=["on", "auto", "off"])
    ap.add_argument("--driver", help="the cua-driver binary (default: $CUA_DRIVER, CuaDriver.app, or cua-driver on PATH)")
    a = ap.parse_args(argv)
    drv = driver_path(a.driver)
    if not drv:
        print("cua-color-proxy: cua-driver not found (install Cua Driver, or pass --driver)", file=sys.stderr)
        return 1
    p = Proxy(a.agent.strip().lower(), a.theme or f"com.rainbowomma.cursor.{a.agent.strip().lower()}", a.reduced_motion,
              [drv, *(extra or ["mcp"])])
    threading.Thread(target=p.pump_agent, args=(sys.stdin.buffer,), daemon=True).start()
    t = threading.Thread(target=p.pump_driver, daemon=True)
    t.start()
    code = p.proc.wait()
    t.join(timeout=5)
    return code


if __name__ == "__main__":
    sys.exit(main())
