#!/bin/bash
# RainbowOMMA installer — copies the tools into one folder, creates the registry from the example (never overwrites yours),
# creates the state folders, and optionally loads the launchd sweep for office-owner with absolute paths.
#
#   ./install.sh [--bin DIR] [--with-sweep] [--with-heal] [--with-menubar] [--adapter AGENT …] [--dry-run]
#
#   --bin DIR      where the tools go (default: ~/bin). They look for each other in the same folder.
#   --with-sweep   install + load the launchd job that sweeps stale document leases every 15 minutes
#   --with-heal    install + load the launchd job that puts back agent colors Chrome Sync took (every 30 min, at login)
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
MENUBAR=0
ADAPTERS=""
DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --bin) BIN="${2:?--bin needs a folder}"; shift 2 ;;
    --with-sweep) SWEEP=1; shift ;;
    --with-heal) HEAL=1; shift ;;
    --with-menubar) MENUBAR=1; shift ;;
    --adapter) ADAPTERS="$ADAPTERS ${2:?--adapter needs an agent framework, e.g. claude-code}"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    -h|--help) sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (see --help)" >&2; exit 2 ;;
  esac
done
case "$BIN" in /*) ;; *) BIN="$(pwd)/$BIN" ;; esac
ROOT="${RAINBOW_HOME:-$HOME/.rainbowomma}"
AGENTS_DIR="${RAINBOW_LAUNCH_AGENTS:-$HOME/Library/LaunchAgents}"   # overridable for tests
LABEL="com.rainbowomma.agent-office-sweep"

if [ "$(uname -s)" != "Darwin" ] && [ "${RAINBOW_INSTALL_ANY_OS:-0}" != "1" ]; then
  echo "RainbowOMMA runs on macOS (it drives Chrome, Word and the Dock through osascript)." >&2
  exit 1
fi
command -v python3 >/dev/null 2>&1 || { echo "python3 is needed (macOS: xcode-select --install)" >&2; exit 1; }

run() { if [ "$DRY" = 1 ]; then echo "would: $*"; else "$@"; fi; }

echo "→ tools into $BIN"
run mkdir -p "$BIN"
for f in "$HERE"/bin/*; do
  name="$(basename "$f")"
  case "$name" in
    browsers.json|__pycache__) continue ;;
  esac
  run cp -p "$f" "$BIN/$name"
done

if [ -e "$BIN/browsers.json" ]; then
  echo "→ $BIN/browsers.json exists — kept as it is"
else
  echo "→ $BIN/browsers.json created from the example — edit it: one row per agent"
  run cp "$HERE/examples/browsers.example.json" "$BIN/browsers.json"
fi

echo "→ state in $ROOT"
run mkdir -p "$ROOT/logs" "$ROOT/state" "$ROOT/word-convert"

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

if [ "$MENUBAR" = 1 ]; then
  PLUGINS="$(defaults read com.ameba.SwiftBar PluginDirectory 2>/dev/null || true)"
  [ -n "$PLUGINS" ] || PLUGINS="$ROOT/swiftbar"
  echo "→ menu-bar item $PLUGINS/rainbowomma.10s.sh (SwiftBar runs it every 10 s)"
  if [ "$DRY" = 1 ]; then echo "would: write it"; else
    mkdir -p "$PLUGINS"
    printf '#!/bin/bash\n# <swiftbar.title>RainbowOMMA</swiftbar.title>\n# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>\nexec %q\n' \
      "$BIN/rainbowomma-menubar" > "$PLUGINS/rainbowomma.10s.sh"
    chmod +x "$PLUGINS/rainbowomma.10s.sh"
    if [ "$PLUGINS" = "$ROOT/swiftbar" ]; then
      echo "   install SwiftBar (brew install --cask swiftbar) and choose $PLUGINS as its plugin folder"
    fi
  fi
fi

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
