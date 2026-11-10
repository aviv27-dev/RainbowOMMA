"""tool_defs — the tools the agent gets, as one table: name, what the model reads, and the owner call behind it.

Every tool is one call of one owner, run as this agent. The owners answer with one JSON object whose "status" says what
happened ("refused" is final: ask the human) and often a "next" telling what to do; the handler returns it unchanged.
"""
from __future__ import annotations


def _clamp(v, lo, hi, default):
    try:
        return min(max(float(v), lo), hi)
    except (TypeError, ValueError):
        return default


def _s(v) -> str:
    return "" if v is None else str(v)


def _obj(props=None, required=None):
    out = {"type": "object", "properties": props or {}}
    if required:
        out["required"] = required
    return out


STR, INT, NUM, BOOL = {"type": "string"}, {"type": "integer"}, {"type": "number"}, {"type": "boolean"}


def _d(t, text):
    return {**t, "description": text}


# (name, description, parameters, script, argv(me, args), options)
TOOLS = [
    # ---- your own browser ----------------------------------------------------------------------------------------
    ("rainbow_start_browser",
     "Open YOUR OWN Chrome (its window frame carries your colour and name; it is never the human's Chrome). The answer has "
     "its CDP port. If it answers refused, closed-by-person, blocked or profile-busy: stop and ask the human.",
     _obj(), "browser-owner.py", lambda me, a: ["start", me, "--by", me], {}),
    ("rainbow_browser_status",
     "Your browser's state: up, down, hung, blocked, profile-busy or closed by the human, and its CDP port.",
     _obj(), "browser-owner.py", lambda me, a: ["status", me], {}),
    ("rainbow_recover_browser",
     "Restart your browser when it is hung. Never reopens one the human closed.",
     _obj(), "browser-owner.py", lambda me, a: ["recover", me, "--by", me], {}),
    ("rainbow_open_url",
     "Open an address (a page, a sign-in, an OAuth link) in YOUR browser. Use it instead of `open <url>`, which would "
     "open the human's browser.",
     _obj({"url": _d(STR, "http(s) address")}, ["url"]), "browser-owner.py",
     lambda me, a: ["open", me, _s(a["url"]), "--by", me], {}),
    ("rainbow_job_start",
     "A job begins: remember which tabs your browser has now, so the tabs this job opens can be closed when it ends.",
     _obj(), "browser-owner.py", lambda me, a: ["job-start", me], {}),
    ("rainbow_job_end",
     "The job is done: lists the tabs it opened that will close. Keep the ones you still need with rainbow_keep_tabs, "
     "then call rainbow_close_job_tabs (they also close by themselves after a minute).",
     _obj(), "browser-owner.py", lambda me, a: ["job-end", me], {}),
    ("rainbow_keep_tabs",
     "Keep these tabs open after the job (ids from rainbow_job_end); tabs they opened stay too.",
     _obj({"ids": {"type": "array", "items": STR}}, ["ids"]), "browser-owner.py",
     lambda me, a: ["job-keep", me, *[_s(x) for x in a["ids"]]], {}),
    ("rainbow_close_job_tabs",
     "Close the finished job's tabs that were not kept (never the last tab, never one another client is driving).",
     _obj(), "browser-owner.py", lambda me, a: ["job-close", me], {}),
    ("rainbow_tidy_tabs",
     "Tab housekeeping in your own browser: reload tabs that burn CPU and close old idle ones. Without apply it only "
     "reports what it would do.",
     _obj({"apply": _d(BOOL, "act now instead of reporting")}), "browser-owner.py",
     lambda me, a: ["tabs", me, *(["--apply"] if a.get("apply") else [])], {}),
    # ---- network ports --------------------------------------------------------------------------------------------
    ("rainbow_lease_port",
     "Get a free network port of your own (from your range; never the human's 3000/5173/8000/8080). Use it for every "
     "server you start: PORT=<port>. The same name gives the same port back.",
     _obj({"name": _d(STR, "what it is for, e.g. web, api"), "prefer": _d(INT, "a port inside your own range")}),
     "port-owner.py", lambda me, a: ["lease", me, "--name", _s(a.get("name") or "default"),
                                     *(["--prefer", str(int(a["prefer"]))] if a.get("prefer") is not None else [])], {}),
    ("rainbow_release_port", "Give a leased port back (all of yours with all=true).",
     _obj({"name": STR, "all": BOOL}), "port-owner.py",
     lambda me, a: ["release", me, *(["--all"] if a.get("all") else ["--name", _s(a.get("name") or "default")])], {}),
    ("rainbow_who_port", "Whose a port is (an agent's or the human's) and what listens on it.",
     _obj({"port": INT}, ["port"]), "port-owner.py", lambda me, a: ["who", str(int(a["port"]))], {}),
    # ---- processes ------------------------------------------------------------------------------------------------
    ("rainbow_whose_process", "Whose a process is: yours, another agent's, or the human's.",
     _obj({"pid": INT}, ["pid"]), "proc-owner.py", lambda me, a: ["whose", str(int(a["pid"]))], {}),
    ("rainbow_stop_process",
     "Stop one of YOUR processes (refused for another agent's or the human's). Use this instead of kill / pkill / "
     "killall / kill-port.",
     _obj({"pid": INT, "force": _d(BOOL, "KILL if it has not stopped after 5 s")}, ["pid"]), "proc-owner.py",
     lambda me, a: ["kill", str(int(a["pid"])), "--by", me, *(["--force"] if a.get("force") else [])], {}),
    ("rainbow_my_processes", "Your processes and the ports they listen on.",
     _obj(), "proc-owner.py", lambda me, a: ["list", me], {}),
    # ---- the screen -----------------------------------------------------------------------------------------------
    ("rainbow_take_screen",
     "Hold the screen (keyboard, mouse, the window in front) before driving the foreground for a while. Background "
     "drivers don't need it. Refused while the human types or holds the screen.",
     _obj({"minutes": NUM, "wait_seconds": NUM}), "screen-owner.py",
     lambda me, a: ["take", me, "--minutes", str(_clamp(a.get("minutes"), 0.1, 60.0, 5.0)),
                    "--wait", str(_clamp(a.get("wait_seconds"), 0.0, 120.0, 0.0))], {"timeout": 150}),
    ("rainbow_release_screen", "Give the screen back as soon as you are done with the foreground.",
     _obj(), "screen-owner.py", lambda me, a: ["release", me], {}),
    # ---- signing in -----------------------------------------------------------------------------------------------
    ("rainbow_take_login",
     "Before signing in to a site the human listed as one-agent-at-a-time: take it, so no other agent signs in to the "
     "same account at once. Refused while another agent holds it. For a one-time code, ask the human with `clarify`.",
     _obj({"site": _d(STR, "host name, e.g. accounts.example.com"), "wait_seconds": NUM}, ["site"]), "auth-owner.py",
     lambda me, a: ["lease", me, _s(a["site"]), "--wait", str(_clamp(a.get("wait_seconds"), 0.0, 600.0, 0.0))],
     {"timeout": 630}),
    ("rainbow_release_login", "Done signing in: give the site back.",
     _obj({"site": STR}, ["site"]), "auth-owner.py", lambda me, a: ["release", me, _s(a["site"])], {}),
    # ---- documents in the shared Office / PDF apps -----------------------------------------------------------------
    ("rainbow_open_document",
     "Open a document in the shared app (Word, Excel, Acrobat, Preview) under a lease in your name, so you — and only "
     "you — close it later. A document the human already has open stays theirs.",
     _obj({"file": _d(STR, "absolute path"), "app": _d(STR, "word | excel | acrobat | preview (default: by extension)")},
          ["file"]), "agent-office.py",
     lambda me, a: ["open", "--agent", me, *(["--app", _s(a["app"])] if a.get("app") else []), _s(a["file"])], {}),
    ("rainbow_save_document",
     "Save, in place, a document you opened with rainbow_open_document (Word, Excel, Preview). A document the human "
     "already had open is theirs to save: refused.",
     _obj({"file": STR}, ["file"]), "agent-office.py", lambda me, a: ["save", "--agent", me, _s(a["file"])], {}),
    ("rainbow_close_document",
     "Close a document you opened with rainbow_open_document. It closes only if you leased it, nobody had it open "
     "before you, and the app says it is saved; otherwise it is left open and the answer says why.",
     _obj({"file": STR}, ["file"]), "agent-office.py", lambda me, a: ["close", "--agent", me, _s(a["file"])], {}),
    ("rainbow_renew_document", "Still working on a document: keep your lease on it from expiring.",
     _obj({"file": STR}, ["file"]), "agent-office.py", lambda me, a: ["renew", "--agent", me, _s(a["file"])], {}),
    ("rainbow_convert_to_pdf",
     "Convert a Word document to PDF through the real Word, on a uniquely named temp copy that is closed by name — the "
     "human's open documents are never touched.",
     _obj({"file": _d(STR, "absolute path of the .docx / .doc / .rtf"), "out": _d(STR, "PDF path, in the same folder as the file (default: beside it, same name)"),
           "force": _d(BOOL, "replace a PDF that an earlier conversion of yours wrote; anyone else's file is never replaced")}, ["file"]), "agent-office.py",
     lambda me, a: ["pdf", "--agent", me, *(["--out", _s(a["out"])] if a.get("out") else []),
                    *(["--force"] if a.get("force") else []), _s(a["file"])], {"timeout": 260}),
    ("rainbow_recalc_workbook",
     "Recalculate a workbook's formulas through the real Excel (optionally saving a copy or a PDF), on a temp copy.",
     _obj({"file": _d(STR, "absolute path of the .xlsx"), "out": _d(STR, "save the recalculated copy here (same folder as the file)"),
           "pdf": _d(STR, "also save this PDF (same folder as the file)"), "force": _d(BOOL, "replace outputs an earlier call of yours wrote")}, ["file"]), "agent-office.py",
     lambda me, a: ["xlsx", "--agent", me, *(["--out", _s(a["out"])] if a.get("out") else []),
                    *(["--pdf", _s(a["pdf"])] if a.get("pdf") else []), *(["--force"] if a.get("force") else []),
                    _s(a["file"])], {"timeout": 260}),
    ("rainbow_documents", "The document leases every agent holds in the shared apps, and which apps an agent launched.",
     _obj(), "agent-office.py", lambda me, a: ["list"], {}),
    # ---- a clipboard of your own -----------------------------------------------------------------------------------
    ("rainbow_clip_copy",
     "Keep a text on YOUR clipboard (the system clipboard is the human's: pbcopy and pbpaste are refused).",
     _obj({"text": STR, "name": _d(STR, "a slot name (default: default)")}, ["text"]), "rainbowomma-clip.py",
     lambda me, a: ["copy", me, *(["--name", _s(a["name"])] if a.get("name") else [])], {"stdin": "text"}),
    ("rainbow_clip_paste", "Read a text back from your clipboard.",
     _obj({"name": STR}), "rainbowomma-clip.py",
     lambda me, a: ["paste", me, *(["--name", _s(a["name"])] if a.get("name") else [])], {}),
    # ---- an iOS simulator of your own ------------------------------------------------------------------------------
    ("rainbow_sim_lease",
     "Your own iOS Simulator (created once, booted): use the UDID it returns in simctl and xcodebuild instead of "
     "`booted`, which may be another agent's device.",
     _obj({"device": _d(STR, "device type, e.g. iPhone 16")}), "sim-owner.py",
     lambda me, a: ["lease", me, *(["--device", _s(a["device"])] if a.get("device") else [])], {"timeout": 300}),
    ("rainbow_sim_release", "Give your simulator back (it stays installed for next time).",
     _obj({"shutdown": BOOL}), "sim-owner.py",
     lambda me, a: ["release", me, *(["--shutdown"] if a.get("shutdown") else [])], {}),
]
NAMES = [t[0] for t in TOOLS] + ["rainbow_status"]
STATUS_TOOL = ("rainbow_status",
               "Who holds what on this Mac right now: every agent's browser, the leased ports, the screen, the document "
               "leases, and whether the human paused the agents.", _obj())


def schema(name, description, parameters):
    return {"name": name, "description": description, "parameters": parameters}


# The owners' answers name their own command lines in hints ("next", "keep", "why"). Inside Hermes the same call is a tool.
CLI_TO_TOOL = {
    "browser-owner start": "rainbow_start_browser", "browser-owner recover": "rainbow_recover_browser",
    "browser-owner status": "rainbow_browser_status", "browser-owner open": "rainbow_open_url",
    "browser-owner job-start": "rainbow_job_start", "browser-owner job-end": "rainbow_job_end",
    "browser-owner job-keep": "rainbow_keep_tabs", "browser-owner job-close": "rainbow_close_job_tabs",
    "browser-owner tabs": "rainbow_tidy_tabs", "browser-owner list": "rainbow_status",
    "port-owner lease": "rainbow_lease_port", "port-owner release": "rainbow_release_port",
    "port-owner who": "rainbow_who_port", "port-owner list": "rainbow_status",
    "proc-owner whose": "rainbow_whose_process", "proc-owner kill": "rainbow_stop_process",
    "proc-owner list": "rainbow_my_processes",
    "screen-owner take": "rainbow_take_screen", "screen-owner release": "rainbow_release_screen",
    "screen-owner who": "rainbow_status",
    "auth-owner lease": "rainbow_take_login", "auth-owner release": "rainbow_release_login",
    "auth-owner who": "rainbow_status", "auth-owner list": "rainbow_status",
    "auth-owner code": "the clarify tool (ask the human for the code)",
    "office-owner open": "rainbow_open_document", "office-owner save": "rainbow_save_document", "office-owner close": "rainbow_close_document",
    "office-owner renew": "rainbow_renew_document", "office-owner pdf": "rainbow_convert_to_pdf",
    "office-owner xlsx": "rainbow_recalc_workbook", "office-owner list": "rainbow_documents",
    "office-owner apps": "rainbow_documents",
    "sim-owner lease": "rainbow_sim_lease", "sim-owner release": "rainbow_sim_release",
    "rainbowomma-clip copy": "rainbow_clip_copy", "rainbowomma-clip paste": "rainbow_clip_paste",
    "rainbowomma-doctor status": "/rainbow", "rainbowomma-doctor": "/rainbow",
}
_CLI = __import__("re").compile("|".join(sorted((__import__("re").escape(k) for k in CLI_TO_TOOL), key=len, reverse=True)))


def as_tools(value):
    """the same answer with every owner command line in its texts replaced by the tool that does it"""
    if isinstance(value, str):
        return _CLI.sub(lambda m: CLI_TO_TOOL[m.group(0)], value)
    if isinstance(value, list):
        return [as_tools(v) for v in value]
    if isinstance(value, dict):
        return {k: (as_tools(v) if k in ("why", "next", "keep", "hint", "how", "fix", "detail") else v) for k, v in value.items()}
    return value
