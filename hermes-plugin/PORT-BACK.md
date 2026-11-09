# What the Hermes plugin changed in the shared code — to carry into the rest of the repo

Notes for carrying these changes into the stand-alone tools and the other adapters.

1. `bin/rainbowomma-guard.py`
   - `judge(event) -> (why, command)`: the decision without the hook's exit codes; `main()` now calls it. Any in-process or
     long-lived host can use it (the plugin's `guard_worker.py` is a 60-line example of a JSON-lines guard server —
     worth offering as `rainbowomma-guard --serve` for frameworks that pay for a process per tool call).
   - New refusal `doc-app`: `osascript` that quits Word / Excel / PowerPoint / Acrobat / Preview / Pages / Numbers / Keynote,
     or closes their documents or windows. Needs its rows in the adapters' test lists and in docs/DESIGN.md.
   - `RAINBOW_ENV` now also refuses `OFFICE_EXTRA_APPS=` and `OFFICE_WORD_DIR=` set by an agent.
   - One comment reworded (a scanner read "echo … | sh" in it as a real pipe).
2. `bin/agent-office.py`: `add_apps()` / `OFFICE_EXTRA_APPS` — more document apps from a setting, with fixed AppleScript
   expressions (`SUITES`). Not verified against a live app yet (TextEdit did not answer Apple Events in the test run:
   the one-time Automation consent). Verify, then document in README + `browsers.json` (`officeApps`?).
3. `bin/browser-owner.py` `THEME_FILES` now includes `Cached Theme.pak`. Chrome compiles the theme into that file inside
   the theme folder on install and paints the frame from it at every later start (the unpacked extension itself does
   not outlive the session that loaded it). `theme_clean()` saw the file as foreign, so the first "kept" start rebuilt
   the folder, the cache was gone, and the agent's second window opened without its colour and name — while
   `theme_saved()` still read the id in Preferences, so `heal` did not notice. Any install of the stand-alone tools has
   this: after the fix a start no longer rebuilds, and a profile that already lost its frame gets it back by clearing
   `theme` in its state file (or `heal` after Chrome drops the id).
4. Ideas the plugin has that the stand-alone tools don't:
   - an agent's registry row created on first use (free colour, free port, skipping another registry's ports);
   - owner hints translated to the host's tool names (`tool_defs.CLI_TO_TOOL`) — the MCP server could do the same;
   - a multiplexed host (one process, several agents): never register the process as a root; mark each shell command.
5. Tests to add to `tests/test_rainbowomma.py`: `judge()`, `doc-app` (blocked and allowed rows), `add_apps()`, `theme_clean()` with `Cached Theme.pak`.
