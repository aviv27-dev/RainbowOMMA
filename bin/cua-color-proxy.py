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
import re
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
READ_ONLY = re.compile(r"^(screenshot|take_screenshot|get_\w+|list_\w+|\w+_state|start_session|end_session|set_agent_cursor\w*|zoom)$")
HUMAN_IDLE_S = float(os.environ.get("RAINBOW_HUMAN_IDLE_S") or 5)       # the human touched keyboard/mouse less than this ago → wait
HUMAN_WAIT_S = float(os.environ.get("RAINBOW_HUMAN_WAIT_S") or 30)      # …but never longer than this: then the action goes through
PAUSE_WAIT_S = float(os.environ.get("RAINBOW_PAUSE_WAIT_S") or 60)      # the human paused all agents: hold this long, then answer an error
ROOT = Path(os.path.expanduser(os.environ.get("RAINBOW_HOME") or str(Path.home() / ".rainbowomma")))


def log(msg):
    try:
        p = ROOT / "logs" / "cua-color-proxy.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(p), os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as fh:
            fh.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {' '.join(str(msg).split())}\n")
    except OSError:
        pass


def human_idle_s():
    """seconds since the human last touched the keyboard or mouse (macOS HIDIdleTime), or None when unknown"""
    if os.environ.get("RAINBOW_TEST_IDLE_S"):
        return float(os.environ["RAINBOW_TEST_IDLE_S"])
    if sys.platform != "darwin":
        return None
    try:
        out = subprocess.run(["ioreg", "-c", "IOHIDSystem", "-d", "4"], capture_output=True, text=True, timeout=3).stdout
        m = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', out)
        return int(m.group(1)) / 1e9 if m else None
    except Exception:
        return None


def wait_for_human(name, sleep=time.sleep):
    """a click or keystroke while the human is typing lands in their window: hold it until they pause (at most HUMAN_WAIT_S).
    → seconds waited"""
    if not name or READ_ONLY.search(name):
        return 0.0
    waited = 0.0
    while waited < HUMAN_WAIT_S:
        idle = human_idle_s()
        if idle is None or idle >= HUMAN_IDLE_S:
            break
        step = max(0.25, HUMAN_IDLE_S - idle)
        sleep(step)
        waited += step
    return waited


def paused():
    """the human paused all agents, took over the screen, or is answering an approval dialog"""
    if (ROOT / "state" / "paused.json").exists():
        return True
    try:                                             # an approval dialog is up: the agent must not click it itself
        if time.time() - (ROOT / "state" / "approval-pending.json").stat().st_mtime < 150:
            return True
    except OSError:
        pass
    try:
        d = json.loads((ROOT / "state" / "screen.json").read_text(encoding="utf-8"))
        return d.get("holder") == "human" and float(d.get("until") or 0) > time.time()
    except (OSError, ValueError):
        return False


def held_by_pause(name, sleep=time.sleep):
    """→ True when the action must not run: the human paused all agents and did not resume within PAUSE_WAIT_S"""
    if not name or READ_ONLY.search(name) or not paused():
        return False
    waited = 0.0
    while paused() and waited < PAUSE_WAIT_S:
        sleep(1.0)
        waited += 1.0
    return paused()


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
        self.out_lock = threading.Lock()
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
                    ours = rid in self.waiting
                    if ours:
                        self.replies[rid] = msg
                        self.cv.notify_all()
                if ours:
                    continue            # our own calls never reach the agent
            self._write_out(line)

    def _write_out(self, line):
        with self.out_lock:             # two threads answer the agent: never interleaved
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
        try:
            waited = wait_for_human(name)
            if waited:
                log(f"{self.agent}: {name} waited {waited:.1f}s for the human to pause")
        except Exception:
            pass
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
            msg = self._parse(line)
            try:
                if not isinstance(msg, dict) and line.strip() and paused():
                    log(f"{self.agent}: a message that isn't one request (a batch, or unreadable) held back — the human paused all agents")
                    continue            # what can't be read can't be let through while the human said stop
                if self.refuse_if_paused(msg):
                    continue
                self.before(msg)
            except Exception as exc:                     # a message we can't read still reaches the driver — unless paused
                log(f"{self.agent}: skipped theming for one message — {type(exc).__name__}: {exc}")
                if paused():
                    continue
            self._send_raw(line)
        try:
            self.proc.stdin.close()
        except OSError:
            pass

    def refuse_if_paused(self, msg):
        """the human's stop: an action held past PAUSE_WAIT_S is answered with an error and never reaches the driver"""
        if not isinstance(msg, dict) or msg.get("method") != "tools/call":
            return False
        params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
        if not held_by_pause(str(params.get("name") or "unnamed")):
            return False
        if "id" not in msg:                                  # a notification: nothing to answer, and nothing runs
            log(f"{self.agent}: {params.get('name')} (no id) dropped — the human paused all agents")
            return True
        reply = {"jsonrpc": "2.0", "id": msg["id"], "result": {"isError": True, "content": [
            {"type": "text", "text": "The human paused all agents or took over the screen (RainbowOMMA). Nothing was done. "
                                     "Wait for them to hand it back, or ask them."}]}}
        self._write_out((json.dumps(reply) + "\n").encode())
        log(f"{self.agent}: {params.get('name')} refused — the human paused all agents")
        return True

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
