# Add rainbowomma to the plugin catalog

**RainbowOMMA — one Mac, one human, many agents.** Hackathon entry.

## What it does

Several Hermes profiles working on the Mac their human also works on collide in ways a prompt can't prevent: `pkill
Chrome` closes everyone's browser, "free port 3000" kills the human's dev server, a Word document is closed unsaved, two
agents drive the same window. The plugin gives each profile resources of its own and refuses the calls that would reach
a neighbour's:

- its own Chrome per profile, with a coloured, named window frame (the human sees whose window it is);
- a `pre_tool_call` guard: kills by pattern, quitting Chrome / Word through AppleScript, a port or process that isn't the
  agent's, the human's clipboard and Chrome profile, GUI input while the human is typing — refused before they run, with
  the tool that does it safely. A Messages/Mail send is escalated to Hermes's approval gate;
- leases for ports, the screen, sign-ins and documents in Word / Excel / Acrobat / Preview — an agent closes only what
  it leased;
- cleanup at session end and on an idle timer (job tabs, hot tabs, expired document leases, an app an agent launched and
  left empty, orphaned servers, an idle browser);
- `/rainbow` (who holds what) and `/rainbow pause | resume` (one stop button for every agent on the Mac);
- a browser provider (`browser.cloud_provider: rainbowomma`): Hermes's own browser tools drive the agent's framed
  Chrome instead of a throwaway Chromium — the human sees what the agent sees;
- a Desktop panel with the same picture.

Why a plugin and not a skill: the guard has to run before the tool does, and ownership has to be decided outside the
model.

## Hermes surfaces used

`ctx.register_tool` (30 tools, toolset `rainbowomma`, `check_fn` macOS), `ctx.register_hook` (`pre_tool_call` with
`block` / `approve` / `modify` directives; `on_session_start`; `on_session_finalize`), `ctx.register_command`
(`/rainbow`), `ctx.register_system_prompt_section`, `ctx.get_config` + `config_schema`, `ctx.profile_name`,
`ctx.on_unload`, `ctx.register_browser_provider` (`agent.browser_provider.BrowserProvider`), the Desktop plugin SDK (`desktop/plugin.js`). No core imports, no overrides, no middleware.

## Disclosures (rule 13)

- **Platform:** macOS only (`platforms: [macos]`).
- **Shell commands / programs started:** Google Chrome for the agent (own `--user-data-dir` under
  `~/.rainbowomma/profiles/<agent>`, a DevTools port bound to 127.0.0.1, an unpacked theme extension for the frame);
  `osascript` (Word, Excel, Acrobat, Preview, System Events); `ps`, `pgrep`, `lsof`, `ioreg`, `sysctl`, `defaults read`,
  `open -g`; `xcrun simctl` for the simulator tools.
- **Processes stopped:** only ones provably the agent's (`rainbow_stop_process`, the orphan reap at session end), the
  agent's own Chrome when idle, an Office/PDF app that an agent launched and that has had no documents for ten minutes.
- **Background:** one `guard_worker.py` helper per profile (the guard cannot run inside Hermes: one gateway process may
  serve several profiles, and the guard takes the caller's identity from its environment), and a housekeeping timer thread
  (default 5 min; `housekeeping_minutes: 0` turns it off). Both end on unload. The agent's Chrome keeps running until its
  idle stop (default 30 min).
- **Files:** only under `~/.rainbowomma/` (registry `browsers.json`, leases/state, `logs/receipts.jsonl`, themes, Chrome
  profiles, clipboard slots, temp copies for Word conversions). The registry is shared by the profiles on the Mac on purpose.
- **Tool-call changes:** in a process shared by several profiles the `terminal` command is prefixed with
  `export RAINBOW_AGENT=… RAINBOW_HOME=… BROWSER_OWNER_REGISTRY=…;` so the processes it starts are known as the agent's
  (`mark_commands: auto | always | never`).
  A `browser_exec` call is given the session name `rb-<agent>`, so two Hermes processes on one Mac never share one
  browser daemon (found in testing: the second profile's browser call landed in the first profile's Chrome).
- **Approvals:** nothing is auto-approved; the plugin only adds an `approve` escalation (Messages/Mail sends). It opens no
  dialog of its own, so unattended runs fall under Hermes's approval timeout.
- **Network:** one request, to `http://127.0.0.1:<port>/json/version` of the agent's own Chrome (the browser provider). Nothing leaves the machine. The vendored receipts module has an OTLP
  export command that the plugin never calls.
- **Credentials:** none read or stored. **Updates:** no self-update code.
- **Vendored code:** `vendor/` is a byte-for-byte copy of this repository's `bin/` owners (Apache-2.0, same author); a
  test fails when they differ.

## Checks

- `hermes plugins validate hermes-plugin/rainbowomma --install-deps`: passes; security scan `safe`.
- `python3 hermes-plugin/tests/test_plugin.py`: all pass (fake context, real guard helper, real owners on a temp home).
- Live on Hermes 0.22.5 with two profiles and a real model: registry rows created on first use, both browsers framed,
  `pkill` and the human's port refused, a Word → PDF conversion, job tabs closed at job end, `/rainbow`.

Screenshot (two profiles, each in its own framed Chrome; the human's Chrome untouched; refusals in the terminals):
`hermes-plugin/assets/overview.jpg`. The demo video shows the same run.

Submitted by the repository owner.
