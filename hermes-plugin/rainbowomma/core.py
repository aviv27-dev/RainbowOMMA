"""core — who this agent is on the shared Mac, where RainbowOMMA keeps its state, and how an owner is run.

The plugin is one Hermes profile's view of a Mac that a human and other agents use too. Each profile is one agent: its
name is the profile's name, and the first time it is seen it gets a row in the shared registry (browsers.json) with a
free colour and a free Chrome debugging port. Every profile on the Mac points at the same registry and the same state
folder, which is what lets the owners keep the agents apart.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import shlex
import socket
import subprocess
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENDOR = HERE / "vendor"
TIMEOUT_S = 120
NAME_OK = re.compile(r"^[a-z][a-z0-9-]{0,30}$")
# the frame colours handed out in order; the names are what the status view prints
PALETTE = [("#FB8C00", "orange"), ("#1E88E5", "blue"), ("#43A047", "green"), ("#8E24AA", "purple"),
           ("#E53935", "red"), ("#00ACC1", "teal"), ("#F4511E", "coral"), ("#6D4C41", "brown")]
# 9222–9299 is the owners' range. A plugin-made row starts at 9240: 9222 and up are what a stand-alone RainbowOMMA install
# and most "remote debugging" examples use, and a port that is merely down right now may be someone's.
CDP_PORTS = [*range(9240, 9300), *range(9222, 9240)]
DEFAULTS = {"home": "~/.rainbowomma", "registry": "", "agent_name": "", "color": "", "idle_minutes": 30,
            "tab_cleanup": "apply", "housekeeping_minutes": 5, "guard": True, "mark_commands": "auto", "word_folder": "", "language": "en", "extra_apps": {}}
TAB_MODES = {"apply", "dry-run", "off"}
# what a child process inherits from Hermes's environment: enough to run, and nothing else. Hermes's environment holds
# provider keys and tokens, and the owners start programs the plugin does not own (Chrome, a launcher script, Office
# through osascript) — none of them may see those.
ENV_PASS = ("PATH", "HOME", "USER", "LANG", "TMPDIR", "__CF_USER_TEXT_ENCODING")
ENV_OWN = ("RAINBOW_", "BROWSER_OWNER_", "OFFICE_")
_lock = threading.Lock()


def child_env(own: dict, environ=None) -> dict:
    """the whole environment of a process the plugin starts: the few inherited names in ENV_PASS and LC_*, plus the
    plugin's own RAINBOW_* / BROWSER_OWNER_* / OFFICE_* values. Never the inherited environment."""
    src = os.environ if environ is None else environ
    out = {k: v for k, v in src.items() if k in ENV_PASS or k.startswith("LC_")}
    out.setdefault("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
    out.update({k: str(v) for k, v in own.items() if k.startswith(ENV_OWN)})
    return out


def agent_name(profile: str, override: str = "") -> str:
    """the agent's name in the registry: the setting if given, else the Hermes profile's name (the default profile is
    `hermes`). Lower case, letters digits and dashes — what the owners accept."""
    raw = (override or profile or "").strip().lower()
    if raw in ("", "default", "custom"):
        raw = "hermes"
    name = re.sub(r"[^a-z0-9-]+", "-", raw).strip("-")
    if not name or not name[0].isalpha():
        name = "agent-" + name if name else "hermes"
    return name[:31]


class Rainbow:
    """one profile's settings, resolved once per call (settings can change between calls; nothing is cached but the
    registry row check)"""

    def __init__(self, get_config, profile_name):
        self._get, self._profile = get_config, profile_name
        self._row_seen = False

    def setting(self, key):
        try:
            v = self._get(key, DEFAULTS[key])
        except Exception:
            v = DEFAULTS[key]
        return DEFAULTS[key] if v is None else v

    @property
    def me(self) -> str:
        try:
            profile = self._profile() if callable(self._profile) else str(self._profile or "")
        except Exception:
            profile = ""
        return agent_name(profile, str(self.setting("agent_name") or ""))

    @property
    def home(self) -> Path:
        return Path(os.path.expanduser(str(self.setting("home") or DEFAULTS["home"])))

    @property
    def registry(self) -> Path:
        r = str(self.setting("registry") or "").strip()
        return Path(os.path.expanduser(r)) if r else self.home / "browsers.json"

    def env(self) -> dict:
        """what an owner needs to know whose call this is and where the shared state lives"""
        out = {"RAINBOW_AGENT": self.me, "RAINBOW_HOME": str(self.home), "BROWSER_OWNER_REGISTRY": str(self.registry),
               "OFFICE_CONFINE": "1"}                 # conversions write beside the source, and replace only their own files
        lang = str(self.setting("language") or "en").strip().lower()
        if lang in ("en", "he"):                      # the owners' answers and the browser frame's text; auto: macOS's language
            out["RAINBOW_LANG"] = lang
        extra = self.setting("extra_apps")
        if isinstance(extra, dict) and extra:         # more document apps for the leases (office-owner validates each entry)
            out["OFFICE_EXTRA_APPS"] = json.dumps(extra, ensure_ascii=False)
        folder = str(self.setting("word_folder") or "").strip()
        if folder:                                    # the folder Word converts in (Word's sandbox asks for access once per folder)
            out["OFFICE_WORD_DIR"] = os.path.expanduser(folder)
        return out

    def shared_process(self) -> bool:
        """is this Hermes process serving more than this profile (a multiplexed gateway)? Then the process itself is not
        this agent's, and nothing under it may be counted as the agent's by ancestry."""
        try:
            profile = self._profile() if callable(self._profile) else str(self._profile or "")
        except Exception:
            return True
        return profile != process_profile()

    def guard_env(self) -> dict:
        """the guard's environment: who is asking, and — in a process shared by several profiles — never register
        that process as this agent's root"""
        return {**self.env(), **({"RAINBOW_TRACK_ROOT": "off"} if self.shared_process() else {})}

    def mark_command(self, command):
        """a shell command with this agent's identity exported in front, or None when it needs no mark. The owners tell
        whose process something is by RAINBOW_AGENT in its environment or by its ancestry. In a Hermes process of this
        profile alone, ancestry is enough (the guard registers the process as the agent's root). In a process shared by
        several profiles there is no such root, so each command carries the mark itself. mark_commands: auto | always | never."""
        mode = str(self.setting("mark_commands") or "auto").lower()
        if mode == "never" or (mode != "always" and not self.shared_process()):
            return None
        if not isinstance(command, str) or not command.strip() or "RAINBOW_AGENT=" in command:
            return None
        env = {k: v for k, v in self.env().items() if k in ("RAINBOW_AGENT", "RAINBOW_HOME", "BROWSER_OWNER_REGISTRY")}
        return "export " + " ".join(f"{k}={shlex.quote(v)}" for k, v in env.items()) + "; " + command

    # ---- the registry row -------------------------------------------------------------------------------------------
    def ensure_row(self) -> dict:
        """this agent's row in the shared registry, created the first time (a free colour, a free port, its own Chrome
        profile folder). An existing row is never changed here: the registry is the human's to edit."""
        me, reg_path = self.me, self.registry
        with _lock:
            reg_path.parent.mkdir(parents=True, exist_ok=True)
            with open(reg_path.parent / ".registry.lock", "w") as lk:
                fcntl.flock(lk, fcntl.LOCK_EX)
                try:
                    data = json.loads(reg_path.read_text()) if reg_path.exists() else {}
                except ValueError as exc:
                    raise RuntimeError(f"the registry {reg_path} is not valid JSON ({exc}); fix or remove it") from exc
                if not isinstance(data, dict):
                    raise RuntimeError(f"the registry {reg_path} is not a JSON object")
                agents = data.setdefault("agents", {})
                if not isinstance(agents, dict):
                    raise RuntimeError(f"the registry {reg_path} has no usable \"agents\" object")
                if me in agents:
                    self._row_seen = True
                    return agents[me]
                row = new_row(me, agents, self.home, str(self.setting("color") or ""), self.setting("idle_minutes"))
                agents[me] = row
                mode = str(self.setting("tab_cleanup") or "apply")
                if "tabSweep" not in data and mode in ("apply", "dry-run"):
                    data["tabSweep"] = {"mode": mode}
                tmp = reg_path.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
                os.replace(tmp, reg_path)
                self._row_seen = True
                return row

    # ---- running an owner -------------------------------------------------------------------------------------------
    def run(self, script: str, *args: str, timeout: float = TIMEOUT_S, stdin: str | None = None):
        """run one vendored owner as this agent → (ok, answer). The owners print one JSON answer; anything else (a
        crash, a timeout) becomes a failed answer with the reason. Never raises."""
        try:
            if not self._row_seen:
                self.ensure_row()
        except Exception as exc:
            return False, {"status": "failed", "why": str(exc)[:300]}
        cmd = [sys.executable, "-I", str(VENDOR / script), *[str(a) for a in args]]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, input=stdin,
                               env=child_env(self.env()))
        except subprocess.TimeoutExpired:
            return False, {"status": "failed", "why": f"{script.rsplit('.', 1)[0]} did not answer within {int(timeout)} s"}
        except OSError as exc:
            return False, {"status": "failed", "why": f"{type(exc).__name__}: {exc}"[:300]}
        return r.returncode == 0, parse_answer(r.stdout, r.stderr, r.returncode)


def process_profile(environ=None) -> str:
    """the profile this PROCESS was started for, from its HERMES_HOME: `default`, the name under profiles/, or `custom`"""
    home = (environ if environ is not None else os.environ).get("HERMES_HOME") or ""
    if not home:
        return "default"
    path = Path(os.path.expanduser(home))
    if path.parent.name == "profiles":
        return path.name
    return "default" if path.name == ".hermes" else "custom"


def parse_answer(stdout: str, stderr: str, code: int) -> dict:
    """the owner's JSON answer (its last line that parses as an object), else a failed answer carrying what it printed"""
    for line in reversed((stdout or "").strip().splitlines()):
        line = line.strip()
        if line[:1] == "{":
            try:
                out = json.loads(line)
            except ValueError:
                continue
            if isinstance(out, dict):
                return out
    text = (stdout or "").strip() or (stderr or "").strip()
    if code == 0:
        return {"status": "done", **({"text": text[:4000]} if text else {})}
    return {"status": "failed", "why": (text or f"exit {code}")[:1500]}


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        return s.connect_ex(("127.0.0.1", port)) != 0


def other_registry_ports(own: Path | None = None) -> set:
    """the browser ports of a stand-alone RainbowOMMA install on this Mac (browsers.json beside its browser-owner):
    its agents may be down right now, and their ports are still theirs"""
    import shutil
    found, seen = set(), set()
    exe = shutil.which("browser-owner")
    for cand in ([Path(exe).resolve().parent / "browsers.json"] if exe else []) + [Path.home() / "bin" / "browsers.json"]:
        try:
            if cand in seen or (own and cand.resolve() == own.resolve()) or not cand.exists():
                continue
            seen.add(cand)
            rows = json.loads(cand.read_text()).get("agents") or {}
            found |= {int(r["port"]) for r in rows.values() if isinstance(r, dict) and str(r.get("port", "")).isdigit()}
        except (OSError, ValueError, AttributeError):
            continue
    return found


def new_row(me: str, agents: dict, home: Path, color: str = "", idle_minutes=30, free=port_free, taken=None) -> dict:
    """a row for an agent the registry hasn't seen: the first colour and the first port no other row uses"""
    used_ports = {int(r["port"]) for r in agents.values() if isinstance(r, dict) and str(r.get("port", "")).isdigit()}
    used_ports |= set(other_registry_ports() if taken is None else taken)
    port = next((p for p in CDP_PORTS if p not in used_ports and free(p)), None)
    if port is None:
        raise RuntimeError("no free browser port left between 9222 and 9299")
    used_colors = {str(r.get("color", "")).upper() for r in agents.values() if isinstance(r, dict)}
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color or ""):
        color = next((c for c, _ in PALETTE if c.upper() not in used_colors), PALETTE[len(agents) % len(PALETTE)][0])
    row = {"label": me.replace("-", " ").title(), "port": port, "profile": str(home / "profiles" / me), "color": color.upper()}
    try:
        idle = int(idle_minutes)
    except (TypeError, ValueError):
        idle = 0
    if idle > 0:
        row["idleMinutes"] = idle
    return row


def color_name(hex_color: str) -> str:
    return next((n for c, n in PALETTE if c.upper() == str(hex_color or "").upper()), str(hex_color or ""))
