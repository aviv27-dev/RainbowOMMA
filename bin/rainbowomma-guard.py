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
        if name == "rm" and _recursive(args) and any(_protected(x) for x in args if not x.startswith("-")):
            return WHY["rm-home"]
        me_ = (os.environ.get("RAINBOW_AGENT") or "").strip().lower()
        if me_ and (name in ("pbcopy", "pbpaste") or (name == "osascript" and "the clipboard" in " ".join(args))):
            return WHY["clipboard"]
        if me_ and (name == "simctl" or (name == "xcrun" and args[:1] == ["simctl"]) or name == "xcodebuild"):
            why = sim_verdict(name, args, me_)
            if why:
                return why
        if name == "osascript" and _sends(" ".join(args)) and not _approved(command):
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
            elif name.startswith("python") and a == "http.server" and nxt.isdigit():
                got.add(nxt)
    return sorted({int(p) for p in got if str(p).isdigit() and 1 <= int(p) <= 65535})


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


def _recursive(args):
    return any(a in ("--recursive", "-r", "-R") or (a.startswith("-") and not a.startswith("--") and "r" in a.lower()) for a in args)


def _protected(target):
    t = target.strip().rstrip("/") + ("/" if target.strip().endswith("/") and target.strip() != "/" else "")
    return t in PROTECTED or target.strip() in PROTECTED or bool(re.fullmatch(r"/users/[^/]+/?\*?", target.strip()))


GUI_WORDS = ("keystroke", "key code", " click", "click at", "set frontmost")
READ_ONLY_ACTIONS = re.compile(r"(screenshot|^get_|^list_|_state$|^start_session$|^end_session$|^zoom$|^wait$)")


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


def _sensitive_verdict(urls):
    hosts = [m.group(1) for u in urls for m in [URL_HOST.match(u.strip())] if m]
    if not hosts:
        return None
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
    return os.path.exists(os.path.join(root, "state", "paused.json"))


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


def _approved(command):
    try:
        return bool(_load_beside("rainbow_approve", "rainbowomma-approve.py").consume(command))
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


CDP_URL = re.compile(r"(?:127\.0\.0\.1|localhost):(92(?:2[2-9]|[3-9]\d))\b")


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


def killed_pids(cmds):
    """the literal process ids a plain `kill` names (signals and $VARIABLES are skipped)"""
    got, skip = [], False
    for name, args in cmds:
        if name != "kill":
            continue
        for a in args:
            if skip:
                skip = False
            elif a in ("-s", "-n"):
                skip = True
            elif a.isdigit():
                got.append(int(a))
    return got


def kill_verdict(cmds):
    """with RAINBOW_AGENT set: only that agent's own processes. Without it: never another agent's"""
    pids = killed_pids(cmds)
    if not pids:
        return None
    try:
        pc = _load_beside("rainbow_proc_owner", "proc-owner.py")
        reg = pc.registry()
        _, own = pc.ownership(reg)
    except Exception:
        return None
    me = (os.environ.get("RAINBOW_AGENT") or "").strip().lower()
    for pid in pids:
        owner, via = own.get(pid, ("human", "none"))
        if pid not in own:
            continue                                  # no such process: kill fails on its own
        if (me and owner != me) or (not me and owner != "human"):
            hint = f"`proc-owner kill <pid> --by {me}` stops your own" if me else "`proc-owner whose <pid>` says whose a process is"
            return f"process {pid} is {owner}'s (by {via}), not yours — {hint}"
    return None


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
    for cmd in [None] + commands(event):
        why = (gui_tool_verdict(event) or browser_tool_verdict(event)) if cmd is None else verdict(cmd)
        if cmd is None and not why and is_paused() and (commands(event) or event.get("tool_name") or event.get("toolName")):
            why = WHY["paused"]
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
