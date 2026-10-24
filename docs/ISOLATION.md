# Isolation, credentials and the screen: beyond one shared Mac

RainbowOMMA keeps several agents and a human civil on **one** macOS session. Some work needs a harder wall. This page
says when to move an agent behind one, which wall to pick, and how RainbowOMMA fits on each side of it.

## Pick a tier

| Tier | What the agent shares with you | Good for | How |
|---|---|---|---|
| **Shared session** (RainbowOMMA's default) | the screen, the clipboard, your user's files and Keychain | everyday agents you trust with your files | `install.sh`; one row per agent in `browsers.json` |
| **Its own macOS user** | the machine only: its own home folder, Keychain, TCC grants, Chrome profiles | an agent that handles another account's logins, or files you don't want it to see | below |
| **A macOS VM** (Lume, Tart, UTM) | nothing but the network | untrusted or experimental agents, anything that installs software | below |
| **A Linux container** (Apple `container`, Docker) | the folder you mount | coding agents' shell commands and builds, with no GUI | below |

macOS lets one Mac run at most **two** macOS VMs at a time, so a VM per agent doesn't scale. That limit is why a shared
session stays the normal case, and why the tiers mix well: one risky agent in a VM, the rest on the shared Mac.

### Its own macOS user
- **The quick way:** `install/isolate-agent.sh create alpha` prints what it would do; add `--apply` to do it: a hidden
  standard user `rainbow-alpha` (no password anyone keeps), a sudoers rule that lets only you run commands as it
  (`/etc/sudoers.d/rainbowomma-alpha`, checked with `visudo`), a work folder you and it share
  (`/Users/Shared/rainbowomma/alpha`, nobody else), and RainbowOMMA in its home. Then
  `install/isolate-agent.sh run alpha -- claude` runs the agent as that user; `status` lists them; `remove alpha --apply`
  takes the user and the rule out and keeps the work folder. Its browser runs headless there (another user can't open
  windows on your screen) — keep computer use with agents of your own user.
- Create a standard user per agent (System Settings → Users & Groups), log it in with Fast User Switching, and run the
  agent there. GUI computer use works only in the session that is on screen; shell and browser (CDP) work in the
  background.
- Install RainbowOMMA in each user. Give each agent a distinct CDP port and port range across users (`browsers.json`
  `port` and `ports`), since ports are machine-wide; `port-owner` in one user can't see another user's leases.
- Grant TCC permissions (Accessibility, Automation) per user. On a managed Mac, a PPPC profile can pre-grant
  Accessibility and Automation; Screen Recording can't be pre-granted.

### A macOS VM
- [Lume](https://github.com/trycua/cua) (Cua's VM manager, which pairs with Cua Driver), [Tart](https://tart.run) or UTM.
  Install RainbowOMMA inside the VM like on any Mac; the agent's colors and owners work there unchanged.
- From the host, the VM is one window: keep it on its own Space, or give it a virtual display (below).

### A Linux container for code
- Apple's [`container`](https://github.com/apple/container) runs each Linux container in its own lightweight VM.
  `container-use` / dev containers give each coding agent a worktree and a container.
- On the host, `port-owner` still hands out the ports you publish (`docker -p` / `container run -p` are checked by the
  guardrail), and `proc-owner` still knows whose container process is whose through `RAINBOW_AGENT`.

## A display of its own (virtual displays)
A virtual display gives an agent's windows a screen you don't look at, so they never cover your work.
[BetterDisplay](https://github.com/waydabber/BetterDisplay) and [DeskPad](https://github.com/Stengo/DeskPad) create one
with a click; move the agent's browser there once and macOS keeps it there. RainbowOMMA doesn't create them itself: the
API is private and changes between macOS versions.

## Credentials
- **Never your profile.** `browsers.json` refuses a personal Chrome profile as an agent's; each agent logs in inside its
  own profile.
- **Password managers.** 1Password's agentic autofill fills a login into the agent's browser without the model ever
  seeing the password, and asks you to approve each fill. Install the extension in the agent's Chrome profile, not
  yours. For API keys, a 1Password service account per agent with only that agent's vault keeps the blast radius small.
- **Keychain.** Store an agent's own tokens as Keychain items named for it (`security add-generic-password -s
  rainbowomma-alpha-<service> …`), and read them in its launcher. Separate macOS users give each agent its own Keychain.
- **Sensitive sites.** List banks and government portals in `sensitiveSites`: an agent goes there only while you're at
  the Mac.

## Standards to watch
- **WebMCP** (a W3C draft): sites expose tools to agents directly. RainbowOMMA would relay them from each agent's own
  browser.
- **MCP authorization and elicitation**: `rainbowomma-mcp` already asks the human through its own dialogs; MCP
  elicitation would let the client ask instead.
- **A2A agent cards** and the IETF agent-identity drafts: a standard way to name an agent and its owner, which could
  replace the `RAINBOW_AGENT` convention.
- **OpenTelemetry GenAI semantic conventions**: `receipts --export-otlp` already tags receipts with
  `gen_ai.agent.name`; the conventions are still in development.
