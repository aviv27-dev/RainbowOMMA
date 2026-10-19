#!/usr/bin/env python3
"""rainbowomma-mcp — RainbowOMMA's owners as MCP tools, for any agent that speaks MCP (stdio).

    rainbowomma-mcp --agent NAME          (or RAINBOW_AGENT=NAME in its environment)

Register it once per agent, e.g. for Claude Code:
    claude mcp add-json --scope user rainbowomma '{"command":"/Users/you/bin/rainbowomma-mcp","args":["--agent","alpha"]}'

Every tool runs the same command-line owner an agent could run itself (browser-owner, port-owner, proc-owner) as this
agent, and returns its one JSON answer. A refusal or failure comes back with isError, its status word and its reason.
Standard library only; no SDK.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROTOCOL = "2025-06-18"
TIMEOUT_S = 120

TOOLS = [
    {"name": "lease_port", "description": "Get a free network port of your own (from your range; never the human's 3000/5173/8000/8080). "
                                          "Use it for every server you start: PORT=<port>. The same name gives the same port back.",
     "inputSchema": {"type": "object", "properties": {"name": {"type": "string", "description": "what it is for, e.g. web, api"},
                                                      "prefer": {"type": "integer", "description": "a port of your own range"}}},
     "argv": lambda me, a: ["port-owner", "lease", me, "--name", str(a.get("name") or "default"),
                            *(["--prefer", str(int(a["prefer"]))] if a.get("prefer") is not None else [])]},
    {"name": "release_port", "description": "Give a leased port back (all of yours with all=true).",
     "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "all": {"type": "boolean"}}},
     "argv": lambda me, a: ["port-owner", "release", me, *(["--all"] if a.get("all") else ["--name", str(a.get("name") or "default")])]},
    {"name": "who_port", "description": "Whose a port is (an agent's, or the human's) and what listens on it.",
     "inputSchema": {"type": "object", "properties": {"port": {"type": "integer"}}, "required": ["port"]}, "anyone": True,
     "argv": lambda me, a: ["port-owner", "who", str(int(a["port"]))]},
    {"name": "whose_process", "description": "Whose a process is: yours, another agent's, or the human's.",
     "inputSchema": {"type": "object", "properties": {"pid": {"type": "integer"}}, "required": ["pid"]}, "anyone": True,
     "argv": lambda me, a: ["proc-owner", "whose", str(int(a["pid"]))]},
    {"name": "stop_process", "description": "Stop one of YOUR processes (refused for another agent's or the human's). "
                                            "Use this instead of kill / pkill / kill-port.",
     "inputSchema": {"type": "object", "properties": {"pid": {"type": "integer"}, "force": {"type": "boolean"}}, "required": ["pid"]},
     "argv": lambda me, a: ["proc-owner", "kill", str(int(a["pid"])), "--by", me, *(["--force"] if a.get("force") else [])]},
    {"name": "my_processes", "description": "Your processes and the ports they listen on.",
     "inputSchema": {"type": "object", "properties": {}},
     "argv": lambda me, a: ["proc-owner", "list", me]},
    {"name": "take_screen", "description": "Hold the screen (keyboard, mouse, the window in front) before driving the foreground for a while. "
                                           "Background drivers (Cua) don't need it. Refused while the human types or holds it.",
     "inputSchema": {"type": "object", "properties": {"minutes": {"type": "number"}, "wait_seconds": {"type": "number"}}},
     "argv": lambda me, a: ["screen-owner", "take", me, "--minutes", str(float(a.get("minutes") or 5)), "--wait", str(float(a.get("wait_seconds") or 0))]},
    {"name": "release_screen", "description": "Give the screen back as soon as you're done with the foreground.",
     "inputSchema": {"type": "object", "properties": {}},
     "argv": lambda me, a: ["screen-owner", "release", me]},
    {"name": "ask_human_approval", "description": "Before sending anything that can't be taken back (Messages, Mail): the human sees exactly "
                                                  "this command and allows it once, or not. Then run exactly that command.",
     "inputSchema": {"type": "object", "properties": {"why": {"type": "string"}, "command": {"type": "array", "items": {"type": "string"}}},
                     "required": ["command"]},
     "argv": lambda me, a: ["rainbowomma-approve", "ask", "--agent", me, "--why", str(a.get("why") or ""), "--", *[str(x) for x in a["command"]]]},
    {"name": "browser_status", "description": "Your browser: up, down, hung, blocked, profile-busy, or closed by the human.",
     "inputSchema": {"type": "object", "properties": {}},
     "argv": lambda me, a: ["browser-owner", "status", me]},
    {"name": "start_my_browser", "description": "Open your own browser (its CDP port is in browser_status). "
                                                "If it answers refused or closed-by-person, stop and ask the human.",
     "inputSchema": {"type": "object", "properties": {}},
     "argv": lambda me, a: ["browser-owner", "start", me, "--by", me]},
    {"name": "recover_my_browser", "description": "Restart your browser if it is hung (never one the human closed).",
     "inputSchema": {"type": "object", "properties": {}},
     "argv": lambda me, a: ["browser-owner", "recover", me, "--by", me]},
]
BY_NAME = {x["name"]: x for x in TOOLS}


def run_tool(me, name, args):
    tool = BY_NAME.get(name)
    if not tool:
        return True, {"status": "failed", "why": f"unknown tool: {name}"}
    if not me and not tool.get("anyone"):
        return True, {"status": "refused", "why": "this server has no agent name: start it with --agent NAME (or RAINBOW_AGENT)"}
    try:
        argv = tool["argv"](me, args if isinstance(args, dict) else {})
    except (KeyError, TypeError, ValueError) as exc:
        return True, {"status": "failed", "why": f"bad arguments: {type(exc).__name__}: {exc}"[:200]}
    env = dict(os.environ, **({"RAINBOW_AGENT": me} if me else {}))
    try:
        r = subprocess.run([str(HERE / argv[0]), *argv[1:]], capture_output=True, text=True, timeout=TIMEOUT_S, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return True, {"status": "failed", "why": f"{type(exc).__name__}: {exc}"[:200]}
    try:
        out = json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        out = {"status": "failed", "why": (r.stdout or r.stderr or f"exit {r.returncode}").strip()[:300]}
    return r.returncode != 0, out


def answer(msg, me):
    method, mid = msg.get("method"), msg.get("id")
    if method == "initialize":
        want = (msg.get("params") or {}).get("protocolVersion")
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": want if isinstance(want, str) and want else PROTOCOL,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "rainbowomma", "version": "0.2.0"},
            "instructions": "You share this Mac with a human and other agents. Use lease_port for every server you start, "
                            "stop_process instead of kill, and your own browser only. A refused answer is final: ask the human."}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": [{k: v for k, v in x.items() if k in ("name", "description", "inputSchema")}
                                                                   for x in TOOLS]}}
    if method == "tools/call":
        params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
        err, out = run_tool(me, params.get("name"), params.get("arguments") or {})
        return {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False)}],
                                                        "structuredContent": out, "isError": err}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if mid is None:
        return None                                   # a notification (initialized, cancelled …): nothing to say
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="rainbowomma-mcp")
    ap.add_argument("--agent", help="this agent's name in browsers.json (default: $RAINBOW_AGENT)")
    a = ap.parse_args(argv)
    me = (a.agent or os.environ.get("RAINBOW_AGENT") or "").strip().lower()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        else:
            reply = answer(msg, me) if isinstance(msg, dict) else \
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "one request per line"}}
        if reply is not None:
            sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
