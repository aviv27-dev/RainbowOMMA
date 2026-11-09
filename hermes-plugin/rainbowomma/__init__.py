"""RainbowOMMA for Hermes — one Mac, one human, many agents, and none of them in each other's way.

register(ctx) gives this Hermes profile:
  · tools (rainbow_*): its own colour-framed Chrome, ports, processes, the screen, sign-ins, documents in the shared
    Office/PDF apps, a clipboard and an iOS simulator of its own — each one a call of a RainbowOMMA owner;
  · a pre_tool_call guard that refuses the commands that would hit the human or another agent, and sends
    Messages/Mail sends to Hermes's approval gate;
  · housekeeping at the end of a session and while idle (tabs, documents, apps an agent launched, orphaned servers);
  · /rainbow — who holds what — and /rainbow pause | resume, the human's stop button for every agent.
macOS only: on another system nothing is registered but the /rainbow command, which says so.
"""
from __future__ import annotations

import json
import logging
import sys

from . import guard_hook, status, tool_defs
from .core import Rainbow
from .housekeeping import Housekeeper

logger = logging.getLogger(__name__)
TOOLSET = "rainbowomma"
IS_MAC = sys.platform == "darwin"
PROMPT = (
    "You share this Mac with a human and with other AI agents (RainbowOMMA keeps you apart). Your identity here is "
    "`{me}`. Use your own browser (rainbow_start_browser, rainbow_open_url), never the human's Chrome. Lease a port "
    "with rainbow_lease_port for every server you start. Stop only your own processes, with rainbow_stop_process. "
    "Open Word/Excel/PDF documents with rainbow_open_document and close them with rainbow_close_document when you are "
    "done; convert to PDF with rainbow_convert_to_pdf. Take the screen (rainbow_take_screen) before driving the "
    "foreground and give it back. When a rainbow_* tool or the guard answers refused, that is final: ask the human."
)


def _dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _handler(rb, script, argv, options):
    def handle(args: dict, **kwargs) -> str:
        a = args if isinstance(args, dict) else {}
        try:
            words = argv(rb.me, a)
        except (KeyError, TypeError, ValueError) as exc:
            return _dumps({"status": "failed", "why": f"bad arguments: {type(exc).__name__}: {exc}"[:200]})
        stdin = str(a.get(options["stdin"]) or "") if options.get("stdin") else None
        try:
            _ok, out = rb.run(script, *words, timeout=options.get("timeout", 120), stdin=stdin)
        except Exception as exc:                       # a handler never raises
            out = {"status": "failed", "why": f"{type(exc).__name__}: {exc}"[:300]}
        return _dumps(tool_defs.as_tools(out))
    return handle


def register(ctx):
    rb = Rainbow(ctx.get_config, lambda: ctx.profile_name)
    keeper = Housekeeper(rb)
    worker = guard_hook.GuardWorker()

    def rainbow_command(raw_args: str = "", **kwargs) -> str:
        if not IS_MAC:
            return "RainbowOMMA works on macOS only; on this system it does nothing."
        word = (raw_args or "").strip().lower()
        if word in ("pause", "resume"):
            # typed by the human in their own session — the stop button for every agent on the Mac
            _ok, out = rb.run("rainbowomma-pause.py", "on" if word == "pause" else "off")
            return ("⏸ All agents are paused: every tool call is refused until /rainbow resume."
                    if out.get("status") == "paused" else "▶ Agents resumed." if out.get("status") == "running"
                    else f"RainbowOMMA: {out.get('why') or out}")
        if word == "tidy":
            return _dumps(keeper.idle_pass())
        if word == "json":
            return _dumps(status.snapshot(rb))         # the same picture as data: what the Desktop panel reads
        if word in ("help", "?"):
            return "/rainbow — who holds what · /rainbow pause | resume — stop or release every agent · /rainbow tidy — run the idle cleanup now"
        return status.render(status.snapshot(rb))

    ctx.register_command("rainbow", rainbow_command, description="RainbowOMMA: who holds what on this Mac; pause | resume | tidy",
                         args_hint="[pause|resume|tidy]")
    if not IS_MAC:
        logger.info("rainbowomma: not macOS — tools and guard are not registered")
        return

    mac_only = lambda: IS_MAC                          # noqa: E731
    for name, description, parameters, script, argv, options in tool_defs.TOOLS:
        ctx.register_tool(name=name, toolset=TOOLSET, schema=tool_defs.schema(name, description, parameters),
                          handler=_handler(rb, script, argv, options), check_fn=mac_only, description=description, emoji="🌈")
    sname, sdesc, sparams = tool_defs.STATUS_TOOL
    ctx.register_tool(name=sname, toolset=TOOLSET, schema=tool_defs.schema(sname, sdesc, sparams),
                      handler=lambda args, **kw: _dumps(status.snapshot(rb)), check_fn=mac_only, description=sdesc, emoji="🌈")

    def pre_tool_call(tool_name: str = "", args: dict | None = None, **kwargs):
        try:
            if not rb.setting("guard"):
                return None
            verdict = guard_hook.decide(worker, tool_name, args or {}, rb.guard_env())
            if verdict is None and tool_name == "terminal":
                marked = rb.mark_command((args or {}).get("command"))
                if marked:
                    return {"action": "modify", "args": {"command": marked}}
            return verdict
        except Exception as exc:                       # the guard itself fails closed; this is the wrapper around it
            logger.warning("rainbowomma guard: %s: %s", type(exc).__name__, exc)
            return {"action": "block", "message": f"Blocked by RainbowOMMA: the guard could not judge this call ({type(exc).__name__})."}

    def on_session_start(**kwargs):
        try:
            rb.ensure_row()
            keeper.start()
        except Exception as exc:
            logger.warning("rainbowomma: %s", exc)

    def on_session_finalize(session_id: str | None = None, **kwargs):
        try:
            keeper.session_end(session_id or "")
        except Exception as exc:
            logger.warning("rainbowomma session end: %s: %s", type(exc).__name__, exc)

    ctx.register_hook("pre_tool_call", pre_tool_call)
    ctx.register_hook("on_session_start", on_session_start)
    ctx.register_hook("on_session_finalize", on_session_finalize)
    ctx.register_system_prompt_section("rainbowomma.shared-mac", lambda info: PROMPT.format(me=rb.me))
    ctx.on_unload(keeper.stop)
    ctx.on_unload(worker.stop)
