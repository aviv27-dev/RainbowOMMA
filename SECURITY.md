# Security policy

RainbowOMMA stops and starts browser processes, edits Chrome profile files of the agents' own profiles, and closes
documents in shared apps. A mistake here can cost someone unsaved work or a logged-in session, so we treat such bugs as
security issues.

## What RainbowOMMA never does for an agent

Only the human's own commands (such as `kill-chrome.sh` or `stop --by human`) close the human's Chrome or an agent's
browser for good. On an agent's behalf, RainbowOMMA never does any of these:

- touch the human's own Chrome profile, or any profile not listed in `browsers.json`;
- quit an app the human launched, or close a document the agent didn't open or that has unsaved changes;
- open a Chrome debugging port to any origin other than the agent's own `127.0.0.1` / `localhost` port;
- kill a process without re-checking it is still the agent's browser right before the signal.

If you find a way to make it do any of these, that is a security issue.

## Reporting

Please report privately through GitHub's **Report a vulnerability** button on the repository's Security tab, not in a
public issue. Include the steps, your macOS and Chrome versions, and what was affected.

## Supported versions

Fixes go into the latest release only.
