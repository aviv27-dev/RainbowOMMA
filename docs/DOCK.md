# Telling agent browsers apart in the Dock

Every agent browser is a Chrome running on its own profile, so each running browser gets its own Dock icon, and every
one of them is named **"Google Chrome"**. With several agents running, or with their windows minimized, the human can't
tell from the Dock which icon is whose. The frame color and name help only while a window is visible (#77).

## What RainbowOMMA does today

**Decision (#77):** no second app bundle. A per-agent copy of Chrome is ruled out, because Keychain prompts and broken
updates are not acceptable. The running icon stays "Google Chrome", and the agents are told apart by name through the
tray, the window names, the panel and the menu bar, below.

- **"Agents" — the running agent windows by name** (the first applet in the Dock group): a click lists every agent
  browser running now by its name (`browser-owner windows`; each window also carries `--window-name=<Label>-CDP`). The
  one chosen comes to the front, un-minimized (`desk-browser.sh pick`). This is the way to find a minimized agent window
  when every running icon says "Google Chrome".
- **One applet per agent, in its color and with its name** (`install/make-dock-tray.sh`): a group in the Dock right
  after the last Chrome. A click opens that agent's browser, or brings it to the front un-minimized if it is already
  running (`desk-browser.sh open <agent>` → `browser-owner front`). This is the way to find a minimized agent window by
  name. `rainbowomma-doctor` shows whether the group is built and in the Dock.
- **The window's own name.** Each agent's Chrome runs with `--window-name=<Label>-CDP`. That name appears in the window
  list you get by right-clicking the agent's Chrome icon in the Dock, in Mission Control, and in the Window menu.
- **`rainbow-panel`** (one window listing every browser on the Mac) and the **menu-bar item** (one dot per agent in its
  color) both have "bring to front" for each agent.

## The options for naming the running icon itself

These were looked at before the decision; none has been measured. They stay here so the reasons are on record.

1. **A per-agent copy of Chrome** — *ruled out by the decision above*: an APFS clone (`cp -c`) of `Google Chrome.app` with its own `CFBundleName`,
   `CFBundleIdentifier` and a tinted icon, signed ad hoc. The Dock would show the agent's name and color.
   - *Keychain.* Chrome keeps its cookie encryption key in the login keychain as "Chrome Safe Storage". Access to that
     item is tied to Google's code signature, so a re-signed copy is expected to prompt for it, or to be unable to read
     it on an existing profile. `--password-store=basic` avoids the keychain, but it changes how cookies and saved
     passwords are stored, and an existing profile's would no longer be readable. *Measure:* start the copy on a copy
     of a signed-in profile; note any prompt and whether sites are still signed in.
   - *Updates.* Google's updater updates only the original app. Each copy stays on the version it was made from until
     it is made again. *Measure:* the version of the copy a week later.
   - *Disk.* A clone costs almost nothing until either side changes; after an update of the original, every copy is a
     full Chrome (about 1.5 GB). *Measure:* `du` before and after an update.
   - *Gatekeeper.* A locally made, ad-hoc-signed copy without the quarantine flag should open; one that came from
     elsewhere would not. *Measure:* `spctl --assess` on the copy, then the first launch.
2. **Chrome for Testing (or Chromium) for the agents** (`--agent-chrome cft`): a separate bundle and no Google
   auto-update. It separates the agents from the human's Chrome, but all agents still share one name ("Google Chrome
   for Testing"), so it doesn't tell one agent from another. It only helps combined with option 1.
3. **Setting another app's Dock tile at runtime** (`NSDockTile` label or badge): a Dock tile belongs to the app that
   owns it, and only that app can change its icon or badge. A helper process can't change Chrome's. Expected not to
   work. *Measure:* a 20-line Swift helper that tries, to confirm.
4. **No second bundle: the agents by name in the tray** — the "Agents" applet, the per-agent applets, the window names,
   the panel and the menu bar, as above. **Chosen.** `install/make-dock-tray.sh` builds it, `rainbowomma-doctor` shows
   whether it is built and in the Dock, and the human's own Chrome is never touched.
