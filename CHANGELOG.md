# Changelog

All notable changes to RainbowOMMA. Versions follow [Semantic Versioning](https://semver.org/); JSON status words and
exit codes are an API and change only in a major version.

## [Unreleased]

### Added
- `cua-color-proxy`: an MCP proxy in front of `cua-driver mcp` that gives every session of any MCP agent (Claude Code,
  OpenClaw, OpenCode, Codex CLI, Cursor, …) that agent's colored cursor, with no change to the agent.

## [0.1.0] — 2026-10-14

First public release.

### Added
- `browser-owner`: one owner per agent Chrome (its CDP port + profile), with one lock per agent, human-only stop,
  ⌘Q detection, a careful `recover`, focus given back to the human, and a real Chrome theme in each agent's color.
- `office-owner` (= `agent-office`): per-document leases in Word / Excel / Acrobat / Preview, Word → PDF through the real
  Word, and an idle quit only for apps it launched itself.
- Colored CUA cursor per agent for Cua Driver computer use, with Hermes Agent adapters.
- **English and Hebrew** user interface: one message catalog (`bin/rainbow_i18n.py`), chosen by `RAINBOW_LANG`, the Mac's
  preferred language, or the locale. In English (LTR) the agent's name is drawn along the right part of the frame.
- `install.sh`: installs the tools, creates `browsers.json` from the example without ever overwriting yours, and with
  `--with-sweep` loads the launchd sweep with absolute paths.
- `RAINBOW_HOME`: one configurable root for logs, state and themes (default `~/.rainbowomma`).
- Claude Code guard (`adapters/claude-code/`): a PreToolUse hook that blocks pkill / killall / AppleScript-quit of Chrome /
  Chrome on a debug port, plus a settings example.
- Desktop open/close icons, the human's Chrome theme, and `kill-chrome.sh` that spares every agent browser.
- Tests on macOS in CI (fakes only — never a real browser or app).

[0.1.0]: https://github.com/aviv27-dev/RainbowOMMA/releases/tag/v0.1.0
