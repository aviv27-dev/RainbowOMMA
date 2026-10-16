// OpenClaw plugin — DRAFT, not yet run against a real OpenClaw. OpenClaw has no deny list for shell commands
// (exec approvals are allowlist-only), so a plugin's before_tool_call hook is the content-aware guard.
// The same patterns as bin/rainbowomma-guard.py. If the field holding the command is not params.command in your
// OpenClaw version, adjust `commandOf`.
const RULES: [RegExp, string][] = [
  [/(^|[\s;&|(`$])(sudo\s+)?pkill\b/i, "pkill can hit another agent's browser"],
  [/(^|[\s;&|(`$])(sudo\s+)?killall\b/i, "killall stops other agents' processes too"],
  [/\bkill\b.*(\$\(|`)\s*pgrep\b/i, "kill $(pgrep …) is pkill by another name"],
  [/\bpgrep\b.*\|\s*xargs\b.*\bkill\b/i, "pgrep | xargs kill is pkill by another name"],
  [/osascript.*quit.*google chrome|osascript.*google chrome.*quit/i, "quitting Chrome through AppleScript closes the human's windows too"],
  [/macos\/google chrome.*--remote-debugging-port/i, "an agent's Chrome is started only by browser-owner"],
]

const commandOf = (ev: any): string => String(ev?.params?.command ?? ev?.params?.cmd ?? "")

export default function register(api: any) {
  api.on("before_tool_call", (ev: any) => {
    const cmd = commandOf(ev)
    for (const [re, why] of RULES) {
      if (re.test(cmd)) return { block: true, blockReason: `Blocked by RainbowOMMA: ${why}. Use browser-owner start|recover <agent> --by <agent>.` }
    }
    return undefined
  }, { matcher: ["exec"] })
}
