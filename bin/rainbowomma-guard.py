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
import os
import re
import shlex
import sys

WHY = {
    "pkill": "pkill matches processes by pattern and can hit another agent's browser",
    "killall": "killall stops every process of that name, other agents' too",
    "search-kill": "killing what a process search found (pgrep / ps / lsof) is pkill by another name",
    "osascript": "quitting Chrome through AppleScript closes every Chrome window, the human's too",
    "debug-port": "an agent's Chrome is started only by browser-owner",
    "human": "only the human acts as the human: --by human (and the desktop controls) are the person's, never an agent's",
}
HELP = ("Use the owner instead: `browser-owner start|recover <agent> --by <agent>` for your browser "
        "(stop when it answers refused / closed-by-person / blocked / profile-busy), `office-owner` for Word/Excel/Acrobat.")

SEP = set(";&|()<>`")
WRAPPERS = {"sudo": {"-u", "-g", "-h", "-p", "-c", "-r", "-t", "-d"}, "env": {"-u", "-s", "-c", "-p"}, "command": set(), "exec": {"-a"},
            "nohup": set(), "time": set(), "nice": {"-n"}, "xargs": {"-n", "-i", "-l", "-p", "-s", "-e", "-j", "-r", "-d", "-a"},
            "caffeinate": {"-w", "-t"}, "arch": set(), "builtin": set(), "doas": {"-u"}}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish"}
OWNER_TOOLS = {"browser-owner", "browser-owner.py", "office-owner", "agent-office", "agent-office.py"}
HUMAN_TOOLS = {"desk-browser.sh", "kill-chrome.sh", "human-chrome.sh"}
CHROMES = {"google chrome", "chromium", "google chrome for testing", "google chrome canary", "google chrome beta"}
ASSIGN = re.compile(r"^[a-z_][a-z0-9_]*=")
HEREDOC = re.compile(r"<<-?\s*(['\"]?)([a-z_][a-z0-9_]*)\1")
CHROME_HINT = re.compile(r"chrom|\b92(2[2-9]|[3-9][0-9])\b")


def _drop_heredocs(text):
    """a heredoc's body is data written to a file or a pipe, not commands"""
    out, end = [], None
    for line in text.split("\n"):
        if end is not None:
            if line.strip() == end:
                end = None
            continue
        out.append(line)
        m = HEREDOC.search(line)
        if m:
            end = m.group(2)
    return "\n".join(out)


def _tokens(text):
    lx = shlex.shlex(text, posix=True, punctuation_chars="();<>|&`")
    lx.whitespace_split = True
    try:
        return list(lx)
    except ValueError:                              # unbalanced quotes: read it word by word, quotes ignored (stricter, never looser)
        return re.findall(r"[^\s;&|()<>`]+|[;&|()<>`]+", text.replace('"', " ").replace("'", " "))


def _simple_commands(text, depth=0):
    """every simple command in a shell line → [(name, args)], looking inside $( ), backticks, sh -c and eval"""
    text = _drop_heredocs(text).replace("\\\n", " ").replace("\n", " ; ")
    out, cur = [], []
    for tok in _tokens(text) + [";"]:
        if tok and all(c in SEP for c in tok):
            if cur:
                out += _one(cur, depth)
            cur = []
            continue
        if depth < 4 and ("$(" in tok or "`" in tok) and len(tok) > 2:      # a substitution inside quotes
            out += _simple_commands(tok.split("$(", 1)[-1].split("`", 1)[-1], depth + 1)
        cur.append(tok)
    return out


def _one(words, depth):
    words = [w for w in words if w != "$"]
    while words and ASSIGN.match(words[0]):
        words = words[1:]
    found = []
    while words:
        name = os.path.basename(words[0]) or words[0]
        if name in WRAPPERS:
            takes, words = WRAPPERS[name], words[1:]
            if name == "xargs":
                found.append(("xargs", list(words)))
            while words and (words[0].startswith("-") or ASSIGN.match(words[0])):
                words = words[2:] if words[0] in takes else words[1:]
            continue
        if (name in SHELLS or name.startswith("python")) and len(words) > 1:
            rest = words[1:]
            for i, w in enumerate(rest):
                if name in SHELLS and w.startswith("-") and "c" in w[1:] and not w.startswith("--") and i + 1 < len(rest) and depth < 4:
                    return found + _simple_commands(rest[i + 1], depth + 1)
            i = next((i for i, w in enumerate(rest) if not w.startswith("-")), None)
            if i is not None and (rest[i].endswith((".sh", ".py")) or os.path.basename(rest[i]) in OWNER_TOOLS | HUMAN_TOOLS):
                words = rest[i:]
                name = os.path.basename(words[0])
            else:
                break
        if name == "eval" and depth < 4:
            return found + _simple_commands(" ".join(words[1:]), depth + 1)
        found.append((name, words[1:]))
        break
    return found


def verdict(command):
    """the reason a command is blocked, or None"""
    low = command.lower()
    cmds = _simple_commands(low)
    names = {n for n, _ in cmds}
    for name, args in cmds:
        if name in ("pkill", "killall"):
            return WHY[name]
        if name == "osascript" and "quit" in " ".join(args) and "chrome" in " ".join(args):
            return WHY["osascript"]
        debug = any(a.startswith("--remote-debugging-port") for a in args)
        if debug and name in CHROMES:
            return WHY["debug-port"]
        if debug and name == "open" and any("chrom" in a for a in args):
            return WHY["debug-port"]
        if name in OWNER_TOOLS and any(a == "--by=human" or (a == "--by" and i + 1 < len(args) and args[i + 1].strip() == "human")
                                       for i, a in enumerate(args)):
            return WHY["human"]
        if name in HUMAN_TOOLS:
            return WHY["human"]
    if re.search(r"\blaunch_by=['\"]?human\b", low):          # export LAUNCH_BY=human; ./agent-launcher.sh
        return WHY["human"]
    killing = "kill" in names or any(n == "xargs" and "kill" in a for n, a in cmds)
    if killing and (names & {"pgrep", "pidof"} or (names & {"ps", "lsof"} and CHROME_HINT.search(low))):
        return WHY["search-kill"]
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
