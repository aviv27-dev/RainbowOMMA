// OpenCode / Kilo Code plugin (~/.config/opencode/plugins/rainbowomma.js): the same patterns as rainbowomma-guard,
// applied before every bash tool call. Throwing refuses the call and tells the agent why.
const RULES = [
  [/(^|[\s;&|(`$])(sudo\s+)?pkill\b/i, "pkill can hit another agent's browser"],
  [/(^|[\s;&|(`$])(sudo\s+)?killall\b/i, "killall stops other agents' processes too"],
  [/\bkill\b.*(\$\(|`)\s*pgrep\b/i, "kill $(pgrep …) is pkill by another name"],
  [/\bpgrep\b.*\|\s*xargs\b.*\bkill\b/i, "pgrep | xargs kill is pkill by another name"],
  [/osascript.*quit.*google chrome|osascript.*google chrome.*quit/i, "quitting Chrome through AppleScript closes the human's windows too"],
  [/macos\/google chrome.*--remote-debugging-port/i, "an agent's Chrome is started only by browser-owner"],
]

export const RainbowOMMA = async () => ({
  "tool.execute.before": async (input, output) => {
    if (input.tool !== "bash") return
    const cmd = String(output?.args?.command ?? "")
    for (const [re, why] of RULES) {
      if (re.test(cmd)) throw new Error(`Blocked by RainbowOMMA: ${why}. Use browser-owner start|recover <agent> --by <agent>.`)
    }
  },
})
