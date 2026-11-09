"""status — who holds what on the shared Mac, as data (rainbow_status, the Desktop panel) and as text (/rainbow)."""
from __future__ import annotations

from .core import color_name


def snapshot(rb) -> dict:
    """one picture of the Mac: every agent's browser, the ports, the screen, the documents, the logins, the pause"""
    me = rb.me
    try:
        rb.ensure_row()
    except Exception as exc:
        return {"me": me, "error": str(exc)[:300]}
    browsers = rb.run("browser-owner.py", "list")[1]
    ports = rb.run("port-owner.py", "list")[1]
    screen = rb.run("screen-owner.py", "who")[1]
    docs = rb.run("agent-office.py", "list")[1]
    apps = rb.run("agent-office.py", "apps")[1]
    logins = rb.run("auth-owner.py", "list")[1]
    pause = rb.run("rainbowomma-pause.py", "status")[1]
    agents = []
    for a in browsers.get("agents") or []:
        if not isinstance(a, dict):
            continue
        name = a.get("agent")
        agents.append({
            "agent": name, "label": a.get("label") or name, "me": name == me, "color": a.get("color"),
            "colorName": color_name(a.get("color")), "browser": a.get("status") or "unknown", "cdpPort": a.get("port"),
            "closedByHuman": bool(a.get("offByHuman")), "portRange": (ports.get("ranges") or {}).get(name),
            "ports": [{"port": x.get("port"), "name": x.get("name")} for x in ports.get("leases") or []
                      if isinstance(x, dict) and x.get("agent") == name],
            "documents": [x.get("file") or x.get("path") for x in docs.get("leases") or []
                          if isinstance(x, dict) and x.get("agent") == name],
        })
    holder = screen.get("holder")
    return {
        "me": me, "paused": pause.get("status") == "paused", "agents": agents,
        "screen": {"holder": holder if isinstance(holder, str) else (holder or {}).get("agent") if isinstance(holder, dict) else None,
                   "until": screen.get("until")},
        "logins": logins.get("leases") or {},
        # only the apps an agent launched: one that was already running is the human's, and is never quit
        "apps": {k: v.get("launchedBy") for k, v in (apps.get("apps") or {}).items()
                 if isinstance(v, dict) and v.get("launchedBy") not in (None, "human")},
        "errors": [x.get("why") for x in (browsers, ports, screen, docs, apps, logins, pause) if x.get("status") == "failed"],
    }


def render(snap: dict) -> str:
    """the snapshot as a few plain lines, readable in a terminal and in a chat app alike"""
    if snap.get("error"):
        return f"RainbowOMMA: {snap['error']}"
    lines = [f"RainbowOMMA · you are {snap.get('me')}" + (" · ⏸ the human paused all agents" if snap.get("paused") else "")]
    for a in snap.get("agents") or []:
        mark = "→" if a.get("me") else " "
        bits = [f"browser {a.get('browser')}" + (" (closed by the human)" if a.get("closedByHuman") else "")
                + (f", CDP {a.get('cdpPort')}" if a.get("browser") == "up" else "")]
        if a.get("ports"):
            bits.append("ports " + ", ".join(f"{p['port']} ({p['name']})" if p.get("name") else str(p["port"]) for p in a["ports"]))
        if a.get("documents"):
            bits.append("documents " + ", ".join(str(d).rsplit("/", 1)[-1] for d in a["documents"]))
        lines.append(f"{mark} {a.get('label')} [{a.get('colorName')}] — " + " · ".join(bits))
    if not snap.get("agents"):
        lines.append("  no agents in the registry yet")
    screen = snap.get("screen") or {}
    lines.append("screen: " + (f"held by {screen['holder']}" + (f" until {screen['until']}" if screen.get("until") else "")
                               if screen.get("holder") else "free"))
    if snap.get("logins"):
        lines.append("sign-ins: " + ", ".join(f"{site} ← {(v or {}).get('agent', v) if isinstance(v, dict) else v}"
                                               for site, v in snap["logins"].items()))
    if snap.get("apps"):
        lines.append("apps an agent launched: " + ", ".join(sorted(snap["apps"])))
    for e in snap.get("errors") or []:
        if e:
            lines.append(f"! {e}")
    return "\n".join(lines)
