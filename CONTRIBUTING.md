# Contributing to RainbowOMMA

Thanks for helping! RainbowOMMA runs next to a person's real work, so the bar is "never surprise the human".

## Before you open a pull request

1. **Run the tests:** `python3 tests/test_rainbowomma.py`. They use a fake process table, a fake `osascript` and a fake
   Chrome, and never start a real browser or app. Keep it that way.
2. **Every behavior change gets a test** in `tests/test_rainbowomma.py`, built from fakes.
3. **Keep the API stable.** JSON status words (`started`, `refused`, `blocked`, …), JSON keys and exit codes are parsed
   by agents in the wild. Don't rename them; add new ones instead, and note them in `CHANGELOG.md`.
4. **Text people read goes in the catalog.** Put every user-facing message in `bin/rainbow_i18n.py`, in every language.
5. **When in doubt, do nothing.** A new code path that kills, quits or closes something must re-check right before it
   acts, and must refuse when it can't tell.
6. **Examples use placeholders.** Agents are `alpha`, `bravo`, `charlie`; the person is `human`. No real names, paths,
   hostnames or site URLs.
7. Check shell syntax with `bash -n` on any script you touch.

## Reporting a bug

Open an issue with your macOS and Chrome versions, the command you ran, and the JSON answer it printed. Logs are in
`~/.rainbowomma/logs/` (or under `$RAINBOW_HOME`). Remove anything private before you paste them.

## Adding support for an agent framework

A guardrail adapter goes in `adapters/<framework>/` with a short README, and gets a test that feeds it the blocked and
allowed commands the existing adapters are tested with.

## Releasing

1. Move the `[Unreleased]` notes in `CHANGELOG.md` under `## [X.Y.Z] — date`, add its link at the bottom, and bump the
   plugin versions in `adapters/` (openclaw, goose); merge that.
2. Actions → **release** → Run workflow on `main` with the version. It tests, then tags and publishes the release
   with that section as its notes.
3. Homebrew: point `Formula/rainbowomma.rb` at the new tag and its checksum —
   `curl -sL https://github.com/aviv27-dev/RainbowOMMA/archive/refs/tags/vX.Y.Z.tar.gz | shasum -a 256` — and merge.
