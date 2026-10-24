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
{"cancel": true, "errorMessage": …} on stdout. A payload that isn't JSON is let through (it carries no command); an
error while judging one is a refusal ("can't tell" never means yes). The rules see the command text: they close the
cheap ways around RainbowOMMA, not every way a program running as you could take — docs/ISOLATION.md says what does.

    rainbowomma-guard [--format exit2|cline] < payload.json
"""
import json
import os
import re
import shlex
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))   # -I drops the script's folder; the receipts live beside it

WHY = {
    "pkill": "pkill matches processes by pattern and can hit another agent's browser",
    "killall": "killall stops every process of that name, other agents' too",
    "search-kill": "killing what a process search found (pgrep / ps / lsof) is pkill by another name",
    "port-kill": "freeing a port by killing whatever holds it (kill-port, fkill, fuser -k) can hit another agent's or the human's server",
    "osascript": "quitting Chrome through AppleScript closes every Chrome window, the human's too",
    "debug-port": "an agent's Chrome is started only by browser-owner",
    "rm-home": "rm -r of your home folder, the whole disk or a system folder can't be undone — name the exact folder inside your work",
    "human-active": "the human is using the keyboard or mouse right now — wait a few seconds and try again (a GUI action now would land in their window)",
    "human-browser": "a browser MCP attached to the human's own Chrome (--autoConnect, --extension) would act in their tabs — "
                     "point it at your own browser: `browser-owner mcp-config <agent>`",
    "clipboard": "the system clipboard is the human's — keep yours with `rainbowomma-clip copy|paste <you>`",
    "sim-booted": "`booted` means whichever simulator happens to be running, maybe another agent's — use your own: `sim-owner lease <you>`",
    "send": "sending through Messages or Mail can't be taken back — ask the human first: "
            "`rainbowomma-approve ask --agent <you> --why \"…\" -- <this exact command>`, then run it again",
    "approval-up": "the human is answering an approval dialog — no agent clicks or types until they do",
    "human-screen": "the human took over the screen — no agent clicks or types until they hand it back; wait, or ask them",
    "paused": "the human paused all agents (the menu-bar stop) — nothing runs until they resume; wait, or ask them",
    "human": "only the human acts as the human: --by human (and the desktop controls) are the person's, never an agent's",
    "kill-group": "kill -1, kill 0 and a negative id stop whole process groups — every process you own, the human's too; "
                  "stop one process of yours: `proc-owner kill <pid> --by <you>`",
    "xargs-kill": "`xargs kill` stops pids the guard can't see — stop your own one by one: `proc-owner kill <pid> --by <you>`",
    "inline-kill": "killing from inline code (python -c, perl -e, node -e …) skips the ownership check — use `proc-owner kill <pid> --by <you>`",
    "rainbow-state": "RainbowOMMA's own state (approvals, leases, process marks, the pause) changes only through its tools, and "
                     "browsers.json is the human's to edit — never an agent's",
    "rainbow-env": "RAINBOW_HOME, BROWSER_OWNER_REGISTRY, RAINBOW_AGENT and RAINBOW_TEST_* decide whose and where — an agent "
                   "doesn't set them; its name comes from as-agent or its settings",
    "human-chrome": "the human's own Chrome profile (Library/Application Support/Google/Chrome) holds their logins — an agent never "
                    "reads or changes it",
    "shell-script": "AppleScript's `do shell script` with a text built at run time can't be checked — run the shell command directly",
    "chrome-script": "closing or quitting Chrome windows through AppleScript reaches the human's windows too — use `browser-owner`",
    "guard-error": "the guard couldn't judge this command, and \"can't tell\" is a refusal",
}
HELP = ("Use the owner instead: `browser-owner start|recover <agent> --by <agent>` for your browser "
        "(stop when it answers refused / closed-by-person / blocked / profile-busy), `office-owner` for Word/Excel/Acrobat, "
        "`port-owner lease <agent>` for a port of your own (`port-owner who <port>` says whose a port is).")

SEP = set(";&|()<>`")
WRAPPERS = {"sudo": {"-u", "-g", "-h", "-p", "-c", "-r", "-t", "-d"}, "env": {"-u", "-c", "-p"}, "command": set(), "exec": {"-a"},
            "nohup": set(), "time": set(), "nice": {"-n"}, "xargs": {"-n", "-i", "-l", "-p", "-s", "-e", "-j", "-r", "-d", "-a"},
            "caffeinate": {"-w", "-t"}, "arch": set(), "builtin": set(), "doas": {"-u"}, "setsid": set(), "stdbuf": set(),
            "ionice": {"-c", "-n"}, "taskpolicy": {"-c", "-d", "-g", "-t", "-l"}, "chronic": set(), "unbuffer": set(),
            "timeout": {"-s", "-k", "--signal", "--kill-after"}, "gtimeout": {"-s", "-k"}, "flock": {"-w", "-e", "-s", "-x", "-n", "-o"},
            "watch": {"-n", "-d"}, "script": {"-t", "-T"}, "busybox": set()}
TAKES_FIRST = {"timeout": 1, "gtimeout": 1, "flock": 1, "script": 1}       # wrapper WORD command …: the word isn't the command
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish"}
OWNER_TOOLS = {"browser-owner", "browser-owner.py", "office-owner", "agent-office", "agent-office.py", "proc-owner", "proc-owner.py",
               "port-owner", "port-owner.py", "sim-owner", "sim-owner.py", "screen-owner", "screen-owner.py", "rainbowomma-clip",
               "rainbowomma-clip.py", "rainbowomma-approve", "rainbowomma-approve.py", "rainbowomma-pause", "rainbowomma-pause.py",
               "auth-owner", "auth-owner.py"}
HUMAN_TOOLS = {"desk-browser.sh", "kill-chrome.sh", "human-chrome.sh"}
# subcommands whose first argument is the agent acting: it must be the caller
AGENT_ARG = {"proc-owner": {"list", "reap", "register"}, "port-owner": {"lease", "release", "env"},
             "sim-owner": {"lease", "release"}, "auth-owner": {"lease", "release", "code"}, "screen-owner": {"take", "release"}, "rainbowomma-clip": {"copy", "paste"},
             "browser-owner": {"start", "stop", "recover", "idle-stop", "front", "heal", "mcp-config", "tabs"}}
HUMAN_ONLY = {("screen-owner", "takeover"), ("screen-owner", "handback"), ("rainbowomma-pause", "off")}
INLINE = {"python": "-c", "perl": "-e", "ruby": "-e", "node": "-e", "osascript": None, "php": "-r", "bun": "-e", "deno": "eval"}
INLINE_KILL = re.compile(r"\b(os\.kill|killpg|os\.system|subprocess|pkill|killall|process\.kill|\bkill\s*\(|signal\.sig(kill|term))")
RAINBOW_ENV = re.compile(r"^(rainbow_home|browser_owner_registry|rainbow_test_\w*|rainbow_env_markers|rainbow_track_root|"
                         r"rainbow_human_idle_s|rainbow_human_present_s|rainbow_agent|rainbow_session)=")
STATE_WORDS = re.compile(r"(\.rainbowomma|\$\{?rainbow_home\}?)/(state|logs|cdp)\b|proc-roots\.json|approvals\.json|approval-pending\.json|"
                         r"paused\.json|screen\.json|ports\.json|auth\.json|browsers\.json|receipts\.jsonl")
WRITERS = {"rm", "mv", "cp", "ln", "tee", "sed", "perl", "truncate", "touch", "chmod", "chflags", "dd", "install", "rsync", "ruby",
           "node", "unlink", "rmdir", "mkdir", "ditto", "patch", "ed", "vi", "vim", "nano", "emacs", "shred", "srm", "trash",
           "plutil", "sqlite3"}
HUMAN_CHROME = re.compile(r"application(?:\\ | |%20)+support/google/chrome")
CHROMES = {"google chrome", "chromium", "google chrome for testing", "google chrome canary", "google chrome beta"}
ASSIGN = re.compile(r"^[a-z_][a-z0-9_]*=")
HEREDOC = re.compile(r"<<-?\s*(['\"]?)([a-z_][a-z0-9_]*)\1")
ASSIGNED_PORT = re.compile(r"(?:[a-z0-9_]*_)?port=(\d{2,5})")
CONTAINERS = {"docker", "podman", "nerdctl"}
PORT_KILLERS = {"kill-port", "fkill", "fkill-cli"}


def _unquoted(line, pos):
    """is position pos of line outside quotes?"""
    q = None
    for c in line[:pos]:
        if q:
            q = None if c == q else q
        elif c in "'\"":
            q = c
    return q is None


def _drop_heredocs(text):
    """a heredoc's body is data written to a file or a pipe — unless a shell or an interpreter reads it: then it runs"""
    out, end, keep = [], None, False
    for line in text.split("\n"):
        if end is not None:
            if line.strip() == end:
                end = None
            elif keep:
                out.append(line)
            continue
        out.append(line)
        m = next((m for m in HEREDOC.finditer(line) if _unquoted(line, m.start())), None)
        if m:
            end = m.group(2)
            words = re.split(r"[;&|(]", line[:m.start()])[-1].split()
            first = next((os.path.basename(w) for w in words if not ASSIGN.match(w) and os.path.basename(w) not in WRAPPERS), "")
            keep = first in SHELLS or first.startswith(("python", "perl", "ruby", "node", "osascript", "php"))
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
                if name == "env" and (words[0] in ("-s", "--split-string") or words[0].startswith(("-s", "--split-string="))) \
                        and depth < 4:                                    # env -S 'cmd args': one more command line
                    rest_ = words[0].split("=", 1)[1] if "=" in words[0] else words[0][2:] or (words[1] if len(words) > 1 else "")
                    return found + [("=", assigns)] * bool(assigns) + _simple_commands(rest_ + " " + " ".join(words[2:]), depth + 1)
                if ASSIGN.match(words[0]):
                    assigns.append(words[0])
                elif name == "env" and words[0] in ("-u", "--unset") and len(words) > 1:
                    assigns.append(words[1] + "=")                        # unsetting is setting to nothing
                words = words[2:] if words[0] in takes else words[1:]
            if words and words[0] == "--":
                words = words[1:]
            words = words[TAKES_FIRST.get(name, 0):]
            continue
        if name == "as-agent":
            found.append(("as-agent", words[1:2]))                         # as-agent NAME cmd …: judged as NAME, then cmd
            words = words[2:]
            continue
        if name == "find" and depth < 4:
            for i, w in enumerate(words):
                if w in ("-exec", "-execdir", "-ok", "-okdir"):
                    end = next((j for j in range(i + 1, len(words)) if words[j] in ("\\;", ";", "+", "{}+")), len(words))
                    found += _one([x for x in words[i + 1:end] if x != "{}"], depth + 1)
        base = re.sub(r"[\d.]+$", "", name)
        if base in INLINE and base != "osascript":
            flag = INLINE[base]
            code = " ".join(words[i + 1] for i, w in enumerate(words[:-1]) if w == flag or (w.startswith("-") and not w.startswith("--")
                                                                                            and flag and flag[1] in w[1:]))
            if code and INLINE_KILL.search(code):
                found.append(("inline-kill", [code]))
        if (name in SHELLS or name.startswith("python")) and len(words) > 1:
            rest = words[1:]
            for i, w in enumerate(rest):
                if name in SHELLS and w.startswith("-") and "c" in w[1:] and not w.startswith("--") and i + 1 < len(rest) and depth < 4:
                    j = i + 2 if rest[i + 1] == "--" and i + 2 < len(rest) else i + 1
                    return found + [("=", assigns)] * bool(assigns) + _simple_commands(rest[j], depth + 1)
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


HERESTRING = re.compile(r"<<<\s*(?:'([^']*)'|\"([^\"]*)\"|(\S+))")
SHELL_STRING = re.compile(r'do shell script\s+(?:"((?:[^"\\]|\\.)*)"|(.))')


def _me():
    return (os.environ.get("RAINBOW_AGENT") or "").strip().lower()


CDP_DIR = re.compile(r"(?:\.rainbowomma|\$\{?rainbow_home\}?)/cdp/([a-z][a-z0-9-]*)")


def cdp_dir_verdict(text, me):
    """an agent's broker token and socket ($RAINBOW_HOME/cdp/AGENT) are that agent's alone — they open its browser"""
    for m in CDP_DIR.finditer(text.lower()):
        if m.group(1) != me:
            return f"{m.group(0)} holds {m.group(1)}'s browser key — {'yours is ' + me + chr(39) + 's' if me else 'an agent without a name has none'}"
    return None


def owner_tool_verdict(name, args, me):
    """an owner tool acts as the caller only: --by and the agent argument are the caller's own name, never the human's"""
    base = name[:-3] if name.endswith(".py") else name
    base = "office-owner" if base == "agent-office" else base
    sub = next((a for a in args if not a.startswith("-")), "")
    if (base, sub) in HUMAN_ONLY:
        return WHY["human"]
    named = []
    for i, a in enumerate(args):
        if a in ("--by", "--agent") and i + 1 < len(args):
            named.append(args[i + 1].strip())
        elif a.startswith(("--by=", "--agent=")):
            named.append(a.split("=", 1)[1].strip())
    if sub in AGENT_ARG.get(base, ()):
        rest = args[args.index(sub) + 1:]
        if rest and not rest[0].startswith("-"):
            named.append(rest[0].strip())
    for who in named:
        if who == "human":
            return WHY["human"]
        if any(c in who for c in "$`*?[") or not who:
            return f"`{base}` must name the agent literally — the guard can't see whose `{who}` is"
        if me and who not in (me, "keepalive"):
            return f"you are {me}: `{base}` acts only as you, never as {who}"
    return None


def verdict(command):
    """the reason a command is blocked, or None"""
    low = command.lower()
    for m in HERESTRING.finditer(low):                 # bash <<< 'cmd': the string runs
        if _unquoted(low, m.start()):
            why = verdict(next(g for g in m.groups() if g is not None))
            if why:
                return why
    cmds = _simple_commands(low)
    names = {n for n, _ in cmds}
    me = _me()
    if any(n in SHELLS or n.startswith("python") for n, a in cmds if not [x for x in a if not x.startswith("-")]):
        for n, a in cmds:                              # echo 'cmd' | sh: what the shell reads from its input runs
            if n in ("echo", "printf") and a:
                why = verdict(" ".join(x for x in a if not x.startswith("-")).replace("\\n", "\n"))
                if why:
                    return why
    if HUMAN_CHROME.search(low):
        return WHY["human-chrome"]
    why = cdp_dir_verdict(low, me)
    if why:
        return why
    if STATE_WORDS.search(low) and (names & WRITERS or any(n.startswith(("python", "perl", "ruby", "node")) for n in names)
                                    or re.search(r">\s*\S*(?:" + STATE_WORDS.pattern + ")", low)):
        return WHY["rainbow-state"]
    for name, args in cmds:
        if name == "inline-kill":
            return WHY["inline-kill"]
        if name in ("=", "export", "unset", "declare", "typeset", "set") and any(
                RAINBOW_ENV.match(a if name != "unset" else a + "=") for a in args):
            bad = [a for a in args if RAINBOW_ENV.match(a if name != "unset" else a + "=")]
            if not all(me and b == f"rainbow_agent={me}" for b in bad):
                return WHY["rainbow-env"]
        if name == "as-agent" and me and args and args[0] != me:
            return f"you are {me}: you can't start a command as {args[0]}"
        if name in ("pkill", "killall"):
            return WHY[name]
        if name == "xargs" and "kill" in args:
            return WHY["xargs-kill"]
        if name == "osascript":
            text = " ".join(args)
            for m in SHELL_STRING.finditer(text):
                inner = m.group(1)
                if inner is None:
                    return WHY["shell-script"]
                why = verdict(inner.replace('\\"', '"').replace("\\\\", "\\"))
                if why:
                    return why
            if "chrome" in text and re.search(r"\b(quit|close)\b", text):
                return WHY["chrome-script"]
            if re.search(r"tell application\s*\(", text) and re.search(r"\b(quit|close)\b", text):
                return WHY["chrome-script"]
        if name == "osascript" and "quit" in " ".join(args) and "chrome" in " ".join(args):
            return WHY["osascript"]
        debug = any(a.startswith("--remote-debugging-port") for a in args)
        if debug and name in CHROMES:
            return WHY["debug-port"]
        if debug and name == "open" and any("chrom" in a for a in args):
            return WHY["debug-port"]
        if name in OWNER_TOOLS:
            why = owner_tool_verdict(name, args, me)
            if why:
                return why
        if name in HUMAN_TOOLS:
            return WHY["human"]
        if name == "rm" and _recursive(args) and any(_protected(x) for x in args if not x.startswith("-")):
            return WHY["rm-home"]
        me_ = me
        if me_ and (name in ("pbcopy", "pbpaste") or (name == "osascript" and "the clipboard" in " ".join(args))):
            return WHY["clipboard"]
        if me_ and (name == "simctl" or (name == "xcrun" and args[:1] == ["simctl"]) or name == "xcodebuild"):
            why = sim_verdict(name, args, me_)
            if why:
                return why
        why = app_verdict(name, args)
        if why:
            return why
        if name == "osascript" and _sends(" ".join(args)) and not _approved(command, me):
            return WHY["send"]
        if _gui_command(name, args):
            why = WHY["approval-up"] if _approval_up() else WHY["human-active"] if human_active() else screen_verdict(foreground=True)
            if why:
                return why
        if any("chrome-devtools-mcp" in x for x in [name] + args) and "--autoconnect" in args:
            return WHY["human-browser"]
        if any("@playwright/mcp" in x for x in [name] + args) and "--extension" in args:
            return WHY["human-browser"]
        if name == "open" or name.endswith("chrome") or name.endswith("chromium"):
            why = _sensitive_verdict([x for x in args if "://" in x])
            if why:
                return why
    if re.search(r"\blaunch_by=['\"]?human\b", low):          # export LAUNCH_BY=human; ./agent-launcher.sh
        return WHY["human"]
    if killed_groups(cmds):
        return WHY["kill-group"]
    killing = "kill" in names or any(n == "xargs" and "kill" in a for n, a in cmds)
    if killing and names & {"pgrep", "pidof", "ps", "lsof"}:
        return WHY["search-kill"]
    if names & PORT_KILLERS or any(a and a[0] in PORT_KILLERS for n, a in cmds if n in ("npx", "pnpx", "bunx", "pnpm", "yarn")) \
            or any(n == "fuser" and any(x.startswith("-") and "k" in x for x in a) for n, a in cmds):
        return WHY["port-kill"]
    return port_verdict(claimed_ports(low, cmds)) or kill_verdict(cmds) or cdp_verdict(low)


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
            elif name.startswith("python") and a == "http.server":
                got |= {x for x in args[i + 1:] if x.isascii() and x.isdigit()}
            elif name == "php" and a == "-s" and ":" in nxt:
                got.add(nxt.rsplit(":", 1)[1])
            elif name in ("nc", "ncat", "netcat", "socat") and a.isascii() and a.isdigit():
                got.add(a)
            elif name == "socat" and "listen:" in a:
                got.add(re.split(r"[,:]", a.split("listen:", 1)[1])[0])
            elif a in ("-p", "--listen", "-l") and nxt.isascii() and nxt.isdigit() and (
                    name in ("next", "serve", "vite", "nuxt", "astro", "remix", "http-server", "live-server", "hugo", "jekyll")
                    or (name in ("npx", "pnpx", "bunx") and args[:1] and args[0] in ("next", "serve", "vite", "http-server"))):
                got.add(nxt)
    return sorted({int(p) for p in got if str(p).isascii() and str(p).isdigit() and 1 <= int(p) <= 65535})


def _port_owner():
    return _load_beside("rainbow_port_owner", "port-owner.py")


def _load_beside(modname, file):
    import importlib.machinery
    import importlib.util
    path = os.path.join(os.path.dirname(os.path.realpath(__file__)), file)
    loader = importlib.machinery.SourceFileLoader(modname, path)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


PROTECTED = {"/", "/*", "~", "~/", "~/*", "$home", "$home/", "$home/*", "${home}", "${home}/", "${home}/*", "/users", "/users/*",
             "/system", "/library", "/applications", "/usr", "/bin", "/sbin", "/etc", "/var", "/private", "/opt"}
HOME_DIRS = {"library", "documents", "desktop", "downloads", "pictures", "movies", "music", "applications", "bin", ".ssh",
             ".rainbowomma", ".config", "icloud drive", "library/mobile documents"}


def _recursive(args):
    return any(a in ("--recursive", "-r", "-R") or (a.startswith("-") and not a.startswith("--") and "r" in a.lower()) for a in args)


def _protected(target):
    raw = re.sub(r"(/\.)+/?$", "/", target.strip())                    # ~/. and ~/./ are ~
    raw = re.sub(r"/+", "/", raw)
    t = raw.rstrip("/") + ("/" if raw.endswith("/") and raw != "/" else "")
    if t in PROTECTED or raw in PROTECTED or re.fullmatch(r"/users/[^/]+/?\*?", raw):
        return True
    m = re.fullmatch(r"(?:~|\$home|\$\{home\}|/users/[^/]+)/(.+?)/?\*?", raw)
    return bool(m and m.group(1).rstrip("/") in HOME_DIRS)


GUI_WORDS = ("keystroke", "key code", " click", "click at", "set frontmost")
READ_ONLY_ACTIONS = re.compile(r"^(screenshot|take_screenshot|get_\w+|list_\w+|\w+_state|start_session|end_session|zoom|wait)$")


def _gui_command(name, args):
    """a shell command that types or clicks into whatever window is in front"""
    if name == "cliclick":
        return True
    text = " ".join(args)
    return name == "osascript" and "system events" in text and any(w in text for w in GUI_WORDS)


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


def human_active():
    idle = human_idle_s()
    return idle is not None and idle < float(os.environ.get("RAINBOW_HUMAN_IDLE_S") or 5)


URL_HOST = re.compile(r"^[a-z][a-z0-9+.-]*://([^/:?#\s]+)", re.I)
NAV_ACTION = re.compile(r"navigate|goto|new_page|open|new_tab|url", re.I)


def _host_sensitive(host, sites):
    host = host.lower().rstrip(".")
    return next((d for d in sites if host == d or host.endswith("." + d)), None)


def human_present():
    idle = human_idle_s()
    return idle is not None and idle < float(os.environ.get("RAINBOW_HUMAN_PRESENT_S") or 120)


def auth_verdict(hosts):
    """authSites (optional): one agent at a time signs in — another agent's browser stays off the site until it is free"""
    try:
        sites = _port_owner().BO.auth_sites()
        if not sites:
            return None
        ao = _load_beside("rainbow_auth_owner", "auth-owner.py")
    except Exception:
        return None
    me = _me()
    for h in hosts:
        site = ao.covered(h, sites)
        if not site:
            continue
        held = ao.holder(site)
        if not me:
            return f"{site} is signed in to by one agent at a time — this agent has no name (as-agent <name> …)"
        if held != me:
            return (f"{held} is signing in to {site} right now — wait, `auth-owner lease {me} {site} --wait 120`" if held else
                    f"{site} is signed in to by one agent at a time — take it first: `auth-owner lease {me} {site}`, "
                    f"and `auth-owner release {me} {site}` when you're done")
    return None


def _sensitive_verdict(urls):
    hosts = [m.group(1) for u in urls for m in [URL_HOST.match(u.strip())] if m]
    if not hosts:
        return None
    why = auth_verdict(hosts)
    if why:
        return why
    try:
        sites = _port_owner().BO.sensitive_sites()
    except Exception:
        return None
    for h in hosts:
        d = _host_sensitive(h, sites)
        if d and not human_present():
            return (f"{h} is a sensitive site ({d}) — an agent goes there only while the human is at the Mac "
                    f"(used it in the last {int(float(os.environ.get('RAINBOW_HUMAN_PRESENT_S') or 120))} s); ask the human")
    return None


def browser_tool_verdict(event):
    """a browser MCP tool navigating to a sensitive site while the human is away"""
    name = str(event.get("tool_name") or event.get("toolName") or "")
    action = re.split(r"__|\.|/", name)[-1]
    if not NAV_ACTION.search(action):
        return None
    ti = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    return _sensitive_verdict([str(v) for k, v in ti.items() if k.lower() in ("url", "uri", "href") and isinstance(v, str)])


def is_paused():
    root = os.path.expanduser(os.environ.get("RAINBOW_HOME") or os.path.join(os.path.expanduser("~"), ".rainbowomma"))
    return os.path.lexists(os.path.join(root, "state", "paused.json"))     # a planted dangling link still means paused


def gui_tool_verdict(event):
    """an MCP computer-use action (click, type, key, scroll …) while the human is at the keyboard or mouse"""
    name = str(event.get("tool_name") or event.get("toolName") or "")
    if not re.search(r"cua|computer", name, re.I):
        return None
    action = re.split(r"__|\.|/", name)[-1].lower()
    if READ_ONLY_ACTIONS.search(action):
        return None
    if _approval_up():
        return WHY["approval-up"]
    if human_active():
        return WHY["human-active"]
    return screen_verdict(foreground=not re.search(r"cua", name, re.I))      # Cua drives apps in the background


APP_REF = re.compile(r'(?:application|process|app) "([^"]+)"')
APP_KEYS = ("app", "app_name", "application", "bundle_id", "bundle", "name", "process")


def _denied():
    me = (os.environ.get("RAINBOW_AGENT") or "").strip().lower() or None
    try:
        return set(_port_owner().BO.denied_apps(me))
    except Exception:
        return set()


def app_verdict(name, args):
    """AppleScript to, open -a of, an app the agent may not drive (terminals, System Settings, Keychain … — deniedApps)"""
    apps = []
    if name == "osascript":
        apps = [m.group(1) for m in APP_REF.finditer(" ".join(args)) if m.group(1) != "system events"]
    elif name == "open":
        apps = [args[i + 1] for i, a in enumerate(args[:-1]) if a in ("-a", "-b")]
    if not apps:
        return None
    bad = _denied() & {a.strip().lower() for a in apps}
    return f"an agent may not drive {sorted(bad)[0]} (deniedApps in browsers.json) — ask the human" if bad else None


def app_tool_verdict(event):
    """a computer-use action aimed at a denied app (its app / bundle / process argument)"""
    name = str(event.get("tool_name") or event.get("toolName") or "")
    if not re.search(r"cua|computer", name, re.I):
        return None
    ti = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    named = {str(v).strip().lower() for k, v in ti.items() if k.lower() in APP_KEYS and isinstance(v, str)}
    named |= {n.rsplit(".", 1)[-1] for n in named if n.startswith("com.")}       # com.apple.Terminal → terminal
    bad = _denied() & named if named else set()
    return f"an agent may not drive {sorted(bad)[0]} (deniedApps in browsers.json) — ask the human" if bad else None


UDID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def sim_verdict(name, args, me):
    """an agent's simctl / xcodebuild must name its own simulator — never `booted`, a shared device or another agent's"""
    if name != "xcodebuild":
        if "booted" in args:
            return WHY["sim-booted"]
        targets = [a for a in args if UDID.fullmatch(a) or a.startswith("rainbowomma-")]
    else:
        dest = " ".join(args[i + 1] for i, a in enumerate(args[:-1]) if a == "-destination")
        if "simulator" not in dest and "id=" not in dest:
            return None
        targets = [m.group(1) for m in re.finditer(r"(?:id|name)=([^,'\"]+)", dest)]
        if not targets:
            return None
    try:
        so = _load_beside("rainbow_sim_owner", "sim-owner.py")
        devs = so.devices()
    except Exception:
        return None
    for tgt in targets:
        owner = so.owner_of(tgt, devs)
        if owner != me and (owner or name == "xcodebuild"):
            whose = f"{owner}'s" if owner else "a shared one"
            return f"simulator {tgt} is {whose}, not {me}'s — use your own: `sim-owner lease {me}`"
    return None


SEND = re.compile(r'tell application "?(messages|mail)"?.*\b(send|outgoing message)\b', re.S)


def _sends(text):
    return bool(SEND.search(text))


def _approved(command, me=""):
    try:
        return bool(_load_beside("rainbow_approve", "rainbowomma-approve.py").consume(command, me))
    except Exception:
        return False


def _approval_up():
    try:
        return _load_beside("rainbow_approve", "rainbowomma-approve.py").pending()
    except Exception:
        return False


def screen_verdict(foreground):
    """the human's takeover stops every GUI action; a foreground one also needs the screen lease (taken here, 15 s, renewed)"""
    try:
        so = _load_beside("rainbow_screen_owner", "screen-owner.py")
        cur = so.holder()
    except Exception:
        return None
    if cur and cur["holder"] == "human":
        return WHY["human-screen"]
    if not foreground:
        return None
    me = (os.environ.get("RAINBOW_AGENT") or "").strip().lower()
    if not me:
        return f"the screen is {cur['holder']}'s right now — wait for it" if cur else None
    ok, lease = so.try_take(me, so.AUTO_TTL_S, auto=True)
    if ok:
        return None
    left = max(1, int(float(lease["until"]) - time.time()))
    return (f"the screen is {lease['holder']}'s for {left} s more — wait, or `screen-owner take {me} --wait 60` "
            f"(an agent that drives in the background, like Cua, doesn't need it)")


CDP_URL = re.compile(r"[\w.\]-]:(92(?:2[2-9]|[3-9]\d))\b")         # any host: 127.1, [::1], 0.0.0.0, localhost. …


def cdp_verdict(low):
    """with RAINBOW_AGENT set: a CDP endpoint of ANOTHER agent's browser (--browserUrl, --cdp-endpoint, curl …) is not yours"""
    me = (os.environ.get("RAINBOW_AGENT") or "").strip().lower()
    ports = {int(p) for p in CDP_URL.findall(low)}
    if not me or not ports:
        return None
    try:
        reg = _port_owner().registry()
    except Exception:
        return None
    owner = {a["port"]: n for n, a in reg.items()}
    for p in sorted(ports):
        if p in owner and owner[p] != me:
            return f"port {p} is {owner[p]}'s browser, not {me}'s — drive your own: `browser-owner mcp-config {me}`"
    return None


def _kill_targets(args):
    """a kill's targets: after one signal option (-9, -TERM, -s SIG, -n N) or `--`, every word is a target — -1 too"""
    i = 0
    if i < len(args) and args[i].strip() in ("-s", "-n"):
        i += 2
    elif i < len(args) and args[i].strip().startswith("-") and args[i].strip() not in ("--", "-l", "-L"):
        i += 1
    if i < len(args) and args[i].strip() == "--":
        i += 1
    return [a.strip() for a in args[i:]]


def killed_groups(cmds):
    """kill -1, kill 0, kill -- -PGID: whole process groups"""
    return any(t in ("0", "-1") or (t.startswith("-") and t[1:].isascii() and t[1:].isdigit())
               for name, args in cmds if name == "kill" for t in _kill_targets(args))


def killed_pids(cmds):
    """the literal process ids a plain `kill` names (signals and $VARIABLES are skipped)"""
    return [int(t) for name, args in cmds if name == "kill" for t in _kill_targets(args) if t.isascii() and t.isdigit()]


def kill_verdict(cmds):
    """with RAINBOW_AGENT set: only that agent's own processes. Without it: never another agent's"""
    pids = []
    for pid in killed_pids(cmds):
        try:
            os.kill(pid, 0)
            pids.append(pid)
        except ProcessLookupError:
            continue                                  # no such process: kill fails on its own
        except (PermissionError, OverflowError, ValueError):
            pids.append(pid)
    if not pids:
        return None
    try:
        pc = _load_beside("rainbow_proc_owner", "proc-owner.py")
        reg = pc.registry()
        _, own = pc.ownership(reg)
    except Exception as exc:                          # whose it is can't be told: no
        return f"whose process {pids[0]} is can't be checked ({type(exc).__name__}) — `proc-owner kill <pid> --by <you>`"
    me = (os.environ.get("RAINBOW_AGENT") or "").strip().lower()
    for pid in pids:
        if pid not in own:
            continue                                  # no such process: kill fails on its own
        owner, via = own[pid]
        if not me:                                    # who is asking can't be told, so nothing is provably theirs
            return (f"process {pid} can't be shown to be yours — this agent has no name; start it with `as-agent <name> …` "
                    f"(or RAINBOW_AGENT in its settings), then `proc-owner kill <pid> --by <name>`")
        if owner != me:
            whose = "not provably any agent's" if via == "none" else f"{owner}'s (by {via})"
            return f"process {pid} is {whose}, not yours — `proc-owner kill <pid> --by {me}` stops only your own"
    return None


def track(me):
    """the agent framework's own process becomes the agent's root (once), and what runs under it is recorded every 10 s —
    so its processes stay its own even where the OS hides their environment (macOS 27)"""
    if os.environ.get("RAINBOW_TRACK_ROOT") == "off":
        return
    try:
        pc = _load_beside("rainbow_proc_owner", "proc-owner.py")
        rows = pc.processes()
        root = pc.framework_root(os.getpid(), rows)
        fresh = root is not None and pc.register(me, root, rows) and pc.load_roots().get(root, {}).get("agent") == me
        f = pc.roots_file()
        if fresh and (not f.exists() or time.time() - f.stat().st_mtime > 10):
            pc.ownership(pc.registry(), rows, keep=True)
    except Exception:
        pass


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


FILE_KEYS = ("file_path", "path", "notebook_path", "filepath", "target_file", "filename", "absolute_path", "dir_path")
PATCH_FILE = re.compile(r"^\*\*\* (?:add file|update file|delete file|move to): (.+?)\s*$", re.I | re.M)   # Codex / Hermes patches
READ_TOOL = re.compile(r"(read|view|glob|grep|ls|list|search|pre_read_code|beforereadfile).*")


def _file_paths(event):
    """every path a file tool names: its path fields (tool_input; Cursor's top level; Windsurf's tool_info) and the files
    a patch adds, updates, deletes or moves to (apply_patch, Hermes patch — also a patch run through the shell)"""
    got = []
    for d in (_maybe_json(event.get("tool_input")), event, event.get("tool_info")):
        if not isinstance(d, dict):
            continue
        got += [d[k] for k in FILE_KEYS if isinstance(d.get(k), str) and d[k]]
        got += [m.group(1).strip() for v in d.values() if isinstance(v, str) and "*** " in v for m in PATCH_FILE.finditer(v)]
    cwd = event.get("cwd") if isinstance(event.get("cwd"), str) else None
    return [os.path.join(cwd, os.path.expanduser(x)) if cwd and not os.path.isabs(os.path.expanduser(x)) else x for x in got]


def file_verdict(event):
    """a file tool (Write, Edit, Read, a patch …) aimed at RainbowOMMA's own state or the human's Chrome profile"""
    name = str(event.get("tool_name") or event.get("toolName") or event.get("agent_action_name")
               or event.get("hook_event_name") or "").lower()
    reading = bool(READ_TOOL.fullmatch(name))
    for v in _file_paths(event):
        low = os.path.realpath(os.path.expanduser(v)).lower() + " " + v.lower()
        if HUMAN_CHROME.search(low):
            return WHY["human-chrome"]
        why = cdp_dir_verdict(low, _me())
        if why:
            return why
        if STATE_WORDS.search(low) and not reading:
            return WHY["rainbow-state"]
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
    me = (os.environ.get("RAINBOW_AGENT") or "").strip().lower()
    if me:
        track(me)
    try:
        cmds = commands(event)
    except Exception:
        cmds = []
    for cmd in [None] + cmds:
        try:
            why = (file_verdict(event) or app_tool_verdict(event) or gui_tool_verdict(event) or browser_tool_verdict(event)) \
                if cmd is None else verdict(cmd)
            if cmd is None and not why and is_paused() and (cmds or event.get("tool_name") or event.get("toolName")):
                why = WHY["paused"]
        except Exception as exc:                       # can't tell → no
            why = f"{WHY['guard-error']} ({type(exc).__name__})"
        if why:
            try:
                import rainbow_receipts
                me = (os.environ.get("RAINBOW_AGENT") or "").strip().lower() or None
                rainbow_receipts.write("guard", "blocked", me, me, "blocked", why=why,
                                       command=cmd or str(event.get("tool_name") or event.get("toolName") or ""))
            except Exception:
                pass
            msg = f"Blocked by RainbowOMMA: {why}. {HELP}"
            if fmt == "cline":
                print(json.dumps({"cancel": True, "errorMessage": msg}))
                return 0
            print(msg, file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
