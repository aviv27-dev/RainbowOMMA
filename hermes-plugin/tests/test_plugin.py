#!/usr/bin/env python3
"""Tests of the Hermes plugin. Run: python3 hermes-plugin/tests/test_plugin.py

No Hermes, no Chrome, no Office: a fake plugin context, fake owners, and a temp state folder. The guard's helper process
is real (it is the vendored guard), with tracking off and a temp home.
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent / "rainbowomma"
spec = importlib.util.spec_from_file_location("rainbowomma", PLUGIN / "__init__.py", submodule_search_locations=[str(PLUGIN)])
rb_mod = importlib.util.module_from_spec(spec)
sys.modules["rainbowomma"] = rb_mod
spec.loader.exec_module(rb_mod)
from rainbowomma import core, guard_hook, housekeeping, status, tool_defs  # noqa: E402

PASSED = FAILED = 0


def check(name, ok, detail=""):
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print(f"✅ {name}")
    else:
        FAILED += 1
        print(f"❌ {name}  — {detail!r}"[:600])


class Ctx:
    def __init__(self, profile="alpha", settings=None):
        self.profile_name, self.settings = profile, settings or {}
        self.tools, self.hooks, self.commands, self.unload, self.sections = {}, {}, {}, [], {}

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def register_tool(self, name, toolset, schema, handler, **kw):
        self.tools[name] = {"toolset": toolset, "schema": schema, "handler": handler, **kw}

    def register_hook(self, name, cb, **kw):
        self.hooks[name] = cb

    def register_command(self, name, handler, **kw):
        self.commands[name] = handler

    def register_system_prompt_section(self, id, content, **kw):
        self.sections[id] = content

    def on_unload(self, cb):
        self.unload.append(cb)


tmp = Path(tempfile.mkdtemp(prefix="rb-plugin-"))

# ---- identity ---------------------------------------------------------------------------------------------------------
check("identity: the agent is the Hermes profile; the default profile is `hermes`; odd names are made safe",
      [core.agent_name(p) for p in ("alpha", "default", "custom", "", "My Agent!", "9lives")] ==
      ["alpha", "hermes", "hermes", "hermes", "my-agent", "agent-9lives"] and core.agent_name("alpha", "Bravo") == "bravo")
check("identity: the process's own profile comes from its HERMES_HOME",
      [core.process_profile(e) for e in ({}, {"HERMES_HOME": "/u/x/.hermes"}, {"HERMES_HOME": "/u/x/.hermes/profiles/charlie"},
                                         {"HERMES_HOME": "/srv/hermes-data"})] == ["default", "default", "charlie", "custom"])
r = core.Rainbow(lambda k, d=None: {"home": str(tmp / "s1")}.get(k, d), lambda: "alpha")
old_home = os.environ.pop("HERMES_HOME", None)
os.environ["HERMES_HOME"] = "/u/x/.hermes/profiles/alpha"
alone = (r.shared_process(), r.guard_env().get("RAINBOW_TRACK_ROOT"), r.mark_command("npm run dev"))
os.environ["HERMES_HOME"] = "/u/x/.hermes"                       # the default profile's gateway serving `alpha` too
shared = (r.shared_process(), r.guard_env().get("RAINBOW_TRACK_ROOT"), r.mark_command("npm run dev"))
check("shared process: a profile alone in its process is tracked by ancestry and its commands are left as they are",
      alone == (False, None, None), alone)
check("shared process: served by another profile's gateway → never registered as a root, and each command carries the mark",
      shared[0] is True and shared[1] == "off" and shared[2].startswith("export RAINBOW_AGENT=alpha RAINBOW_HOME=")
      and shared[2].endswith("; npm run dev") and r.mark_command("") is None
      and r.mark_command("RAINBOW_AGENT=x ls") is None, shared)
if old_home is None:
    os.environ.pop("HERMES_HOME", None)
else:
    os.environ["HERMES_HOME"] = old_home

# ---- the registry row -------------------------------------------------------------------------------------------------
row = core.new_row("alpha", {}, tmp, free=lambda p: True, taken=set())
row2 = core.new_row("bravo", {"alpha": row}, tmp, free=lambda p: True, taken=set())
row3 = core.new_row("carol", {"alpha": row, "bravo": row2}, tmp, free=lambda p: p != 9242, taken={9243})
check("registry: a new agent gets the first free colour and port; a port in use or another install's is skipped",
      (row["port"], row["color"], row2["port"], row2["color"], row3["port"], row3["color"]) ==
      (9240, "#FB8C00", 9241, "#1E88E5", 9244, "#43A047") and row["idleMinutes"] == 30
      and row["profile"].endswith("/profiles/alpha") and " " not in row["profile"], (row, row2, row3))
check("registry: an explicit colour is kept; idle 0 leaves the browser running",
      core.new_row("d", {}, tmp, "#123abc", 0, free=lambda p: True, taken=set()) ==
      {"label": "D", "port": 9240, "profile": str(tmp / "profiles" / "d"), "color": "#123ABC"})
r1 = core.Rainbow(lambda k, d=None: {"home": str(tmp / "s2")}.get(k, d), lambda: "alpha")
made = r1.ensure_row()
reg = json.loads((tmp / "s2" / "browsers.json").read_text())
reg["agents"]["alpha"]["color"] = "#000001"                      # the human edits the registry
(tmp / "s2" / "browsers.json").write_text(json.dumps(reg))
again = core.Rainbow(lambda k, d=None: {"home": str(tmp / "s2")}.get(k, d), lambda: "alpha").ensure_row()
r2 = core.Rainbow(lambda k, d=None: {"home": str(tmp / "s2")}.get(k, d), lambda: "bravo")
r2.ensure_row()
reg = json.loads((tmp / "s2" / "browsers.json").read_text())
check("registry: created on first use with the tab sweep on; an existing row is never rewritten; a second profile joins it",
      made["port"] in core.CDP_PORTS and again["color"] == "#000001" and set(reg["agents"]) == {"alpha", "bravo"}
      and reg["agents"]["bravo"]["port"] != reg["agents"]["alpha"]["port"] and reg["tabSweep"] == {"mode": "apply"}, reg)
(tmp / "s3").mkdir()
(tmp / "s3" / "browsers.json").write_text("{not json")
ok, out = core.Rainbow(lambda k, d=None: {"home": str(tmp / "s3")}.get(k, d), lambda: "alpha").run("port-owner.py", "list")
check("registry: a broken registry is reported, not replaced", ok is False and "not valid JSON" in out.get("why", "")
      and (tmp / "s3" / "browsers.json").read_text() == "{not json", out)

# ---- answers ----------------------------------------------------------------------------------------------------------
check("answers: the owner's last JSON line; plain text; a silent success; a crash",
      core.parse_answer('note\n{"status": "leased", "port": 41000}\n', "", 0) == {"status": "leased", "port": 41000}
      and core.parse_answer("hello\n", "", 0) == {"status": "done", "text": "hello"}
      and core.parse_answer("", "", 0) == {"status": "done"}
      and core.parse_answer("", "Traceback …", 1) == {"status": "failed", "why": "Traceback …"}
      and core.parse_answer("", "", 3) == {"status": "failed", "why": "exit 3"})

# ---- the tool table ---------------------------------------------------------------------------------------------------
manifest = (PLUGIN / "plugin.yaml").read_text()
declared = re.findall(r"^  - (rainbow_\w+)$", manifest, re.M)
check("tools: plugin.yaml declares exactly the tools the plugin registers, all under the rainbow_ prefix",
      declared == tool_defs.NAMES and len(set(declared)) == len(declared) == 30, declared)
SAMPLE = {"url": "https://example.com", "ids": ["A", "B"], "port": 41000, "pid": 4242, "site": "accounts.example.com",
          "file": "/tmp/a.docx", "text": "hello", "name": "web"}
built, bad = {}, []
for name, desc, params, script, argv, opts in tool_defs.TOOLS:
    if not (PLUGIN / "vendor" / script).exists() or len(desc) < 20 or params.get("type") != "object":
        bad.append(name)
    need = {k: SAMPLE[k] for k in params.get("required", [])}
    built[name] = [script, *argv("alpha", need)]
check("tools: every tool is one owner call that exists, with a description and an object schema", not bad, bad)
check("tools: the owner calls are the ones the owners document",
      built["rainbow_start_browser"] == ["browser-owner.py", "start", "alpha", "--by", "alpha"]
      and built["rainbow_open_url"] == ["browser-owner.py", "open", "alpha", "https://example.com", "--by", "alpha"]
      and built["rainbow_keep_tabs"] == ["browser-owner.py", "job-keep", "alpha", "A", "B"]
      and built["rainbow_stop_process"] == ["proc-owner.py", "kill", "4242", "--by", "alpha"]
      and built["rainbow_lease_port"] == ["port-owner.py", "lease", "alpha", "--name", "default"]
      and built["rainbow_take_screen"] == ["screen-owner.py", "take", "alpha", "--minutes", "5.0", "--wait", "0.0"]
      and built["rainbow_convert_to_pdf"] == ["agent-office.py", "pdf", "--agent", "alpha", "/tmp/a.docx"]
      and built["rainbow_close_document"] == ["agent-office.py", "close", "--agent", "alpha", "/tmp/a.docx"], built)
argvs = {t[0]: t[4] for t in tool_defs.TOOLS}
check("tools: numbers are clamped and options are passed only when given",
      argvs["rainbow_take_screen"]("a", {"minutes": 999, "wait_seconds": -3}) == ["take", "a", "--minutes", "60.0", "--wait", "0.0"]
      and argvs["rainbow_lease_port"]("a", {"name": "api", "prefer": "41005"}) == ["lease", "a", "--name", "api", "--prefer", "41005"]
      and argvs["rainbow_release_port"]("a", {"all": True}) == ["release", "a", "--all"]
      and argvs["rainbow_tidy_tabs"]("a", {"apply": True}) == ["tabs", "a", "--apply"]
      and argvs["rainbow_open_document"]("a", {"file": "/x.pdf", "app": "preview"}) == ["open", "--agent", "a", "--app", "preview", "/x.pdf"])

hint = tool_defs.as_tools({"status": "ask", "keep": "keep any you still need: browser-owner job-keep alpha <id> … — the rest close: browser-owner job-close alpha",
                           "close": [{"title": "browser-owner job-close stays in a page title"}], "next": "run rainbowomma-doctor status"})
check("tools: an owner's hint names the tool, not its command line — and only in hint fields, never in data",
      hint["keep"] == "keep any you still need: rainbow_keep_tabs alpha <id> … — the rest close: rainbow_close_job_tabs alpha"
      and hint["close"][0]["title"].startswith("browser-owner") and hint["next"] == "run /rainbow", hint)
check("tools: every owner call a tool makes has its hint translation",
      not [f"{t[3][:-3].replace('agent-office', 'office-owner')} {t[4]('a', {k: SAMPLE[k] for k in t[2].get('required', [])})[0]}"
           for t in tool_defs.TOOLS
           if f"{t[3][:-3].replace('agent-office', 'office-owner')} {t[4]('a', {k: SAMPLE[k] for k in t[2].get('required', [])})[0]}" not in tool_defs.CLI_TO_TOOL])

# ---- register() -------------------------------------------------------------------------------------------------------
ctx = Ctx("alpha", {"home": str(tmp / "s4"), "housekeeping_minutes": 0})
was_mac, rb_mod.IS_MAC = rb_mod.IS_MAC, True
rb_mod.register(ctx)
check("register: 30 tools in one toolset, three hooks, /rainbow, a prompt section, cleanup on unload",
      list(ctx.tools) == tool_defs.NAMES and {t["toolset"] for t in ctx.tools.values()} == {"rainbowomma"}
      and set(ctx.hooks) == {"pre_tool_call", "on_session_start", "on_session_finalize"} and "rainbow" in ctx.commands
      and "rainbowomma.shared-mac" in ctx.sections and len(ctx.unload) == 2, (list(ctx.hooks), len(ctx.unload)))
hooks_declared = re.findall(r"^  - (pre_tool_call|on_\w+)$", manifest, re.M)
check("register: plugin.yaml declares exactly the hooks it registers", sorted(hooks_declared) == sorted(ctx.hooks), hooks_declared)
check("register: the prompt section names this agent and the tools, not another agent's name",
      "`alpha`" in ctx.sections["rainbowomma.shared-mac"]({}) and "rainbow_start_browser" in ctx.sections["rainbowomma.shared-mac"]({}))
out = json.loads(ctx.tools["rainbow_who_port"]["handler"]({}))
check("handlers: a missing argument is a failed answer, never an exception", out["status"] == "failed" and "bad arguments" in out["why"], out)
out = json.loads(ctx.tools["rainbow_lease_port"]["handler"]({"name": "web"}))
out2 = json.loads(ctx.tools["rainbow_lease_port"]["handler"]({"name": "web"}))
check("handlers: a real owner answers through the tool — a leased port is this agent's and stays the same by name",
      out.get("status") == "leased" and out.get("agent") == "alpha" and out.get("port") == out2.get("port"), (out, out2))
json.loads(ctx.tools["rainbow_clip_copy"]["handler"]({"text": "secret-ish ✓"}))
out = json.loads(ctx.tools["rainbow_clip_paste"]["handler"]({}))
check("handlers: the agent's own clipboard round-trips a text (through stdin, not the command line)", out == {"status": "done", "text": "secret-ish ✓"}, out)
other = Ctx("nonmac", {"home": str(tmp / "s5")})
rb_mod.IS_MAC = False
rb_mod.register(other)
check("register: off macOS only /rainbow exists, and it says why", not other.tools and not other.hooks
      and "macOS only" in other.commands["rainbow"](""), (list(other.tools), list(other.hooks)))
rb_mod.IS_MAC = True

# ---- the guard hook ---------------------------------------------------------------------------------------------------
class FakeWorker:
    def __init__(self, answer=None, boom=None):
        self.answer, self.boom, self.asked = answer, boom, []

    def ask(self, env, request):
        self.asked.append((env, request))
        if self.boom:
            raise self.boom
        return self.answer


env = {"RAINBOW_AGENT": "alpha"}
d_none = guard_hook.decide(FakeWorker({"why": None, "kind": "none"}), "terminal", {"command": "ls"}, env)
d_block = guard_hook.decide(FakeWorker({"why": "pkill … use `proc-owner kill <pid> --by <you>`", "kind": "block"}), "terminal", {"command": "pkill x"}, env)
d_send = guard_hook.decide(FakeWorker({"why": "sending …", "kind": "send"}), "terminal", {"command": "osascript …"}, env)
d_dead = guard_hook.decide(FakeWorker(boom=TimeoutError("late")), "terminal", {"command": "ls"}, env)
check("guard: nothing to say → the call runs", d_none is None)
check("guard: a refusal blocks, and its hint names the Hermes tool, not the command-line owner",
      d_block["action"] == "block" and "rainbow_stop_process" in d_block["message"] and "proc-owner" not in d_block["message"], d_block)
check("guard: a Messages/Mail send goes to Hermes's approval gate, not to a refusal",
      d_send["action"] == "approve" and d_send["rule_key"] == "rainbowomma.send", d_send)
check("guard: no answer from the guard is a refusal", d_dead["action"] == "block" and "can't tell" in d_dead["message"], d_dead)
w = FakeWorker({"paused": False})
check("guard: the plugin's own tools are only asked about the pause", guard_hook.decide(w, "rainbow_start_browser", {}, env) is None
      and w.asked[0][1] == {"ask": "paused"}
      and guard_hook.decide(FakeWorker({"paused": True}), "rainbow_start_browser", {}, env)["action"] == "block", w.asked)
check("guard: every command-line hint in the guard's reasons has a Hermes tool to name",
      "rainbow_close_document" in guard_hook.translate("close only the document you leased: `office-owner close --agent <you> <file>`")
      and "rainbow_lease_port" in guard_hook.translate("Take one of yours: `port-owner lease alpha`")
      and "rainbow_clip_copy" in guard_hook.translate("keep yours with `rainbowomma-clip copy|paste <you>`"))

genv = {"RAINBOW_AGENT": "alpha", "RAINBOW_HOME": str(tmp / "s4"), "BROWSER_OWNER_REGISTRY": str(tmp / "s4" / "browsers.json"),
        "RAINBOW_TRACK_ROOT": "off"}
worker = guard_hook.GuardWorker()
REFUSED = ["pkill -f rainbowomma-test-no-such-process", "killall rainbowomma-test-no-such-process",
           "osascript -e 'tell application \"Microsoft Word\" to quit'", "osascript -e 'quit app \"Microsoft Excel\"'",
           "osascript -e 'tell application \"Preview\" to close every window'", "python3 -m http.server 8000", "pbpaste"]
ALLOWED = ["ls -la", "git status", "echo hello", "osascript -e 'tell application \"Microsoft Word\" to get name of documents'",
           "npm test"]
got_refused = [guard_hook.decide(worker, "terminal", {"command": c}, genv) for c in REFUSED]
got_allowed = [guard_hook.decide(worker, "terminal", {"command": c}, genv) for c in ALLOWED]
check("guard (real helper): kills by pattern, quitting Word/Excel, closing Preview's windows, the human's port and clipboard are refused",
      all(d and d["action"] == "block" for d in got_refused), [c for c, d in zip(REFUSED, got_refused) if not d])
check("guard (real helper): ordinary commands, and reading from Word, run", all(d is None for d in got_allowed),
      [(c, d) for c, d in zip(ALLOWED, got_allowed) if d])
d = guard_hook.decide(worker, "terminal", {"command": "osascript -e 'tell application \"Messages\" to send \"hi\" to buddy \"x\"'"}, genv)
check("guard (real helper): a Messages send asks the human through Hermes", d and d["action"] == "approve", d)
d = guard_hook.decide(worker, "write_file", {"path": str(tmp / "s4" / "state" / "approvals.json"), "content": "{}"}, genv)
check("guard (real helper): a file tool aimed at RainbowOMMA's own state is refused", d and d["action"] == "block", d)
first_pid = worker._proc.pid
guard_hook.decide(worker, "terminal", {"command": "ls"}, genv)
same = worker._proc.pid == first_pid
guard_hook.decide(worker, "terminal", {"command": "ls"}, {**genv, "RAINBOW_AGENT": "bravo"})
check("guard (real helper): one helper serves call after call; another identity gets a helper of its own",
      same and worker._proc.pid != first_pid, (first_pid, worker._proc.pid))
worker._proc.kill()
worker._proc.wait()
d = guard_hook.decide(worker, "terminal", {"command": "ls"}, genv)
check("guard (real helper): a helper that died is replaced on the next call", d is None and worker._proc.poll() is None, d)
worker.stop()
check("guard (real helper): stop() ends the helper", worker._proc is None)
before = dict(os.environ)
guard_hook.decide(guard_hook.GuardWorker(), "terminal", {"command": "ls"}, genv)
check("guard: Hermes's own environment is never given an agent's identity (one gateway may serve several profiles)",
      not [k for k in os.environ if k.startswith(("RAINBOW_", "BROWSER_OWNER_")) and k not in before], sorted(set(os.environ) - set(before)))
paused_env = {**genv, "RAINBOW_HOME": str(tmp / "s6"), "BROWSER_OWNER_REGISTRY": str(tmp / "s4" / "browsers.json")}
subprocess.run([sys.executable, "-I", str(PLUGIN / "vendor" / "rainbowomma-pause.py"), "on"], capture_output=True,
               env={**os.environ, **{k: v for k, v in paused_env.items() if k != "RAINBOW_AGENT"}})
pw = guard_hook.GuardWorker()
d1 = guard_hook.decide(pw, "terminal", {"command": "ls"}, paused_env)
d2 = guard_hook.decide(pw, "rainbow_start_browser", {}, paused_env)
pw.stop()
check("guard: while the human paused the agents, every call is refused — the plugin's own tools too",
      d1 and d1["action"] == "block" and "paused" in d1["message"] and d2 and d2["action"] == "block", (d1, d2))

# ---- the hook as Hermes calls it --------------------------------------------------------------------------------------
os.environ["HERMES_HOME"] = "/u/x/.hermes"                       # shared: served by the default profile's gateway
got = ctx.hooks["pre_tool_call"](tool_name="terminal", args={"command": "echo hi"}, task_id="t1")
blocked = ctx.hooks["pre_tool_call"](tool_name="terminal", args={"command": "pkill -f rainbowomma-test-no-such-process"})
check("hook: in a shared process an allowed shell command is passed on with the agent's mark; a refused one is blocked, unmarked",
      got and got["action"] == "modify" and got["args"]["command"].endswith("; echo hi") and "RAINBOW_AGENT=alpha" in got["args"]["command"]
      and blocked["action"] == "block", (got, blocked))
off = Ctx("alpha", {"home": str(tmp / "s4"), "guard": False, "housekeeping_minutes": 0})
rb_mod.register(off)
check("hook: guard: false turns the refusals off (the tools stay)",
      off.hooks["pre_tool_call"](tool_name="terminal", args={"command": "pkill -f rainbowomma-test-no-such-process"}) is None and len(off.tools) == 30)
for c in (ctx, off):
    for cb in c.unload:
        cb()
if old_home is None:
    os.environ.pop("HERMES_HOME", None)
else:
    os.environ["HERMES_HOME"] = old_home


# ---- housekeeping -----------------------------------------------------------------------------------------------------
class FakeRainbow:
    me = "alpha"

    def __init__(self, **settings):
        self.settings, self.calls = {"tab_cleanup": "apply", "housekeeping_minutes": 5, **settings}, []

    def setting(self, key):
        return self.settings[key]

    def run(self, script, *args, **kw):
        self.calls.append([script, *args])
        return True, {"status": "ok"}


fr = FakeRainbow()
housekeeping.Housekeeper(fr).idle_pass()
check("housekeeping: the idle pass sweeps this agent's tabs, runs the idle reaper, and closes expired leases and idle apps",
      fr.calls == [["browser-owner.py", "tabs", "alpha", "--apply"], ["browser-owner.py", "heal", "--scheduled"],
                   ["agent-office.py", "sweep", "--scheduled"]], fr.calls)
fr = FakeRainbow(tab_cleanup="dry-run")
housekeeping.Housekeeper(fr).idle_pass()
fo = FakeRainbow(tab_cleanup="off")
housekeeping.Housekeeper(fo).idle_pass()
check("housekeeping: tab_cleanup dry-run only reports, off skips the tab sweep",
      fr.calls[0] == ["browser-owner.py", "tabs", "alpha"] and [c[1] for c in fo.calls] == ["heal", "sweep"], (fr.calls, fo.calls))
fr = FakeRainbow()
housekeeping.Housekeeper(fr).session_end("s1")
check("housekeeping: a session's end closes the job's tabs, frees the screen, reaps orphaned servers and sweeps documents",
      [c[:2] for c in fr.calls] == [["browser-owner.py", "job-close"], ["screen-owner.py", "release"], ["proc-owner.py", "reap"],
                                    ["agent-office.py", "sweep"]], fr.calls)
k = housekeeping.Housekeeper(FakeRainbow(housekeeping_minutes=0))
k2 = housekeeping.Housekeeper(FakeRainbow())
check("housekeeping: the timer starts once, not at all with housekeeping_minutes 0, and stops on unload",
      k.start() is False and k2.start() is True and k2.start() is False and (k2.stop() or k2._thread is None))

# ---- status -----------------------------------------------------------------------------------------------------------
snap = {"me": "alpha", "paused": True, "agents": [
    {"agent": "alpha", "label": "Alpha", "me": True, "colorName": "orange", "browser": "up", "cdpPort": 9240,
     "ports": [{"port": 41000, "name": "web"}], "documents": ["/tmp/report.docx"]},
    {"agent": "bravo", "label": "Bravo", "me": False, "colorName": "blue", "browser": "down", "closedByHuman": True, "ports": [], "documents": []}],
    "screen": {"holder": "bravo", "until": "12:00"}, "logins": {"accounts.example.com": {"agent": "alpha"}}, "apps": {"word": "office-owner/alpha"}, "errors": []}
text = status.render(snap)
check("status: /rainbow says who you are, each agent's browser, ports and documents, the screen, sign-ins and the pause",
      all(x in text for x in ("you are alpha", "paused", "→ Alpha [orange] — browser up, CDP 9240", "ports 41000 (web)",
                              "documents report.docx", "Bravo [blue] — browser down (closed by the human)", "screen: held by bravo until 12:00",
                              "accounts.example.com ← alpha", "apps an agent launched: word")), text)
live = status.snapshot(core.Rainbow(lambda k, d=None: {"home": str(tmp / "s4")}.get(k, d), lambda: "alpha"))
check("status: a live snapshot from the real owners lists this agent with its leased port, the screen free, not paused",
      live.get("me") == "alpha" and [a["agent"] for a in live["agents"]] == ["alpha"] and live["agents"][0]["ports"]
      and live["screen"]["holder"] is None and live["paused"] is False and not live["errors"], live)

# ---- more document apps -----------------------------------------------------------------------------------------------
import importlib.machinery  # noqa: E402
sys.path.insert(0, str(PLUGIN / "vendor"))
os.environ["RAINBOW_HOME"] = str(tmp / "s7")
ld = importlib.machinery.SourceFileLoader("rb_agent_office", str(PLUGIN / "vendor" / "agent-office.py"))
ao = importlib.util.module_from_spec(importlib.util.spec_from_loader(ld.name, ld))
ld.exec_module(ao)
os.environ.pop("RAINBOW_HOME", None)
skipped = ao.add_apps(json.dumps({
    "textedit": {"app": "TextEdit", "extensions": [".txt", ".docx", "bad"]},
    "powerpoint": {"app": "Microsoft PowerPoint", "suite": "office", "collection": "presentations", "extensions": [".pptx"]},
    "word": {"app": "Not Word"}, "evil": {"app": 'X" to quit\ntell application "Finder'},
    "odd": {"app": "Odd", "suite": "office", "collection": "every window"}, "raw": {"app": "Raw", "suite": "custom"}}))
check("documents: apps added in the settings use fixed AppleScript expressions; a built-in app, a name that could carry "
      "script text, an unknown suite or collection are skipped; a built-in extension keeps its app",
      sorted(skipped) == ["evil", "odd", "raw", "word"] and ao.APPS["textedit"][:2] == ("TextEdit", "documents")
      and ao.APPS["powerpoint"][:2] == ("Microsoft PowerPoint", "presentations") and ao.APPS["word"][0] == "Microsoft Word"
      and ao.EXT_APP[".txt"] == "textedit" and ao.EXT_APP[".docx"] == "word" and ao.EXT_APP[".pptx"] == "powerpoint"
      and "bad" not in ao.EXT_APP and ao.add_apps("{nope") == ["(not JSON)"], (skipped, ao.EXT_APP))
rx = core.Rainbow(lambda k, d=None: {"home": str(tmp / "s4"), "extra_apps": {"textedit": {"app": "TextEdit"}}, "word_folder": "~/w",
                                     "language": "he"}.get(k, d), lambda: "alpha")
e = rx.env()
check("settings: extra apps, the Word work folder and the language reach the owners; a shell command's mark carries only the identity",
      json.loads(e["OFFICE_EXTRA_APPS"]) == {"textedit": {"app": "TextEdit"}} and e["OFFICE_WORD_DIR"].endswith("/w")
      and e["RAINBOW_LANG"] == "he" and "OFFICE" not in (rx.mark_command("ls") or "") , e)

# ---- the Desktop panel (desktop/plugin.js) ----------------------------------------------------------------------------
keep_mac, rb_mod.IS_MAC = rb_mod.IS_MAC, True
as_data = json.loads(ctx.commands["rainbow"]("json"))
rb_mod.IS_MAC = keep_mac
check("panel: /rainbow json answers the snapshot as data, the same keys rainbow_status gives",
      as_data.get("me") == "alpha" and {"paused", "agents", "screen", "logins", "apps", "errors"} <= set(as_data), as_data)
panel = PLUGIN / "desktop" / "plugin.js"
js = panel.read_text() if panel.is_file() else ""
check("panel: desktop/plugin.js ships, default-exports the plugin under the package's own id and registers a pane",
      bool(js) and "export default {" in js and re.search(r"const ID = 'rainbowomma'", js) and "area: PANES_AREA" in js
      and [p.name for p in (PLUGIN / "desktop").iterdir()] == ["plugin.js"])
imports = re.findall(r"^\s*import\b[^'\"]*?['\"]([^'\"]+)['\"]", js, re.M)
check("panel: imports only the plugin SDK and React", imports and set(imports) <= {"@hermes/plugin-sdk", "react", "react/jsx-runtime"}, imports)
code = re.sub(r"^\s*//.*$|\s//\s.*$", "", js, flags=re.M)            # the rules below are about code, not about the comments
forbidden = {
    "eval / new Function": r"\beval\s*\(|\bnew\s+Function\b",
    "dynamic import": r"\bimport\s*\(",
    "script injection": r"createElement\(\s*['\"]script|<script\b|\.innerHTML|dangerouslySetInnerHTML|insertAdjacentHTML",
    "app markup reach": r"\bdocument\b|querySelector|getElementBy|MutationObserver|\[data-",
    "raw desktop bridge": r"hermesDesktop",
    "prototype patching": r"\.prototype\b|__proto__|Object\.defineProperty",
    "network": r"\bfetch\s*\(|XMLHttpRequest|WebSocket|EventSource|sendBeacon|https?://",
    "browser storage": r"localStorage|sessionStorage|indexedDB",
    "untracked globals": r"\bwindow\b|globalThis|\bsetInterval\s*\(|\bsetTimeout\s*\(",
    "JSX syntax": r"<[A-Za-z][\w.]*(\s[^<>]*)?/?>",
}
hits = [name for name, rx in forbidden.items() if re.search(rx, code)]
check("panel: stays inside the SDK surface (catalog rule 8) — no eval, dynamic import, injection, app markup, bridge, network or globals",
      bool(js) and not hits, hits)
check("panel: theme tokens only — no hard-coded colour beside the agents' own swatches",
      bool(js) and not re.search(r"['\"`]#[0-9a-fA-F]{3,8}['\"`]|\b(?:rgb|hsl|oklch)a?\(|:\s*'(?:white|black|red|green|blue|orange|yellow|gray|grey)'", code)
      and "var(--ui-" in js and "SWATCH.test(agent.color" in js)
check("panel: reads and acts only through the plugin's own /rainbow command (json, pause, resume), every ~10 s while on screen",
      re.search(r"host\.request\('command\.dispatch', \{ name: 'rainbow'", js) and len(re.findall(r"host\.request\(", js)) == 1
      and all(f"'{w}'" in js for w in ("json", "pause", "resume")) and "REFRESH_MS = 10000" in js and "refetchInterval" in js)
check("panel: documents are shown by file name only, and nothing private is written into the file",
      "baseName(d)" in js and not re.search(r"/Users/|/home/|@[\w-]+\.(?:com|net|org)\b", js))

# ---- Hermes's own browser tools in the agent's own Chrome --------------------------------------------------------------
from rainbowomma import own_browser  # noqa: E402


class FakeOwner:
    me = "alpha"

    def __init__(self, start):
        self.start, self.calls = start, []

    def run(self, script, *args, **kw):
        self.calls.append([script, *args])
        return True, (self.start if args[0] == "start" else {"status": "up", "port": 9240})


fo = FakeOwner({"status": "started", "detail": "CDP up on 9240"})
prov = own_browser.make_provider(fo, object, read_url=lambda port: f"ws://127.0.0.1:{port}/devtools/browser/abc")
sess = prov.create_session("t1")
check("browser provider: a session is this agent's own Chrome, started by its owner; ending it leaves the browser running",
      prov.name == "rainbowomma" and sess == {"session_name": "rainbowomma-alpha-t1", "bb_session_id": "alpha",
                                               "cdp_url": "ws://127.0.0.1:9240/devtools/browser/abc",
                                               "features": {"own_browser": True, "visible": True}}
      and fo.calls == [["browser-owner.py", "start", "alpha", "--by", "alpha"], ["browser-owner.py", "status", "alpha"]]
      and prov.close_session("alpha") is True and prov.emergency_cleanup("alpha") is None and len(fo.calls) == 2, (sess, fo.calls))
closed = own_browser.make_provider(FakeOwner({"status": "closed-by-person", "why": "the human closed it"}), object)
try:
    closed.create_session("t2")
    raised = ""
except RuntimeError as exc:
    raised = str(exc)
check("browser provider: a browser the human closed is not reopened — the session fails with the owner's reason",
      "closed-by-person" in raised and "the human closed it" in raised, raised)
check("browser provider: declared in plugin.yaml, registered through ctx.register_browser_provider, 127.0.0.1 only",
      "provides_browser_providers:\n  - rainbowomma" in manifest and "register_browser_provider" in (PLUGIN / "__init__.py").read_text()
      and re.findall(r"https?://[^\s\"']+", (PLUGIN / "own_browser.py").read_text()) == ["http://127.0.0.1:{int(port)}/json/version"])

# ---- the frame survives a restart ---------------------------------------------------------------------------------------
os.environ["RAINBOW_HOME"], os.environ["BROWSER_OWNER_REGISTRY"] = str(tmp / "s8"), str(tmp / "s8" / "browsers.json")
ld = importlib.machinery.SourceFileLoader("rb_browser_owner", str(PLUGIN / "vendor" / "browser-owner.py"))
bo = importlib.util.module_from_spec(importlib.util.spec_from_loader(ld.name, ld))
ld.exec_module(bo)
os.environ.pop("RAINBOW_HOME", None)
os.environ.pop("BROWSER_OWNER_REGISTRY", None)
bo.THEMES = tmp / "s8" / "themes"
td = bo.THEMES / "alpha"
td.mkdir(parents=True)
(td / "manifest.json").write_text(json.dumps({"manifest_version": 3, "name": "x", "version": "1", "theme": {}}))
(td / "frame.png").write_bytes(b"png")
plain = bo.theme_clean("alpha")
(td / "Cached Theme.pak").write_bytes(b"pak")                      # Chrome writes it on install and paints from it later
with_cache = bo.theme_clean("alpha")
(td / "background.js").write_text("// not ours")
foreign = bo.theme_clean("alpha")
check("browser frame: Chrome's own cached theme file is not a reason to rebuild the theme folder (rebuilding it threw the "
      "frame away at the second start); a script someone added still is", (plain, with_cache, foreign) == (True, True, False),
      (plain, with_cache, foreign))

check("browser provider: every browser_exec call runs under the agent's own session name, so two Hermes processes never "
      "share one browser daemon", own_browser.session_for("alpha") == "rb-alpha" and own_browser.session_for("alpha", "r7k2") == "rb-alpha-r7k2"
      and own_browser.session_for("alpha", "rb-alpha-r7k2") == "rb-alpha-r7k2" and own_browser.session_for("alpha", "rb-alpha") == "rb-alpha"
      and len(own_browser.session_for("a" * 31, "x" * 80)) <= 64)
shared_ctx = Ctx("alpha", {"home": str(tmp / "s4"), "housekeeping_minutes": 0})
rb_mod.register(shared_ctx)
m1 = shared_ctx.hooks["pre_tool_call"](tool_name="browser_exec", args={"code": "goto('https://example.com')"})
m2 = shared_ctx.hooks["pre_tool_call"](tool_name="browser_exec", args={"code": "x", "session": "rb-alpha"})
for cb in shared_ctx.unload:
    cb()
check("hook: a browser_exec call without the agent's session name gets it (modify); one that has it is left alone",
      m1 == {"action": "modify", "args": {"session": "rb-alpha"}} and m2 is None, (m1, m2))

# ---- what ships -------------------------------------------------------------------------------------------------------
r = subprocess.run([sys.executable, str(HERE.parent / "tools" / "sync_vendor.py"), "--check"], capture_output=True, text=True)
check("vendor: the owners inside the plugin are byte-for-byte the ones in bin/", r.returncode == 0, r.stdout)
shipped = sorted(p.name for p in (PLUGIN / "vendor").iterdir())
check("vendor: nothing that sends data anywhere or patches Hermes ships (no reporter, no menu bar, no cursor proxy, no web panel)",
      not [n for n in shipped if re.search(r"report|menubar|cua-color|panel|doctor|mcp", n)], shipped)
src = "\n".join(p.read_text() for p in PLUGIN.glob("*.py") if p.name != "own_browser.py")   # its one URL is checked above
check("plugin: no self-update, no credential files, no auto-approval, Hermes's environment left alone",
      not re.search(r"auth\.json|[\"'/]\.env\b|hooks_auto_accept|yolo|check_for_update|urllib|requests\.|os\.environ\[|os\.environ\.update|os\.putenv", src, re.I))
check("plugin: no compiled files are committed beside the sources",
      not subprocess.run(["git", "ls-files", "*.pyc", "*__pycache__*"], capture_output=True, text=True, cwd=str(HERE.parent)).stdout.strip())

print(f"\n{PASSED}/{PASSED + FAILED} passed")
sys.exit(1 if FAILED else 0)
