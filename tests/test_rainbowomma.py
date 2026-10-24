#!/usr/bin/env python3
"""RainbowOMMA tests — fake process table, fake osascript, fake Chrome; never a real browser or app.
Run: python3 tests/test_rainbowomma.py
"""
import importlib.machinery, importlib.util, json, os, re, sys, tempfile, time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "bin"
def load(name):
    loader = importlib.machinery.SourceFileLoader(name.replace("-", "_"), str(HERE / name))
    spec = importlib.util.spec_from_loader(loader.name, loader); m = importlib.util.module_from_spec(spec); loader.exec_module(m); return m

os.environ["RAINBOW_LANG"] = "he"     # the checks below read the Hebrew messages; English has its own checks at the end
results = []
def check(name, cond, info=""):
    results.append(bool(cond)); print(("✅ " if cond else "❌ ") + name + ("" if cond else f"  — {info}"))

os.environ["RAINBOW_TRACK_ROOT"] = "off"      # the guard would register this test runner as an agent's root; one test turns it on
SAFE_HOME = Path(tempfile.mkdtemp(prefix="rainbow-home-"))
os.environ["RAINBOW_HOME"] = str(SAFE_HOME)   # a test run never shares a live lock, lease or state file with the real one
bo = load("browser-owner.py")
tmp = Path(tempfile.mkdtemp(prefix="bo-"))
REG = tmp / "reg.json"
REG.write_text(json.dumps({"agents": {
    "alpha": {"label": "אלפא", "port": 9222, "profile": str(tmp / "alpha-profile"), "color": "#7E57C2", "state": str(tmp / "alpha.json"),
             "log": str(tmp / "owner.log"), "launcher": str(tmp / "launcher.sh"), "launcherEnv": "ALPHA_BROWSER_OWNER"},
    "bravo": {"label": "בראבו", "port": 9223, "profile": str(tmp / "bravo"), "color": "#26A69A", "managedBy": "x.py"},
    "charlie": {"label": "צ׳רלי", "port": 9224, "profile": str(tmp / "charlie"), "color": "#F4511E", "state": str(tmp / "charlie.json"), "log": str(tmp / "owner.log")}}}))
(tmp / "launcher.sh").write_text("true")
reg = bo.registry(REG)
ALPHA_A, CHARLIE_A = reg["alpha"], reg["charlie"]
bo.time.sleep = lambda s: None                               # the 3-probe wait, instant in tests
def fake_install(a, folder=None, timeout=25.0, record=None):
    """never a real Chrome in a test: record the theme in the profile the way Chrome does (extensions.theme.id)"""
    prefs = Path(a["profile"]) / "Default" / "Preferences"; prefs.parent.mkdir(parents=True, exist_ok=True)
    try:
        d = json.loads(prefs.read_text())
    except (OSError, ValueError):
        d = {}
    d.setdefault("extensions", {})["theme"] = {"id": "a" * 32}
    prefs.write_text(json.dumps(d))
    if record is not None:
        record.append(1)
    return True, "fakethemeid"
bo.install_theme = fake_install
bo.build_theme = lambda a: tmp / ("theme-" + a["name"])
bo.front_pid = lambda: 200
bo.set_front = lambda pid: True
P = ALPHA_A["profile"]
CH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
ALPHA = f"{CH} --user-data-dir={P} --remote-debugging-port=9222 --no-first-run"
HUMAN = f"{CH} --no-startup-window"
HELPER = "/Applications/Google Chrome.app/Contents/Frameworks/Google Chrome Helper (Renderer).app/Contents/MacOS/Google Chrome Helper (Renderer) --type=renderer"
rows = [(100, 1, ALPHA), (101, 100, HELPER), (102, 101, HELPER), (200, 1, HUMAN), (201, 200, HELPER)]
bo.processes = lambda: rows
up = {9222: False, 9224: False}
bo.healthy = lambda a, timeout=2.0: up[a["port"]]
roots, tree = bo.tree_of(ALPHA_A, rows)
check("only Alpha's root (port 9222 + its profile) and its descendants — never the human's Chrome", roots == [100] and tree == {100, 101, 102}, (roots, tree))
check("another profile on 9222 is not Alpha's", not bo.is_root(ALPHA_A, ALPHA.replace(P, "/tmp/x")))
check("whole argument values: port 92220 / profile alpha-profile-personal are not Alpha's",
      not bo.is_root(ALPHA_A, ALPHA.replace("9222 ", "92220 ")) and not bo.is_root(ALPHA_A, ALPHA.replace(P, P + "-personal")))
check("Charlie's browser is Charlie's, not Alpha's", not bo.is_root(ALPHA_A, ALPHA.replace(P, CHARLIE_A["profile"]).replace("9222", "9224"))
      and bo.is_root(CHARLIE_A, ALPHA.replace(P, CHARLIE_A["profile"]).replace("9222", "9224")))
for bad, why in ((dict(port=9222), "duplicate port"), (dict(port=8080), "port outside the range"), (dict(color="not-a-color"), "color"),
                 (dict(profile="/tmp/with space"), "space in profile")):
    r = json.loads(REG.read_text()); r["agents"]["zed"] = dict({"label": "z", "port": 9230, "profile": "/tmp/z", "color": "#000000"}, **bad)
    bp = tmp / "bad.json"; bp.write_text(json.dumps(r))
    try:
        bo.registry(bp); ok_ = False
    except ValueError:
        ok_ = True
    check(f"registry refuses a broken row ({why})", ok_)
check("the example registry loads: alpha 9222, bravo 9223, charlie 9224",
      (lambda r: r["alpha"]["port"] == 9222 and r["bravo"]["port"] == 9223 and not r["bravo"].get("managedBy")
       and r["bravo"]["idleMinutes"] == 60 and r["charlie"]["port"] == 9224)(bo.registry(HERE.parent / "examples" / "browsers.example.json")))
killed = []
bo.terminate_tree = lambda t, grace=8.0: killed.append(set(t)) or []
code, out = bo.do_stop(ALPHA_A, "alpha")
check("stop is the human's only — an agent is refused", code == 2 and not killed, out)
code, out = bo.do_stop(ALPHA_A, "human")
st_file = Path(ALPHA_A["state"])
check("stop --by human: Alpha's tree only, and remembered", code == 0 and killed == [{100, 101, 102}] and json.loads(st_file.read_text())["offByHuman"], (code, out, killed))
code, out = bo.do_start(ALPHA_A, "keepalive")
check("start by the keepalive is refused while the human closed it", code == 2 and out["status"] == "refused", out)
code, out = bo.do_recover(ALPHA_A, "alpha")
check("recover by Alpha is refused while the human closed it", code == 2, out)
up[9222] = True                                              # still answering in the seconds after the stop (SIGTERM grace)
before = st_file.read_text()
v = bo.view(ALPHA_A)
check("status is read-only — it never clears the flag", st_file.read_text() == before and v["offByHuman"] is True, v)
code, out = bo.do_start(ALPHA_A, "keepalive")
check("…and a start right after the stop does not 'reconcile' it either: < 2 min → still the human's", code == 2 and json.loads(st_file.read_text())["offByHuman"], out)
st = json.loads(st_file.read_text()); st["offAt"] = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(time.time() - 600)); st_file.write_text(json.dumps(st))
code, out = bo.do_start(ALPHA_A, "keepalive")
check("UP (its own root) minutes after the stop → the stale flag is cleared under the lock",
      code == 0 and out["status"] == "already-up" and json.loads(st_file.read_text())["offByHuman"] is False, out)
FOREIGN = f"{CH} --remote-debugging-port=9222 --user-data-dir=/tmp/other/alpha-chrome-profile"
bo.processes = lambda: [(300, 1, FOREIGN), (200, 1, HUMAN)]
bo.save(ALPHA_A, {"offByHuman": True, "offAt": "2026-01-01T00:00:00+0000"})
v = bo.view(ALPHA_A)
code, out = bo.do_start(ALPHA_A, "alpha")
check("a foreign Chrome on 9222 = 'blocked': not up, not reconciled, not killed",
      v["status"] == "blocked" and v["up"] is False and code == 1 and out["status"] == "blocked" and json.loads(st_file.read_text())["offByHuman"]
      and killed == [{100, 101, 102}], (v, out))
code, out = bo.do_recover(ALPHA_A, "human")
check("recover on a blocked port touches nothing — even for the human", code == 1 and out["status"] == "blocked" and len(killed) == 1, out)
up[9222] = False
bo.save(ALPHA_A, {"offByHuman": True, "offAt": "x"})
launched = []
bo.processes = lambda: [(200, 1, HUMAN)]
def fake_launch(a):
    launched.append(a["name"]); up[a["port"]] = True; return 0, f"CDP up on {a['port']}"
bo.launch = fake_launch
code, out = bo.do_start(ALPHA_A, "human")
check("start --by human clears the flag and launches", code == 0 and not json.loads(st_file.read_text())["offByHuman"] and launched == ["alpha"], (code, out, launched))
bo.processes = lambda: rows
code, out = bo.do_start(ALPHA_A, "keepalive")
check("start when already up = no second launch", code == 0 and out["status"] == "already-up" and launched == ["alpha"], out)
probes = []
def slow_then_up(a, timeout=2.0):
    probes.append(timeout); return len(probes) >= 2          # the first probe misses (swap), the second answers
bo.healthy = slow_then_up
killed.clear()
code, out = bo.do_recover(ALPHA_A, "alpha")
check("recover by an agent: one missed probe on a slow Mac does NOT kill the browser",
      code == 0 and not killed and out["status"] == "healthy" and any(t >= 10 for t in probes), (out, killed, probes))
up[9222] = False
bo.healthy = lambda a, timeout=2.0: up[a["port"]]
def term(t, grace=8.0):
    killed.append(set(t)); bo.processes = lambda: [(200, 1, HUMAN)]; return []
bo.terminate_tree = term
code, out = bo.do_recover(ALPHA_A, "alpha")
check("recover: really hung (3 misses) → its own tree closed, then started", killed == [{100, 101, 102}] and launched == ["alpha", "alpha"], (killed, launched, out))
bo.processes = lambda: rows + [(300, 1, ALPHA)]
up[9222] = False
code, out = bo.do_recover(ALPHA_A, "alpha")
check("two Alpha roots → refuse, touch nothing", code == 1 and "יותר משורש" in out["why"], out)
Path(P, "Default").mkdir(parents=True, exist_ok=True)
Path(P, "Default", "Preferences").write_text(json.dumps({"profile": {"exit_type": "Normal"}}))
check("Chrome's own exit record is read (Normal = a clean quit)", bo.last_exit_type(ALPHA_A) == "Normal")
# paint: the rainbow
bo.processes = lambda: [(200, 1, HUMAN)]
code, out = bo.do_start(CHARLIE_A, "charlie")
mp = json.loads(Path(CHARLIE_A["profile"], "Default", "Preferences").read_text())
ls = json.loads(Path(CHARLIE_A["profile"], "Local State").read_text())
agent_color = bo.chrome_color("#F4511E")
mst = json.loads(Path(CHARLIE_A["state"]).read_text())
check("a new agent: its THEME is installed before the first launch (solid frame + its name), the profile named 'צ׳רלי — סוכן · לא לגעת'",
      code == 0 and launched[-1] == "charlie" and mst["themeId"] == "fakethemeid" and mst["theme"] == bo.theme_key(CHARLIE_A)
      and mst["lastStart"]["theme"] == "installed" and mp["profile"]["name"] == "צ׳רלי — סוכן · לא לגעת"
      and "theme" not in mp.get("browser", {}) and ls["profile"]["info_cache"]["Default"]["profile_highlight_color"] == agent_color, (out, mp, mst))
check("…the theme install closed its windowless Chrome — recorded apart from lastStop (never read as the human's ⌘Q, never hides the real stop)",
      "at" in mst["lastThemeInstall"] and (mst.get("lastStop") or {}).get("by") != "theme-install")
up[9224] = False
inst = []
_it = bo.install_theme; bo.install_theme = lambda a, folder, timeout=25.0: fake_install(a, record=inst)
code, out = bo.do_start(CHARLIE_A, "charlie")
check("the next start keeps the installed theme — no second install", not inst and json.loads(Path(CHARLIE_A["state"]).read_text())["lastStart"]["theme"] == "kept")
up[9224] = False
CHARLIE_A["color"] = "#00897B"
code, out = bo.do_start(CHARLIE_A, "charlie")
check("its color changed in the registry → the theme is rebuilt", inst == [1])
up[9224] = False
pc_ = Path(CHARLIE_A["profile"], "Default", "Preferences"); d_ = json.loads(pc_.read_text()); d_["extensions"]["theme"]["id"] = ""
pc_.write_text(json.dumps(d_))
code, out = bo.do_start(CHARLIE_A, "charlie")
check("Google Sync took the theme off the profile (extensions.theme.id empty) → the next start puts it back",
      inst == [1, 1] and json.loads(Path(CHARLIE_A["state"]).read_text())["lastStart"]["theme"] == "installed", inst)
CHARLIE_A["color"] = "#F4511E"
up[9224] = False
bo.install_theme = lambda a, folder, timeout=25.0: (False, "Extensions.loadUnpacked not allowed")
st0 = json.loads(Path(CHARLIE_A["state"]).read_text()); st0.pop("theme"); Path(CHARLIE_A["state"]).write_text(json.dumps(st0))
code, out = bo.do_start(CHARLIE_A, "charlie")
mp = json.loads(Path(CHARLIE_A["profile"], "Default", "Preferences").read_text())
mst = json.loads(Path(CHARLIE_A["state"]).read_text())
check("theme install fails → the start goes on with the profile color (fallback) and the reason is recorded",
      code == 0 and mst["lastStart"]["theme"] == "failed" and "loadUnpacked" in mst["themeError"] and mp["browser"]["theme"]["user_color2"] == agent_color, (out, mst))
bo.install_theme = fake_install
mp2 = {"profile": {}, "account_values": {"browser": {"theme": {"user_color2": -8497214}}}}
pp = Path(tmp / "acct" / "Default"); pp.mkdir(parents=True, exist_ok=True); (pp / "Preferences").write_text(json.dumps(mp2))
bo.paint(dict(CHARLIE_A, profile=str(tmp / "acct")))
check("a profile copied from another agent: its account_values color is overwritten too (a copied profile must not keep the other agent's color)",
      json.loads((pp / "Preferences").read_text())["account_values"]["browser"]["theme"]["user_color2"] == agent_color)
up[9224] = False
check("the agent's start recorded the focus check (kept — the human's app stayed in front)", json.loads(Path(CHARLIE_A["state"]).read_text())["lastStart"]["focus"] == "kept")
bo.processes = lambda: [(200, 1, HUMAN), (400, 1, ALPHA.replace(P, CHARLIE_A["profile"]).replace("9222", "9224"))]
fr = {"pid": 400}
bo.front_pid = lambda: fr["pid"]
bo.set_front = lambda pid: fr.update(pid=pid) or True
_real_time = time.time
bo.time.time = (lambda c=[0.0]: (c.__setitem__(0, c[0] + 0.5), c[0])[1])
check("an agent's browser that takes the front is sent back behind the human's app",
      bo.give_focus_back(CHARLIE_A, 200) == "restored" and fr["pid"] == 200)
bo.set_front = lambda pid: False
fr["pid"] = 400
check("…and when focus cannot be given back, it says 'lost' (never pretends)", bo.give_focus_back(CHARLIE_A, 200) == "lost")
bo.time.time = _real_time
bo.front_pid = lambda: 200; bo.set_front = lambda pid: True
check("color encoding = Chrome's signed ARGB (-8497214 = #7E57C2)", bo.chrome_color("#7E57C2") == -8497214)
Path(P, "Default", "Preferences").write_text('{"profile": {"exit_type": "Normal", "name": "x"}, "keep": 1}')
bo.paint(ALPHA_A)
pp = json.loads(Path(P, "Default", "Preferences").read_text())
check("painting MERGES into Chrome's file (nothing else lost)", pp["keep"] == 1 and pp["profile"]["exit_type"] == "Normal" and pp["profile"]["name"].startswith("אלפא"), pp)
Path(P, "Local State").write_text("{broken")
bo.paint(ALPHA_A)
check("an unreadable Chrome file is left alone, never replaced", Path(P, "Local State").read_text() == "{broken")
args = bo.chrome_args(CHARLIE_A)
check("a new agent gets exact CDP origins, not *, and its own window name",
      "--remote-allow-origins=http://127.0.0.1:9224,http://localhost:9224" in args and "--window-name=צ׳רלי-CDP" in args and not any("=*" in x for x in args), args)
_r = bo.REGISTRY
mreg = tmp / "managed.json"
mreg.write_text(json.dumps({"agents": {"ext": {"label": "אקו", "port": 9240, "profile": str(tmp / "ext"), "color": "#123456", "managedBy": "x.py"}}}))
bo.REGISTRY = mreg
code = bo.main(["start", "ext", "--by", "human"])
bo.REGISTRY = _r
check("an agent managed by another program — the owner only reports (temp registry: never a real browser)", code == 2)
bo.processes = lambda: [(200, 1, HUMAN)]
up[9224] = True
v = bo.view(CHARLIE_A)
check("the port answers but no Charlie root (Chromium / proxy / other profile) → blocked, never 'up'", v["status"] == "blocked" and v["up"] is False, v)
bo.listener = lambda a: "node (pid 777)"
code, out = bo.do_start(CHARLIE_A, "charlie")
check("…start refuses and names the listener (lsof)", code == 1 and out["status"] == "blocked" and "node (pid 777)" in out["why"], out)
up[9224] = False
BUSY = f"{CH} --user-data-dir={CHARLIE_A['profile']} --no-first-run"
bo.processes = lambda: [(200, 1, HUMAN), (500, 1, BUSY)]
painted = []
_paint = bo.paint; bo.paint = lambda a: painted.append(a["name"]) or []
code, out = bo.do_start(CHARLIE_A, "charlie")
check("profile in use by a Chrome WITHOUT the port → profile-busy: nothing painted, nothing launched",
      code == 1 and out["status"] == "profile-busy" and not painted and bo.view(CHARLIE_A)["status"] == "profile-busy", out)
bo.paint = _paint
bo.processes = lambda: [(200, 1, HUMAN)]
_q = bo.quit_by_person; bo.quit_by_person = lambda a, now=None, st=None: True
n0 = len(launched)
code, out = bo.do_start(CHARLIE_A, "keepalive")
check("⌘Q in the last 2h → an agent/keepalive start is refused (closed-by-person); the human still opens it", code == 2 and out["status"] == "closed-by-person" and len(launched) == n0, out)
bo.launch = fake_launch
code, out = bo.do_start(CHARLIE_A, "human")
check("…the human's own start is not blocked by it", code == 0 and len(launched) == n0 + 1, out)
up[9224] = False
bo.quit_by_person = _q
prefs = Path(CHARLIE_A["profile"], "Default", "Preferences")
prefs.write_text(json.dumps({"profile": {"exit_type": "Normal"}}))
os.utime(prefs, (1_700_000_000, 1_700_000_000))
bo.paint(CHARLIE_A)
check("paint keeps Chrome's Preferences mtime (it is how a ⌘Q is told from a reboot)", prefs.stat().st_mtime == 1_700_000_000 and json.loads(prefs.read_text())["profile"]["name"].startswith("צ׳רלי"))
for bad, why in ((dict(label=""), "missing label"), (dict(profile=str(tmp / "alpha-profile")), "profile of another agent"),
                 (dict(state=str(tmp / "alpha.json")), "state file of another agent"),
                 (dict(profile=str(Path.home() / "Library" / "Application Support" / "Google" / "Chrome")), "the human's personal Chrome")):
    r = json.loads(REG.read_text()); r["agents"]["zed"] = dict({"label": "z", "port": 9230, "profile": str(tmp / "zed"), "color": "#000000"}, **bad)
    bp = tmp / "bad.json"; bp.write_text(json.dumps(r))
    try:
        bo.registry(bp); ok_ = False
    except ValueError:
        ok_ = True
    check(f"registry refuses ({why})", ok_)
(tmp / "alias").symlink_to(tmp / "alpha-profile")
r = json.loads(REG.read_text()); r["agents"]["zed"] = {"label": "z", "port": 9230, "profile": str(tmp / "alias"), "color": "#000000"}
bp = tmp / "bad.json"; bp.write_text(json.dumps(r))
try:
    bo.registry(bp); ok_ = False
except ValueError:
    ok_ = True
check("registry: a symlink alias of Alpha's profile is Alpha's profile", ok_)
r = json.loads(REG.read_text()); r["agents"]["bravo"] = {"label": "בראבו", "port": 9223, "profile": str(tmp / "bravo"), "color": "#26A69A",
    "state": str(tmp / "bravo.json"), "log": str(tmp / "owner.log"), "idleMinutes": 60}
REG.write_text(json.dumps(r)); reg = bo.registry(REG); BRAVO_A = reg["bravo"]
BRAVO_CMD = f"{CH} --user-data-dir={BRAVO_A['profile']} --remote-debugging-port=9223"
bo.processes = lambda: [(200, 1, HUMAN), (600, 1, BRAVO_CMD)]
bo.terminate_tree = lambda t, grace=8.0: killed.append(set(t)) or []
killed.clear()
code0, out0 = bo.do_idle_stop(BRAVO_A, "bravo-reaper")
check("idle-stop: a browser opened outside the owner (how long it's been idle can't be told) is not stopped",
      code0 == 2 and not killed, out0)
Path(BRAVO_A["state"]).write_text(json.dumps({"lastStart": {"at": "2020-01-01T00:00:00", "by": "bravo"}}))
code, out = bo.do_idle_stop(BRAVO_A, "bravo-reaper")
check("idle-stop: an agent with idleMinutes closes its own tree, and it is NOT recorded as 'the human closed it'",
      code == 0 and killed == [{600}] and not json.loads(Path(BRAVO_A["state"]).read_text()).get("offByHuman"), out)
code, out = bo.do_idle_stop(CHARLIE_A, "charlie")
check("idle-stop is refused for an agent without idleMinutes", code == 2 and not any(600 not in k for k in killed[1:]), out)
# --allow-reopen and the owner's own close vs ⌘Q
bo.processes = lambda: [(200, 1, HUMAN), (600, 1, BRAVO_CMD)]
code, out = bo.do_stop(BRAVO_A, "human", allow_reopen=True)
stn = json.loads(Path(BRAVO_A["state"]).read_text())
check("stop --by human --allow-reopen: closed now, but the agents may open it again", code == 0 and stn["offByHuman"] is False and stn["lastStop"].get("allowReopen"), stn)
prefs_n = Path(BRAVO_A["profile"], "Default"); prefs_n.mkdir(parents=True, exist_ok=True)
(prefs_n / "Preferences").write_text(json.dumps({"profile": {"exit_type": "Normal"}}))
_bt = bo.boot_time; bo.boot_time = lambda: time.time() - 86400
check("a 'Normal' exit right after the OWNER's stop is not a ⌘Q — the agent may start", bo.quit_by_person(BRAVO_A) is False)
stn["lastStop"]["at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(time.time() - 3600)); Path(BRAVO_A["state"]).write_text(json.dumps(stn))
check("…a 'Normal' exit with no owner stop around it IS a person's ⌘Q", bo.quit_by_person(BRAVO_A) is True)
bo.boot_time = _bt
# recover revalidates the tree right before the kill
bo.processes = lambda: [(200, 1, HUMAN), (600, 1, BRAVO_CMD)]
seq = iter([[(200, 1, HUMAN), (600, 1, BRAVO_CMD)], [(200, 1, HUMAN), (601, 1, BRAVO_CMD)]])
bo.processes = lambda: next(seq)
up[9223] = False
bo.healthy = lambda a, timeout=2.0: up.get(a["port"], False)
killed.clear()
code, out = bo.do_recover(BRAVO_A, "bravo")
check("recover: the browser's pid changed during the 30-second probes → nothing signalled", code == 1 and not killed, out)
# focus
bo.processes = lambda: [(200, 1, HUMAN), (400, 1, ALPHA.replace(P, CHARLIE_A["profile"]).replace("9222", "9224"))]
fr = {"seq": [400, 900]}
bo.front_pid = lambda: fr["seq"].pop(0) if len(fr["seq"]) > 1 else fr["seq"][0]
gives = []
bo.set_front = lambda pid: gives.append(pid) or True
bo.time.time = (lambda c=[0.0]: (c.__setitem__(0, c[0] + 0.5), c[0])[1])
res = bo.give_focus_back(CHARLIE_A, 200)
bo.time.time = _real_time
check("focus: given back at most once", res in ("restored", "lost") and len(gives) == 1, (res, gives))
fr = {"seq": [900]}
gives.clear()
bo.time.time = (lambda c=[0.0]: (c.__setitem__(0, c[0] + 0.5), c[0])[1])
res = bo.give_focus_back(CHARLIE_A, 200)
bo.time.time = _real_time
check("focus: the human picked another app meanwhile → 'user-moved', never pulled back", res == "user-moved" and not gives, res)
check("focus: no Automation consent (-1743) is recorded as no-permission, not 'kept'", bo.give_focus_back(CHARLIE_A, bo.FOCUS_NO_PERMISSION) == "no-permission")
bo.front_pid = lambda: 200; bo.set_front = lambda pid: True
import io, contextlib
buf = io.StringIO()
_r = bo.REGISTRY; bo.REGISTRY = REG
with contextlib.redirect_stdout(buf):
    bo.main(["names"])
bo.REGISTRY = _r
check("`names` = the agents this owner may stop, plain words for kill-chrome", set(buf.getvalue().split()) == {"alpha", "bravo", "charlie"}, buf.getvalue())
bo.launch = None

# ── agent-office ──
ao = load("agent-office.py")
ao.LEASES = tmp / "leases"; ao.LOG = tmp / "office.log"
ao.APPS_STATE = tmp / "office_apps.json"; ao.INFLIGHT = tmp / "office_inflight"; ao.WORD_DIR = tmp / "word-convert"
ao.PGREP = lambda app: None              # never the real process table or the real state file in a test
SEP = ao.SEP
d1 = tmp / "agent"; d1.mkdir(); d2 = tmp / "human"; d2.mkdir()
f1 = d1 / "טיוטה, סופית.docx"; f1.write_text("x")
f2 = d2 / "טיוטה, סופית.docx"; f2.write_text("x")
docs = {"Microsoft Word": {str(f2): True}}
state = {"fail": False}
def osa(script):
    if state["fail"]:
        return 124, ""
    if "System Events" in script:
        return 0, "true" if any(a in script for a in docs) else "false"
    app = next((a for a in docs if f'application "{a}"' in script), None)
    if app is None:
        return 1, ""
    if "text item delimiters" in script:
        return 0, str(len(docs[app])) + SEP + SEP.join(docs[app])
    m = re.search(r'if \{(.*?)\} contains', script)
    if m:
        cands = set(re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1)))
        hits = [p for p in docs[app] if p in cands]
        if not hits: return 0, "gone"
        if len(hits) > 1: return 0, "ambiguous"
        if not docs[app][hits[0]]: return 0, "unsaved"
        docs[app].pop(hits[0]); return 0, "closed"
    return 1, ""
ao.RUN = osa
code, out = ao.cmd_open("delta", str(f1))
docs["Microsoft Word"][str(f1)] = False
check("open: leased to the agent by full path — the human's same-named file elsewhere does not make it 'shared'", code == 0 and out["shared"] is False, out)
code, out = ao.cmd_open("delta", str(f2))
check("open a PATH the human already has open → lease is 'shared'", out["shared"] is True, out)
for f in ao.LEASES.glob("*.json"):
    d = json.loads(f.read_text()); d["openedAt"] = time.time() - 5 * 3600; f.write_text(json.dumps(d))
code, out = ao.cmd_sweep(3.0)
res = {(Path(i["path"]).parent.name): i["result"] for i in out["items"]}
check("sweep: the agent's unsaved document stays open", res.get("agent") == "unsaved" and str(f1) in docs["Microsoft Word"], res)
check("sweep: the human's document (same name, ', ' in it) is never touched", res.get("human") == "shared" and str(f2) in docs["Microsoft Word"], res)
docs["Microsoft Word"][str(f1)] = True
state["fail"] = True
code, out = ao.cmd_sweep(3.0)
check("the app does not answer (dialog / permission prompt / timeout) → unknown, lease KEPT, nothing closed",
      all(i["result"] in ("unknown", "shared") for i in out["items"]) and len(list(ao.LEASES.glob("*.json"))) == 2, out)
check("open while the app cannot answer → 'shared' (never auto-closed)", ao.cmd_open("delta", str(f1))[1]["shared"] is True)
for f in ao.LEASES.glob("*.json"):
    d = json.loads(f.read_text())
    if d["shared"] and d["path"] in ao.forms(f1): f.unlink()
state["fail"] = False
code, out = ao.cmd_renew("delta", str(f1))
check("renew: still working on it — the clock starts again", code == 0 and out["count"] == 1, out)
code, out = ao.cmd_sweep(3.0)
check("…so the sweep leaves it alone", not any(Path(i["path"]) == f1 for i in out["items"]), out)
code, out = ao.cmd_close("delta", str(f1))
check("close by the agent: saved → closed (check + close in ONE AppleScript)", code == 0 and out["status"] == "closed" and str(f1) not in docs["Microsoft Word"], out)
code, out = ao.cmd_close("alpha", str(f2))
check("close: only the agent that leased that exact path", code == 1, out)
check("a Hebrew path with quotes is escaped for AppleScript", ao.q('a"b\\c') == '"a\\"b\\\\c"')
# a list that does not split into the count the app gave is untrusted
real_osa = ao.RUN
docs["Microsoft Word"] = {"/a": True, "/b": True}
ao.RUN = lambda sc: (0, "2" + SEP + "/a, /b") if "text item delimiters" in sc else real_osa(sc)
check("the app says 2 documents but the list does not split in 2 → None, never one long path", ao.open_paths("word") is None)
ao.RUN = real_osa
# a lease whose document is no longer open is dropped every tick — shared ones too
for f in ao.LEASES.glob("*.json"): f.unlink()
docs["Microsoft Word"] = {str(f1): False, str(f2): True}
ao.cmd_open("delta", str(f1)); ao.cmd_open("delta", str(f2))
docs["Microsoft Word"] = {}
code, out = ao.cmd_sweep(3.0)
check("…but a lease younger than 2 minutes is never dropped",
      len(list(ao.LEASES.glob("*.json"))) == 2 and not out["items"], out)
for f in ao.LEASES.glob("*.json"):
    d = json.loads(f.read_text()); d["openedAt"] = time.time() - 300; f.write_text(json.dumps(d))
code, out = ao.cmd_sweep(3.0)
check("sweep: leases of documents closed by hand are dropped at once, the shared one too",
      not list(ao.LEASES.glob("*.json")) and sum(i["result"] == "dropped" for i in out["items"]) == 2, out)
docs["Microsoft Word"] = {str(f1): True}
ao.cmd_open("delta", str(f1))
lf = next(ao.LEASES.glob("*.json")); d = json.loads(lf.read_text()); d["openedAt"] = time.time() - 5 * 3600; lf.write_text(json.dumps(d))
_leases = ao.leases
def leases_then_renew():
    ls = _leases(); ao.leases = _leases; ao.cmd_renew("delta", str(f1)); return ls
ao.leases = leases_then_renew
code, out = ao.cmd_sweep(3.0)
ao.leases = _leases
check("sweep re-reads each lease before closing — renewed in between → left open", str(f1) in docs["Microsoft Word"], out)
for f in ao.LEASES.glob("*.json"): f.unlink()
# an app that is not running is never asked — `tell application` would launch it
asked = []
def quit_word(sc):
    if "System Events" in sc:
        return 0, "false"
    asked.append(sc); return 0, "closed"
ao.RUN = quit_word
check("close: Word not running → 'gone', and Word is never addressed (it would launch on the human's screen)",
      ao.close_if_saved("word", [str(f1)]) == "gone" and not asked, asked)
ao.RUN = lambda sc: (124, "")
check("close: cannot tell whether Word runs → unknown", ao.close_if_saved("word", [str(f1)]) == "unknown")
ao.RUN = real_osa
docs.clear()
check("an app that is not running is never started to look", ao.open_paths("word") == [])

# ── office-owner : who launched the app, Word→PDF, quit only what the owner launched ──
ao.APPS_STATE = tmp / "office_apps.json"; ao.INFLIGHT = tmp / "office_inflight"; ao.WORD_DIR = tmp / "word-convert"
pids = {"word": None}
ao.PGREP = lambda app: pids.get(app)
calls = []
def word_osa(sc):
    calls.append(sc)
    if "save as d file name" in sc:
        m = re.search(r'file name "([^"]+)"', sc); Path(m.group(1)).write_bytes(b"%PDF- test"); pids["word"] = 777
        return 0, ""
    if "count of documents) is 0 then" in sc:
        return 0, "quit" if not docs.get("Microsoft Word") else "busy %d" % len(docs["Microsoft Word"])
    return osa(sc)
ao.RUN = word_osa
src = tmp / "agent" / "מכתב.docx"; src.write_text("x")
code, out = ao.cmd_pdf("bravo", str(src))
st = json.loads(ao.APPS_STATE.read_text())
check("pdf: through real Word, its own uniquely named copy (never 'active document'), PDF beside the source",
      code == 0 and out["renderer"] == "Microsoft Word" and Path(out["pdf"]).exists() and "active document" not in calls[0]
      and "ofc-pdf-" in calls[0] and not list(ao.WORD_DIR.glob("ofc-pdf-*.docx")), (out, calls[:1]))
check("pdf: Word was NOT running → recorded as launched by the owner, with its pid", st["word"]["launchedBy"].startswith("office-owner/")
      and st["word"]["pid"] == 777, st)
st["word"]["lastActivity"] = time.time() - 5; ao.save_apps_state(st)
check("idle < 10 min → not quit", ao.idle_quit() == [])
st["word"]["lastActivity"] = time.time() - 700; ao.save_apps_state(st)
docs["Microsoft Word"] = {"/x/human.docx": True}
r = ao.idle_quit()
check("idle 10+ min but a document is open in it → 'busy', never quit (count checked in the same AppleScript)", r and r[0]["result"].startswith("busy"), r)
docs["Microsoft Word"] = {}
r = ao.idle_quit()
check("owner-launched, idle 10+ min, no lease, no documents → quit", r and r[0]["result"] == "quit" and "word" not in json.loads(ao.APPS_STATE.read_text()), r)
pids["word"] = 888
ao.note_use("word", "office-owner/bravo")
st = json.loads(ao.APPS_STATE.read_text())
check("Word already running when the owner arrives → the human's, never quit", st["word"]["launchedBy"] == "human")
st["word"]["lastActivity"] = time.time() - 9999; ao.save_apps_state(st)
check("…even after hours idle", ao.idle_quit() == [])
ao.save_apps_state({"word": {"launchedBy": "office-owner/x", "pid": 777, "lastActivity": time.time() - 9999}})
pids["word"] = 999
ao.idle_quit()
check("owner launched pid 777, but Word now runs as 999 (the human relaunched it) → it becomes the human's", json.loads(ao.APPS_STATE.read_text())["word"]["launchedBy"] == "human")
ao.save_apps_state({"word": {"launchedBy": "office-owner/x", "pid": 999, "lastActivity": time.time() - 9999}})
with ao.inflight("word"):
    r = ao.idle_quit()
check("a conversion in flight → never quit", r == [], r)
def stuck(sc):
    calls.append(sc); return 124, ""
ao.RUN = stuck; calls.clear()
code, out = ao.cmd_pdf("bravo", str(src), force=True)
check("Word hangs (a dialog) → clear failure, and the cleanup closes ONLY that copy by name", code == 1 and any("close x saving no" in c and "ofc-pdf-" in c for c in calls[1:]), (out, len(calls)))
check("…and no leftover temp copy or empty PDF in the work folder", not list(ao.WORD_DIR.glob("ofc-pdf-*")), list(ao.WORD_DIR.glob("*")))
calls.clear()
code, out = ao.cmd_pdf("bravo", str(src), out=str(src))
check("pdf --out = the source itself → refused before Word is touched (never overwrite the document)", code == 1 and not calls and src.read_text() == "x", out)
code, out = ao.cmd_pdf("bravo", str(src), out=str(tmp / "agent" / "x.docx"))
check("pdf --out must end in .pdf", code == 1 and not calls, out)
ao.RUN = osa

# ── English + Hebrew: the message catalog, the frame's side, one configurable root ──
import subprocess
sys.path.insert(0, str(HERE))
import rainbow_i18n as i18n
check("every message has a text in every language", all(set(v) >= set(i18n.LANGS) and all(v.values()) for v in i18n.M.values()),
      [k for k, v in i18n.M.items() if not set(v) >= set(i18n.LANGS)])
used = set()
for f in [*HERE.glob("*.sh"), HERE.parent / "examples" / "agent-launcher.sh", HERE.parent / "install" / "make-desktop-apps.sh"]:
    used |= set(re.findall(r"msg ([a-z]+\.[a-z_.]+)", f.read_text(encoding="utf-8")))
used |= {"desk.name.human", "desk.name.all"}
check("every message a shell script asks for exists in the catalog", used and used <= set(i18n.M), sorted(used - set(i18n.M)))
for f in [*HERE.glob("*.py"), *HERE.glob("*.sh"), HERE.parent / "examples" / "agent-launcher.sh", HERE.parent / "install" / "make-desktop-apps.sh"]:
    if f.name == "rainbow_i18n.py":
        continue
    heb = [ln for ln in f.read_text(encoding="utf-8").splitlines() if re.search("[\u0590-\u05FF]", ln)]
    check(f"no Hebrew left in code outside the catalog: {f.name}", not heb, heb[:2])

os.environ["RAINBOW_LANG"] = "en"
code, out = bo.do_stop(CHARLIE_A, "alpha")
check("English: an agent's stop is refused with an English why — the status word and exit code unchanged",
      code == 2 and out["status"] == "refused" and out["why"] == "only the human closes צ׳רלי's browser (stop --by human). An agent that needs a recovery uses recover", out)
check("English: the profile is named '<label> — agent · do not touch'", bo.display_name({"label": "Charlie"}) == "Charlie — agent · do not touch")
code, out = ao.cmd_pdf("bravo", str(tmp / "missing.docx"))
check("English: office-owner explains in English too", code == 1 and out["why"].startswith("no such file"), out)
os.environ["RAINBOW_LANG"] = "he"
code, out = bo.do_stop(CHARLIE_A, "alpha")
check("Hebrew: the same refusal in Hebrew", code == 2 and out["why"].startswith("רק האדם סוגר"), out)

check("RTL keeps the theme key it always had (no rebuild for existing Hebrew installs)", bo.theme_key(CHARLIE_A) == f"{bo.THEME_VERSION}:#F4511E:צ׳רלי")
os.environ["RAINBOW_LANG"] = "en"
check("LTR has its own theme key, so switching language rebuilds the frame once", bo.theme_key(CHARLIE_A).endswith(":ltr2"))
bo_fresh = load("browser-owner.py")
bo_fresh.THEMES = tmp / "themes-i18n"
seen = []
_run = bo_fresh.subprocess.run
bo_fresh.subprocess.run = lambda args, **kw: (seen.append(args), subprocess.CompletedProcess(args, 1, "", ""))[1]
try:
    for lg in ("en", "he"):
        os.environ["RAINBOW_LANG"] = lg
        bo_fresh.build_theme({"name": "zed", "label": "Zed", "color": "#8E24AA"})
finally:
    bo_fresh.subprocess.run = _run
check("frame text and side follow the language: LTR → 'Zed · AI Agent · Do not touch' drawn on the right",
      seen[0][5] == "Zed · AI Agent · Do not touch" and seen[0][-1] == "ltr", seen[0][4:])
check("…RTL → the Hebrew text on the left", seen[1][5] == "Zed · סוכן · לא לגעת" and seen[1][-1] == "rtl", seen[1][4:])
check("the theme's name follows the language", json.loads((tmp / "themes-i18n" / "zed" / "manifest.json").read_text())["name"] == "סוכן: Zed")

os.environ.pop("RAINBOW_LANG")
i18n._mac_lang = lambda: ""
for env, want in (({"LANG": "he_IL.UTF-8"}, "he"), ({"LANG": "en_US.UTF-8"}, "en"), ({}, "en")):
    i18n._detected = None
    saved = {k: os.environ.pop(k, None) for k in ("LC_ALL", "LC_MESSAGES", "LANG")}
    os.environ.update(env)
    got = i18n.lang()
    for k, v in saved.items():
        os.environ.pop(k, None)
        if v is not None:
            os.environ[k] = v
    check(f"no RAINBOW_LANG: locale {env.get('LANG', '(none)')} → {want}", got == want, got)
i18n._detected = None
i18n._mac_lang = lambda: "he-il"
check("macOS preferred language Hebrew → he (before LANG, which launchd sets to en_US)", i18n.lang() == "he")
os.environ["RAINBOW_LANG"] = "en"
check("RAINBOW_LANG wins over the Mac's language", i18n.lang() == "en")
r = subprocess.run([sys.executable, "-I", str(HERE / "rainbow_i18n.py"), "desk.opened", "name=Alpha"], capture_output=True, text=True,
                   env=dict(os.environ, RAINBOW_LANG="en"))
check("the shell scripts' helper prints one message", r.stdout.strip() == "Alpha's browser is open", r.stdout)
os.environ["RAINBOW_LANG"] = "he"

os.environ["RAINBOW_HOME"] = str(tmp / "root")
bo_root, ao_root = load("browser-owner.py"), load("agent-office.py")
os.environ["RAINBOW_HOME"] = str(SAFE_HOME)
check("RAINBOW_HOME moves logs, state and themes in one place",
      bo_root.SHARED == tmp / "root" and bo_root.THEMES == tmp / "root" / "themes" and ao_root.LEASES == tmp / "root" / "state" / "doc_leases"
      and ao_root.LOG == tmp / "root" / "logs" / "agent-office.log" and ao_root.WORD_DIR == tmp / "root" / "word-convert",
      (bo_root.SHARED, ao_root.LEASES))

# ── install.sh (into a fake home; launchd is never touched in a test) ──
fake_home = tmp / "home"; fake_home.mkdir()
ienv = dict(os.environ, HOME=str(fake_home), RAINBOW_INSTALL_ANY_OS="1", RAINBOW_INSTALL_NO_LAUNCHCTL="1")
ienv.pop("RAINBOW_HOME", None)
installer = str(HERE.parent / "install.sh")
r = subprocess.run(["bash", installer, "--with-sweep"], capture_output=True, text=True, env=ienv)
ib = fake_home / "bin"
plist = fake_home / "Library" / "LaunchAgents" / "com.rainbowomma.agent-office-sweep.plist"
check("install: the tools land together in ~/bin, executable, with the message catalog",
      r.returncode == 0 and all(os.access(ib / n, os.X_OK) for n in ("browser-owner", "port-owner", "proc-owner", "as-agent", "rainbowomma-mcp", "rainbowomma-session-end", "office-owner", "agent-office", "kill-chrome.sh", "rainbowomma-guard", "cua-color-proxy"))
      and (ib / "rainbow_i18n.py").exists(), r.stdout + r.stderr)
check("install: browsers.json is created from the example", json.loads((ib / "browsers.json").read_text())["agents"].keys() >= {"alpha"})
check("install: the state folders exist", all((fake_home / ".rainbowomma" / d).is_dir() for d in ("logs", "state", "word-convert")))
ptxt = plist.read_text() if plist.exists() else ""
check("install: the sweep job has absolute paths — launchd does not expand ~",
      "~" not in ptxt and f"<string>{ib}/agent-office</string>" in ptxt and str(fake_home / ".rainbowomma" / "logs") in ptxt, ptxt[:300])
(ib / "browsers.json").write_text('{"agents": {"mine": {}}}')
r = subprocess.run(["bash", installer], capture_output=True, text=True, env=ienv)
check("install: a second run never overwrites your browsers.json", r.returncode == 0 and "mine" in (ib / "browsers.json").read_text())
r = subprocess.run(["bash", installer, "--with-sweep"], capture_output=True, text=True, env=dict(ienv, RAINBOW_HOME=str(tmp / "elsewhere")))
check("install: a custom RAINBOW_HOME is handed to the sweep job", "<key>RAINBOW_HOME</key><string>" + str(tmp / "elsewhere") in plist.read_text())
dry_home = tmp / "dry"; dry_home.mkdir()
r = subprocess.run(["bash", installer, "--with-sweep", "--dry-run"], capture_output=True, text=True, env=dict(ienv, HOME=str(dry_home)))
check("install --dry-run changes nothing", r.returncode == 0 and not any(dry_home.iterdir()), list(dry_home.iterdir()))
r = subprocess.run(["bash", installer], capture_output=True, text=True, env=dict(ienv, RAINBOW_INSTALL_ANY_OS="0"))
check("install: refuses to run anywhere but macOS", sys.platform == "darwin" or (r.returncode == 1 and "macOS" in r.stderr), r.stderr)

# ── the shared guard (bin/rainbowomma-guard.py), fed each agent framework's hook payload on stdin ──
guard = str(HERE / "rainbowomma-guard.py")
def run_guard(ev, *args):
    r = subprocess.run([sys.executable, "-I", guard, *args], input=json.dumps(ev), capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr
def hook(cmd, tool="Bash"):
    code, _, err = run_guard({"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": {"command": cmd}})
    return code, err
blocked_cmds = ["pkill -f 'Google Chrome'", "cd /tmp && pkill -f chrome", "sudo killall 'Google Chrome'", "kill -9 $(pgrep -f remote-debugging)",
                "kill `pgrep Chrome`", "pgrep -f Chrome | xargs kill", "osascript -e 'tell application \"Google Chrome\" to quit'",
                "osascript -e 'quit app \"Google Chrome\"'",
                "'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --remote-debugging-port=9222 --user-data-dir=/tmp/x"]
res = [hook(c) for c in blocked_cmds]
check("guard blocks every way around the owner (exit 2, a reason for the agent on stderr)",
      all(code == 2 and "browser-owner" in err for code, err in res), [c for c, (code, _) in zip(blocked_cmds, res) if code != 2])
allowed = ["~/bin/browser-owner start alpha --by alpha", "~/bin/office-owner pdf --agent alpha a.docx", "kill 12345", "ls ~/pkill-notes",
           "echo skill", "osascript -e 'tell application \"Google Chrome\" to get URL of active tab of front window'"]
res = [hook(c) for c in allowed]
check("…and lets the owner and ordinary commands through", all(code == 0 for code, _ in res), [c for c, (code, _) in zip(allowed, res) if code])
check("…and lets through a payload that carries no command (e.g. a file read)",
      run_guard({"tool_name": "Read", "tool_input": {"file_path": "/tmp/pkill-notes"}})[0] == 0)
check("…and lets through anything it can't parse", subprocess.run([sys.executable, "-I", guard], input="not json", capture_output=True, text=True).returncode == 0)
BAD = "pkill -f 'Google Chrome'"
shapes = {
    "Claude Code / Codex / Gemini / Qwen / Factory / Hermes / Goose / Copilot PreToolUse": {"tool_name": "run_shell_command", "tool_input": {"command": BAD}},
    "Cursor beforeShellExecution": {"hook_event_name": "beforeShellExecution", "command": BAD, "cwd": "/tmp"},
    "Windsurf pre_run_command": {"agent_action_name": "pre_run_command", "tool_info": {"command_line": BAD, "cwd": "/tmp"}},
    "Copilot CLI preToolUse (toolArgs as JSON text)": {"toolName": "bash", "toolArgs": json.dumps({"command": BAD})},
    "Cline CLI": {"tool_call": {"name": "run_commands", "input": {"commands": ["ls", BAD]}}},
    "Cline extension": {"preToolUse": {"toolName": "execute_command", "parameters": {"command": BAD}}},
    "Cline extension (stringified parameters)": {"preToolUse": {"toolName": "execute_command", "parameters": json.dumps({"command": BAD})}},
}
missed = [name for name, ev in shapes.items() if run_guard(ev)[0] != 2]
check("guard finds the command in every framework's payload shape", not missed, missed)
code, out, _ = run_guard(shapes["Cline CLI"], "--format", "cline")
check("guard --format cline answers Cline's way: {cancel: true, errorMessage}", code == 0 and json.loads(out)["cancel"] is True and "browser-owner" in json.loads(out)["errorMessage"], out)

# ── the adapters: every file parses, and every hook points at the shared guard ──
AD = HERE.parent / "adapters"
bad_json = []
for f in AD.rglob("*.json"):
    try:
        json.loads(f.read_text(encoding="utf-8"))
    except ValueError:
        bad_json.append(str(f.relative_to(AD)))
check("every adapter JSON file parses", not bad_json, bad_json)
try:
    import tomllib
    pol = tomllib.loads((AD / "gemini-cli" / "policies" / "rainbowomma.toml").read_text(encoding="utf-8"))
    rx = [r["commandRegex"] for r in pol["rule"] if "commandRegex" in r][0]
    check("Gemini policy: a hard deny for pkill/killall, and its regex catches AppleScript quitting Chrome",
          pol["rule"][0]["decision"] == "deny" and set(pol["rule"][0]["commandPrefix"]) == {"pkill", "killall"}
          and re.search(rx, '{"command":"osascript -e \'tell application \\"Google Chrome\\" to quit\'"') and not re.search(rx, '{"command":"ls"'))
except ImportError:
    pass
zed = json.loads((AD / "zed" / "settings.json").read_text())["agent"]["tool_permissions"]["tools"]["terminal"]["always_deny"]
check("Zed always_deny regexes catch what the guard catches", all(any(re.search(p["pattern"], c.lower()) for p in zed) for c in blocked_cmds)
      and not any(re.search(p["pattern"], c.lower()) for p in zed for c in allowed))
hooks_files = ["claude-code/settings.json", "codex/hooks.json", "gemini-cli/settings.json", "qwen-code/settings.json", "factory-droid/hooks.json",
               "goose/rainbowomma/hooks/hooks.json", "copilot/copilot-cli.json", "copilot/vscode.json", "cursor/hooks.json", "windsurf/hooks.json",
               "hermes/hooks.yaml", "cline/PreToolUse"]
check("every hook adapter runs the shared guard", all("rainbowomma-guard" in (AD / f).read_text(encoding="utf-8") for f in hooks_files),
      [f for f in hooks_files if "rainbowomma-guard" not in (AD / f).read_text(encoding="utf-8")])
check("the Cline hook asks the guard for Cline's answer format", "--format cline" in (AD / "cline" / "PreToolUse").read_text())
check("Codex exec policy forbids pkill and killall", 'decision = "forbidden"' in (AD / "codex" / "rainbowomma.rules").read_text()
      and "pkill" in (AD / "codex" / "rainbowomma.rules").read_text())
oc = json.loads((AD / "opencode" / "opencode.json").read_text())["permission"]["bash"]
check("OpenCode: pkill/killall denied after the catch-all (the last match wins)", list(oc)[0] == "*" and oc["pkill *"] == "deny" and oc["killall *"] == "deny")
check("the OpenCode and Kilo plugins are the same file", (AD / "opencode" / "plugins" / "rainbowomma.js").read_text() == (AD / "kilo-code" / "plugins" / "rainbowomma.js").read_text())
agents_md = (HERE.parent / "docs" / "AGENTS.md").read_text(encoding="utf-8")
linked = set(re.findall(r"\(\.\./(adapters/[^)]+)\)", agents_md))
check("docs/AGENTS.md links only to adapter files that exist", linked and all((HERE.parent / l.rstrip("/")).exists() for l in linked),
      [l for l in linked if not (HERE.parent / l.rstrip("/")).exists()])

# ── cua-color-proxy: a fake `cua-driver mcp` (MCP over stdio) — never the real driver in a test ──
FAKE_DRIVER = r"""
import json, sys
calls = open(sys.argv[1], "a")
for line in sys.stdin:
    m = json.loads(line)
    calls.write(line); calls.flush()
    if "id" not in m:
        continue
    if m["method"] == "initialize":
        res = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "fake-cua", "version": "0.21.0"}}
    elif m["method"] == "tools/call":
        n, a = m["params"]["name"], m["params"].get("arguments") or {}
        if n == "start_session":
            sc = {"session": a.get("session") or "implicit-7", "active": True}
            res = {"content": [{"type": "text", "text": json.dumps(sc)}], "structuredContent": sc}
        elif n == "set_agent_cursor_theme" and a["theme_id"].endswith(".missing"):
            res = {"content": [{"type": "text", "text": "theme not installed"}], "isError": True}
        else:
            res = {"content": [{"type": "text", "text": n + " ok"}], "structuredContent": {"ok": True}}
    else:
        res = {}
    print(json.dumps({"jsonrpc": "2.0", "id": m["id"], "result": res}), flush=True)
"""
(tmp / "fake_cua.py").write_text(FAKE_DRIVER)
proxy = str(HERE / "cua-color-proxy.py")
def through_proxy(msgs, agent="alpha", idle=None):
    log_f = tmp / f"cua-calls-{time.time_ns()}.jsonl"
    env = dict(os.environ, RAINBOW_HOME=str(tmp / "cua-home"))
    if idle is not None:
        env["RAINBOW_CUA_IDLE_S"] = str(idle)
    r = subprocess.run([sys.executable, "-I", proxy, "--agent", agent, "--driver", sys.executable, "--", "-I", str(tmp / "fake_cua.py"), str(log_f)],
                       input="".join(json.dumps(m) + "\n" for m in msgs), capture_output=True, text=True, timeout=60, env=env)
    got = [json.loads(x) for x in r.stdout.splitlines() if x.strip()]
    seen = [json.loads(x) for x in log_f.read_text().splitlines()] if log_f.exists() else []
    return got, [(c["params"]["name"], c["params"].get("arguments") or {}) for c in seen if c.get("method") == "tools/call"]
def tc(i, name, **args):
    return {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": name, "arguments": args}}
INIT = [{"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"}]
got, calls = through_proxy(INIT + [tc(1, "click", x=1, y=2), tc(2, "type_text", text="hi")])
check("proxy: before the agent's first action, its implicit session starts with the agent's cursor theme",
      calls[:3] == [("start_session", {"cursor_theme": {"theme_id": "com.rainbowomma.cursor.alpha", "reduced_motion": "on"}}),
                    ("set_agent_cursor_theme", {"session": "implicit-7", "theme_id": "com.rainbowomma.cursor.alpha", "reduced_motion": "on"}),
                    ("click", {"x": 1, "y": 2})], calls)
check("proxy: …once — the next action goes straight through", [c[0] for c in calls] == ["start_session", "set_agent_cursor_theme", "click", "type_text"], calls)
check("proxy: the agent sees only its own answers, ids unchanged (ours never reach it)",
      [m.get("id") for m in got] == [0, 1, 2] and got[1]["result"]["content"][0]["text"] == "click ok", got)
got, calls = through_proxy(INIT + [tc(1, "click", session="run1"), tc(2, "click", session="run1"), tc(3, "end_session", session="run1"),
                                   tc(4, "click", session="run1")], agent="bravo")
check("proxy: a named session is themed once, with the agent's own theme",
      calls[:2] == [("start_session", {"cursor_theme": {"theme_id": "com.rainbowomma.cursor.bravo", "reduced_motion": "on"}, "session": "run1"}),
                    ("set_agent_cursor_theme", {"session": "run1", "theme_id": "com.rainbowomma.cursor.bravo", "reduced_motion": "on"})], calls)
check("proxy: a session the agent ended is never revived by the proxy",
      [c[0] for c in calls] == ["start_session", "set_agent_cursor_theme", "click", "click", "end_session", "click"], calls)
got, calls = through_proxy(INIT + [tc(1, "click"), tc(2, "click")], idle=0)
check("proxy: after an idle gap (the driver drops the implicit session) it is themed again",
      [c[0] for c in calls].count("start_session") == 2, calls)
got, calls = through_proxy(INIT + [tc(1, "click")], agent="missing")
check("proxy: a theme that is not installed never blocks the agent — its call goes through and it gets its answer",
      calls[-1] == ("click", {}) and [m.get("id") for m in got] == [0, 1] and "isError" not in got[1]["result"], (calls, got))
r = subprocess.run([sys.executable, "-I", proxy, "--agent", "alpha", "--driver", ""], capture_output=True, text=True,
                   env=dict(os.environ, PATH="/nonexistent", CUA_DRIVER=""))
check("proxy: no cua-driver → a clear error on stderr, nothing on stdout (stdout belongs to the MCP client)",
      sys.platform == "darwin" or (r.returncode == 1 and not r.stdout and "cua-driver not found" in r.stderr), (r.stdout, r.stderr))

# ── the review's findings stay fixed ──
ROOT_DIR = HERE.parent
mk = (ROOT_DIR / "install" / "make-desktop-apps.sh").read_text(encoding="utf-8")
check("desktop icons come from browsers.json, not from hard-coded agents", not re.search(r"\b(alpha|bravo|charlie)\b", mk) and "browser-owner\" list" in mk)
desk = (HERE / "desk-browser.sh").read_text(encoding="utf-8")
check("desk-browser.sh accepts any registered agent", not re.search(r"\b(alpha|bravo|charlie)\b", desk) and "names" in desk)
launcher = (ROOT_DIR / "examples" / "agent-launcher.sh").read_text(encoding="utf-8")
check("the example launcher never claims to be the human", "--by human" not in launcher and 'LAUNCH_BY="${LAUNCH_BY:-alpha}"' in launcher)
check("the example launcher stops recursing when browser-owner calls it (BROWSER_OWNER_LAUNCH)", "BROWSER_OWNER_LAUNCH" in launcher)
check("the example launcher allows exact CDP origins, never *", "--remote-allow-origins=*" not in launcher and "127.0.0.1:9222" in launcher)
check("shell tools find each other beside themselves, so install.sh --bin works",
      all("$HOME/bin" not in (HERE / f).read_text(encoding="utf-8") for f in ("desk-browser.sh", "kill-chrome.sh", "human-chrome.sh")))
_reg = bo.REGISTRY
bo.REGISTRY = tmp / "nowhere" / "browsers.json"
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = bo.main(["list"])
bo.REGISTRY = _reg
check("no browsers.json → one JSON answer that says how to create it", rc == 1 and "install.sh" in json.loads(buf.getvalue())["why"], buf.getvalue())

# ── the second review's findings stay fixed ──
# 1–3: the guard reads the shell line (words, pipes, $( ), sh -c), not the raw text
bypasses = ["/usr/bin/pkill -f Chrome", "/usr/bin/killall 'Google Chrome'", "\\pkill Chrome", "sudo -u root /usr/bin/pkill x", "nohup env A=1 pkill x &",
            "bash -c 'pkill Chrome'", "eval \"killall Chrome\"", "ls\npkill Chrome", "kill -9 \"$(pgrep -f Chrome)\"",
            "ps aux | grep Chrome | awk '{print $2}' | xargs kill -9", "lsof -ti :9223 | xargs kill",
            "open -na 'Google Chrome' --args --remote-debugging-port=9223 --user-data-dir=/tmp/x",
            "~/bin/browser-owner stop bravo --by human", "browser-owner start bravo --by=HUMAN", "python3 -I ~/bin/browser-owner.py stop bravo --by human",
            "~/bin/office-owner close --agent bravo x.docx --by human", "~/bin/desk-browser.sh close agents", "bash ~/bin/kill-chrome.sh --all",
            "LAUNCH_BY=human ~/bin/agent-launcher.sh", "export LAUNCH_BY=human; ~/bin/agent-launcher.sh", "lsof -ti :3000 | xargs kill"]
res = [hook(c) for c in bypasses]
check("guard: no way around it by path, backslash, wrapper, sh -c, eval, a new line, ps/lsof | xargs kill, open -a, or posing as the human",
      all(code == 2 for code, _ in res), [c for c, (code, _) in zip(bypasses, res) if code != 2])
harmless = ["git commit -m 'stop using killall and pkill'", "echo \"don't pkill please\"", "grep -rn pkill bin/",
            "cat > notes.md <<'EOF'\nnever run pkill or killall\nEOF", "~/bin/browser-owner stop alpha --by alpha", "~/bin/browser-owner idle-stop bravo --by bravo",
            "echo \"unbalanced", "npm run build && npm test", "python3 -c 'print(1)'"]
res = [hook(c) for c in harmless]
check("guard: words in a message, a search or a heredoc are not commands — let through", all(code == 0 for code, _ in res),
      [c for c, (code, _) in zip(harmless, res) if code])
# 4: one message the proxy can't read never stops the agent's traffic
pm = load("cua-color-proxy.py")
class _Sink:
    def __init__(self): self.lines = []
    def write(self, b): self.lines.append(b)
    def flush(self): pass
    def close(self): pass
px = pm.Proxy.__new__(pm.Proxy); px.agent, px.themed, px.ended = "alpha", {}, set()
px.proc = type("P", (), {"stdin": _Sink()})()
px.theme_session = lambda label: None
feed = [b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"click","arguments":[1]}}\n',
        b'{"jsonrpc":"2.0","id":2,"method":"tools/call","params":"x"}\n', b'{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"click"}}\n']
px.pump_agent(io.BytesIO(b"".join(feed)))
check("proxy: malformed tool calls pass through, and the messages after them still reach the driver", px.proc.stdin.lines == feed, px.proc.stdin.lines)
# 5: pdf never replaces a PDF that is already there
ao.RUN = word_osa; calls.clear()
src2 = tmp / "agent" / "report.docx"; src2.write_text("x"); (tmp / "agent" / "report.pdf").write_bytes(b"%PDF- the human's")
code, out = ao.cmd_pdf("bravo", str(src2))
check("pdf: report.pdf already exists → refused before Word is touched, the old PDF intact",
      code == 1 and not calls and (tmp / "agent" / "report.pdf").read_bytes() == b"%PDF- the human's", out)
code, out = ao.cmd_pdf("bravo", str(src2), force=True)
check("pdf --force: replaces it on purpose", code == 0 and (tmp / "agent" / "report.pdf").read_bytes() == b"%PDF- test", out)
ao.RUN = osa
# 6: a launch record with no pid of ours never adopts the human's Word
ao.save_apps_state({"word": {"launchedBy": "office-owner/x", "pid": None, "launchedAt": time.time() - 9999, "lastActivity": time.time() - 9999}})
pids["word"] = 555
ao.touch("word")
check("touch: a stale owner record without a pid does not adopt the Word running now", json.loads(ao.APPS_STATE.read_text())["word"]["pid"] is None)
r = ao.idle_quit()
check("idle quit: …and that Word becomes the human's, never quit", r == [] and json.loads(ao.APPS_STATE.read_text())["word"]["launchedBy"] == "human", r)
import subprocess as _sp
class _FailOpen:
    TimeoutExpired = _sp.TimeoutExpired
    @staticmethod
    def run(args, **kw):
        return _sp.CompletedProcess(args, 1 if args[0] == "open" else 0, "false", "could not open")
ao.save_apps_state({}); pids["word"] = None
_sub, _run = ao.subprocess, ao.RUN
ao.subprocess, ao.RUN = _FailOpen, None
code, out = ao.cmd_open("bravo", str(src2))
ao.subprocess, ao.RUN = _sub, _run
check("open fails → no 'launched by the owner' record is left behind", code == 1 and "word" not in ao.apps_state(), (out, ao.apps_state()))
# 7: a theme install leaves no file descriptors behind
bo3 = load("browser-owner.py")
class _NoChrome:
    def __init__(self, *a, **k): pass
    def terminate(self): pass
    def wait(self, timeout=None): return 0
    def kill(self): pass
bo3.subprocess = type("S", (), {"Popen": _NoChrome, "DEVNULL": _sp.DEVNULL})
fd_dir = "/proc/self/fd" if os.path.isdir("/proc/self/fd") else "/dev/fd"
n0 = len(os.listdir(fd_dir))
t0 = time.time()
ok, why = bo3.install_theme({"profile": str(tmp / "fd-profile")}, tmp, timeout=3)
check("install_theme: no file descriptor leaks, and a Chrome that never answers is seen at once (EOF), not after the timeout",
      not ok and len(os.listdir(fd_dir)) == n0 and time.time() - t0 < 2, (n0, len(os.listdir(fd_dir)), why))
# 8: the theme install's own clean quit is told apart, without hiding the real lastStop
qp = tmp / "q-profile"; (qp / "Default").mkdir(parents=True, exist_ok=True)
(qp / "Default" / "Preferences").write_text(json.dumps({"profile": {"exit_type": "Normal"}}))
_bt = bo.boot_time; bo.boot_time = lambda: 0
qa = {"profile": str(qp), "state": str(tmp / "q.json")}
check("a clean quit right after a theme install is the owner's, not a person's ⌘Q", bo.quit_by_person(qa, st={"lastThemeInstall": {"at": bo.now_iso()}}) is False)
check("…and a clean quit with no owner close around it is still a person's ⌘Q", bo.quit_by_person(qa, st={}) is True)
bo.boot_time = _bt
# 9: idle-stop only by the agent itself (or its reaper), and only once it can be idle
bo.processes = lambda: [(200, 1, HUMAN), (600, 1, BRAVO_CMD)]
BR = dict(BRAVO_A, peers=["alpha", "bravo", "charlie"])
Path(BR["state"]).write_text(json.dumps({"lastStart": {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(time.time() - 7200))}}))
killed.clear()
code, out = bo.do_idle_stop(BR, "alpha")
check("idle-stop: another agent is refused — Alpha never closes Bravo's browser", code == 2 and out["status"] == "refused" and not killed, out)
Path(BR["state"]).write_text(json.dumps({"lastStart": {"at": bo.now_iso()}}))
code, out = bo.do_idle_stop(BR, "bravo")
check("idle-stop: refused when the browser was opened less than idleMinutes ago", code == 2 and not killed, out)
Path(BR["state"]).write_text(json.dumps({"lastStart": {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(time.time() - 7200))}}))
code, out = bo.do_idle_stop(BR, "bravo")
check("idle-stop: by the agent itself, after its idle time → closed", code == 0 and killed == [{600}], out)
# 10: the shell tools never call macOS's python3 stub (it pops up an install dialog)
stubby = [f for f in ("bin/kill-chrome.sh", "bin/desk-browser.sh", "bin/human-chrome.sh", "install/make-desktop-apps.sh", "examples/agent-launcher.sh")
          if re.search(r"^[^#]*/usr/bin/python3 -I", (ROOT_DIR / f).read_text(encoding="utf-8"), re.M) or "xcode-select -p" not in (ROOT_DIR / f).read_text(encoding="utf-8")]
stubby += [f for f in ("browser-owner", "office-owner", "agent-office", "rainbowomma-guard", "cua-color-proxy") if "xcode-select -p" not in (HERE / f).read_text()]
check("shell tools and wrappers skip the python3 stub when the developer tools are missing", not stubby, stubby)
r = subprocess.run(["bash", str(HERE / "desk-browser.sh"), "nonsense"], capture_output=True, text=True, env=dict(os.environ, RAINBOW_LANG="en"))
check("…and still print their messages", r.returncode == 2 and "usage" in r.stdout, (r.stdout, r.stderr))
check("desktop icons: a label is escaped inside the AppleScript strings", 'asq "$name"' in mk and '\\"$name\\"' not in mk)

# ── port-owner: a range of ports per agent, leases inside it, the usual ports left to the human ──
check("ports: an agent without \"ports\" gets 100 of its own, from its CDP port (9222 → 41000-41099, 9224 → 41200-41299)",
      reg["alpha"]["ports"] == (41000, 41099) and reg["charlie"]["ports"] == (41200, 41299), (reg["alpha"]["ports"], reg["charlie"]["ports"]))
for bad, why in (({"ports": "41000-41150"}, "overlaps another agent's range"), ({"ports": "80-90"}, "below 1024"), ({"ports": "lots"}, "not a range")):
    r = json.loads(REG.read_text()); r["agents"]["zed"] = dict({"label": "z", "port": 9230, "profile": str(tmp / "zp"), "color": "#000000"}, **bad)
    bp = tmp / "bad-ports.json"; bp.write_text(json.dumps(r))
    try:
        bo.registry(bp); ok_ = False
    except ValueError:
        ok_ = True
    check(f"ports: the registry refuses a range that is {why}", ok_)
os.environ["RAINBOW_HOME"] = str(tmp / "po-home")
po = load("port-owner.py")
os.environ["RAINBOW_HOME"] = str(SAFE_HOME)
po.REGISTRY = REG
listening = {}
po.LISTENERS = lambda: dict(listening)
po.BINDABLE = lambda port: port not in listening
code, out = po.cmd_lease("alpha")
check("lease: Alpha gets the first port of its own range", code == 0 and out["status"] == "leased" and out["port"] == 41000, out)
code, out = po.cmd_lease("alpha")
check("lease: asking again for the same name gives the same port back", out["port"] == 41000 and out.get("existing"), out)
listening[41001] = "node (pid 4242)"
code, out = po.cmd_lease("alpha", "web")
check("lease: a second name skips a port something already listens on", out["port"] == 41002, out)
code, out = po.cmd_lease("bravo")
check("lease: Bravo gets its own range, never Alpha's", out["port"] == 41100, out)
code, out = po.cmd_lease("alpha", "api", prefer=3000)
check("lease --prefer 3000: refused — the usual dev ports stay the human's", code == 2 and out["status"] == "refused" and "3000" in out["why"], out)
code, out = po.cmd_lease("alpha", "api", prefer=41150)
check("lease --prefer: a port in Bravo's range is refused for Alpha", code == 2 and "41000-41099" in out["why"], out)
code, out = po.cmd_lease("alpha", "api", prefer=41001)
check("lease --prefer: a port something listens on is refused, and says who", code == 2 and "node (pid 4242)" in out["why"], out)
code, out = po.cmd_lease("ghost")
check("lease: an unknown agent is a failure that names the registered ones", code == 1 and "alpha" in out["why"], out)
w = [po.cmd_who(p)[1] for p in (3000, 41100, 41150, 41001, 12345)]
check("who: 3000 the human's (reserved) · 41100 Bravo's lease · 41150 Bravo's range · 41001 Alpha's range, with its listener · 12345 the human's",
      [(x["owner"], x["why"]) for x in w] == [("human", "reserved"), ("bravo", "lease"), ("bravo", "range"), ("alpha", "range"), ("human", "unassigned")]
      and w[3]["listening"] == "node (pid 4242)", w)
st = json.loads(po.STATE.read_text()); st["leases"][0]["at"] = time.time() - 3600; po.STATE.write_text(json.dumps(st))
code, out = po.cmd_list("alpha")
check("a lease nobody listens on is dropped after 10 minutes", [x["name"] for x in out["leases"]] == ["web"] and out["ranges"] == {"alpha": "41000-41099"}, out)
code, out = po.cmd_release("alpha", every=True)
check("release --all gives back every lease of that agent, and only its", out["count"] == 1 and [x["agent"] for x in po.leases_of()] == ["bravo"], (out, po.leases_of()))
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = po.main(["env", "alpha", "--name", "web", "--var", "vite_port"])
check("env: shell words for eval — PORT and any other variable set to the same leased port", rc == 0 and buf.getvalue().strip() == "PORT=41000 VITE_PORT=41000", buf.getvalue())
# the guard, with each agent's ranges and leases
po.cmd_lease("bravo", "web")
genv = dict(os.environ, BROWSER_OWNER_REGISTRY=str(REG), RAINBOW_HOME=str(tmp / "po-home"))
def as_agent(cmd, agent=None):
    e = dict(genv, **({"RAINBOW_AGENT": agent} if agent else {}))
    r = subprocess.run([sys.executable, "-I", guard], input=json.dumps({"tool_input": {"command": cmd}}), capture_output=True, text=True, env=e)
    return r.returncode
alpha_blocked = ["npm run dev -- --port 3000", "PORT=8080 npm start", "PORT=41100 npm start", "python3 -m http.server 8000",
                 "docker run -p 3000:80 nginx", "PORT=3000 bash -c 'npm start'", "export VITE_PORT=5173; npm run dev"]
alpha_allowed = ["PORT=41000 npm run dev", "npm run dev -- --port=41050", "docker run -p 127.0.0.1:41005:80 nginx", "git commit -m 'serve on PORT=3000'",
                 "eval \"$(port-owner env alpha) npm run dev\"", "npm test"]
check("guard as Alpha: no port outside Alpha's own — the human's 3000/8080/5173 and Bravo's range are refused",
      all(as_agent(c, "alpha") == 2 for c in alpha_blocked), [c for c in alpha_blocked if as_agent(c, "alpha") != 2])
check("guard as Alpha: its own ports, a commit message and the port-owner way are let through",
      all(as_agent(c, "alpha") == 0 for c in alpha_allowed), [c for c in alpha_allowed if as_agent(c, "alpha")])
check("guard without RAINBOW_AGENT: only another agent's port is refused (its range or lease); 3000 is let through",
      as_agent("npm run dev -- --port 3000") == 0 and as_agent("npm run dev -- --port 41150") == 2 and as_agent("PORT=41100 npm start") == 2)
port_killers = ["npx kill-port 3000", "kill-port 41100", "fuser -k 3000/tcp", "lsof -ti :41100 | xargs kill -9"]
check("guard: freeing a port by killing whoever holds it is refused (kill-port, fuser -k, lsof | xargs kill)",
      all(as_agent(c, "alpha") == 2 for c in port_killers), [c for c in port_killers if as_agent(c, "alpha") != 2])

# ── proc-owner: whose process this is, and stopping only your own ──
os.environ["RAINBOW_HOME"] = str(tmp / "po-home")
pc = load("proc-owner.py")
os.environ["RAINBOW_HOME"] = str(SAFE_HOME)
pc.PO.REGISTRY = REG
listening.clear()
pc.PO.LISTENERS = lambda: dict(listening)
pc.PO.BINDABLE = lambda port: port not in listening
ALPHA_CHROME = f"{CH} --user-data-dir={reg['alpha']['profile']} --remote-debugging-port=9222"
prows = [(1, 0, "launchd"), (500, 1, "/bin/zsh"), (510, 500, "claude"), (511, 510, "npm run dev"), (512, 511, "node server.js"),
         (520, 1, "node orphan.js"), (530, 1, "node bravo-api.js"), (540, 500, "vim notes.txt"), (100, 1, ALPHA_CHROME), (101, 100, HELPER),
         (550, 1, "python3 -m http.server 41003"), (560, 1, "tail -f log")]
pc.PROCESSES = lambda: list(prows)
pc.MARKERS = lambda: {510: "alpha", 520: "alpha", 530: "bravo", 550: "alpha", 560: "alpha"}
sent = []
pc.KILL = lambda pid, sig: sent.append((pid, sig))
pc.ALIVE = lambda pid: False
w = {p: pc.cmd_whose(p)[1] for p in (510, 512, 101, 530, 540)}
check("whose: by RAINBOW_AGENT (env) · by an ancestor that carries it · by the agent's Chrome tree · another agent · the human's",
      [(w[p]["agent"], w[p]["via"]) for p in (510, 512, 101, 530, 540)]
      == [("alpha", "env"), ("alpha", "ancestor"), ("alpha", "browser"), ("bravo", "env"), ("human", "none")], w)
check("whose: no such process → a clear failure", pc.cmd_whose(99999)[0] == 1)
code, out = pc.cmd_kill(530, "alpha")
check("kill: Alpha may not stop Bravo's server", code == 2 and out["status"] == "refused" and not sent, out)
code, out = pc.cmd_kill(540, "alpha")
check("kill: …nor the human's editor", code == 2 and not sent, out)
code, out = pc.cmd_kill(512, "alpha")
check("kill: Alpha stops its own (a child of its session)", code == 0 and out["status"] == "stopped" and sent == [(512, 15)], out)
sent.clear()
code, out = pc.cmd_kill(530, "human")
check("kill --by human: the human may stop any process", code == 0 and sent == [(530, 15)], out)
sent.clear()
check("kill: pid 1 is never stopped from here", pc.cmd_kill(1, "human")[0] == 2 and not sent)
listening.update({41001: "node (pid 520)", 41003: "Python (pid 550)", 41101: "node (pid 530)"})
code, out = pc.cmd_list("alpha")
check("list: Alpha's processes, with the ports they listen on",
      {x["pid"] for x in out["processes"]} == {510, 511, 512, 520, 550, 560, 100, 101}
      and next(x for x in out["processes"] if x["pid"] == 520)["ports"] == [41001], out)
pc.PO.cmd_release("alpha", every=True)
pc.PO.cmd_lease("alpha", "web", prefer=41007)
code, out = pc.cmd_reap("alpha", dry=True)
check("reap --dry-run: names Alpha's orphaned servers (520, 550) and its idle lease, stops nothing",
      out["status"] == "would-reap" and sorted(out["processes"]) == [520, 550] and out["leases"] == [41007] and not sent, out)
code, out = pc.cmd_reap("alpha")
check("reap: stops only Alpha's orphaned servers — never its live session (511/512), its Chrome, a non-server (560) or Bravo's (530)",
      code == 0 and sorted(p for p, _ in sent) == [520, 550] and out["released"] == [41007]
      and not any(x["agent"] == "alpha" for x in pc.PO.leases_of()), (out, sent))
sent.clear()
_gp = os.getpid
prows.append((os.getpid(), 1, "proc-owner reap"))
pc.MARKERS = lambda: {510: "alpha", 520: "alpha", 530: "bravo", 550: "alpha", 560: "alpha", os.getpid(): "alpha"}
listening[41009] = f"Python (pid {os.getpid()})"
code, out = pc.cmd_reap("alpha", dry=True)
check("reap: never the process running it, nor its ancestors (the agent's own session-end hook)", os.getpid() not in out["processes"], out)
listening.clear()
# the guard's `kill <pid>` check, against real processes (RAINBOW_AGENT in their environment)
kids = {who: subprocess.Popen(["sleep", "60"], env=dict(os.environ, **({"RAINBOW_AGENT": who} if who != "human" else {})))
        for who in ("alpha", "bravo", "human")}
os.environ.pop("RAINBOW_AGENT", None)
try:
    time.sleep(0.3)
    got = {(me, who): as_agent(f"kill {kids[who].pid}", me) for me in ("alpha", None) for who in ("alpha", "bravo", "human")}
finally:
    for k in kids.values():
        k.kill()
check("guard as Alpha: `kill <pid>` only for Alpha's own process — Bravo's and the human's are refused",
      got[("alpha", "alpha")] == 0 and got[("alpha", "bravo")] == 2 and got[("alpha", "human")] == 2, got)
check("guard without RAINBOW_AGENT: nothing is provably the caller's — every live process is refused",
      got[(None, "bravo")] == 2 and got[(None, "alpha")] == 2 and got[(None, "human")] == 2, got)

# ── after a session: reap, the session-end hook, as-agent ──
listening.clear(); listening.update({41001: "node (pid 520)", 41003: "Python (pid 550)"})
pc.MARKERS = lambda: {510: "alpha", 520: "alpha", 530: "bravo", 550: "alpha", 560: "alpha"}
pc.SESSIONS = lambda: {520: "alpha-1", 550: "alpha-2"}
sent.clear()
code, out = pc.cmd_reap("alpha", session="alpha-1")
check("reap --session: only the servers that session left behind — another live Alpha session's server stays",
      code == 0 and [p for p, _ in sent] == [520], (out, sent))
listening.clear(); sent.clear()
senv = dict(genv, BROWSER_OWNER_REGISTRY=str(REG))
senv.pop("RAINBOW_AGENT", None)
r = subprocess.run(["bash", str(HERE / "rainbowomma-session-end")], input="{}", capture_output=True, text=True, env=senv)
check("session-end hook: an agent without RAINBOW_AGENT → nothing to do, never in the way (exit 0, silent)", r.returncode == 0 and not r.stdout, r)
r = subprocess.run(["bash", str(HERE / "as-agent"), "alpha", "bash", "-c", 'echo "$RAINBOW_AGENT $RAINBOW_SESSION"; exit 3'],
                   capture_output=True, text=True, env=senv)
check("as-agent: the command runs as alpha with its own session id, and its exit code comes back",
      r.returncode == 3 and re.fullmatch(r"alpha alpha-\d+-\d+", r.stdout.strip()), (r.returncode, r.stdout, r.stderr))
r = subprocess.run(["bash", str(HERE / "as-agent"), "ghost", "true"], capture_output=True, text=True, env=senv)
check("as-agent: an agent that is not in browsers.json is refused", r.returncode == 2 and "not an agent" in r.stderr, r.stderr)
ends = {"claude-code/settings.json": "SessionEnd", "gemini-cli/settings.json": "SessionEnd", "factory-droid/hooks.json": "SessionEnd",
        "copilot/copilot-cli.json": "sessionEnd"}
check("adapters: Claude Code, Gemini CLI, Factory Droid and Copilot CLI run the session-end hook",
      all("rainbowomma-session-end" in json.dumps(json.loads((AD / f).read_text())["hooks"][k]) for f, k in ends.items()))
check("adapters: the Claude Code adapter names the agent (RAINBOW_AGENT) for the guard and the reaper",
      json.loads((AD / "claude-code" / "settings.json").read_text())["env"]["RAINBOW_AGENT"] == "alpha")

# ── rainbowomma-mcp: the owners as MCP tools ──
def mcp(msgs, *args, env=None):
    r = subprocess.run(["bash", str(HERE / "rainbowomma-mcp"), *args], input="".join(json.dumps(m) + "\n" for m in msgs),
                       capture_output=True, text=True, timeout=60, env=env or senv)
    return [json.loads(x) for x in r.stdout.splitlines() if x.strip()]
init = {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}}
got = mcp([init, {"jsonrpc": "2.0", "method": "notifications/initialized"}, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
           {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "lease_port", "arguments": {"name": "mcp-web"}}},
           {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "who_port", "arguments": {"port": 3000}}},
           {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "lease_port", "arguments": {"prefer": 8080}}},
           {"jsonrpc": "2.0", "id": 5, "method": "nope"}], "--agent", "alpha")
names = [x["name"] for x in got[1]["result"]["tools"]]
check("mcp: initialize answers the client's protocol version; the notification gets no reply",
      [m["id"] for m in got] == [0, 1, 2, 3, 4, 5] and got[0]["result"]["protocolVersion"] == "2025-06-18", got[:1])
check("mcp: the tools — ports, processes, the agent's own browser",
      {"lease_port", "release_port", "who_port", "whose_process", "stop_process", "my_processes", "browser_status", "start_my_browser",
       "recover_my_browser", "take_screen", "release_screen", "ask_human_approval", "take_login", "ask_login_code", "release_login"} == set(names), names)
lp = got[2]["result"]
check("mcp lease_port: a port from Alpha's own range, as structured JSON", not lp["isError"] and 41000 <= lp["structuredContent"]["port"] <= 41099, lp)
check("mcp who_port: 3000 is the human's", got[3]["result"]["structuredContent"]["owner"] == "human")
check("mcp: a refusal comes back as isError with its status word and reason",
      got[4]["result"]["isError"] and got[4]["result"]["structuredContent"]["status"] == "refused", got[4])
check("mcp: an unknown method is a JSON-RPC error", got[5]["error"]["code"] == -32601)
got = mcp([init, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "stop_process", "arguments": {"pid": 1}}}])
check("mcp without an agent name: acting tools are refused (only the who/whose questions work)",
      got[1]["result"]["isError"] and "agent name" in got[1]["result"]["structuredContent"]["why"], got)

# ── from the private installation (19.10): front un-minimizes, the Dock tray, ONLY=, office-owner's reasons ──
import base64, hashlib, socket, struct, threading
class FakeCDP:
    """Chrome's DevTools endpoint, enough for restore_windows: /json/version, /json/list and the browser WebSocket"""
    def __init__(self, windows):
        self.windows, self.calls = windows, []                   # {targetId: (windowId, state)}
        self.sock = socket.socket(); self.sock.bind(("127.0.0.1", 0)); self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self.serve, daemon=True).start()
    def serve(self):
        while True:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self.one, args=(c,), daemon=True).start()
    def one(self, c):
        req = b""
        while b"\r\n\r\n" not in req:
            req += c.recv(4096)
        line = req.split(b"\r\n", 1)[0].decode()
        if line.startswith("GET /json/version"):
            body = json.dumps({"webSocketDebuggerUrl": f"ws://127.0.0.1:{self.port}/devtools/browser/fake"}).encode()
        elif line.startswith("GET /json/list"):
            body = json.dumps([{"id": t, "type": "page"} for t in self.windows]).encode()
        else:
            key = re.search(rb"Sec-WebSocket-Key: (\S+)", req).group(1)
            acc = base64.b64encode(hashlib.sha1(key + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest())
            c.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: " + acc + b"\r\n\r\n")
            return self.ws(c)
        c.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n" % len(body) + body); c.close()
    def ws(self, c):
        def recv(n):
            b = b""
            while len(b) < n:
                x = c.recv(n - len(b))
                if not x:
                    raise OSError
                b += x
            return b
        def send(obj):
            d = json.dumps(obj).encode()
            c.sendall(bytes([0x81]) + (bytes([len(d)]) if len(d) < 126 else bytes([126]) + struct.pack(">H", len(d))) + d)
        try:
            while True:
                b1, b2 = recv(2); n = b2 & 0x7F
                n = struct.unpack(">H", recv(2))[0] if n == 126 else n
                mask = recv(4); msg = json.loads(bytes(x ^ mask[i % 4] for i, x in enumerate(recv(n))))
                self.calls.append((msg["method"], msg.get("params")))
                send({"method": "Target.targetInfoChanged", "params": {}})                     # an event first: skipped
                m, prm = msg["method"], msg.get("params") or {}
                if m == "Target.getTargets":
                    res = {"targetInfos": [{"targetId": t, "type": "page"} for t in self.windows] + [{"targetId": "sw", "type": "service_worker"}]}
                elif m == "Browser.getWindowForTarget":
                    w, state = self.windows[prm["targetId"]]; res = {"windowId": w, "bounds": {"windowState": state}}
                else:
                    res = {}
                send({"id": msg["id"], "result": res})
        except OSError:
            c.close()
cdp = FakeCDP({"t1": (1, "minimized"), "t2": (2, "normal")})
check("CDP client (standard library WebSocket): calls in order, events skipped, results back",
      bo._cdp_browser_calls(cdp.port, [("Target.getTargets", {})])[0]["targetInfos"][0]["targetId"] == "t1")
cdp.calls.clear()
n = bo.restore_windows({"port": cdp.port})
check("front: only the minimized window goes back to normal, and the tab already shown is activated (never another)",
      n == 1 and ("Browser.setWindowBounds", {"windowId": 1, "bounds": {"windowState": "normal"}}) in cdp.calls
      and not any(c == ("Browser.setWindowBounds", {"windowId": 2, "bounds": {"windowState": "normal"}}) for c in cdp.calls)
      and cdp.calls[-1] == ("Target.activateTarget", {"targetId": "t1"}), cdp.calls)
check("front: no CDP answer → 0 restored, never an exception", bo.restore_windows({"port": 1}) == 0)
bo.processes = lambda: [(100, 1, ALPHA)]
_rw, _sf = bo.restore_windows, bo.set_front
bo.restore_windows = lambda a: 1; bo.set_front = lambda pid: True
code, out = bo.do_front(ALPHA_A)
check("front: the agent's browser comes to the front, saying how many windows came back", code == 0 and out == {"status": "front", "pid": 100, "restored": 1}, out)
bo.processes = lambda: [(200, 1, HUMAN)]
code, out = bo.do_front(ALPHA_A)
check("front: a browser that isn't running → down", code == 1 and out["status"] == "down", out)
bo.restore_windows, bo.set_front = _rw, _sf
desk_sh = (HERE / "desk-browser.sh").read_text()
check("desk-browser open: an open browser is brought to the front; a failure is exit 1 with the reason on stderr",
      '"$OWNER" front "$WHO"' in desk_sh and 'fail msg desk.not_opened' in desk_sh and 'fail msg desk.not_closed' in desk_sh)
# the Dock tray
sys.path.insert(0, str(HERE.parent / "install"))
import dock_tray
def tile(path):
    return {"tile-type": "file-tile", "tile-data": {"file-data": {"_CFURLString": "file://" + path.replace(" ", "%20") + "/"}}}
dock = {"persistent-apps": [tile("/System/Applications/Mail.app"), tile("/Applications/Google Chrome.app"), tile("/Applications/Notes.app")], "other": 1}
apps = ["/Users/you/Applications/RainbowOMMA/1 · Alpha — agent browser.app", "/Users/you/Applications/RainbowOMMA/2 · Bravo — agent browser.app"]
d1 = dock_tray.place(dock, "/Users/you/Applications/RainbowOMMA", apps)
kinds = [t["tile-type"] for t in d1["persistent-apps"]]
check("Dock tray: the agents side by side right after Chrome, between two small spacers; the rest of the Dock as it was",
      kinds == ["file-tile", "file-tile", "small-spacer-tile", "file-tile", "file-tile", "small-spacer-tile", "file-tile"]
      and d1["persistent-apps"][3]["tile-data"]["file-label"] == "1 · Alpha — agent browser" and d1["other"] == 1, kinds)
d2 = dock_tray.place(d1, "/Users/you/Applications/RainbowOMMA", apps[:1])
check("Dock tray: running it again replaces the group in place (no second group)", [t["tile-type"] for t in d2["persistent-apps"]]
      == ["file-tile", "file-tile", "small-spacer-tile", "file-tile", "small-spacer-tile", "file-tile"])
d3 = dock_tray.place(d2, "/Users/you/Applications/RainbowOMMA")
check("Dock tray --remove: only the group goes", d3["persistent-apps"] == dock["persistent-apps"])
d4 = dock_tray.place({"persistent-apps": [tile("/System/Applications/Mail.app")]}, "/x/RainbowOMMA", apps[:1])
check("Dock tray: no Chrome in the Dock → the group goes at the end", d4["persistent-apps"][0]["tile-data"]["file-data"]["_CFURLString"].endswith("Mail.app/"))
tray = (HERE.parent / "install" / "make-dock-tray.sh").read_text()
check("Dock tray: one applet per agent from browsers.json, no second Dock icon (LSUIElement), a dialog only on failure",
      "browser-owner\" list" in tray and "LSUIElement" in tray and "on error e" in tray and not re.search(r"\b(alpha|bravo|charlie)\b", tray))
mk2 = (HERE.parent / "install" / "make-desktop-apps.sh").read_text()
check("ONLY=<agent>: only that agent's icons are built, and nothing is archived",
      'ONLY="${ONLY:-}"' in mk2 and '[ "$who" != "$ONLY" ] && return 0' in mk2 and 'if [ -z "$ONLY" ]; then' in mk2)
# office-owner: a failure says why
_sub = ao.subprocess
class _Fails:
    TimeoutExpired = subprocess.TimeoutExpired
    @staticmethod
    def run(args, **kw):
        return subprocess.CompletedProcess(args, 1, "", "Microsoft Excel got an error: Parameter error. (-50)")
ao.subprocess, _run = _Fails, ao.RUN
ao.RUN = None
code, why = ao.osa("tell application \"Microsoft Excel\" to calculate")
ao.subprocess, ao.RUN = _sub, _run
check("office-owner: osascript's own reason comes back on a failure (it used to read only 'exit 1')", code == 1 and "(-50)" in why, why)
check("tests never touch the live state: every owner here keeps it in a temporary folder",
      all(str(m).startswith(tempfile.gettempdir()) for m in (bo.SHARED, ao.ROOT, po.STATE, pc.PO.STATE)), (bo.SHARED, ao.ROOT))

# ── heal: the colors survive Chrome Sync and Chrome updates ──
notes, inst = [], []
_nt, _vw, _cv, _pr = bo.notify, bo.view, bo.chrome_version, bo.processes
bo.notify = lambda title, text: notes.append(text)
bo.install_theme = lambda a, folder, timeout=25.0: fake_install(a, record=inst)
bo.CHROME_VER_FILE = tmp / "chrome-version.json"; bo.DOCK_APPS = tmp / "dock-apps"; bo.DOCK_APPS.mkdir(exist_ok=True)
(bo.DOCK_APPS / "3 · צ׳רלי — agent browser.app").mkdir(exist_ok=True)
def drop_theme(a):
    pp = Path(a["profile"], "Default", "Preferences"); d = json.loads(pp.read_text())
    d.setdefault("extensions", {})["theme"] = {"id": ""}; pp.write_text(json.dumps(d))
bo.chrome_version = lambda: "155.0.1"
drop_theme(CHARLIE_A); up[9224] = False; bo.processes = lambda: [(200, 1, HUMAN)]
r = bo.heal({"charlie": CHARLIE_A})
check("heal: a CLOSED browser whose theme Chrome Sync took gets it back now (windowless), with no notification",
      inst == [1] and r["agents"][0]["theme"] == "installed" and not notes and bo.theme_saved(CHARLIE_A), r)
r = bo.heal({"charlie": CHARLIE_A})
check("heal: …and the next pass leaves it alone", inst == [1] and r["agents"][0]["theme"] == "ok", r)
drop_theme(CHARLIE_A); bo.view = lambda a, st=None, rows=None: {"roots": [400], "profileBusy": []}
r1 = bo.heal({"charlie": CHARLIE_A}); r2 = bo.heal({"charlie": CHARLIE_A})
check("heal: an OPEN browser is never restarted — one notification (not one per pass), put back on its next start",
      inst == [1] and r1["agents"][0]["theme"] == "missing-open" and len(notes) == 1 and "צ׳רלי" in notes[0]
      and json.loads(Path(CHARLIE_A["state"]).read_text()).get("themeMissingSince"), (r1, notes))
bo.view = _vw; up[9224] = False
r = bo.heal({"charlie": CHARLIE_A})
check("heal: once it's closed the theme comes back and the 'missing' mark is cleared",
      inst == [1, 1] and not json.loads(Path(CHARLIE_A["state"]).read_text()).get("themeMissingSince"), r)
notes.clear(); bo.chrome_version = lambda: "156.0.2"
r = bo.heal({"charlie": CHARLIE_A})
check("heal: a Chrome update is noted, colors and Dock applets checked — one notification that all is in place",
      r["chromeChanged"] and r["dockMissing"] == [] and len(notes) == 1 and "156.0.2" in notes[0], (r, notes))
notes.clear(); bo.chrome_version = lambda: "157.0.0"
r = bo.heal({"charlie": CHARLIE_A, "alpha": ALPHA_A})
check("heal: …an agent without its Dock applet is named in that notification", r["dockMissing"] == [ALPHA_A["label"]]
      and len(notes) == 1 and ALPHA_A["label"] in notes[0], (r, notes))
r = bo.heal({"charlie": CHARLIE_A})
check("heal: no Chrome change → no notification", not r["chromeChanged"] and len(notes) == 1)
bo.notify, bo.chrome_version, bo.processes = _nt, _cv, _pr
bo.install_theme = fake_install
r = subprocess.run(["bash", installer, "--with-heal"], capture_output=True, text=True, env=ienv)
hp = fake_home / "Library" / "LaunchAgents" / "com.rainbowomma.heal.plist"
check("install --with-heal: the heal job, every 30 minutes and at login, with absolute paths",
      r.returncode == 0 and hp.exists() and "~" not in hp.read_text() and f"{fake_home}/bin/browser-owner" in hp.read_text()
      and "<integer>1800</integer>" in hp.read_text(), r.stdout + r.stderr)
tray = (HERE.parent / "install" / "make-dock-tray.sh").read_text()
check("Dock tray: the person's own Chrome closes the group (human.json color, or neutral grey)",
      "human-chrome.sh" in tray and "dock.human_name" in tray and "#B0BEC5" in tray)

# ── wave A: receipts, rm -rf of home, the human at the keyboard ──
import rainbow_receipts as rr
rpath = rr.path()
check("receipts live under RAINBOW_HOME (never the live install's during a test)", str(rpath).startswith(str(SAFE_HOME)), rpath)
_reg0 = bo.REGISTRY; bo.REGISTRY = REG
with contextlib.redirect_stdout(io.StringIO()):
    bo.main(["stop", "charlie", "--by", "alpha"])
bo.REGISTRY = _reg0
last = rr.read(n=1)[0]
check("a receipt for every acting command: who asked, for which agent, and the answer",
      (last["tool"], last["action"], last["agent"], last["by"], last["status"]) == ("browser-owner", "stop", "charlie", "alpha", "refused"), last)
rr.write("port-owner", "lease", "alpha", "alpha", "leased", port=41000)
check("receipts: read back by agent and tool, oldest first", [r["action"] for r in rr.read(agent="alpha")][-1] == "lease"
      and all(r["tool"] == "port-owner" for r in rr.read(tool="port-owner")))
rm_blocked = ["rm -rf ~", "rm -rf ~/", "rm -rf $HOME", "rm -Rf \"$HOME\"/", "sudo rm -rf /", "rm -rf /Users/someone", "rm -fr ~/*", "rm --recursive /usr"]
rm_allowed = ["rm -rf ~/projects/app/node_modules", "rm -rf build/", "rm ~/notes.txt", "rm -rf /tmp/scratch", "rm -rf \"$HOME/.cache/thing\""]
check("guard: rm -r of the home folder, the whole disk or a system folder is refused",
      all(hook(c)[0] == 2 for c in rm_blocked), [c for c in rm_blocked if hook(c)[0] != 2])
check("guard: rm -r of a folder inside your work is let through", all(hook(c)[0] == 0 for c in rm_allowed), [c for c in rm_allowed if hook(c)[0]])
def guard_idle(ev, idle):
    r = subprocess.run([sys.executable, "-I", guard], input=json.dumps(ev), capture_output=True, text=True,
                       env=dict(genv, RAINBOW_TEST_IDLE_S=str(idle), RAINBOW_AGENT="alpha"))
    return r.returncode
typing = {"tool_input": {"command": "osascript -e 'tell application \"System Events\" to keystroke \"hello\"'"}}
click = {"tool_name": "mcp__cua-computer-use__click", "tool_input": {"x": 10, "y": 10}}
shot = {"tool_name": "mcp__cua-computer-use__screenshot", "tool_input": {}}
check("guard: a keystroke or click (osascript, cliclick, MCP computer use) waits while the human is at the keyboard",
      guard_idle(typing, 1) == 2 and guard_idle(click, 1) == 2 and guard_idle({"tool_input": {"command": "cliclick c:10,10"}}, 2) == 2)
check("guard: …goes through once the human paused, and a screenshot never waits",
      guard_idle(typing, 60) == 0 and guard_idle(click, 60) == 0 and guard_idle(shot, 1) == 0)
os.environ["RAINBOW_HOME"] = str(tmp / "po-home")
blocked_receipt = rr.read(tool="guard", n=1)
os.environ["RAINBOW_HOME"] = str(SAFE_HOME)
check("guard: every refusal leaves a receipt with the agent and the reason",
      blocked_receipt and blocked_receipt[0]["status"] == "blocked" and blocked_receipt[0]["agent"] == "alpha", blocked_receipt)
check("the Claude Code adapter also runs the guard before MCP computer-use actions",
      any("cua|computer" in h["matcher"] for h in json.loads((AD / "claude-code" / "settings.json").read_text())["hooks"]["PreToolUse"]))
idles, slept = iter([1.0, 2.5, 6.0]), []
pm.human_idle_s = lambda: next(idles)
w = pm.wait_for_human("click", sleep=slept.append)
check("cursor proxy: a click waits until the human pauses (5 s without input), then goes through", w > 0 and len(slept) == 2, (w, slept))
pm.human_idle_s = lambda: 0.0; slept.clear()
check("cursor proxy: …never longer than RAINBOW_HUMAN_WAIT_S (30 s), and a screenshot never waits",
      pm.wait_for_human("type_text", sleep=slept.append) <= 30 + 5 and pm.wait_for_human("screenshot", sleep=slept.append) == 0)

# ── a Chrome of its own: each agent may run another Chrome channel (separate app, Dock icon and ⌘Q) ──
r = json.loads(REG.read_text()); r["agents"]["zed"] = {"label": "z", "port": 9230, "profile": str(tmp / "zed-prof"), "color": "#000000", "chrome": "canary"}
bp = tmp / "chan.json"; bp.write_text(json.dumps(r)); creg = bo.registry(bp)
check("chrome: stable by default; \"canary\" (or beta, dev, cft, or a path to a Chrome .app) per agent",
      creg["alpha"]["chrome_app"] == "/Applications/Google Chrome.app" and creg["zed"]["chrome_app"] == "/Applications/Google Chrome Canary.app")
r["agents"]["zed"]["chrome"] = "firefox"; bp.write_text(json.dumps(r))
try:
    bo.registry(bp); ok_ = False
except ValueError:
    ok_ = True
check("chrome: an unknown channel is refused by the registry", ok_)
ZED = creg["zed"]
CAN = f"/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary --user-data-dir={ZED['profile']} --remote-debugging-port=9230"
CAN_HELPER = "/Applications/Google Chrome Canary.app/Contents/Frameworks/Google Chrome Helper.app/Contents/MacOS/Google Chrome Helper --type=gpu"
check("chrome: a Canary (or any flavor) root on the agent's port and profile is the agent's; its helpers are not roots",
      bo.is_root(ZED, CAN) and not bo.is_root(ZED, CAN_HELPER) and not bo.is_root(ALPHA_A, CAN))
opened = []
_srun = bo.subprocess.run
bo.subprocess.run = lambda args, **kw: (opened.append(args), subprocess.CompletedProcess(args, 0, "", ""))[1]
_h, bo.healthy = bo.healthy, (lambda a, timeout=2.0: True)
ZED_LOCAL = dict(ZED, chrome_app=str(tmp / "Google Chrome Canary.app")); Path(ZED_LOCAL["chrome_app"]).mkdir(exist_ok=True)
bo_l = load("browser-owner.py")
bo_l.healthy = bo.healthy   # subprocess.run is already the fake above (one module for all)
rc, txt = bo_l.launch(ZED_LOCAL)
missing = bo_l.launch(dict(ZED, chrome_app=str(tmp / "nowhere" / "Google Chrome Beta.app")))
bo.subprocess.run, bo.healthy = _srun, _h
check("chrome: the agent's own Chrome app is the one opened; a channel that isn't installed is a clear failure",
      rc == 0 and opened and opened[0][4] == ZED_LOCAL["chrome_app"] and missing[0] == 1 and "nowhere" in missing[1], (opened, missing))

# ── doctor, --adapter, uninstall ──
denv = dict(genv, BROWSER_OWNER_REGISTRY=str(REG), RAINBOW_LANG="en")
r = subprocess.run(["bash", str(HERE / "rainbowomma-doctor"), "--json"], capture_output=True, text=True, env=denv)
dj = json.loads(r.stdout)
names = [c["check"] for c in dj["checks"]]
check("doctor: one JSON answer — python, the registry, the state folder, the tools, and the optional parts (Word, Cua, jobs, guard)",
      any("registry" in n for n in names) and any("state folder" in n for n in names) and any("Cua" in n for n in names)
      and any("guardrail" in n for n in names) and next(c for c in dj["checks"] if "registry" in c["check"])["ok"], dj)
check("doctor: missing optional parts never fail it (exit 0 when everything needed is there)",
      (r.returncode == 0) == (dj["status"] == "ok") and all(c["ok"] or not c["needed"] or sys.platform == "darwin" for c in dj["checks"]), dj)
r = subprocess.run(["bash", str(HERE / "rainbowomma-doctor"), "--json"], capture_output=True, text=True,
                   env=dict(denv, BROWSER_OWNER_REGISTRY=str(tmp / "nowhere.json")))
check("doctor: no browsers.json → exit 1, with the fix", r.returncode == 1 and "install.sh" in r.stdout, r.stdout[:300])
r = subprocess.run(["bash", installer, "--adapter", "claude-code", "--adapter", "codex"], capture_output=True, text=True, env=ienv)
ad = fake_home / ".rainbowomma" / "adapters"
check("install --adapter: the adapter's files with your own paths filled in, nothing left as /Users/you",
      r.returncode == 0 and f"{fake_home}/bin/rainbowomma-guard" in (ad / "claude-code" / "settings.json").read_text()
      and (ad / "codex" / "rainbowomma.rules").exists() and "/Users/you" not in (ad / "claude-code" / "settings.json").read_text(), r.stdout + r.stderr)
r = subprocess.run(["bash", installer, "--adapter", "nope"], capture_output=True, text=True, env=ienv)
check("install --adapter: an unknown framework is refused and the known ones are listed", r.returncode == 2 and "claude-code" in r.stderr)
uninstaller = str(HERE.parent / "uninstall.sh")
(fake_home / "bin" / "my-own-script").write_text("keep me")
r = subprocess.run(["bash", uninstaller], capture_output=True, text=True, env=ienv)
check("uninstall: the tools and the jobs go; browsers.json, the state folder and your own files in ~/bin stay",
      r.returncode == 0 and not (fake_home / "bin" / "browser-owner").exists() and (fake_home / "bin" / "browsers.json").exists()
      and (fake_home / "bin" / "my-own-script").exists() and (fake_home / ".rainbowomma").is_dir()
      and not (fake_home / "Library" / "LaunchAgents" / "com.rainbowomma.heal.plist").exists(), r.stdout + r.stderr)
r = subprocess.run(["bash", uninstaller, "--purge"], capture_output=True, text=True, env=ienv)
check("uninstall --purge: browsers.json and the state folder go too; the agents' Chrome profiles are never touched",
      r.returncode == 0 and not (fake_home / "bin" / "browsers.json").exists() and not (fake_home / ".rainbowomma").exists()
      and (fake_home / "bin" / "my-own-script").exists() and "profiles were not touched" in r.stdout, r.stdout)

# ── office-owner xlsx: formulas recalculated by the real Excel ──
xcalls = []
def excel_osa(sc):
    xcalls.append(sc)
    if "calculate (worksheet i of wb)" in sc:
        m = re.search(r'workbook file name "([^"]+)"', sc); Path(m.group(1)).write_text("recalculated")
        pm_ = re.search(r'filename "([^"]+\.pdf)"', sc)
        if pm_:
            Path(pm_.group(1)).write_bytes(b"%PDF- sheet")
        return 0, ""
    return osa(sc)
ao.RUN = excel_osa
book = tmp / "agent" / "report.xlsx"; book.write_text("formulas without values")
docs.pop("Microsoft Excel", None)
code, out = ao.cmd_xlsx("bravo", str(book))
check("xlsx: Excel recalculates a copy (calculate by sheet index, never 'repeat with sh in'), and the result replaces the workbook",
      code == 0 and out["status"] == "recalculated" and book.read_text() == "recalculated" and "repeat with i from 1 to (count of worksheets of wb)" in xcalls[-1]
      and "ofc-xlsx-" in xcalls[-1] and not list(ao.WORD_DIR.glob("ofc-xlsx-*")), (out, xcalls[-1:]))
code, out = ao.cmd_xlsx("bravo", str(book), out=str(tmp / "agent" / "report-calc.xlsx"), pdf=str(tmp / "agent" / "report-sheet.pdf"))
check("xlsx --out --pdf: the recalculated copy elsewhere, plus the active sheet as a PDF",
      code == 0 and (tmp / "agent" / "report-calc.xlsx").read_text() == "recalculated" and (tmp / "agent" / "report-sheet.pdf").read_bytes() == b"%PDF- sheet", out)
code, out = ao.cmd_xlsx("bravo", str(book), pdf=str(tmp / "agent" / "report-sheet.pdf"))
check("xlsx --pdf: never over an existing PDF without --force", code == 1 and "--force" in out["why"], out)
docs["Microsoft Excel"] = {str(book): True}
book.write_text("the human's edits")
code, out = ao.cmd_xlsx("bravo", str(book))
check("xlsx: a workbook open in Excel is never written under — refused, untouched", code == 1 and book.read_text() == "the human's edits", out)
docs.pop("Microsoft Excel", None)
def excel_fails(sc):
    xcalls.append(sc)
    return (1, "Microsoft Excel got an error: Parameter error. (-50)") if "calculate" in sc else osa(sc)
ao.RUN = excel_fails
code, out = ao.cmd_xlsx("bravo", str(book))
check("xlsx: Excel's failure → the workbook untouched, Excel's own reason, no leftover copy",
      code == 1 and "(-50)" in out["why"] and book.read_text() == "the human's edits" and not list(ao.WORD_DIR.glob("ofc-xlsx-*")), out)
code, out = ao.cmd_xlsx("bravo", str(tmp / "agent" / "x.docx"))
check("xlsx: only xlsx / xlsm / xls", code == 1, out)
ao.RUN = osa

# ── wave B: browser MCPs on the agent's own browser, sensitive sites, the menu bar and the stop button ──
cfg = bo.mcp_config(BRAVO_A, "devtools")
pw = bo.mcp_config(BRAVO_A, "playwright")
cl = bo.mcp_config(BRAVO_A, "devtools", "claude")
check("mcp-config: Chrome DevTools MCP and Playwright MCP pointed at the agent's own CDP port, never --autoConnect",
      cfg["mcpServers"]["bravo-browser"]["args"][-2:] == ["--browserUrl", "http://127.0.0.1:9223"]
      and pw["mcpServers"]["bravo-browser"]["args"][-2:] == ["--cdp-endpoint", "http://127.0.0.1:9223"]
      and cl["command"].startswith("claude mcp add-json --scope user bravo-browser") and "--autoConnect" not in json.dumps([cfg, pw]), (cfg, pw))
attach = ["npx chrome-devtools-mcp@latest --autoConnect", "npx @playwright/mcp@latest --extension",
          "npx chrome-devtools-mcp@latest --browserUrl http://127.0.0.1:9223", "curl -s http://localhost:9224/json/list"]
check("guard: a browser MCP on the human's Chrome is refused; as Alpha, another agent's CDP port too — its own is fine",
      [as_agent(c, "alpha") for c in attach] == [2, 2, 2, 2] and as_agent("npx chrome-devtools-mcp@1.11.0 --browserUrl http://127.0.0.1:9222", "alpha") == 0,
      [as_agent(c, "alpha") for c in attach])
sreg = json.loads(REG.read_text()); sreg["sensitiveSites"] = ["bank.example", "*.gov.example"]; SREG = tmp / "sensitive.json"; SREG.write_text(json.dumps(sreg))
def nav(url, idle, tool="mcp__alpha-browser__navigate_page"):
    r = subprocess.run([sys.executable, "-I", guard], input=json.dumps({"tool_name": tool, "tool_input": {"url": url}}), capture_output=True,
                       text=True, env=dict(genv, BROWSER_OWNER_REGISTRY=str(SREG), RAINBOW_TEST_IDLE_S=str(idle), RAINBOW_AGENT="alpha"))
    return r.returncode
check("sensitive sites: an agent opens one only while the human is at the Mac (used it in the last 2 minutes)",
      nav("https://login.bank.example/a", 900) == 2 and nav("https://login.bank.example/a", 30) == 0
      and nav("https://portal.gov.example/x", 900) == 2 and nav("https://news.example.com", 900) == 0
      and nav("https://login.bank.example/a", 900, tool="mcp__playwright__browser_navigate") == 2)
check("the Claude Code adapter also runs the guard before browser MCP tools",
      any("playwright" in h["matcher"] for h in json.loads((AD / "claude-code" / "settings.json").read_text())["hooks"]["PreToolUse"]))
# the stop button
pause_env = dict(genv, RAINBOW_HOME=str(tmp / "pause-home"))
r = subprocess.run(["bash", str(HERE / "rainbowomma-pause"), "on"], capture_output=True, text=True, env=pause_env)
on = json.loads(r.stdout)
gp = subprocess.run([sys.executable, "-I", guard], input=json.dumps({"tool_input": {"command": "npm test"}}), capture_output=True, text=True, env=pause_env)
gm = subprocess.run([sys.executable, "-I", guard], input=json.dumps({"tool_name": "mcp__cua__screenshot", "tool_input": {}}), capture_output=True, text=True, env=pause_env)
r2 = subprocess.run(["bash", str(HERE / "rainbowomma-pause"), "toggle"], capture_output=True, text=True, env=pause_env)
ga = subprocess.run([sys.executable, "-I", guard], input=json.dumps({"tool_input": {"command": "npm test"}}), capture_output=True, text=True, env=pause_env)
check("pause: while the human paused all agents, the guard refuses every command and tool call; after resume all goes on",
      on["status"] == "paused" and gp.returncode == 2 and "paused all agents" in gp.stderr and gm.returncode == 2
      and json.loads(r2.stdout)["status"] == "running" and ga.returncode == 0, (on, gp.stderr[:120], r2.stdout))
pflag = pm.ROOT / "state" / "paused.json"; pflag.parent.mkdir(parents=True, exist_ok=True); pflag.write_text("{}")
_pw = pm.PAUSE_WAIT_S; pm.PAUSE_WAIT_S = 2
px2 = pm.Proxy.__new__(pm.Proxy); px2.agent, px2.themed, px2.ended = "alpha", {}, set()
px2.proc = type("P", (), {"stdin": _Sink()})(); px2.out = io.BytesIO(); px2.theme_session = lambda label: None
px2.out_lock = threading.Lock()
pm.time.sleep, _sl = (lambda s: None), pm.time.sleep
px2.pump_agent(io.BytesIO(b'{"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":"click","arguments":{}}}\n'
                          b'{"jsonrpc":"2.0","id":8,"method":"tools/call","params":{"name":"screenshot","arguments":{}}}\n'))
px3 = pm.Proxy.__new__(pm.Proxy); px3.agent, px3.themed, px3.ended = "alpha", {}, set(); px3.out_lock = threading.Lock()
px3.proc = type("P", (), {"stdin": _Sink()})(); px3.out = io.BytesIO(); px3.theme_session = lambda label: None
px3.pump_agent(io.BytesIO(b'[{"jsonrpc":"2.0","id":9,"method":"tools/call","params":{"name":"click","arguments":{}}}]\n'
                          b'{"jsonrpc":"2.0","method":"tools/call","params":{"name":"click","arguments":{}}}\n'
                          b'\xff{"method":"tools/call"}\n'))
pm.time.sleep, pm.PAUSE_WAIT_S = _sl, _pw
pflag.unlink()
answered = [json.loads(x) for x in px2.out.getvalue().splitlines()]
check("security: while paused, a batch, a call without an id and an unreadable line never reach the driver",
      px3.proc.stdin.lines == [], px3.proc.stdin.lines)
check("pause: the cursor proxy holds a click, then answers it with an error that never reaches the driver; a screenshot passes",
      [m["id"] for m in answered] == [7] and answered[0]["result"]["isError"] and len(px2.proc.stdin.lines) == 1
      and b'"id":8' in px2.proc.stdin.lines[0], (answered, px2.proc.stdin.lines))
mbm = load("rainbowomma-menubar.py")
os.environ["RAINBOW_LANG"] = "en"
ag_rows = [{"agent": "alpha", "label": "Alpha", "color": "#FB8C00", "status": "up", "up": True},
           {"agent": "bravo", "label": "Bravo", "color": "#1E88E5", "status": "down", "up": False}]
txt = mbm.menu(ag_rows, False, [{"at": "2026-10-19T10:15:00+0000", "agent": "alpha", "tool": "port-owner", "action": "lease", "status": "leased"}])
txt_p = mbm.menu(ag_rows, True, [])
os.environ["RAINBOW_LANG"] = "he"
check("menu bar: a dot per agent in its color (filled when up), open/front and close per agent, the latest receipts",
      "\033[38;2;251;140;0m●" in txt.splitlines()[0] and "○" in txt.splitlines()[0] and "param1=open param2=alpha" in txt
      and "param1=close param2=alpha" in txt and "param1=close param2=bravo" not in txt and "10:15 alpha: port-owner lease" in txt, txt)
check("menu bar: pause all agents with ⌘⌥⌃P; while paused the title says so and the item resumes",
      "param1=on" in txt and "shortcut=CMD+OPTION+CTRL+P" in txt and txt_p.startswith("⏸") and "param1=off" in txt_p, txt_p[:200])
r = subprocess.run(["bash", installer, "--with-menubar"], capture_output=True, text=True, env=ienv)
plug = fake_home / ".rainbowomma" / "swiftbar" / "rainbowomma.10s.sh"
check("install --with-menubar: the SwiftBar plugin, pointing at the installed menu-bar tool",
      r.returncode == 0 and plug.exists() and "rainbowomma-menubar" in plug.read_text() and os.access(plug, os.X_OK), r.stdout + r.stderr)

# ── wave C: the screen lease, the human's takeover, approval before sending ──
cenv = dict(genv, RAINBOW_HOME=str(tmp / "screen-home"))
def so(*args, idle=60):
    r = subprocess.run(["bash", str(HERE / "screen-owner"), *args], capture_output=True, text=True, env=dict(cenv, RAINBOW_TEST_IDLE_S=str(idle)))
    return r.returncode, json.loads(r.stdout)
def g(ev, agent=None, idle=60):
    e = dict(cenv, RAINBOW_TEST_IDLE_S=str(idle), **({"RAINBOW_AGENT": agent} if agent else {}))
    return subprocess.run([sys.executable, "-I", guard], input=json.dumps(ev), capture_output=True, text=True, env=e)
check("screen: Alpha takes the screen; Bravo is refused while Alpha holds it; the same agent renews",
      so("take", "alpha")[1]["status"] == "taken" and so("take", "bravo")[0] == 2 and so("take", "alpha")[0] == 0)
check("screen: no agent takes the screen while the human is typing", so("release", "alpha")[1]["status"] == "released"
      and so("take", "bravo", idle=1)[1]["why"].startswith("the human"))
keys = {"tool_input": {"command": "osascript -e 'tell application \"System Events\" to keystroke \"x\"'"}}
cua_click = {"tool_name": "mcp__cua__click", "tool_input": {}}
fg_click = {"tool_name": "mcp__computer-use__left_click", "tool_input": {}}
a1 = g(keys, "alpha"); b1 = g(fg_click, "bravo"); b2 = g(cua_click, "bravo")
check("screen: a foreground action takes a short lease by itself — Bravo's foreground click waits, its Cua click (background) doesn't",
      a1.returncode == 0 and b1.returncode == 2 and "alpha" in b1.stderr and b2.returncode == 0, (a1.stderr, b1.stderr, b2.stderr))
check("screen: the human's takeover stops every agent's GUI action, background ones too; handback lets them go on",
      so("takeover")[1]["status"] == "human" and g(cua_click, "bravo").returncode == 2 and g(keys, "alpha").returncode == 2
      and "took over" in g(cua_click, "bravo").stderr and so("handback")[1]["status"] == "released" and g(cua_click, "bravo").returncode == 0)
so("takeover")
_root = pm.ROOT; pm.ROOT = tmp / "screen-home"
held = pm.paused()
so("handback"); free = pm.paused(); pm.ROOT = _root
check("screen: the cursor proxy holds actions while the human has taken over", held and not free)
# approval before sending
send = "osascript -e 'tell application \"Messages\" to send \"on my way\" to buddy \"+15550100\"'"
mail = "osascript -e 'tell application \"Mail\" to make new outgoing message with properties {subject:\"x\"}'"
apm = load("rainbowomma-approve.py")
def appr(answer, *cmd, agent="alpha", why="tell the client", me="alpha"):
    saved = {k: os.environ.get(k) for k in ("RAINBOW_HOME", "RAINBOW_AGENT")}
    os.environ["RAINBOW_HOME"] = cenv["RAINBOW_HOME"]
    if me:
        os.environ["RAINBOW_AGENT"] = me
    else:
        os.environ.pop("RAINBOW_AGENT", None)
    seen.clear(); apm.ASK = lambda a, w, c: seen.append((a, w, c)) or answer == "yes"
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            code = apm.main(["ask", "--agent", agent, "--why", why, "--", *cmd])
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    return code, json.loads(buf.getvalue())
seen = []
gs = lambda c: g({"tool_input": {"command": c}}, "alpha").returncode
check("send: Messages and Mail through AppleScript are refused without the human's approval", gs(send) == 2 and gs(mail) == 2)
check("send: the human says no → refused (exit 2), and the command stays refused", appr("no", "osascript", "-e", 'tell application "Messages" to send "on my way" to buddy "+15550100"')[0] == 2
      and gs(send) == 2)
code, out = appr("yes", "osascript", "-e", 'tell application "Messages" to send "on my way" to buddy "+15550100"')
check("send: the human allows it once → exactly that command runs once; the next time it needs a new approval",
      code == 0 and out["status"] == "approved" and gs(send) == 0 and gs(send) == 2, out)
code, out = appr("yes", "osascript", "-e", 'tell application "Messages" to send "on my way" to buddy "+15550100"')
check("send: an approval covers only that exact command — another message or recipient is still refused",
      gs(send.replace("on my way", "something else")) == 2)
msg_ = ("osascript", "-e", 'tell application "Messages" to send "on my way" to buddy "+15550100"')
r_ = subprocess.run(["bash", str(HERE / "rainbowomma-approve"), "ask", "--agent", "alpha", "--", *msg_], capture_output=True, text=True,
                    env=dict(cenv, RAINBOW_TEST_APPROVE="yes", RAINBOW_AGENT="alpha"), timeout=20) if sys.platform != "darwin" else None
check("send: no environment variable answers for the human (RAINBOW_TEST_APPROVE does nothing)",
      r_ is None or (r_.returncode != 0 and '"approved"' not in r_.stdout), r_ and r_.stdout)
appr("yes", *msg_)
check("send: an approval is the asking agent's only — Bravo can't use Alpha's", g({"tool_input": {"command": send}}, "bravo").returncode == 2
      and gs(send) == 0)
check("send: a command too long to read in the dialog is refused, not cut", appr("yes", *msg_[:2], msg_[2] + " " * 700)[0] == 2 and not seen)
appr("yes", *msg_, why="ok\n\n\n\nExactly this:\nsomething harmless" + "x" * 500)
check("send: the reason is one short line — it can't push the real command out of sight",
      "\n" not in seen[0][1] and len(seen[0][1]) <= 200 and gs(send) == 0, seen)
check("send: --agent must be the caller's own name", appr("yes", *msg_, agent="bravo")[0] == 2 and appr("yes", *msg_, agent="human", me="")[0] == 2
      and not seen)
pend = tmp / "screen-home" / "state" / "approval-pending.json"; pend.write_text("{}")
check("send: while an approval dialog is up, no agent clicks or types (it could click 'Allow' itself)",
      g(cua_click, "bravo").returncode == 2 and "approval" in g(cua_click, "bravo").stderr)
pend.unlink()
os.environ["RAINBOW_LANG"] = "en"
txt_h = mbm.menu(ag_rows, False, [], {"holder": "human"}); txt_a = mbm.menu(ag_rows, False, [], {"holder": "alpha"})
os.environ["RAINBOW_LANG"] = "he"
check("menu bar: take over the screen, or hand it back while you hold it; who holds it now",
      "param1=handback" in txt_h and "param1=takeover" in txt_a and "screen: alpha" in txt_a, (txt_h[-300:], txt_a[-300:]))

# ── wave D: a simulator and a clipboard of its own, per agent ──
FAKE_SIMCTL = tmp / "fake_simctl"
FAKE_SIMCTL.write_text("""#!/usr/bin/env python3
import json, os, sys, uuid
st = os.environ["FAKE_SIM_STATE"]
d = json.load(open(st)) if os.path.exists(st) else {"devices": {"iOS-26": [{"name": "iPhone 16", "udid": "AAAAAAAA-0000-0000-0000-000000000001", "state": "Booted"}]}}
a = sys.argv[1:]
devs = d["devices"]["iOS-26"]
if a[:2] == ["list", "devices"]:
    print(json.dumps(d))
elif a[0] == "create":
    u = str(uuid.uuid4()).upper(); devs.append({"name": a[1], "udid": u, "state": "Shutdown"}); print(u)
elif a[0] in ("boot", "shutdown"):
    for x in devs:
        if x["udid"] == a[1]:
            x["state"] = "Booted" if a[0] == "boot" else "Shutdown"
json.dump(d, open(st, "w"))
""")
FAKE_SIMCTL.chmod(0o755)
simenv = dict(genv, RAINBOW_SIMCTL=str(FAKE_SIMCTL), FAKE_SIM_STATE=str(tmp / "sims.json"))
def sim(*args):
    r = subprocess.run(["bash", str(HERE / "sim-owner"), *args], capture_output=True, text=True, env=simenv)
    return r.returncode, json.loads(r.stdout)
code, a_sim = sim("lease", "alpha"); _, b_sim = sim("lease", "bravo"); _, again = sim("lease", "alpha")
check("sim-owner: each agent gets its own simulator (created once as rainbowomma-<agent>, booted), the same one next time",
      code == 0 and a_sim["name"] == "rainbowomma-alpha" and a_sim["udid"] != b_sim["udid"] and again["udid"] == a_sim["udid"], (a_sim, b_sim))
check("sim-owner who: a simulator's owner, or the human's", sim("who", b_sim["udid"])[1]["agent"] == "bravo"
      and sim("who", "AAAAAAAA-0000-0000-0000-000000000001")[1]["agent"] == "human")
def sg(cmd, agent="alpha"):
    return subprocess.run([sys.executable, "-I", guard], input=json.dumps({"tool_input": {"command": cmd}}), capture_output=True, text=True,
                          env=dict(simenv, RAINBOW_AGENT=agent)).returncode
sim_blocked = ["xcrun simctl install booted App.app", f"xcrun simctl launch {b_sim['udid']} com.example.app",
               "xcodebuild test -scheme App -destination 'platform=iOS Simulator,name=iPhone 16'",
               f"xcodebuild -scheme App -destination 'platform=iOS Simulator,id={b_sim['udid']}' test"]
sim_allowed = [f"xcrun simctl install {a_sim['udid']} App.app", f"xcodebuild -scheme App -destination 'platform=iOS Simulator,id={a_sim['udid']}' test",
               "xcodebuild -scheme App -destination 'platform=macOS' build", "xcrun simctl list devices"]
check("guard as Alpha: simctl `booted`, another agent's simulator and a shared one in -destination are refused",
      all(sg(c) == 2 for c in sim_blocked), [c for c in sim_blocked if sg(c) != 2])
check("guard as Alpha: its own simulator, a macOS build and read-only simctl go through", all(sg(c) == 0 for c in sim_allowed),
      [c for c in sim_allowed if sg(c)])
clip_env = dict(genv, RAINBOW_HOME=str(tmp / "clip-home"))
subprocess.run(["bash", str(HERE / "rainbowomma-clip"), "copy", "alpha"], input="alpha's text", text=True, env=clip_env)
subprocess.run(["bash", str(HERE / "rainbowomma-clip"), "copy", "bravo"], input="bravo's text", text=True, env=clip_env)
pa = subprocess.run(["bash", str(HERE / "rainbowomma-clip"), "paste", "alpha"], capture_output=True, text=True, env=clip_env).stdout
cf = tmp / "clip-home" / "state" / "clip" / "alpha" / "default"
check("clip: each agent pastes back only what it copied; the files only its user can read",
      pa == "alpha's text" and oct(cf.stat().st_mode & 0o777) == "0o600", (pa, oct(cf.stat().st_mode)))
check("guard as Alpha: pbcopy, pbpaste and AppleScript's clipboard are the human's — refused; rainbowomma-clip goes through",
      sg("echo hi | pbcopy") == 2 and sg("pbpaste > x.txt") == 2 and sg("osascript -e 'set the clipboard to \"x\"'") == 2
      and sg("echo hi | rainbowomma-clip copy alpha") == 0 and as_agent("echo hi | pbcopy") == 0)

# ── wave D, part 2: receipts to OpenTelemetry, apps an agent may not drive ──
from http.server import BaseHTTPRequestHandler, HTTPServer
got_otlp = []
class Collector(BaseHTTPRequestHandler):
    def do_POST(self):
        got_otlp.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
        self.send_response(200); self.end_headers(); self.wfile.write(b"{}")
    def log_message(self, *a):
        pass
srv = HTTPServer(("127.0.0.1", 0), Collector); threading.Thread(target=srv.serve_forever, daemon=True).start()
oenv = dict(genv, RAINBOW_HOME=str(tmp / "otel-home"), NO_PROXY="127.0.0.1,localhost", no_proxy="127.0.0.1,localhost")
for k in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
    oenv.pop(k, None)
def rcpt(*args):
    r = subprocess.run(["bash", str(HERE / "receipts"), *args], capture_output=True, text=True, env=oenv)
    return json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {}
subprocess.run(["bash", str(HERE / "rainbowomma-pause"), "on"], capture_output=True, env=oenv)
subprocess.run(["bash", str(HERE / "rainbowomma-pause"), "off"], capture_output=True, env=oenv)
url = f"http://127.0.0.1:{srv.server_port}"
first = rcpt("--export-otlp", url); second = rcpt("--export-otlp", url)
subprocess.run(["bash", str(HERE / "rainbowomma-pause"), "on"], capture_output=True, env=oenv)
third = rcpt("--export-otlp", url)
srv.shutdown()
recs0 = got_otlp[0][1]["resourceLogs"][0]["scopeLogs"][0]["logRecords"] if got_otlp else []
check("receipts → OpenTelemetry: OTLP/HTTP JSON logs to /v1/logs, each receipt once (a cursor), WARN for refusals",
      first == {"status": "exported", "sent": 2} and second == {"status": "exported", "sent": 0} and third["sent"] == 1
      and got_otlp[0][0] == "/v1/logs" and recs0[0]["body"]["stringValue"] == "pause on → paused"
      and any(a["key"] == "rainbowomma.tool" for a in recs0[0]["attributes"]), (first, second, third, got_otlp[:1]))
check("receipts → OpenTelemetry: no collector named → a clear failure", rcpt("--export-otlp")["status"] == "failed")
areg = json.loads(REG.read_text()); areg["agents"]["alpha"]["apps"] = {"Notes": "deny", "Terminal": "allow"}; AREG = tmp / "apps.json"; AREG.write_text(json.dumps(areg))
def ag_app(ev, agent=None):
    return subprocess.run([sys.executable, "-I", guard], input=json.dumps(ev), capture_output=True, text=True,
                          env=dict(genv, BROWSER_OWNER_REGISTRY=str(AREG), RAINBOW_TEST_IDLE_S="60", **({"RAINBOW_AGENT": agent} if agent else {}))).returncode
term = {"tool_input": {"command": "osascript -e 'tell application \"Terminal\" to do script \"ls\"'"}}
notes = {"tool_input": {"command": "osascript -e 'tell application \"Notes\" to make new note'"}}
keych = {"tool_input": {"command": "open -a 'Keychain Access'"}}
cua_term = {"tool_name": "mcp__cua__click", "tool_input": {"bundle_id": "com.apple.Terminal", "x": 1, "y": 1}}
check("apps: by default no agent drives a terminal, System Settings or Keychain Access (AppleScript, open -a, computer use)",
      ag_app(term, "bravo") == 2 and ag_app(keych, "bravo") == 2 and ag_app(cua_term, "bravo") == 2 and ag_app(notes, "bravo") == 0)
check("apps: per agent, \"apps\" allows or denies more — Alpha may drive Terminal, but not Notes",
      ag_app(term, "alpha") == 0 and ag_app(notes, "alpha") == 2 and bo.denied_apps("alpha", AREG).count("notes") == 1)

# ── ownership where the OS hides process environments (macOS 27): marks the agents write themselves ──
noenv = dict(genv, RAINBOW_ENV_MARKERS="off", BROWSER_OWNER_REGISTRY=str(REG))
noenv.pop("RAINBOW_AGENT", None)
sessions_ = {who: subprocess.Popen(["bash", str(HERE / "as-agent"), who, "sleep", "60"], env=noenv) for who in ("alpha", "bravo")}
human_kid = subprocess.Popen(["sleep", "60"], env=noenv)
try:
    kid = {}
    for _ in range(40):
        threading.Event().wait(0.25)                 # time.sleep is instant in this file (bo.time.sleep above)
        ps_ = [ln.split(None, 2) for ln in subprocess.run(["ps", "-A", "-o", "pid=,ppid=,command="], capture_output=True, text=True).stdout.splitlines()]
        kid = {who: next((int(r[0]) for r in ps_ if len(r) == 3 and int(r[1]) == sp.pid and r[2].startswith("sleep")), None)
               for who, sp in sessions_.items()}
        if all(kid.values()):
            break
    def nk(target, agent):
        e = dict(noenv, **({"RAINBOW_AGENT": agent} if agent else {}))
        return subprocess.run([sys.executable, "-I", guard], input=json.dumps({"tool_input": {"command": f"kill {target}"}}),
                              capture_output=True, text=True, env=e).returncode
    pids_ = {"alpha": kid["alpha"], "bravo": kid["bravo"], "human": human_kid.pid}
    got2 = {(me, who): nk(pids_[who], me) for me in ("alpha", None) for who in ("alpha", "bravo", "human")}
    os.environ["RAINBOW_HOME"] = noenv["RAINBOW_HOME"]; w_pc = load("proc-owner.py"); os.environ["RAINBOW_ENV_MARKERS"] = "off"
    w_pc.PO.REGISTRY = REG
    whose_alpha = w_pc.cmd_whose(kid["alpha"])[1] if kid["alpha"] else {}
    os.environ.pop("RAINBOW_ENV_MARKERS"); os.environ["RAINBOW_HOME"] = str(SAFE_HOME)
finally:
    for sp in [*sessions_.values(), human_kid]:
        sp.kill()
    subprocess.run(["pkill", "-P", str(sessions_["alpha"].pid)], capture_output=True); subprocess.run(["pkill", "-P", str(sessions_["bravo"].pid)], capture_output=True)
check("env unreadable (macOS 27): as-agent registers its own shell, so the process under it is Alpha's by mark",
      whose_alpha.get("agent") == "alpha" and whose_alpha.get("via") == "ancestor", whose_alpha)
check("env unreadable: as Alpha, `kill` only Alpha's own — Bravo's and an unmarked (human's) process are refused",
      got2[("alpha", "alpha")] == 0 and got2[("alpha", "bravo")] == 2 and got2[("alpha", "human")] == 2, got2)
check("env unreadable: an agent without a name can't prove anything is its own — refused for all three",
      got2[(None, "alpha")] == 2 and got2[(None, "bravo")] == 2 and got2[(None, "human")] == 2, got2)
frows = [(1, 0, "launchd"), (50, 1, "/usr/local/bin/node /usr/local/bin/claude"), (60, 50, "/bin/sh -c ~/bin/rainbowomma-guard"),
         (70, 60, "/usr/bin/python3 -I /x/rainbowomma-guard.py"), (80, 50, "node server.js"),
         (90, 1, "/Applications/Code.app/Contents/Frameworks/Code Helper (Plugin).app/Contents/MacOS/Code Helper (Plugin)"),
         (91, 90, "/bin/sh -c guard"), (92, 91, "/usr/bin/python3 -I guard.py")]
check("guard: the agent framework's own process is its root — never a shell, python, launchd, or a GUI app's helper (an editor)",
      pc.framework_root(70, frows) == 50 and pc.framework_root(92, frows) is None)
os.environ["RAINBOW_HOME"] = str(tmp / "roots-home"); rpc = load("proc-owner.py"); os.environ["RAINBOW_HOME"] = str(SAFE_HOME)
rpc.PO.REGISTRY = REG; rpc.MARKERS = lambda: {}
rpc.register("alpha", 50, frows)
check("a live root stays its first agent's: another agent can't claim it", rpc.register("bravo", 50, frows) is False
      and rpc.load_roots()[50]["agent"] == "alpha")
_, own1 = rpc.ownership(rows=frows, keep=True)
orphaned = [(1, 0, "launchd"), (80, 1, "node server.js"), (95, 1, "node other.js")]
_, own2 = rpc.ownership(rows=orphaned)
check("a server an agent left behind stays its own after its session ends (re-parented to launchd, ancestry gone)",
      own1[80] == ("alpha", "ancestor") and own2[80] == ("alpha", "mark") and own2[95] == ("human", "none"), (own1.get(80), own2))
orphaned2 = [(1, 0, "launchd"), (80, 1, "python3 something-else.py")]
_, own3 = rpc.ownership(rows=orphaned2)
check("…but a reused pid (another command line) is never the agent's", own3[80] == ("human", "none"))
check("…nor a login shell (-zsh)", pc.framework_root(2, [(1, 0, "launchd"), (5, 1, "-zsh"), (2, 5, "/bin/sh -c guard")]) is None)

# the guard registers the agent framework above it as the agent's root (RAINBOW_TRACK_ROOT on), env unreadable
fw_dir = tmp / "fw"; fw_dir.mkdir(); (fw_dir / "agentfw").symlink_to("/bin/bash")
th = tmp / "track-home"
tenv = dict(genv, RAINBOW_HOME=str(th), RAINBOW_ENV_MARKERS="off", RAINBOW_AGENT="alpha", RAINBOW_TRACK_ROOT="on")
evt = json.dumps({"tool_input": {"command": "ls"}}).replace("'", "")
fw = subprocess.Popen([str(fw_dir / "agentfw"), "-c", f"sleep 30 & echo '{evt}' | {sys.executable} -I {guard}; wait"], env=tenv)
try:
    t_roots, t_kid = {}, None
    for _ in range(40):
        threading.Event().wait(0.25)
        rf = th / "state" / "proc-roots.json"
        t_roots = json.loads(rf.read_text()) if rf.exists() else {}
        ps_ = [ln.split(None, 2) for ln in subprocess.run(["ps", "-A", "-o", "pid=,ppid=,command="], capture_output=True, text=True).stdout.splitlines()]
        t_kid = next((int(r[0]) for r in ps_ if len(r) == 3 and int(r[1]) == fw.pid and r[2].startswith("sleep")), None)
        if str(fw.pid) in t_roots and t_kid:
            break
    k_env = dict(tenv, RAINBOW_TRACK_ROOT="off")
    t_alpha = subprocess.run([sys.executable, "-I", guard], input=json.dumps({"tool_input": {"command": f"kill {t_kid}"}}),
                             capture_output=True, text=True, env=k_env).returncode
    t_bravo = subprocess.run([sys.executable, "-I", guard], input=json.dumps({"tool_input": {"command": f"kill {t_kid}"}}),
                             capture_output=True, text=True, env=dict(k_env, RAINBOW_AGENT="bravo")).returncode
finally:
    subprocess.run(["pkill", "-P", str(fw.pid)], capture_output=True); fw.kill()
check("guard (env unreadable): the agent framework running it becomes the agent's root — what it starts is the agent's own",
      t_roots.get(str(fw.pid), {}).get("agent") == "alpha" and t_alpha == 0 and t_bravo == 2, (t_roots, t_alpha, t_bravo))

# ── security review: the cheap ways around the guard are closed ──
victim = subprocess.Popen(["sleep", "60"])
vp = victim.pid
try:
    sec_blocked = {
        "kill -9 -1": "process groups", "kill 0": "process groups", f"kill -9 -- -{vp}": "process groups", f"kill -s TERM -{vp}": "process groups",
        f"kill {vp}\\ ": "not yours", f"echo {vp} | xargs kill": "xargs", f"xargs kill <<< {vp}": "xargs",
        "timeout 5 pkill chrome": "pkill", "env -S 'pkill -f chrome'": "pkill", "setsid pkill chrome": "pkill",
        "stdbuf -o0 killall Chrome": "killall", "flock /tmp/l pkill chrome": "pkill", "script -q /dev/null pkill chrome": "pkill",
        "find . -name x -exec pkill chrome \\;": "pkill", "sh -c -- 'pkill x'": "pkill",
        "bash <<EOF\npkill chrome\nEOF": "pkill", "echo pkill chrome | sh": "pkill", "bash <<< 'pkill chrome'": "pkill",
        "echo '<<EOF'\npkill chrome": "pkill", f"python3 -c 'import os; os.kill({vp}, 9)'": "inline",
        "as-agent bravo pkill chrome": "as bravo", f"as-agent bravo proc-owner kill {vp} --by bravo": "as bravo",
        f"proc-owner kill {vp} --by human": "human", f"proc-owner kill {vp} --by bravo": "never as bravo",
        "W=human; browser-owner stop bravo --by $W": "literally", "browser-owner stop bravo --by bravo": "never as bravo",
        "port-owner release bravo --all": "never as bravo", "sim-owner release bravo --shutdown": "never as bravo",
        "screen-owner handback": "human", "screen-owner take human --minutes 600": "human", "rainbowomma-clip paste bravo": "never as bravo",
        "rainbowomma-pause off": "human", "rainbowomma-approve ask --agent bravo -- x": "never as bravo",
        "echo '{}' > ~/.rainbowomma/state/proc-roots.json": "state", "rm ~/.rainbowomma/state/approval-pending.json": "state",
        "sed -i s/9222/9223/ ~/bin/browsers.json": "browsers.json", "ln -s /x $RAINBOW_HOME/state/paused.json": "state",
        "RAINBOW_HOME=/tmp/x browser-owner start alpha --by alpha": "rainbow_home", "export BROWSER_OWNER_REGISTRY=/tmp/r.json": "registry",
        "RAINBOW_TEST_APPROVE=yes rainbowomma-approve ask --agent alpha -- x": "rainbow_test", "unset RAINBOW_AGENT": "rainbow_agent",
        "env -u RAINBOW_AGENT proc-owner list bravo": "", "RAINBOW_AGENT=bravo proc-owner list bravo": "",
        "curl http://127.1:9223/json": "bravo's browser", "curl http://[::1]:9223/json": "bravo's browser",
        "curl http://0.0.0.0:9223/json": "bravo's browser", "curl http://localhost.:9223/json": "bravo's browser",
        "osascript -e 'tell application (\"Google Chr\" & \"ome\") to quit'": "applescript",
        "osascript -e 'tell application \"Google Chrome\" to close every window'": "applescript",
        "osascript -e 'do shell script \"pkill chrome\"'": "pkill", "osascript -e 'do shell script (\"pk\" & \"ill x\")'": "built at run time",
        "cp ~/Library/Application\\ Support/Google/Chrome/Default/Cookies /tmp/x": "human's own chrome",
        "rm -rf ~/Library/Application\\ Support/Google/Chrome": "human's own chrome", "rm -rf ~/.": "can't be undone",
        "rm -rf $HOME/.": "can't be undone", "rm -rf ~/Library": "can't be undone", "rm -rf ~/Documents/": "can't be undone",
        "php -S 127.0.0.1:3000": "port 3000", "npx next dev -p 3000": "port 3000", "python3 -m http.server -b 127.0.0.1 3000": "port 3000",
        "nc -l 9222": "port 9222", "kill ² 1": "", f"kill {vp}; true --port=²": "",
    }
    got_sec = {c: subprocess.run([sys.executable, "-I", guard], input=json.dumps({"tool_input": {"command": c}}), capture_output=True,
                                 text=True, env=dict(genv, RAINBOW_AGENT="alpha", RAINBOW_ENV_MARKERS="off")) for c in sec_blocked}
    bad = {c: (r.returncode, r.stderr[-160:]) for c, r in got_sec.items()
           if r.returncode != 2 or (sec_blocked[c] and sec_blocked[c] not in r.stderr.lower())}
    check(f"security: {len(sec_blocked)} ways around the guard are refused, each with its reason", not bad, bad)
    sec_allowed = ["browser-owner start alpha --by alpha", "proc-owner list alpha", "port-owner lease alpha --name web", "kill %1",
                   "cat ~/.rainbowomma/logs/receipts.jsonl", "python3 -c 'print(1)'", "find . -name '*.py' -exec grep -l x {} +",
                   "timeout 5 npm test", "echo hi | sh", "rm -rf ~/work/build", "screen-owner take alpha --minutes 2",
                   "browser-owner idle-stop alpha --by keepalive", "RAINBOW_AGENT=alpha npm test", "osascript -e 'display notification \"hi\"'",
                   "cat <<EOF > notes.txt\npkill is a command\nEOF", "curl http://127.0.0.1:9222/json/version", "git log -p"]
    ok_ = {c: as_agent(c, "alpha") for c in sec_allowed}
    check("security: …while the agent's ordinary work goes on", all(v == 0 for v in ok_.values()), {c: v for c, v in ok_.items() if v})
finally:
    victim.kill()
crash = subprocess.run([sys.executable, "-I", guard], input=json.dumps({"tool_input": {"command": "x"}, "tool_name": object.__name__}),
                       capture_output=True, text=True, env=dict(genv, RAINBOW_AGENT="alpha"))
g_mod = load("rainbowomma-guard.py"); g_mod.verdict = lambda c: 1 / 0
buf_ = io.StringIO()
with contextlib.redirect_stderr(buf_):
    sys.stdin = io.StringIO(json.dumps({"tool_input": {"command": "ls"}})); rc_ = g_mod.main([]); sys.stdin = sys.__stdin__
check("security: an error while judging is a refusal, never a pass", rc_ == 2 and "couldn't judge" in buf_.getvalue(), buf_.getvalue())
fv = load("rainbowomma-guard.py")
check("security: Write/Edit can't touch RainbowOMMA's state or browsers.json, and no file tool reads the human's Chrome profile",
      fv.file_verdict({"tool_name": "Write", "tool_input": {"file_path": "~/.rainbowomma/state/approvals.json"}})
      and fv.file_verdict({"tool_name": "Edit", "tool_input": {"file_path": "/Users/x/bin/browsers.json"}})
      and fv.file_verdict({"tool_name": "Read", "tool_input": {"file_path": "/Users/x/Library/Application Support/Google/Chrome/Default/Cookies"}})
      and not fv.file_verdict({"tool_name": "Read", "tool_input": {"file_path": "~/.rainbowomma/logs/receipts.jsonl"}})
      and not fv.file_verdict({"tool_name": "Write", "tool_input": {"file_path": "/tmp/work/app.py"}}))
trows = [(1, 0, "launchd"), (100, 1, "tmux new -s work"), (110, 100, "-zsh"), (120, 110, "python3 /opt/hermes/run.py"),
         (130, 120, "/bin/bash -c guard"), (140, 130, "/usr/bin/python3 -I /x/rainbowomma-guard.py"), (150, 110, "vim notes.md"),
         (200, 1, "/usr/bin/login -pf human"), (210, 200, "-zsh"), (220, 210, "/bin/sh -c guard")]
check("security: a Python framework (Hermes) is its own root — never the tmux server, a login or the human's shell above it",
      pc.framework_root(140, trows) == 120 and pc.framework_root(220, trows) is None)
os.environ["RAINBOW_HOME"] = str(tmp / "imp-home"); ipc = load("proc-owner.py"); os.environ["RAINBOW_HOME"] = str(SAFE_HOME)
irows = [(1, 0, "launchd"), (50, 1, "node claude"), (60, 50, "bash"), (70, 60, "bash as-agent alpha x")]
ipc.register("bravo", 50, irows)
check("security: a process under Bravo's mark can't register itself as Alpha (as-agent alpha from inside Bravo)",
      ipc.register("alpha", 70, irows) is False and ipc.register("bravo", 70, irows) is True)
lk_home = tmp / "lock-home"; (lk_home / "state").mkdir(parents=True); victim_f = tmp / "thesis.txt"; victim_f.write_text("my thesis")
(lk_home / "state" / "proc-roots.lock").symlink_to(victim_f)
os.environ["RAINBOW_HOME"] = str(lk_home); lpc = load("proc-owner.py"); os.environ["RAINBOW_HOME"] = str(SAFE_HOME)
try:
    with lpc.roots_locked():
        pass
    lk_ok = False
except OSError:
    lk_ok = True
check("security: a lock file planted as a symlink is refused, and what it points to is never truncated",
      lk_ok and victim_f.read_text() == "my thesis")
sbo = load("browser-owner.py")
human_prof = tmp / "human-chrome-default"; human_prof.mkdir(); (human_prof / "Preferences").write_text('{"profile": {"name": "Me"}}')
evil_prof = tmp / "evil-profile"; evil_prof.mkdir(); (evil_prof / "Default").symlink_to(human_prof)
check("security: a link inside an agent's profile (to the human's Default) stops start, recover and heal before anything is written",
      bool(sbo.profile_unsafe({"profile": str(evil_prof)})) and not sbo.profile_unsafe({"profile": str(tmp / "bravo")})
      and json.loads((human_prof / "Preferences").read_text())["profile"]["name"] == "Me")
sbo.THEMES = tmp / "sec-themes"
sbo.build_theme({"name": "alpha", "label": "Alpha", "color": "#E53935"})
(sbo.THEMES / "alpha" / "x.js").write_text("steal()")
mf = json.loads((sbo.THEMES / "alpha" / "manifest.json").read_text()); mf["content_scripts"] = [{"matches": ["<all_urls>"], "js": ["x.js"]}]
(sbo.THEMES / "alpha" / "manifest.json").write_text(json.dumps(mf))
dirty = sbo.theme_clean("alpha")
sbo.build_theme({"name": "alpha", "label": "Alpha", "color": "#E53935"})
check("security: a theme folder another agent added a script to is found, and rebuilding it leaves only the theme",
      not dirty and sbo.theme_clean("alpha") and not (sbo.THEMES / "alpha" / "x.js").exists())
rr_ = json.loads(REG.read_text())
bad_regs = {"human": {**rr_["agents"]["alpha"], "port": 9240, "profile": str(tmp / "h1")},
            "human-human": {**rr_["agents"]["alpha"], "port": 9241, "profile": str(tmp / "h2")},
            "delta": {**rr_["agents"]["alpha"], "port": 9242, "profile": str(tmp / "h3"), "label": "x\n--y | bash=/tmp/evil"}}
refused_ = []
for nm, row in bad_regs.items():
    rp = tmp / f"badreg-{nm}.json"; rp.write_text(json.dumps({"agents": {nm: row}}))
    try:
        sbo.registry(rp)
    except ValueError:
        refused_.append(nm)
check("security: the names human and human-* are the human's, and a label can't carry a newline or a menu action",
      refused_ == list(bad_regs), refused_)
lk_t = tmp / "bo-thesis.txt"; lk_t.write_text("my thesis"); lk_l = tmp / "bo.lock"; lk_l.symlink_to(lk_t)
try:
    sbo.open_lock(lk_l); lk_ok2 = False
except OSError:
    lk_ok2 = True
check("security: browser-owner's lock never opens through a planted link (the file it points to stays whole)", lk_ok2 and lk_t.read_text() == "my thesis")
r_by = subprocess.run(["bash", str(HERE / "browser-owner"), "stop", "bravo", "--by", "human"], capture_output=True, text=True,
                      env=dict(genv, RAINBOW_AGENT="alpha"))
check("security: an agent can't act as the human or another agent in browser-owner, whatever the guard saw",
      r_by.returncode == 2 and json.loads(r_by.stdout)["status"] == "refused", r_by.stdout)
mbx = load("rainbowomma-menubar.py")
evil = "x\n--allow | bash=/tmp/evil terminal=false"
menu_txt = mbx.menu([{"agent": "alpha", "label": evil, "status": evil, "color": "#E53935", "up": True}], False,
                    [{"at": "2026-10-21T10:00:00", "agent": evil, "tool": evil, "action": "a", "status": "s"}], {"holder": evil})
check("security: a newline or | in a label, a holder or a receipt never becomes a menu item of its own (bash=…)",
      all(ln.count("|") <= 1 for ln in menu_txt.splitlines())
      and "/tmp/evil" not in "".join(ln.split("|")[1] for ln in menu_txt.splitlines() if "|" in ln), menu_txt)
ph = tmp / "pause-sec-home"; (ph / "state").mkdir(parents=True); (ph / "state" / "paused.json").symlink_to(tmp / "nowhere" / "p")
r_p = subprocess.run(["bash", str(HERE / "rainbowomma-pause"), "status"], capture_output=True, text=True, env=dict(genv, RAINBOW_HOME=str(ph)))
r_on = subprocess.run(["bash", str(HERE / "rainbowomma-pause"), "on"], capture_output=True, text=True, env=dict(genv, RAINBOW_HOME=str(ph)))
gx = subprocess.run([sys.executable, "-I", guard], input=json.dumps({"tool_input": {"command": "ls"}}), capture_output=True, text=True,
                    env=dict(genv, RAINBOW_HOME=str(ph)))
check("security: a planted (broken) link at the pause flag counts as paused, and `pause on` replaces it instead of failing",
      json.loads(r_p.stdout)["status"] == "paused" and json.loads(r_on.stdout)["status"] == "paused" and gx.returncode == 2
      and not (ph / "state" / "paused.json").is_symlink(), (r_p.stdout, r_on.stdout, r_on.stderr[-200:]))
own_env = dict(genv, RAINBOW_AGENT="alpha", RAINBOW_HOME=str(tmp / "own-home"))
def tool(*argv):
    r = subprocess.run(["bash", str(HERE / argv[0]), *argv[1:]], capture_output=True, text=True, env=own_env, input="")
    return r.returncode
others = {"screen-owner take bravo": tool("screen-owner", "take", "bravo"), "screen-owner take human": tool("screen-owner", "take", "human"),
          "screen-owner take alpha --minutes 1e12": tool("screen-owner", "take", "alpha", "--minutes", "1e12"),
          "sim-owner release bravo": tool("sim-owner", "release", "bravo", "--shutdown"), "rainbowomma-clip paste bravo": tool("rainbowomma-clip", "paste", "bravo"),
          "port-owner release bravo": tool("port-owner", "release", "bravo", "--all"), "port-owner lease bravo": tool("port-owner", "lease", "bravo"),
          "proc-owner kill 1 --by human": tool("proc-owner", "kill", "1", "--by", "human"), "proc-owner register bravo": tool("proc-owner", "register", "bravo"),
          "office-owner close --agent bravo": tool("office-owner", "close", "--agent", "bravo", "/tmp/x.docx"),
          "rainbowomma-approve ask --agent bravo": tool("rainbowomma-approve", "ask", "--agent", "bravo", "--", "x")}
check("security: every owner tool acts only as the caller (RAINBOW_AGENT) — never as another agent or the human, and no endless lease",
      all(v == 2 for v in others.values()), {k: v for k, v in others.items() if v != 2})
check("…and as yourself it works", tool("screen-owner", "take", "alpha", "--minutes", "1") == 0 and tool("port-owner", "lease", "alpha") == 0)
oh = tmp / "office-sec"; os.environ["RAINBOW_HOME"] = str(oh); aof = load("agent-office.py"); os.environ["RAINBOW_HOME"] = str(SAFE_HOME)
aof.LEASES.mkdir(parents=True, exist_ok=True)
(aof.LEASES / "bad1.json").write_text(json.dumps({"agent": "alpha", "app": "notanapp", "path": "/x"}))
(aof.LEASES / "bad2.json").write_text(json.dumps({"app": "word", "path": "/x"}))
(aof.LEASES / "bad3.json").write_text("[1, 2]")
check("security: a planted lease file (unknown app, no agent, not a lease at all) is never acted on and never stops the sweep",
      aof.leases() == [])
rx = tmp / "otlp-home"; os.environ["RAINBOW_HOME"] = str(rx); rr2 = load("rainbow_receipts.py")
rr2.write("t", "a", "alpha", "alpha", "ok")
mode_ok = (rx.stat().st_mode & 0o077) == 0 and ((rx / "logs" / "receipts.jsonl").stat().st_mode & 0o077) == 0
os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "http://127.0.0.1:1"
rr2.export_otlp("http://127.0.0.1:2")
other_cursor = [f.name for f in (rx / "logs").iterdir() if f.name.startswith("receipts.otlp-cursor")]
os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT"); os.environ["RAINBOW_HOME"] = str(SAFE_HOME)
check("security: receipts are readable by you only (0700 / 0600), and an export to another URL never moves your collector's cursor",
      mode_ok and "receipts.otlp-cursor" not in other_cursor, (mode_ok, other_cursor))
os.environ["RAINBOW_HOME"] = str(tmp / "start-home"); spc = load("proc-owner.py"); os.environ["RAINBOW_HOME"] = str(SAFE_HOME)
spc.PO.REGISTRY = REG; spc.MARKERS = lambda: {}
srows = [(1, 0, "launchd"), (300, 1, "node server.js")]
spc.STARTS = lambda: {300: "Sat Oct 24 09:00:00 2026"}
spc.register("alpha", 300, srows)
same_ = spc.known_marks(srows)
spc.STARTS = lambda: {300: "Sat Oct 24 11:30:00 2026"}            # the pid came back for another node server.js
reused_ = spc.known_marks(srows)
check("proc-owner: a pid that came back with the same command line but a later start is never the agent's",
      same_ == {300: "alpha"} and reused_ == {})
spc.STARTS = lambda: {}
check("…and where start times can't be read, the command line alone decides (as before)", spc.known_marks(srows) == {300: "alpha"})
spc.PROCESSES = lambda: [(400, 1, "/usr/bin/vim notes RAINBOW_AGENT=bravo")]
_sub = spc.subprocess.run
spc.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "400 /usr/bin/vim notes RAINBOW_AGENT=bravo HOME=/Users/x\n"})()
_pd = spc.Path
spc.Path = lambda p: _pd("/nonexistent-proc") if p == "/proc" else _pd(p)
env_marks = spc._env_tags()[0]
spc.subprocess.run, spc.Path = _sub, _pd
check("proc-owner (macOS ps -E): RAINBOW_AGENT=… written in a command's own arguments is not a mark — only its environment",
      env_marks == {}, env_marks)

# ── tab housekeeping: a tab that keeps a core busy long after anyone used it is reloaded, then closed ──
import rainbow_tabs as rt
cfg_t = rt.config({})
T0 = 1_000_000.0
old = {"firstSeen": T0 - 7 * 3600, "url": "https://news.example/live", "urlSince": T0 - 7 * 3600}
def tab_(cpu, tid="a", url="https://news.example/live", attached=False):
    return {"id": tid, "url": url, "title": "", "attached": attached, "cpu": cpu, "session": "s-" + tid}
recs, acts = {"a": dict(old)}, []
for k in range(3):                                   # three runs, 15 min apart, hot each time
    planned, recs = rt.plan([tab_(25.0), tab_(1.0, "b")], recs, cfg_t, T0 + k * 900, 2)
    acts.append(planned[0]["action"])
check("tabs: a stale tab hot (25% of a core) in every run for 30 min is reloaded — not before, and a cool one never",
      acts == [None, None, "reload"] and planned[1]["action"] is None, acts)
recs["a"].update(reloaded=True, hotSince=None)
acts2 = []
for k in range(3):
    planned, recs = rt.plan([tab_(25.0), tab_(1.0, "b")], recs, cfg_t, T0 + 3600 + k * 900, 2)
    acts2.append(planned[0]["action"])
check("tabs: still hot for another 30 min after the reload → closed", acts2 == [None, None, "close"], acts2)
planned, _ = rt.plan([tab_(25.0)], recs, cfg_t, T0 + 3600 + 2 * 900, 1)
check("tabs: never the browser's last tab", planned[0]["action"] == "skip-last-tab", planned[0]["action"])
r_new, acts3 = {}, []
for k in range(3):
    planned, r_new = rt.plan([tab_(40.0, "n")], r_new, cfg_t, T0 + k * 900, 2)
    acts3.append(planned[0]["action"])
check("tabs: a tab first seen half an hour ago, on a page that just loaded, is not stale — left alone however hot", acts3 == [None, None, None])
r_use = {"a": dict(old, hotSince=T0 - 3600)}
planned, _ = rt.plan([tab_(50.0, attached=True)], r_use, cfg_t, T0, 2)
check("tabs: a tab another client is attached to (an agent driving it) is never touched", planned[0]["action"] == "skip-in-use")
r_nav = {"a": dict(old, hotSince=T0 - 3600)}
planned, r_nav = rt.plan([tab_(50.0, url="https://news.example/other")], r_nav, cfg_t, T0, 2)
check("tabs: a tab that navigated since the last run is in use — its clock starts over",
      planned[0]["action"] is None and r_nav["a"]["urlSince"] == T0)
check("tabs: settings from browsers.json, nonsense ignored, dry run unless it says apply",
      rt.config({"tabSweep": {"cpuPercent": 20, "hotMinutes": -5, "mode": "yes", "exclude": ["Delta"]}}) ==
      {**rt.DEFAULTS, "cpuPercent": 20.0, "exclude": ["delta"]})

class FakeTabsCDP(FakeCDP):
    """a browser with page tabs that burn a given share of a core (Performance.getMetrics TaskDuration)"""
    def __init__(self, pages):
        self.pages, self.sessions, self.clock = pages, {}, {}               # {targetId: (url, cpu fraction, attached)}
        super().__init__({})
    def ws(self, c):
        def recv(n):
            b = b""
            while len(b) < n:
                x = c.recv(n - len(b))
                if not x:
                    raise OSError
                b += x
            return b
        def send(obj):
            d = json.dumps(obj).encode()
            c.sendall(bytes([0x81]) + (bytes([len(d)]) if len(d) < 126 else bytes([126]) + struct.pack(">H", len(d))) + d)
        try:
            while True:
                b1, b2 = recv(2); n = b2 & 0x7F
                n = struct.unpack(">H", recv(2))[0] if n == 126 else n
                mask = recv(4); msg = json.loads(bytes(x ^ mask[i % 4] for i, x in enumerate(recv(n))))
                m, prm, sid = msg["method"], msg.get("params") or {}, msg.get("sessionId")
                self.calls.append((m, prm, sid))
                if m == "Target.getTargets":
                    res = {"targetInfos": [{"targetId": t, "type": "page", "url": u, "title": "x", "attached": att}
                                           for t, (u, f, att) in self.pages.items()] + [{"targetId": "sw", "type": "service_worker"}]}
                elif m == "Target.attachToTarget":
                    sid_ = "S" + prm["targetId"]; self.sessions[sid_] = prm["targetId"]; res = {"sessionId": sid_}
                elif m == "Performance.getMetrics":
                    tid = self.sessions[sid]; ts, td = self.clock.get(tid, (0.0, 0.0))
                    ts, td = ts + 1.0, td + self.pages[tid][1]; self.clock[tid] = (ts, td)
                    res = {"metrics": [{"name": "Timestamp", "value": ts}, {"name": "TaskDuration", "value": td}]}
                elif m == "Target.closeTarget":
                    self.pages.pop(prm["targetId"], None); res = {"success": True}
                elif m == "SystemInfo.getProcessInfo":
                    self.gpu_t = getattr(self, "gpu_t", 0.0) + getattr(self, "gpu_rate", 0.0) * 10
                    res = {"processInfo": [{"type": "browser", "id": 1, "cpuTime": 5.0}, {"type": "GPU", "id": 2, "cpuTime": self.gpu_t}]}
                else:
                    res = {}
                send({"id": msg["id"], "result": res})
        except OSError:
            c.close()

fk = FakeTabsCDP({"hot": ("https://news.example/live", 0.25, False), "calm": ("https://docs.example/", 0.01, False),
                  "inuse": ("https://app.example/", 0.6, True)})
tbo = load("browser-owner.py"); tbo.SHARED = tmp / "tabs-home"; tbo.view = lambda a: {"status": "up"}
ag_t = {"name": "alpha", "port": fk.port, "label": "Alpha"}
sp_t = rt.state_path(tbo.SHARED, "alpha")
seed = {"tabs": {t: {"firstSeen": T0 - 8 * 3600, "url": u, "urlSince": T0 - 8 * 3600, "hotSince": T0 - 3600}
                 for t, (u, f, att) in fk.pages.items()}}
rt.save_state(sp_t, seed)
dry = rt.sweep_agent(ag_t, cfg_t, False, tbo.view, tbo.SHARED, tbo.Cdp, now=T0, sleep=lambda s: None)
byid = {x["id"]: x for x in dry["tabs"]}
check("tabs (CDP): each tab's CPU is measured over the window — the hot one 25%, the calm one 1%; the dry run touches nothing",
      byid["hot"]["cpu"] == 25.0 and byid["calm"]["cpu"] == 1.0 and byid["hot"]["action"] == "reload" and not byid["hot"]["done"]
      and not any(c[0] in ("Page.reload", "Target.closeTarget") for c in fk.calls), dry)
check("tabs (CDP): the tab an agent is attached to stays, however hot", byid["inuse"]["action"] == "skip-in-use")
rt.save_state(sp_t, seed); fk.calls.clear()
done = rt.sweep_agent(ag_t, cfg_t, True, tbo.view, tbo.SHARED, tbo.Cdp, now=T0, sleep=lambda s: None)
check("tabs (CDP): applied, the hot tab is reloaded in its own session — no process is signalled",
      ("Page.reload", {"ignoreCache": False}, "Shot") in fk.calls and rt.load_state(sp_t)["tabs"]["hot"]["reloaded"], fk.calls[-6:])
st_ = rt.load_state(sp_t); st_["tabs"]["hot"]["hotSince"] = T0 - 3600; rt.save_state(sp_t, st_); fk.calls.clear()
rt.sweep_agent(ag_t, cfg_t, True, tbo.view, tbo.SHARED, tbo.Cdp, now=T0 + 60, sleep=lambda s: None)
check("tabs (CDP): still hot after its reload → closed through CDP, and it drops out of the record",
      ("Target.closeTarget", {"targetId": "hot"}, None) in fk.calls and "hot" not in fk.pages and "hot" not in rt.load_state(sp_t)["tabs"])
fk.gpu_rate = 0.18; gst = tmp / "gpu-home"
g_runs = [rt.sweep_agent(ag_t, cfg_t, False, lambda a: {"status": "up"}, gst, tbo.Cdp, now=T0 + k * 900, sleep=lambda s: None)
          for k in range(4)]
check("tabs: the browser's GPU process is measured too (18% of a core), with one alert after 30 min hot — not again",
      [r["gpu"] for r in g_runs] == [18.0] * 4 and [r["gpuAlert"] for r in g_runs] == [False, False, True, False], [(r["gpu"], r["gpuAlert"]) for r in g_runs])
fk.gpu_rate = 0.0
tbo.view = lambda a: {"status": "blocked"}
check("tabs: a browser whose port isn't its own (blocked, down, hung) is never swept",
      rt.sweep_agent(ag_t, cfg_t, True, tbo.view, tbo.SHARED, tbo.Cdp)["status"] == "blocked")
treg = tmp / "tabs-reg.json"
treg.write_text(json.dumps({"tabSweep": {"exclude": ["charlie"]}, "agents": {
    "alpha": {"label": "A", "port": 9222, "profile": str(tmp / "ta"), "color": "#E53935"},
    "bravo": {"label": "B", "port": 9223, "profile": str(tmp / "tb"), "color": "#26A69A", "tabSweep": False},
    "charlie": {"label": "C", "port": 9224, "profile": str(tmp / "tc"), "color": "#1E88E5"},
    "delta": {"label": "D", "port": 9225, "profile": str(tmp / "td"), "color": "#FDD835", "managedBy": "x.py"}}}))
tbo.REGISTRY = treg; tbo.view = lambda a: {"status": "down"}
res_t = tbo.tabs(tbo.registry(treg))
check("tabs: an agent with tabSweep false, one in tabSweep.exclude, and one managedBy another tool are never swept; dry run by default",
      {x["agent"]: x["status"] for x in res_t["agents"]} == {"alpha": "down", "bravo": "excluded", "charlie": "excluded", "delta": "excluded"}
      and res_t["mode"] == "dry-run", res_t)
dd = tmp / "tabs-daily"
rt.daily(dd, {"reloaded": 1, "closed": 0, "wouldReload": 0, "wouldClose": 2, "hot": 3}, today="2026-10-23")
rt.daily(dd, {"reloaded": 1, "closed": 1, "wouldReload": 0, "wouldClose": 0, "hot": 1}, today="2026-10-23")
prev_d = rt.daily(dd, {"reloaded": 0, "closed": 0, "wouldReload": 0, "wouldClose": 0, "hot": 0}, today="2026-10-24")
check("tabs: one summary a day — yesterday's totals, when the day changes", prev_d and prev_d["day"] == "2026-10-23"
      and prev_d["reloaded"] == 2 and prev_d["closed"] == 1 and prev_d["wouldClose"] == 2, prev_d)
r_tb = subprocess.run(["bash", str(HERE / "browser-owner"), "tabs", "bravo", "--apply"], capture_output=True, text=True,
                      env=dict(genv, RAINBOW_AGENT="alpha"))
check("tabs: an agent sweeps its own browser only (owner and guard)",
      r_tb.returncode == 2 and as_agent("browser-owner tabs bravo --apply", "alpha") == 2 and as_agent("browser-owner tabs alpha", "alpha") == 0,
      r_tb.stdout)
formula = (HERE.parent / "Formula" / "rainbowomma.rb").read_text()
latest = re.search(r"^## \[(\d+\.\d+\.\d+)\]", (HERE.parent / "CHANGELOG.md").read_text(), re.M).group(1)
check("Homebrew: the formula points at the latest release in CHANGELOG.md, with a checksum",
      f"/v{latest}.tar.gz" in formula and re.search(r'sha256 "[0-9a-f]{64}"', formula), latest)
ich = tmp / "chan-home"; ich.mkdir()
r_ch = subprocess.run(["bash", str(HERE.parent / "install.sh"), "--bin", str(ich / "bin"), "--agent-chrome", "canary"], capture_output=True,
                      text=True, env=dict(os.environ, HOME=str(ich), RAINBOW_INSTALL_ANY_OS="1", RAINBOW_HOME=str(ich / ".rainbowomma")))
chans = {k: v.get("chrome") for k, v in json.loads((ich / "bin" / "browsers.json").read_text())["agents"].items()} if r_ch.returncode == 0 else {}
r_bad = subprocess.run(["bash", str(HERE.parent / "install.sh"), "--bin", str(ich / "bin"), "--agent-chrome", "nightly"], capture_output=True,
                       text=True, env=dict(os.environ, HOME=str(ich), RAINBOW_INSTALL_ANY_OS="1", RAINBOW_HOME=str(ich / ".rainbowomma")))
check("install --agent-chrome canary: every agent of a new registry runs as Chrome Canary (and the registry still loads); a made-up channel is refused",
      set(chans.values()) == {"canary"} and all(a["chrome_app"].endswith("Canary.app") for a in bo.registry(ich / "bin" / "browsers.json").values())
      and r_bad.returncode == 2, (r_ch.stdout[-300:], r_ch.stderr[-300:]))

mh = tmp / "manifest-home"; (mh / "bin").mkdir(parents=True); (mh / "bin" / "receipts").write_text("my own receipts tool\n")
menv = dict(os.environ, HOME=str(mh), RAINBOW_INSTALL_ANY_OS="1", RAINBOW_HOME=str(mh / ".rainbowomma"))
inst = lambda *a: subprocess.run(["bash", str(HERE.parent / a[0]), "--bin", str(mh / "bin"), *a[1:]], capture_output=True, text=True, env=menv)
r1 = inst("install.sh"); saved_once = "saved in" in r1.stdout
r2 = inst("install.sh")
(mh / "bin" / "port-owner").write_text((mh / "bin" / "port-owner").read_text() + "# my change\n")
r3 = inst("uninstall.sh")
left_ = sorted(x.name for x in (mh / "bin").iterdir())
check("install keeps a file of yours it replaces, and uninstall removes only what it put there unchanged — then puts yours back",
      saved_once and "saved in" not in r2.stdout and left_ == ["browsers.json", "port-owner", "receipts"]
      and (mh / "bin" / "receipts").read_text() == "my own receipts tool\n", (left_, r3.stdout[-400:]))
lh = tmp / "legacy-home"; (lh / "bin").mkdir(parents=True)
for f in ("browser-owner", "receipts"):
    (lh / "bin" / f).write_bytes((HERE / f).read_bytes())
(lh / "bin" / "receipts").write_text("another version\n")
subprocess.run(["bash", str(HERE.parent / "uninstall.sh"), "--bin", str(lh / "bin")], capture_output=True, text=True,
               env=dict(menv, HOME=str(lh), RAINBOW_HOME=str(lh / ".rainbowomma")))
check("uninstall without a manifest (an older install) removes only files identical to RainbowOMMA's",
      sorted(x.name for x in (lh / "bin").iterdir()) == ["receipts"])
fv2 = load("rainbowomma-guard.py")
ST = "/Users/x/.rainbowomma/state/approvals.json"; HC = "/Users/x/Library/Application Support/Google/Chrome/Default/Cookies"
shapes = {   # each framework's file-tool payload (from its own source or docs) → refused?
    "codex apply_patch": ({"tool_name": "apply_patch", "tool_input": {"command": f"*** Begin Patch\n*** Update File: {ST}\n@@\n-x\n+y\n*** End Patch"}}, True),
    "codex patch in the shell": ({"tool_name": "Bash", "tool_input": {"command": f"apply_patch <<'EOF'\n*** Begin Patch\n*** Add File: {ST}\n+{{}}\n*** End Patch\nEOF"}}, True),
    "codex relative path": ({"tool_name": "apply_patch", "cwd": "/Users/x/.rainbowomma", "tool_input": {"command": "*** Begin Patch\n*** Delete File: state/paused.json\n*** End Patch"}}, True),
    "gemini write_file": ({"tool_name": "write_file", "tool_input": {"file_path": ST, "content": "{}"}}, True),
    "gemini replace": ({"tool_name": "replace", "tool_input": {"file_path": "/Users/x/bin/browsers.json", "old_string": "a", "new_string": "b"}}, True),
    "gemini read_file (state: fine)": ({"tool_name": "read_file", "tool_input": {"file_path": ST}}, False),
    "gemini read_file (human Chrome)": ({"tool_name": "read_file", "tool_input": {"file_path": HC}}, True),
    "qwen notebook_edit": ({"tool_name": "notebook_edit", "tool_input": {"notebook_path": ST}}, True),
    "factory Create": ({"tool_name": "Create", "tool_input": {"file_path": ST, "content": "{}"}}, True),
    "hermes patch (V4A)": ({"tool_name": "patch", "tool_input": {"mode": "patch", "patch": f"*** Begin Patch\n*** Update File: {ST}\n*** End Patch"}}, True),
    "hermes write_file": ({"tool_name": "write_file", "tool_input": {"path": ST, "content": "{}"}}, True),
    "cursor beforeReadFile": ({"hook_event_name": "beforeReadFile", "file_path": HC, "content": "…"}, True),
    "cursor beforeReadFile (state: fine)": ({"hook_event_name": "beforeReadFile", "file_path": ST, "content": "…"}, False),
    "windsurf pre_write_code": ({"agent_action_name": "pre_write_code", "tool_info": {"file_path": ST}}, True),
    "windsurf pre_read_code": ({"agent_action_name": "pre_read_code", "tool_info": {"file_path": HC}}, True),
    "an ordinary edit": ({"tool_name": "apply_patch", "tool_input": {"command": "*** Begin Patch\n*** Update File: src/app.py\n*** End Patch"}}, False),
}
wrong = {k: bool(fv2.file_verdict(ev)) for k, (ev, want) in shapes.items() if bool(fv2.file_verdict(ev)) != want}
check("guard: file tools of every framework — Codex/Hermes patches, Gemini/Qwen/Factory/Hermes paths, Cursor and Windsurf events", not wrong, wrong)
mt = {"codex/hooks.json": "apply_patch", "gemini-cli/settings.json": "write_file", "qwen-code/settings.json": "notebook_edit",
      "factory-droid/hooks.json": "ApplyPatch", "hermes/hooks.yaml": "patch", "cursor/hooks.json": "beforeReadFile", "windsurf/hooks.json": "pre_write_code"}
check("the adapters send their framework's file tools to the guard too", all(w in (AD / f).read_text() for f, w in mt.items()),
      [f for f, w in mt.items() if w not in (AD / f).read_text()])

# ── auth-owner: one agent at a time signs in to a site (optional: authSites) ──
ah = tmp / "auth-home"; os.environ["RAINBOW_HOME"] = str(ah); aom = load("auth-owner.py")
check("auth: a site from a URL or a host — scheme, port, path and www. dropped", aom.site_of("https://www.Accounts.Example.com:443/x?y") == "accounts.example.com"
      and aom.covered("login.accounts.example.com", ["accounts.example.com"]) == "accounts.example.com" and not aom.covered("example.com", ["accounts.example.com"]))
a1 = aom.cmd_lease("alpha", "accounts.example.com", 10, 0); b1 = aom.cmd_lease("bravo", "accounts.example.com", 10, 0)
check("auth: Alpha signs in; Bravo is refused while Alpha holds the site, and told who", a1[0] == 0 and b1[0] == 2 and b1[1]["holder"] == "alpha", b1)
aom.ASK = lambda agent, site, why: "123456"
cb = aom.cmd_code("bravo", "accounts.example.com", ""); ca = aom.cmd_code("alpha", "accounts.example.com", "")
check("auth: the human's code goes only to the agent holding the site", cb[0] == 2 and ca == (0, {"status": "given", "site": "accounts.example.com", "code": "123456"}))
check("auth: the code itself never goes into the receipts", "123456" not in (ah / "logs" / "receipts.jsonl").read_text())
aom.cmd_release("alpha", "accounts.example.com")
check("auth: released, Bravo may sign in", aom.cmd_lease("bravo", "accounts.example.com", 10, 0)[0] == 0)
check("auth: no endless lease", aom.cmd_lease("alpha", "x.example", float("inf"), 0)[0] == 2 and aom.cmd_lease("alpha", "x.example", 600, 0)[0] == 2)
os.environ["RAINBOW_HOME"] = str(SAFE_HOME)
areg2 = json.loads(REG.read_text()); areg2["authSites"] = ["accounts.example.com"]; AREG2 = tmp / "auth-reg.json"; AREG2.write_text(json.dumps(areg2))
aenv = dict(genv, RAINBOW_HOME=str(ah), BROWSER_OWNER_REGISTRY=str(AREG2))
nav = lambda agent, url: subprocess.run([sys.executable, "-I", guard], input=json.dumps({"tool_name": "mcp__chrome-devtools__navigate_page",
                                         "tool_input": {"url": url}}), capture_output=True, text=True, env=dict(aenv, RAINBOW_AGENT=agent))
check("auth (guard): with authSites set, only the agent holding the site opens it — Bravo holds it, Alpha is refused, a site not listed is free",
      nav("bravo", "https://accounts.example.com/signin").returncode == 0 and nav("alpha", "https://accounts.example.com/signin").returncode == 2
      and "bravo is signing in" in nav("alpha", "https://accounts.example.com/").stderr and nav("alpha", "https://docs.example/").returncode == 0)
check("auth (guard): without authSites it is off — nothing is refused for it",
      subprocess.run([sys.executable, "-I", guard], input=json.dumps({"tool_name": "mcp__chrome-devtools__navigate_page",
                     "tool_input": {"url": "https://accounts.example.com/"}}), capture_output=True, text=True,
                     env=dict(genv, RAINBOW_HOME=str(ah), RAINBOW_AGENT="alpha")).returncode == 0)
check("auth (guard): an agent takes, releases and asks for codes only as itself", as_agent("auth-owner lease bravo accounts.example.com", "alpha") == 2
      and as_agent("auth-owner code bravo accounts.example.com", "alpha") == 2 and as_agent("auth-owner lease alpha accounts.example.com", "alpha") == 0)

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
