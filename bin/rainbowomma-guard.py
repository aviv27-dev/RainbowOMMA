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
    "port-kill": "freeing a port by killing whatever holds it (kill-port, fkill, fuser -k) can hit another agent's or the human's server",
    "osascript": "quitting Chrome through AppleScript closes every Chrome window, the human's too",
    "debug-port": "an agent's Chrome is started only by browser-owner",
    "human": "only the human acts as the human: --by human (and the desktop controls) are the person's, never an agent's",
}
HELP = ("Use the owner instead: `browser-owner start|recover <agent> --by <agent>` for your browser "
        "(stop when it answers refused / closed-by-person / blocked / profile-busy), `office-owner` for Word/Excel/Acrobat, "
        "`port-owner lease <agent>` for a port of your own (`port-owner who <port>` says whose a port is).")

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
ASSIGNED_PORT = re.compile(r"(?:[a-z0-9_]*_)?port=(\d{2,5})")
CONTAINERS = {"docker", "podman", "nerdctl"}
PORT_KILLERS = {"kill-port", "fkill", "fkill-cli"}


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
    assigns = []
    while words and ASSIGN.match(words[0]):
        assigns.append(words[0])
        words = words[1:]
    found = []
    while words:
        name = os.path.basename(words[0]) or words[0]
        if name in WRAPPERS:
            takes, words = WRAPPERS[name], words[1:]
            if name == "xargs":
                found.append(("xargs", list(words)))
            while words and (words[0].startswith("-") or ASSIGN.match(words[0])):
                if ASSIGN.match(words[0]):
                    assigns.append(words[0])
                words = words[2:] if words[0] in takes else words[1:]
            continue
        if (name in SHELLS or name.startswith("python")) and len(words) > 1:
            rest = words[1:]
            for i, w in enumerate(rest):
                if name in SHELLS and w.startswith("-") and "c" in w[1:] and not w.startswith("--") and i + 1 < len(rest) and depth < 4:
                    return found + [("=", assigns)] * bool(assigns) + _simple_commands(rest[i + 1], depth + 1)
            i = next((i for i, w in enumerate(rest) if not w.startswith("-")), None)
            if i is not None and (rest[i].endswith((".sh", ".py")) or os.path.basename(rest[i]) in OWNER_TOOLS | HUMAN_TOOLS):
                words = rest[i:]
                name = os.path.basename(words[0])
            else:
                found.append((name, words[1:]))       # python3 -m http.server 8000, bash with no script: judged as itself
                break
        if name == "eval" and depth < 4:
            return found + [("=", assigns)] * bool(assigns) + _simple_commands(" ".join(words[1:]), depth + 1)
        found.append((name, words[1:]))
        break
    if assigns:
        found.append(("=", assigns))                 # VAR=value before a command (or alone): the environment it gets
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
    if killing and names & {"pgrep", "pidof", "ps", "lsof"}:
        return WHY["search-kill"]
    if names & PORT_KILLERS or any(a and a[0] in PORT_KILLERS for n, a in cmds if n in ("npx", "pnpx", "bunx", "pnpm", "yarn")) \
            or any(n == "fuser" and any(x.startswith("-") and "k" in x for x in a) for n, a in cmds):
        return WHY["port-kill"]
    return port_verdict(claimed_ports(low, cmds))


def claimed_ports(low, cmds):
    """the ports a command line asks to listen on: --port N, PORT=N (any *_PORT=N), docker -p HOST:…, http.server N"""
    got = set()
    for name, args in cmds:
        if name in ("=", "export"):
            got |= {m.group(1) for m in map(ASSIGNED_PORT.fullmatch, args) if m}
            continue
        for i, a in enumerate(args):
            nxt = args[i + 1] if i + 1 < len(args) else ""
            if a.startswith("--port="):
                got.add(a.split("=", 1)[1])
            elif a == "--port" and nxt.isdigit():
                got.add(nxt)
            elif name in CONTAINERS and a in ("-p", "--publish") and ":" in nxt:
                parts = nxt.split(":")
                got.add(parts[-2])                                   # [ip:]host:container → host
            elif name.startswith("python") and a == "http.server" and nxt.isdigit():
                got.add(nxt)
    return sorted({int(p) for p in got if str(p).isdigit() and 1 <= int(p) <= 65535})


def _port_owner():
    import importlib.machinery
    import importlib.util
    path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "port-owner.py")
    loader = importlib.machinery.SourceFileLoader("rainbow_port_owner", path)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def port_verdict(ports):
    """with RAINBOW_AGENT set: only that agent's ports. Without it: never a port another agent holds or owns"""
    if not ports:
        return None
    try:
        po = _port_owner()
        reg, leases, humans = po.registry(), po.leases_of(), set(po.human_ports())
    except Exception:
        return None                                   # no registry here → nothing to compare against
    me = (os.environ.get("RAINBOW_AGENT") or "").strip().lower()
    for p in ports:
        owner, why = po.owner_of(p, reg, leases, humans)
        if me and owner != me:
            whose = "kept for the human" if why == "reserved" else f"{owner}'s ({why})" if owner != "human" else "not in your range"
            return f"port {p} is not {me}'s — it is {whose}. Take one of yours: `port-owner lease {me}`"
        if not me and owner != "human":
            return f"port {p} belongs to agent {owner} ({why})"
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
