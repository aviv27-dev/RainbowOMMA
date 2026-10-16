#!/usr/bin/env python3
"""rainbowomma-guard — one pre-tool hook for every agent framework that can run one.

Blocks every way an agent could kill or launch Chrome without its owner: kill by pattern (pkill / killall /
kill $(pgrep …)), quitting Chrome through AppleScript, starting a Chrome binary on a debug port. The only way left is
browser-owner. It reads the hook payload on stdin and finds the shell command in whichever shape the agent sends:

    tool_input.command            Claude Code, Codex CLI, Gemini CLI, Qwen Code, Factory Droid, Hermes Agent, Goose,
                                  GitHub Copilot (PreToolUse), Kiro, Augment
    command                       Cursor (beforeShellExecution)
    tool_info.command_line        Windsurf / Devin Desktop (pre_run_command)
    toolArgs (JSON text)          GitHub Copilot CLI (preToolUse)
    tool_call.input.command(s)    Cline CLI
    preToolUse.parameters         Cline VS Code extension

A blocked command: the reason on stderr and exit 2 (what all of the above treat as "deny"), or, with --format cline,
{"cancel": true, "errorMessage": …} on stdout. Anything it can't read is let through: pattern rules only see the
command text, and browser-owner's own checks stay the real protection.

    rainbowomma-guard [--format exit2|cline] < payload.json
"""
import json
import re
import sys

RULES = [
    (r"(^|[\s;&|(`$])(sudo\s+)?pkill\b", "pkill matches processes by pattern and can hit another agent's browser"),
    (r"(^|[\s;&|(`$])(sudo\s+)?killall\b", "killall stops every process of that name, other agents' too"),
    (r"\bkill\b[^\n]*(\$\(|`)\s*pgrep\b", "kill $(pgrep …) is pkill by another name"),
    (r"\bpgrep\b[^\n]*\|\s*xargs\b[^\n]*\bkill\b", "pgrep | xargs kill is pkill by another name"),
    (r"osascript[^\n]*quit[^\n]*google chrome|osascript[^\n]*google chrome[^\n]*quit", "quitting Chrome through AppleScript closes every Chrome window, the human's too"),
    (r"macos/google chrome[^\n]*--remote-debugging-port", "an agent's Chrome is started only by browser-owner"),
]
HELP = ("Use the owner instead: `browser-owner start|recover <agent> --by <agent>` for your browser "
        "(stop when it answers refused / closed-by-person / blocked / profile-busy), `office-owner` for Word/Excel/Acrobat.")


def verdict(command):
    """the reason a command is blocked, or None"""
    low = command.lower()
    for pattern, why in RULES:
        if re.search(pattern, low):
            return why
    return None


def _maybe_json(v):
    if isinstance(v, str) and v[:1] in "{[":
        try:
            return json.loads(v)
        except ValueError:
            pass
    return v


def _strings(v):
    v = _maybe_json(v)
    if isinstance(v, str):
        return [v]
    if isinstance(v, list):
        return [s for x in v for s in _strings(x)]
    return []


def commands(event):
    """every shell command text this payload carries, whatever the agent's shape"""
    out = []
    ti = _maybe_json(event.get("tool_input"))
    if isinstance(ti, dict):
        out += _strings(ti.get("command")) + _strings(ti.get("cmd")) + _strings(ti.get("commands"))
    out += _strings(event.get("command"))
    info = event.get("tool_info")
    if isinstance(info, dict):
        out += _strings(info.get("command_line"))
    args = _maybe_json(event.get("toolArgs"))
    if isinstance(args, dict):
        out += _strings(args.get("command"))
    call = event.get("tool_call")
    if isinstance(call, dict) and isinstance(call.get("input"), dict):
        out += _strings(call["input"].get("commands")) + _strings(call["input"].get("command"))
    pre = event.get("preToolUse")
    if isinstance(pre, dict):
        params = _maybe_json(pre.get("parameters"))
        if isinstance(params, dict):
            out += _strings(params.get("command")) + _strings(params.get("commands"))
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    fmt = argv[argv.index("--format") + 1] if "--format" in argv[:-1] else "exit2"
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(event, dict):
        return 0
    for cmd in commands(event):
        why = verdict(cmd)
        if why:
            msg = f"Blocked by RainbowOMMA: {why}. {HELP}"
            if fmt == "cline":
                print(json.dumps({"cancel": True, "errorMessage": msg}))
                return 0
            print(msg, file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
