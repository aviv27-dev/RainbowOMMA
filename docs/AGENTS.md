# Works with your agent

RainbowOMMA itself works with any agent that can run a shell command: the agent calls `browser-owner` and
`office-owner` and reads one JSON answer. Two optional plug-ins go into the agent framework:

- **Guardrail:** stops the agent from going around the owner with its own `pkill`, `killall`, `kill $(pgrep …)`,
  AppleScript `quit` of Chrome, or a Chrome started on a debug port. Most frameworks run a pre-tool hook; all of them
  point to the same script, `~/bin/rainbowomma-guard` (installed by `install.sh`), which understands each framework's
  hook payload. Where a framework also has a native deny list, the adapter adds it as a second layer.
- **Colored cursor:** for agents that do computer use through Cua Driver over MCP, register
  `~/bin/cua-color-proxy --agent <name>` instead of `cua-driver mcp` (see the README's cursor section).

Pattern rules only see the command text an agent runs; `browser-owner`'s own checks stay the real protection.

## At a glance

| Agent | Guardrail plug-in | Blocks by content? | Colored cursor (MCP) | Adapter status |
|---|---|---|---|---|
| Claude Code | PreToolUse hook + `permissions.deny` | yes | yes | tested (hook payload) |
| Codex CLI | PreToolUse hook + exec-policy `.rules` | yes | yes | ready |
| Gemini CLI | policy TOML (hard deny) + BeforeTool hook | yes | yes | ready |
| OpenCode | `permission.bash` deny + plugin | yes | yes | ready |
| Kilo Code | same as OpenCode | yes | yes | ready |
| Qwen Code | PreToolUse hook + `permissions.deny` | yes | yes | ready |
| Factory Droid | `commandBlocklist` (hard) + PreToolUse hook | yes | yes | ready |
| Hermes Agent | `pre_tool_call` hook + approvals deny list | yes | via patch (built-in computer use) | ready |
| Goose | plugin with a PreToolUse hook | yes | yes | ready |
| Zed agent | `always_deny` regex | yes | yes | ready |
| GitHub Copilot CLI | `preToolUse` hook | yes | yes | ready |
| GitHub Copilot in VS Code | `PreToolUse` hook (Preview) | yes | yes | ready |
| Cursor (editor) | `beforeShellExecution` hook | yes | yes | ready |
| Cursor CLI (`cursor-agent`) | `permissions.deny` | first word only | yes | ready |
| Cline | `PreToolUse` hook (cancels the task) | yes | yes | ready |
| Windsurf / Devin Desktop | `pre_run_command` hook | yes | yes | draft: docs not fully verified |
| Amp | `amp.permissions` reject rules | glob | yes | draft: docs not fully verified |
| OpenClaw | plugin `before_tool_call` | yes | yes | draft: not run on OpenClaw yet |
| Continue CLI | `permissions.yaml` exclude | glob, first word | yes | ready (project archived) |
| Kiro, Augment (Auggie) | PreToolUse hooks exist | yes | yes | not yet: config format unverified |
| Warp agent | denylist only *asks*, never denies | — | yes | no hard guardrail possible |
| Aider | no hook or deny list (asks for every command) | — | no MCP | no plug-in possible |
| Roo Code | — | — | — | discontinued (May 2026) |

"Ready" means the files follow the framework's documentation and the shared guard is tested against that payload
shape; please report anything that doesn't work on your version.

## Before you start

`install.sh` puts `rainbowomma-guard`, `cua-color-proxy`, `as-agent`, `rainbowomma-session-end` and `rainbowomma-mcp` in `~/bin`. The adapter files use the placeholder path
`/Users/you/bin/…`; copy them with your own home folder filled in, for example:

```bash
sed "s|/Users/you|$HOME|g" adapters/codex/hooks.json > ~/.codex/hooks.json
```

If the target file already exists, merge the keys into it instead of overwriting it.

Every MCP snippet below registers the colored cursor for agent `alpha`; use the agent's name from `browsers.json`.

## Name the agent, give it the owners as tools, clean up after it

These three work for every agent, whatever its framework:

- **Name it.** Start the agent as a named agent, e.g. `~/bin/as-agent alpha claude`, `~/bin/as-agent bravo codex`.
  Every process it starts then carries `RAINBOW_AGENT=alpha`, and `as-agent` registers its shell as alpha's root, so
  its processes are alpha's even where the OS hides their environment (macOS 27). The guardrail holds it to its own ports (`port-owner`)
  and its own processes (`proc-owner`), and when it exits, the servers it left behind stop and its ports go back.
  Without `as-agent`, set `RAINBOW_AGENT` in the framework's environment where it has one (Claude Code: `"env"` in
  `settings.json`, as in the adapter; Codex: `[shell_environment_policy] set = { RAINBOW_AGENT = "alpha" }` in
  `config.toml`); the guardrail hook then registers the framework's own process as the agent's root on its first call.
  An agent without a name can't stop any process with a plain `kill`.
- **Clean up at session end.** Claude Code, Gemini CLI, Factory Droid and Copilot CLI adapters run
  `~/bin/rainbowomma-session-end` from their session-end hook (it does nothing for an agent without `RAINBOW_AGENT`).
  For the others, `as-agent` does the same when the agent exits.
- **A browser MCP on the agent's own browser.** `~/bin/browser-owner mcp-config alpha` (or `--tool playwright`,
  `--format claude`) prints a Chrome DevTools MCP or Playwright MCP entry pointed at Alpha's own CDP port. The guardrail
  refuses `--autoConnect` and `--extension` (they attach to the human's Chrome) and, for a named agent, another agent's
  CDP port.
- **The owners as MCP tools** (`lease_port`, `who_port`, `whose_process`, `stop_process`, `my_processes`,
  `browser_status`, `start_my_browser`, `recover_my_browser`): register `~/bin/rainbowomma-mcp --agent alpha` the
  same way as the cursor proxy below, e.g.
  `claude mcp add-json --scope user rainbowomma "{\"command\":\"$HOME/bin/rainbowomma-mcp\",\"args\":[\"--agent\",\"alpha\"]}"`.

## File tools, not only the shell

The guardrail also refuses an agent's file tools aimed at RainbowOMMA's own state or `browsers.json` (writing) and the
human's Chrome profile (reading or writing). Each adapter sends its framework's file tools to it:

| Framework | What the hook matches | Where the path is |
|---|---|---|
| Claude Code | `Bash\|Write\|Edit\|MultiEdit\|NotebookEdit\|Read\|Grep\|Glob\|WebFetch\|Task` | `file_path`, `path`, `notebook_path` |
| Codex CLI | `Bash\|apply_patch` | the patch's `*** Add/Update/Delete File:` lines (also a patch run through the shell) |
| Gemini CLI | `^(run_shell_command\|write_file\|replace\|read_file\|read_many_files)$` | `file_path` |
| Qwen Code | `^(run_shell_command\|write_file\|edit\|read_file\|notebook_edit)$` | `file_path`, `notebook_path` |
| Factory Droid | `Execute\|Read\|Edit\|Create\|ApplyPatch` | `file_path` (an ApplyPatch's own lines) |
| Hermes Agent | `terminal\|write_file\|patch\|read_file` | `path`, or a V4A patch's lines |
| Cursor | `beforeShellExecution`, `preToolUse` (`Write\|Delete`), `beforeReadFile` | `file_path` |
| Windsurf | `pre_run_command`, `pre_read_code`, `pre_write_code` | `tool_info.file_path` |
| Copilot (CLI, VS Code), Goose | every tool | `file_path`, `path` |

Cursor's and Windsurf's payload shapes come from their documentation, not from their source; check a real payload if a
file isn't refused. Devin Desktop replaced Cascade with Devin Local, whose hooks file (`.devin/hooks.v1.json`,
`PreToolUse` with regex matchers) is not covered yet — `devin migrate hooks` copies the Windsurf one.

## Claude Code
- Guardrail: merge [`adapters/claude-code/settings.json`](../adapters/claude-code/settings.json) into
  `~/.claude/settings.json` (or a project's `.claude/settings.json`).
- Cursor: `claude mcp add-json --scope user cua-computer-use "{\"command\":\"$HOME/bin/cua-color-proxy\",\"args\":[\"--agent\",\"alpha\"]}"`

## Codex CLI
- Guardrail: [`adapters/codex/hooks.json`](../adapters/codex/hooks.json) → `~/.codex/hooks.json`, and
  [`adapters/codex/rainbowomma.rules`](../adapters/codex/rainbowomma.rules) → `~/.codex/rules/`.
  **Codex loads new user hooks disabled:** open `/hooks` in Codex once and trust the RainbowOMMA hook.
- Cursor, in `~/.codex/config.toml`:
  ```toml
  [mcp_servers.cua]
  command = "/Users/you/bin/cua-color-proxy"
  args = ["--agent", "alpha"]
  ```

## Gemini CLI
- Guardrail: [`adapters/gemini-cli/policies/rainbowomma.toml`](../adapters/gemini-cli/policies/rainbowomma.toml) →
  `~/.gemini/policies/` (a hard deny), and merge [`adapters/gemini-cli/settings.json`](../adapters/gemini-cli/settings.json)
  into `~/.gemini/settings.json` (the hook).
- Cursor, in `~/.gemini/settings.json`: `{"mcpServers":{"cua":{"command":"/Users/you/bin/cua-color-proxy","args":["--agent","alpha"]}}}`

## OpenCode
- Guardrail: merge [`adapters/opencode/opencode.json`](../adapters/opencode/opencode.json) into
  `~/.config/opencode/opencode.json` (the last matching rule wins, so keep the denies after `"*"`), and copy
  [`adapters/opencode/plugins/rainbowomma.js`](../adapters/opencode/plugins/rainbowomma.js) to `~/.config/opencode/plugins/`.
- Cursor: `{"mcp":{"cua":{"type":"local","command":["/Users/you/bin/cua-color-proxy","--agent","alpha"],"enabled":true}}}`

## Kilo Code
- Guardrail: merge [`adapters/kilo-code/kilo.json`](../adapters/kilo-code/kilo.json) into `~/.config/kilo/kilo.json`, and
  copy [`adapters/kilo-code/plugins/rainbowomma.js`](../adapters/kilo-code/plugins/rainbowomma.js) to `~/.config/kilo/plugins/`.
- Cursor: as for OpenCode, under `mcp` in `kilo.json`.

## Qwen Code
- Guardrail: merge [`adapters/qwen-code/settings.json`](../adapters/qwen-code/settings.json) into `~/.qwen/settings.json`.
- Cursor: `{"mcpServers":{"cua":{"command":"/Users/you/bin/cua-color-proxy","args":["--agent","alpha"]}}}` in the same file.

## Factory Droid
- Guardrail: merge [`adapters/factory-droid/settings.json`](../adapters/factory-droid/settings.json) into
  `~/.factory/settings.json` (`commandBlocklist` holds even with `--skip-permissions-unsafe`) and
  [`adapters/factory-droid/hooks.json`](../adapters/factory-droid/hooks.json) into `~/.factory/hooks.json`.
- Cursor, in `~/.factory/mcp.json`: `{"mcpServers":{"cua":{"type":"stdio","command":"/Users/you/bin/cua-color-proxy","args":["--agent","alpha"]}}}`

## Hermes Agent
- Guardrail: add [`adapters/hermes/hooks.yaml`](../adapters/hermes/hooks.yaml) and
  [`adapters/hermes/approvals-deny.yaml`](../adapters/hermes/approvals-deny.yaml) to the profile's `config.yaml`.
- Cursor: Hermes uses its built-in computer use; apply [`adapters/hermes/cua-cursor-theme.patch`](../adapters/hermes/cua-cursor-theme.patch)
  and add [`adapters/hermes/cursor-config.yaml`](../adapters/hermes/cursor-config.yaml).

## Goose
- Guardrail: copy the folder [`adapters/goose/rainbowomma/`](../adapters/goose/rainbowomma/) to `~/.agents/plugins/rainbowomma/`.
- Cursor, in `~/.config/goose/config.yaml`:
  ```yaml
  extensions:
    cua: {type: stdio, name: cua, enabled: true, cmd: /Users/you/bin/cua-color-proxy, args: ["--agent", "alpha"], timeout: 300}
  ```

## Zed agent
- Guardrail: merge [`adapters/zed/settings.json`](../adapters/zed/settings.json) into Zed's `settings.json`.
- Cursor: `{"context_servers":{"cua":{"command":"/Users/you/bin/cua-color-proxy","args":["--agent","alpha"],"env":{}}}}`

## GitHub Copilot
- Copilot CLI guardrail: [`adapters/copilot/copilot-cli.json`](../adapters/copilot/copilot-cli.json) →
  `~/.copilot/hooks/rainbowomma.json`. Note: Copilot lets a command through when a hook times out.
- VS Code agent guardrail (Preview): [`adapters/copilot/vscode.json`](../adapters/copilot/vscode.json) →
  `.github/hooks/rainbowomma.json` in the workspace (or `~/.copilot/hooks/`), with `chat.useHooks` on.
- Cursor: Copilot CLI `~/.copilot/mcp-config.json`
  `{"mcpServers":{"cua":{"type":"stdio","command":"/Users/you/bin/cua-color-proxy","args":["--agent","alpha"],"tools":["*"]}}}`;
  VS Code `.vscode/mcp.json` `{"servers":{"cua":{"command":"/Users/you/bin/cua-color-proxy","args":["--agent","alpha"]}}}`

## Cursor
- Editor guardrail: [`adapters/cursor/hooks.json`](../adapters/cursor/hooks.json) → `~/.cursor/hooks.json`.
- CLI guardrail: merge [`adapters/cursor/cli-config.json`](../adapters/cursor/cli-config.json) into
  `~/.cursor/cli-config.json` (it matches the first word only).
- Cursor (MCP), in `~/.cursor/mcp.json`: `{"mcpServers":{"cua":{"command":"/Users/you/bin/cua-color-proxy","args":["--agent","alpha"]}}}`

## Cline
- Guardrail: [`adapters/cline/PreToolUse`](../adapters/cline/PreToolUse) → `~/Documents/Cline/Hooks/PreToolUse` (VS Code,
  then turn on "Enable Hooks") or `~/.cline/hooks/PreToolUse.sh` (CLI). Cline has no deny list, and a refusal cancels
  the current task.
- Cursor, in `cline_mcp_settings.json`: `{"mcpServers":{"cua":{"command":"/Users/you/bin/cua-color-proxy","args":["--agent","alpha"],"disabled":false}}}`

## Windsurf / Devin Desktop (draft)
- Guardrail: [`adapters/windsurf/hooks.json`](../adapters/windsurf/hooks.json) → `~/.codeium/windsurf/hooks.json`.
- Cursor: `mcpServers` with `command` / `args` in `~/.codeium/windsurf/mcp_config.json`.

## Amp (draft)
- Guardrail and cursor: merge [`adapters/amp/settings.json`](../adapters/amp/settings.json) into
  `~/.config/amp/settings.json`.

## OpenClaw (draft)
- Guardrail: the plugin in [`adapters/openclaw/`](../adapters/openclaw/) (OpenClaw's exec approvals are allowlist-only,
  so a plugin is the only content-aware option). Not yet run on a real OpenClaw.
- Cursor: `openclaw mcp set cua-driver "{\"command\":\"$HOME/bin/cua-color-proxy\",\"args\":[\"--agent\",\"alpha\"]}"`

## Continue CLI
- Guardrail: [`adapters/continue/permissions.yaml`](../adapters/continue/permissions.yaml) → `~/.continue/permissions.yaml`
  (`cn --auto` ignores it). The project is archived.

## Warp, Aider
- **Warp:** its command denylist only asks for confirmation (and auto-approve skips it unless
  `auto_approve_bypasses_command_denylist = false`). The colored cursor works: `~/.warp/.mcp.json`
  `{"mcpServers":{"cua":{"command":"/Users/you/bin/cua-color-proxy","args":["--agent","alpha"]}}}`.
- **Aider:** no hooks, no deny list and no MCP; it asks before every shell command.
