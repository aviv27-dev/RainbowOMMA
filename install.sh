#!/bin/bash
# RainbowOMMA installer — copies the tools into one folder, creates the registry from the example (never overwrites yours),
# creates the state folders, and optionally loads the launchd sweep for office-owner with absolute paths.
#
#   ./install.sh [--bin DIR] [--agent-chrome CHANNEL] [--with-sweep] [--with-heal] [--with-tab-sweep] [--with-menubar] [--adapter AGENT …] [--dry-run]
#
#   --bin DIR      where the tools go (default: ~/bin). They look for each other in the same folder.
#   --agent-chrome C  the agents' browsers run as a Chrome of their own: beta, dev, canary or cft (Chrome for Testing) —
#                  the human's ⌘Q, ⌘-Tab and Chrome updates then never reach them (a new browsers.json only)
#   --with-sweep   install + load the launchd job that sweeps stale document leases every 15 minutes
#   --with-heal    install + load the launchd job that puts back agent colors Chrome Sync took (every 30 min, at login)
#   --with-tab-sweep  the job that finds agent tabs burning CPU for long (every 15 min) — a dry run until browsers.json
#                  says "tabSweep": {"mode": "apply"} (then it reloads them, and closes those that stay hot)
#   --with-menubar the menu-bar item for SwiftBar (agents as colored dots, pause all agents with ⌘⌥⌃P)
#   --adapter A    write agent framework A's adapter, with your paths filled in, to $RAINBOW_HOME/adapters/A (see docs/AGENTS.md)
#   --dry-run      print what would happen, change nothing
#
# RAINBOW_HOME (default ~/.rainbowomma) is where logs, state and themes live; the jobs are given the same value.
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
BIN="$HOME/bin"
SWEEP=0
HEAL=0
CHANNEL=""
TABS=0
MENUBAR=0
ADAPTERS=""
DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --bin) BIN="${2:?--bin needs a folder}"; shift 2 ;;
    --with-sweep) SWEEP=1; shift ;;
    --with-heal) HEAL=1; shift ;;
    --agent-chrome) CHANNEL="${2:?--agent-chrome needs beta, dev, canary or cft}"; shift 2 ;;
    --with-tab-sweep) TABS=1; shift ;;
    --with-menubar) MENUBAR=1; shift ;;
    --adapter) ADAPTERS="$ADAPTERS ${2:?--adapter needs an agent framework, e.g. claude-code}"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    -h|--help) sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (see --help)" >&2; exit 2 ;;
  esac
done
case "$BIN" in /*) ;; *) BIN="$(pwd)/$BIN" ;; esac
[ -z "$ADAPTERS" ] || case "$BIN$HOME" in *[\\\"\|\&]*|*$'\n'*) echo "a folder with \\, \", |, & or a newline in its name can't go into the adapters' settings: $BIN" >&2; exit 2 ;; esac
case "$CHANNEL" in ""|beta|dev|canary|cft) ;; *) echo "--agent-chrome is beta, dev, canary or cft, not $CHANNEL" >&2; exit 2 ;; esac
set -f
for A in $ADAPTERS; do
  case "$A" in ''|*[!a-z0-9-]*) echo "not an adapter name: $A (letters, digits and - only)" >&2; exit 2 ;; esac
done
set +f
ROOT="${RAINBOW_HOME:-$HOME/.rainbowomma}"
AGENTS_DIR="${RAINBOW_LAUNCH_AGENTS:-$HOME/Library/LaunchAgents}"   # overridable for tests
LABEL="com.rainbowomma.agent-office-sweep"

if [ "$(uname -s)" != "Darwin" ] && [ "${RAINBOW_INSTALL_ANY_OS:-0}" != "1" ]; then
  echo "RainbowOMMA runs on macOS (it drives Chrome, Word and the Dock through osascript)." >&2
  exit 1
fi
command -v python3 >/dev/null 2>&1 || { echo "python3 is needed (macOS: xcode-select --install)" >&2; exit 1; }

run() { if [ "$DRY" = 1 ]; then echo "would: $*"; else "$@"; fi; }
sum() { if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | cut -d' ' -f1; else sha256sum "$1" | cut -d' ' -f1; fi; }
MANIFEST="$ROOT/installed.txt"      # "<sha256>  <path>" for every file this installer put in place — uninstall.sh reads it
BACKUPS="$ROOT/backups.txt"         # "<path>\t<backup>" for a file of yours it replaced — uninstall.sh puts it back
BACKUP_DIR="$ROOT/backup/$(date +%Y%m%d-%H%M%S)"
NEW_ENTRIES="$(mktemp)"; trap 'rm -f "$NEW_ENTRIES"' EXIT
ours() { [ -f "$MANIFEST" ] && cut -d' ' -f3- "$MANIFEST" | grep -qxF "$1"; }     # a path this installer wrote before
place() {   # place SRC DEST — a file of yours already at DEST (not one this installer put there) is saved first
  local src="$1" dest="$2"
  if [ "$DRY" = 1 ]; then echo "would: cp -p $src $dest"; return; fi
  if [ -e "$dest" ] && ! cmp -s "$src" "$dest" && ! ours "$dest"; then
    mkdir -p "$BACKUP_DIR" && cp -p "$dest" "$BACKUP_DIR/$(basename "$dest")"
    printf '%s\t%s\n' "$dest" "$BACKUP_DIR/$(basename "$dest")" >> "$BACKUPS"
    echo "   your own $(basename "$dest") was there — saved in $BACKUP_DIR (uninstall.sh puts it back)"
  fi
  cp -p "$src" "$dest"
  printf '%s  %s\n' "$(sum "$dest")" "$dest" >> "$NEW_ENTRIES"
}

echo "→ tools into $BIN"
run mkdir -p "$BIN"
[ "$DRY" = 1 ] || mkdir -p "$ROOT"
for f in "$HERE"/bin/*; do
  name="$(basename "$f")"
  case "$name" in
    browsers.json|__pycache__) continue ;;
  esac
  place "$f" "$BIN/$name"
done

if [ -e "$BIN/browsers.json" ]; then
  echo "→ $BIN/browsers.json exists — kept as it is"
  [ -z "$CHANNEL" ] || echo "   --agent-chrome: add \"chrome\": \"$CHANNEL\" to each agent in it yourself (an existing registry is never rewritten)"
else
  echo "→ $BIN/browsers.json created from the example — edit it: one row per agent"
  run cp "$HERE/examples/browsers.example.json" "$BIN/browsers.json"
  if [ -n "$CHANNEL" ] && [ "$DRY" != 1 ]; then
    python3 -I - "$BIN/browsers.json" "$CHANNEL" <<'PY'
import json, sys
path, channel = sys.argv[1:]
d = json.load(open(path, encoding="utf-8"))
for row in d["agents"].values():
    row["chrome"] = channel
open(path, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False, indent=1) + "\n")
PY
    echo "   every agent's browser runs as Chrome $CHANNEL"
  fi
fi
if [ -n "$CHANNEL" ]; then
  case "$CHANNEL" in beta) APP="Google Chrome Beta" ;; dev) APP="Google Chrome Dev" ;; canary) APP="Google Chrome Canary" ;;
    cft) APP="Google Chrome for Testing" ;; esac
  if [ ! -d "/Applications/$APP.app" ]; then
    if [ "$CHANNEL" = cft ]; then HOW="npx @puppeteer/browsers install chrome@stable, then move it to /Applications"
    else HOW="google.com/chrome, or: brew install --cask google-chrome@$CHANNEL"; fi
    echo "   note: /Applications/$APP.app isn't installed yet — $HOW"
  fi
fi

echo "→ state in $ROOT"
run mkdir -p "$ROOT/logs" "$ROOT/state" "$ROOT/word-convert"
run chmod 700 "$ROOT"     # receipts, approvals and document copies: readable by you only

job() {   # job <label> <what> — write the launchd job from install/<label>.plist with absolute paths, and load it
  local label="$1" what="$2" plist="$AGENTS_DIR/$1.plist"
  echo "→ $what job $plist (absolute paths — launchd does not expand ~)"
  if [ "$DRY" = 1 ]; then echo "would: write $plist and load it"; return; fi
  mkdir -p "$AGENTS_DIR"
  python3 -I - "$HERE/install/$label.plist" "$plist" "$BIN" "$ROOT" "$HOME" <<'PY'
import sys, xml.sax.saxutils as x
tpl, out, bin_dir, root, home = sys.argv[1:]
s = open(tpl, encoding="utf-8").read()
s = s.replace("~/bin/", x.escape(bin_dir + "/"))
s = s.replace("~/.rainbowomma", x.escape(root))
if root != home + "/.rainbowomma":
    s = s.replace("<key>LC_ALL</key><string>en_US.UTF-8</string>",
                  "<key>LC_ALL</key><string>en_US.UTF-8</string><key>RAINBOW_HOME</key><string>" + x.escape(root) + "</string>")
if "~" in s:
    sys.exit("a ~ path is left in the job")
open(out, "w", encoding="utf-8").write(s)
PY
  if [ "${RAINBOW_INSTALL_NO_LAUNCHCTL:-0}" != "1" ]; then
    command -v plutil >/dev/null 2>&1 && plutil -lint "$plist" >/dev/null
    launchctl bootout "gui/$(id -u)/$label" >/dev/null 2>&1 || true
    launchctl bootstrap "gui/$(id -u)" "$plist"
  fi
}
[ "$SWEEP" = 1 ] && job "$LABEL" sweep
[ "$HEAL" = 1 ] && job com.rainbowomma.heal heal
[ "$TABS" = 1 ] && job com.rainbowomma.tabs tab-sweep

if [ "$MENUBAR" = 1 ]; then
  PLUGINS="$(defaults read com.ameba.SwiftBar PluginDirectory 2>/dev/null || true)"
  [ -n "$PLUGINS" ] || PLUGINS="$ROOT/swiftbar"
  echo "→ menu-bar item $PLUGINS/rainbowomma.10s.sh (SwiftBar runs it every 10 s)"
  if [ "$DRY" = 1 ]; then echo "would: write it"; else
    mkdir -p "$PLUGINS"
    printf '#!/bin/bash\n# <swiftbar.title>RainbowOMMA</swiftbar.title>\n# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>\nexec %q\n' \
      "$BIN/rainbowomma-menubar" > "$PLUGINS/rainbowomma.10s.sh"
    chmod +x "$PLUGINS/rainbowomma.10s.sh"
    printf '%s  %s\n' "$(sum "$PLUGINS/rainbowomma.10s.sh")" "$PLUGINS/rainbowomma.10s.sh" >> "$NEW_ENTRIES"
    if [ "$PLUGINS" = "$ROOT/swiftbar" ]; then
      echo "   install SwiftBar (brew install --cask swiftbar) and choose $PLUGINS as its plugin folder"
    fi
  fi
fi

set -f   # the names were checked above; no globbing of them
for A in $ADAPTERS; do
  SRC="$HERE/adapters/$A"
  if [ ! -d "$SRC" ]; then
    echo "no adapter called $A — there are: $(ls "$HERE/adapters" | tr '\n' ' ')" >&2; exit 2
  fi
  DEST="$ROOT/adapters/$A"
  echo "→ adapter $A in $DEST (your paths filled in) — merge it into $A's settings as docs/AGENTS.md says"
  [ "$DRY" = 1 ] && { echo "would: copy $SRC with /Users/you → $HOME"; continue; }
  mkdir -p "$DEST"
  ( cd "$SRC" && find . -type f ) | while IFS= read -r f; do
    mkdir -p "$DEST/$(dirname "$f")"
    sed -e "s|/Users/you/bin|$BIN|g" -e "s|/Users/you|$HOME|g" "$SRC/$f" > "$DEST/$f"
    if [ -x "$SRC/$f" ]; then chmod +x "$DEST/$f"; fi
  done
done
set +f

if [ "$DRY" != 1 ]; then          # the manifest: what is in it now, newest first for a path written again
  { [ -f "$MANIFEST" ] && cat "$MANIFEST"; cat "$NEW_ENTRIES"; } | awk '{ path = substr($0, index($0, "  ") + 2); last[path] = $0; order[path] = NR }
    END { for (p in last) print order[p] "\t" last[p] }' | sort -n | cut -f2- > "$MANIFEST.tmp" && mv "$MANIFEST.tmp" "$MANIFEST"
fi

case ":$PATH:" in *":$BIN:"*) ;; *) echo "note: $BIN is not on your PATH — call the tools by their full path, or add it." ;; esac
cat <<EOF

Done. Next:
  \$EDITOR $BIN/browsers.json                  # port, profile, color, label per agent
  $BIN/browser-owner start alpha --by alpha     # paints and opens Alpha's browser
  $BIN/browser-owner list
  $HERE/install/make-desktop-apps.sh             # optional: colored open/close icons on the desktop
Language: English or Hebrew from your Mac's settings; force one with RAINBOW_LANG=en or RAINBOW_LANG=he.
The first Word → PDF conversion (office-owner pdf) shows a Word permission prompt once — allow it.
EOF
