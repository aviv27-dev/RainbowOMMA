"""RainbowOMMA's owners as Hermes tools.

Each tool runs one command of an installed RainbowOMMA (browser-owner, port-owner, proc-owner, screen-owner,
office-owner) as this agent and returns its one JSON answer as a JSON string. A tool never raises: a missing
install, a refusal, a failure or a timeout comes back as {"status", "why", "next"}.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

TIMEOUT_S = 120
# the environment a command runs with: what the tools need to find their state and the agent's name — nothing else of
# Hermes' environment (keys, tokens) is passed on
PASS_ENV = ("HOME", "PATH", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "RAINBOW_HOME", "RAINBOW_LANG",
            "BROWSER_OWNER_REGISTRY")


def _int(v, lo, hi, default):
    try:
        return min(max(int(v), lo), hi)
    except (TypeError, ValueError):
        return default


def _num(v, lo, hi, default):
    try:
        return min(max(float(v), lo), hi)
    except (TypeError, ValueError):
        return default


def _str(v):
    return "" if v is None else str(v)


def _schema(name, description, props=None, required=()):
    return {"name": name, "description": description,
            "parameters": {"type": "object", "properties": props or {}, **({"required": list(required)} if required else {})}}


# name → (schema, argv(me, args)). Everything an agent does to a shared resource goes through its owner.
TOOLS = {
    "rainbow_start_my_browser": (
        _schema("rainbow_start_my_browser", "Open YOUR own browser: a Chrome in your color with your name on its frame, on "
                "your own CDP port (see rainbow_browser_status). Never the human's Chrome. If it answers refused or "
                "closed-by-person, stop and ask the human."),
        lambda me, a: ["browser-owner", "start", me, "--by", me]),
    "rainbow_browser_status": (
        _schema("rainbow_browser_status", "Your browser's state: up, down, hung, blocked, profile-busy or closed by the "
                "human, with its CDP port."),
        lambda me, a: ["browser-owner", "status", me]),
    "rainbow_recover_my_browser": (
        _schema("rainbow_recover_my_browser", "Restart your browser when it is hung (never one the human closed)."),
        lambda me, a: ["browser-owner", "recover", me, "--by", me]),
    "rainbow_open_in_my_browser": (
        _schema("rainbow_open_in_my_browser", "Open an address (a sign-in, an OAuth page …) in YOUR browser — never the "
                "human's. Use it instead of `open <url>`.", {"url": {"type": "string"}}, ["url"]),
        lambda me, a: ["browser-owner", "open", me, _str(a.get("url")), "--by", me]),
    "rainbow_job_start": (
        _schema("rainbow_job_start", "A job begins: remember which tabs your browser has now, so the tabs the job opens "
                "can close when it ends."),
        lambda me, a: ["browser-owner", "job-start", me]),
    "rainbow_job_end": (
        _schema("rainbow_job_end", "The job is done: lists the tabs it opened that will close. Keep any you still need "
                "with rainbow_keep_tabs, then call rainbow_close_job_tabs (they close by themselves after a minute)."),
        lambda me, a: ["browser-owner", "job-end", me]),
    "rainbow_keep_tabs": (
        _schema("rainbow_keep_tabs", "Keep these tabs (ids from rainbow_job_end) open — the tabs they opened stay too.",
                {"ids": {"type": "array", "items": {"type": "string"}}}, ["ids"]),
        lambda me, a: ["browser-owner", "job-keep", me, *[_str(x) for x in (a.get("ids") or []) if _str(x)]]),
    "rainbow_close_job_tabs": (
        _schema("rainbow_close_job_tabs", "Close the job's tabs you didn't keep (never the last tab, never one another "
                "client drives)."),
        lambda me, a: ["browser-owner", "job-close", me]),
    "rainbow_take_screen": (
        _schema("rainbow_take_screen", "Hold the screen (keyboard, mouse, the window in front) before driving the "
                "foreground for a while. Refused while the human types or holds it.",
                {"minutes": {"type": "number"}, "wait_seconds": {"type": "number"}}),
        lambda me, a: ["screen-owner", "take", me, "--minutes", str(_num(a.get("minutes"), 0.1, 60.0, 5.0)),
                       "--wait", str(_num(a.get("wait_seconds"), 0.0, 120.0, 0.0))]),
    "rainbow_release_screen": (
        _schema("rainbow_release_screen", "Give the screen back as soon as you are done with the foreground."),
        lambda me, a: ["screen-owner", "release", me]),
    "rainbow_lease_port": (
        _schema("rainbow_lease_port", "Get a free network port of your own (from your range; never the human's "
                "3000/5173/8000/8080). Use it for every server you start: PORT=<port>. The same name gives the same "
                "port back.", {"name": {"type": "string", "description": "what it is for, e.g. web, api"},
                               "prefer": {"type": "integer", "description": "a port of your own range"}}),
        lambda me, a: ["port-owner", "lease", me, "--name", _str(a.get("name")) or "default",
                       *(["--prefer", str(_int(a.get("prefer"), 1, 65535, 0))] if a.get("prefer") is not None else [])]),
    "rainbow_release_port": (
        _schema("rainbow_release_port", "Give a leased port back (all of yours with all=true).",
                {"name": {"type": "string"}, "all": {"type": "boolean"}}),
        lambda me, a: ["port-owner", "release", me, *(["--all"] if a.get("all") else ["--name", _str(a.get("name")) or "default"])]),
    "rainbow_who_port": (
        _schema("rainbow_who_port", "Whose a port is (an agent's or the human's) and what listens on it.",
                {"port": {"type": "integer"}}, ["port"]),
        lambda me, a: ["port-owner", "who", str(_int(a.get("port"), 1, 65535, 0))]),
    "rainbow_whose_process": (
        _schema("rainbow_whose_process", "Whose a process is: yours, another agent's or the human's.",
                {"pid": {"type": "integer"}}, ["pid"]),
        lambda me, a: ["proc-owner", "whose", str(_int(a.get("pid"), 1, 2 ** 31 - 1, 0))]),
    "rainbow_stop_process": (
        _schema("rainbow_stop_process", "Stop one of YOUR processes (refused for another agent's or the human's). Use it "
                "instead of kill / pkill / kill-port.", {"pid": {"type": "integer"}, "force": {"type": "boolean"}}, ["pid"]),
        lambda me, a: ["proc-owner", "kill", str(_int(a.get("pid"), 1, 2 ** 31 - 1, 0)), "--by", me,
                       *(["--force"] if a.get("force") else [])]),
    "rainbow_my_processes": (
        _schema("rainbow_my_processes", "Your processes and the ports they listen on."),
        lambda me, a: ["proc-owner", "list", me]),
    "rainbow_office_open": (
        _schema("rainbow_office_open", "Lease a document before you open it in Word, Excel or PowerPoint, so its app is "
                "never quit or closed under you — and never under the human.",
                {"file": {"type": "string"}, "app": {"type": "string", "description": "word, excel or powerpoint"}}, ["file"]),
        lambda me, a: ["office-owner", "open", "--agent", me, *(["--app", _str(a["app"])] if a.get("app") else []), _str(a.get("file"))]),
    "rainbow_office_close": (
        _schema("rainbow_office_close", "Done with a leased document: it closes only if you opened it, nobody had it open "
                "before, and it is saved.", {"file": {"type": "string"}}, ["file"]),
        lambda me, a: ["office-owner", "close", "--agent", me, _str(a.get("file"))]),
    "rainbow_word_to_pdf": (
        _schema("rainbow_word_to_pdf", "Convert a .docx to PDF through the real Word, on a temporary copy — the human's "
                "open documents are never touched.", {"file": {"type": "string"}, "out": {"type": "string"}}, ["file"]),
        lambda me, a: ["office-owner", "pdf", "--agent", me, *(["--out", _str(a["out"])] if a.get("out") else []), _str(a.get("file"))]),
}


def failed(why, nxt=None, status="failed"):
    return json.dumps({"status": status, "why": why, **({"next": nxt} if nxt else {})}, ensure_ascii=False)


def tool_env(agent):
    env = {k: os.environ.get(k) for k in PASS_ENV if os.environ.get(k)}
    env["RAINBOW_AGENT"] = agent
    return env


def run(bin_dir, agent, name, args, runner=subprocess.run):
    """run one tool → its JSON answer as a string (never raises)"""
    try:
        if name not in TOOLS:
            return failed(f"unknown tool {name}")
        exe = Path(bin_dir).expanduser() / TOOLS[name][1]("-", {})[0]
        if not exe.is_file():
            return failed(f"RainbowOMMA is not installed in {Path(bin_dir).expanduser()}",
                          "install it (./install.sh, or brew install rainbowomma) or set the plugin's bin_dir")
        if not agent:
            return failed("this Hermes profile has no RainbowOMMA agent name",
                          "set plugins.entries.rainbowomma.settings.agent to the agent's name in browsers.json", "refused")
        argv = TOOLS[name][1](agent, args if isinstance(args, dict) else {})
        r = runner([str(exe), *argv[1:]], capture_output=True, text=True, timeout=TIMEOUT_S,
                   env=tool_env(agent), stdin=subprocess.DEVNULL)
        lines = [x for x in (r.stdout or "").strip().splitlines() if x.strip()]
        try:
            return json.dumps(json.loads(lines[-1]), ensure_ascii=False)
        except (ValueError, IndexError):
            return failed(((r.stdout or "") + (r.stderr or "")).strip()[:300] or f"exit {r.returncode}")
    except subprocess.TimeoutExpired:
        return failed(f"{name} did not answer within {TIMEOUT_S} s", "rainbow_browser_status, or ask the human")
    except Exception as exc:                       # a tool never raises
        return failed(f"{type(exc).__name__}: {exc}"[:300])
