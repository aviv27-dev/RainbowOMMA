# Filing a bug or a feature request — `rainbowomma-report`

A shared Mac is full of things that say whose Mac it is: the user name, the agents' names, client and project names in
paths, a tailnet's addresses. A bug report written in a hurry carries them all. `rainbowomma-report` sits between the text
and GitHub: it scans the title and the body first, and sends nothing while anything is found.

## Use

```
gh auth login                                   # once
rainbowomma-report scan draft.md                # only the scan: every finding, nothing sent
rainbowomma-report feature --title "…" --body-file draft.md --dry-run
rainbowomma-report feature --title "…" --body-file draft.md
rainbowomma-report bug --title "…" --body-file bug.md
```

Exit codes: `0` sent (or a clean scan / dry run) · `2` refused — a finding, or the template's headings missing · `1` failure
(no `gh`, `gh` refused, an unreadable file). One JSON answer, always: `{"status": "sent" | "would-send" | "refused" | "clean" |
"findings" | "failed", …}`.

## What it checks

1. **The template.** The body must carry the issue template's bold headings, in order — `bug` follows
   `.github/ISSUE_TEMPLATE/bug_report.md`, `feature` follows `feature_request.md` (a test keeps the two lists equal). The
   template's label is set (`bug`, `enhancement`). `gh issue create --template` can't be combined with a body, so the helper
   checks the template itself and passes `--label`.
2. **The privacy scan**, on the title and every line of the body:
   - built in: e-mail addresses (GitHub and Anthropic noreply addresses are fine), home paths (`/Users/<name>`,
     `/home/<name>`; `/Users/you` is fine), private and Tailscale (CGNAT, 100.64/10) addresses, `*.ts.net` names, API keys and
     tokens (`sk-`, `ghp_`, `github_pat_`, `xox…`, `AKIA…`), phone numbers;
   - from this Mac: `$USER`, the computer's name, and every agent name and label in `browsers.json` (the placeholders
     `alpha`, `bravo`, `charlie`, `human` are fine);
   - yours: `$RAINBOW_HOME/report-deny.txt` — one regular expression per line, case-insensitive, `#` for comments; a line
     that isn't a valid expression is matched as plain text. Put client names, project names, case numbers, your domains
     there. This file is yours only: it never goes into the repository and nothing reads it but this helper.

A finding is reported as `body:12: home path` — where, and what kind — never the matched text, so the refusal itself can be
pasted anywhere. Fix the text and run it again; the body is sent exactly as written, never rewritten.

## What it does not do

- It does not redact. A redacted report reads like a puzzle; rewrite the line with the placeholders instead
  (`alpha` / `bravo` / `charlie` / `human`, `~/agents/alpha-profile`, `bank.example`).
- It does not attach logs. Copy only the lines that matter into the body (the scan reads them like the rest).
- It can't know every private word. The scan is a net, not a guarantee: read the body once before sending.
