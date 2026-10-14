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
bo.install_theme = lambda a, folder, timeout=25.0: (True, "fakethemeid")   # never a real Chrome in a test
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
check("the real registry loads: alpha 9222, bravo 9223, charlie 9224",
      (lambda r: r["alpha"]["port"] == 9222 and r["bravo"]["port"] == 9223 and not r["bravo"].get("managedBy")
       and r["bravo"]["idleMinutes"] == 60 and r["charlie"]["port"] == 9224)(bo.registry()))
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
check("…the theme install closed its windowless Chrome — recorded as an OWNER stop (so it is never read as the human's ⌘Q)",
      mst["lastStop"]["by"] == "theme-install")
up[9224] = False
inst = []
_it = bo.install_theme; bo.install_theme = lambda a, folder, timeout=25.0: inst.append(1) or (True, "x")
code, out = bo.do_start(CHARLIE_A, "charlie")
check("the next start keeps the installed theme — no second install", not inst and json.loads(Path(CHARLIE_A["state"]).read_text())["lastStart"]["theme"] == "kept")
up[9224] = False
CHARLIE_A["color"] = "#00897B"
code, out = bo.do_start(CHARLIE_A, "charlie")
check("its color changed in the registry → the theme is rebuilt", inst == [1])
CHARLIE_A["color"] = "#F4511E"
up[9224] = False
bo.install_theme = lambda a, folder, timeout=25.0: (False, "Extensions.loadUnpacked not allowed")
st0 = json.loads(Path(CHARLIE_A["state"]).read_text()); st0.pop("theme"); Path(CHARLIE_A["state"]).write_text(json.dumps(st0))
code, out = bo.do_start(CHARLIE_A, "charlie")
mp = json.loads(Path(CHARLIE_A["profile"], "Default", "Preferences").read_text())
mst = json.loads(Path(CHARLIE_A["state"]).read_text())
check("theme install fails → the start goes on with the profile color (fallback) and the reason is recorded",
      code == 0 and mst["lastStart"]["theme"] == "failed" and "loadUnpacked" in mst["themeError"] and mp["browser"]["theme"]["user_color2"] == agent_color, (out, mst))
bo.install_theme = _it if False else (lambda a, folder, timeout=25.0: (True, "fakethemeid"))
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
code, out = ao.cmd_pdf("bravo", str(src))
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
check("every message has an English and a Hebrew text", all(set(v) >= {"en", "he"} and all(v.values()) for v in i18n.M.values()),
      [k for k, v in i18n.M.items() if set(v) < {"en", "he"}])
used = set()
for f in [*HERE.glob("*.sh"), HERE.parent / "examples" / "agent-launcher.sh", HERE.parent / "install" / "make-desktop-apps.sh"]:
    used |= set(re.findall(r"msg ([a-z]+\.[a-z_.]+)", f.read_text(encoding="utf-8")))
used |= {f"desk.name.{n}" for n in ("alpha", "bravo", "charlie", "human")}
check("every message a shell script asks for exists in the catalog", used and used <= set(i18n.M), sorted(used - set(i18n.M)))
for f in [*HERE.glob("*.py"), *HERE.glob("*.sh"), HERE.parent / "examples" / "agent-launcher.sh", HERE.parent / "install" / "make-desktop-apps.sh"]:
    if f.name == "rainbow_i18n.py":
        continue
    heb = [ln for ln in f.read_text(encoding="utf-8").splitlines() if re.search("[\u0590-\u05FF]", ln) and "*דפדפן*.app" not in ln]
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
check("LTR has its own theme key, so switching language rebuilds the frame once", bo.theme_key(CHARLIE_A).endswith(":ltr"))
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
check("frame text and side follow the language: LTR → 'Zed · AGENT · do not touch' drawn on the right",
      seen[0][5] == "Zed · AGENT · do not touch" and seen[0][-1] == "ltr", seen[0][4:])
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
os.environ.pop("RAINBOW_HOME")
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
      r.returncode == 0 and all(os.access(ib / n, os.X_OK) for n in ("browser-owner", "office-owner", "agent-office", "kill-chrome.sh"))
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

# ── the Claude Code guard (a PreToolUse hook; fed JSON on stdin like Claude Code does) ──
guard = str(HERE.parent / "adapters" / "claude-code" / "rainbowomma-guard.py")
def hook(cmd, tool="Bash"):
    ev = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": {"command": cmd}}
    r = subprocess.run([sys.executable, "-I", guard], input=json.dumps(ev), capture_output=True, text=True)
    return r.returncode, r.stderr
blocked_cmds = ["pkill -f 'Google Chrome'", "cd /tmp && pkill -f chrome", "sudo killall 'Google Chrome'", "kill -9 $(pgrep -f remote-debugging)",
                "kill `pgrep Chrome`", "pgrep -f Chrome | xargs kill", "osascript -e 'tell application \"Google Chrome\" to quit'",
                "osascript -e 'quit app \"Google Chrome\"'",
                "'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --remote-debugging-port=9222 --user-data-dir=/tmp/x"]
res = [hook(c) for c in blocked_cmds]
check("Claude Code guard blocks every way around the owner (exit 2, a reason for Claude on stderr)",
      all(code == 2 and "browser-owner" in err for code, err in res), [c for c, (code, _) in zip(blocked_cmds, res) if code != 2])
allowed = ["~/bin/browser-owner start alpha --by alpha", "~/bin/office-owner pdf --agent alpha a.docx", "kill 12345", "ls ~/pkill-notes",
           "echo skill", "osascript -e 'tell application \"Google Chrome\" to get URL of active tab of front window'"]
res = [hook(c) for c in allowed]
check("…and lets the owner and ordinary commands through", all(code == 0 for code, _ in res), [c for c, (code, _) in zip(allowed, res) if code])
check("…and ignores tools other than Bash", hook("pkill x", tool="Read")[0] == 0)
cc = json.loads((HERE.parent / "adapters" / "claude-code" / "settings.json").read_text())
check("the Claude Code settings example wires the guard on Bash", cc["hooks"]["PreToolUse"][0]["matcher"] == "Bash"
      and "rainbowomma-guard.py" in cc["hooks"]["PreToolUse"][0]["hooks"][0]["command"])

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


print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
