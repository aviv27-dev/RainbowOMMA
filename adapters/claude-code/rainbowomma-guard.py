#!/usr/bin/env python3
"""RainbowOMMA guard for Claude Code — a PreToolUse hook on Bash.

Blocks every way an agent could kill or launch Chrome without its owner: kill by pattern (pkill / killall / kill $(pgrep …)),
quitting Chrome through AppleScript, starting a Chrome binary on a debug port. The only way left is browser-owner.
Same patterns as adapters/hermes-approvals-deny.yaml. Exit 2 blocks the command; Claude reads the reason on stderr.
Pattern rules only see the command text — browser-owner's own checks stay the real protection.
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


def main():
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    if event.get("tool_name") != "Bash":
        return 0
    why = verdict(str((event.get("tool_input") or {}).get("command") or ""))
    if not why:
        return 0
    print(f"Blocked by RainbowOMMA: {why}. {HELP}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
