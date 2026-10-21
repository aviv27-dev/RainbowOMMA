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

## What the guard can and can't stop

Every agent on one Mac runs as the same macOS user. The guard (the pre-tool hook) reads each command and tool call
before it runs and closes the cheap ways around RainbowOMMA: killing by pattern or process group, acting as another agent
or as the human (`--by`, an owner tool's agent argument, `as-agent`, `RAINBOW_AGENT`), changing RainbowOMMA's own state
or `browsers.json`, reading the human's Chrome profile, reaching another agent's DevTools port, sending without the
human's approval. When it can't judge a command, it refuses.

It is not a sandbox. A program that runs as you can, with enough effort, do anything you can — the guard only sees what
goes through the agent's tool calls. For a hard boundary, give each agent its own macOS user or a VM
([docs/ISOLATION.md](docs/ISOLATION.md)). A way around the guard that is cheap to use is still a bug we want to hear about.

## Reporting

Please report privately through GitHub's **Report a vulnerability** button on the repository's Security tab, not in a
public issue. Include the steps, your macOS and Chrome versions, and what was affected.

## Supported versions

Fixes go into the latest release only.
