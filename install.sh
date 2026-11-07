#!/bin/bash
# RainbowOMMA installer — copies the tools into one folder, creates the registry from the example (never overwrites yours),
# creates the state folders, and optionally loads the launchd sweep for office-owner with absolute paths.
#
#   ./install.sh [--bin DIR] [--agent-chrome CHANNEL] [--with-sweep] [--with-heal] [--with-tab-sweep] [--with-menubar] [--adapter AGENT …] [--migrate-from DIR] [--dry-run]
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
#   --migrate-from DIR  carry a pre-release install's state (DIR, e.g. its old state folder) into $RAINBOW_HOME:
#                  copied, never moved or overwritten; a legacy stop flag becomes offByHuman (stopped stays stopped).
#                  With --dry-run it only reports — run that first
#   --dry-run      print what would happen, change nothing
#
# RAINBOW_HOME (default ~/.rainbowomma) is where logs, state and themes live; the jobs are given the same value.
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
BIN="$HOME/bin"
SWEEP=0
HEAL=0
CHANNEL=""
MIGRATE=""
TABS=0
MENUBAR=0
ADAPTERS=""
DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --bin) BIN="${2:?--bin needs a folder}"; shift 2 ;;
    --with-sweep) SWEEP=1; shift ;;
    --with-heal) HEAL=1; shift ;;
    --migrate-from) MIGRATE="${2:?--migrate-from needs the folder of the old install}"; shift 2 ;;
    --agent-chrome) CHANNEL="${2:?--agent-chrome needs beta, dev, canary or cft}"; shift 2 ;;
    --with-tab-sweep) TABS=1; shift ;;
    --with-menubar) MENUBAR=1; shift ;;
    --adapter) ADAPTERS="$ADAPTERS ${2:?--adapter needs an agent framework, e.g. claude-code}"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    -h|--help) sed -n '2,21p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (see --help)" >&2; exit 2 ;;
  esac
done
case "$BIN" in /*) ;; *) BIN="$(pwd)/$BIN" ;; esac
[ -z "$ADAPTERS" ] || case "$BIN$HOME" in *[\\\"\|\&]*|*$'\n'*) echo "a folder with \\, \", |, & or a newline in its name can't go into the adapters' settings: $BIN" >&2; exit 2 ;; esac
case "$CHANNEL" in ""|beta|dev|canary|cft) ;; *) echo "--agent-chrome is beta, dev, canary or cft, not $CHANNEL" >&2; exit 2 ;; esac
set -f
for A in $ADAPTERS; do
  case "$A" in ''|*[!abcdefghijklmnopqrstuvwxyz0123456789-]*) echo "not an adapter name: $A (letters, digits and - only)" >&2; exit 2 ;; esac
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

# numbered steps, each with one result word: [3/7] state in ~/.rainbowomma — done
TOTAL=4                                             # tools, the registry, the state folder, the version
[ -z "$MIGRATE" ] || TOTAL=$((TOTAL + 1))
TOTAL=$((TOTAL + SWEEP + HEAL + TABS + MENUBAR))
[ -z "$ADAPTERS" ] || TOTAL=$((TOTAL + 1))
N=0; STEP="starting"; NOTES=""
begin() { N=$((N + 1)); STEP="$1"; NOTES=""; }
note() { NOTES="${NOTES}      $*"$'\n'; }
end() {   # end WORD [DETAIL] — WORD is done, kept or would
  printf '[%d/%d] %s — %s%s\n' "$N" "$TOTAL" "$STEP" "$1" "${2:+ ($2)}"
  [ -z "$NOTES" ] || printf '%s' "$NOTES"
}
REPORTED=0
WORD="done"; [ "$DRY" = 1 ] && WORD="would"
run() { if [ "$DRY" = 1 ]; then return 0; else "$@"; fi; }   # a dry run changes nothing; the summary says what it would do
sum() { if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | cut -d' ' -f1; else sha256sum "$1" | cut -d' ' -f1; fi; }
MANIFEST="$ROOT/installed.txt"      # "<sha256>  <path>" for every file this installer put in place — uninstall.sh reads it
BACKUPS="$ROOT/backups.txt"         # "<path>\t<backup>" for a file of yours it replaced — uninstall.sh puts it back
BACKUP_DIR="$ROOT/backup/$(date +%Y%m%d-%H%M%S)"
finish() {   # on the way out: the temp file goes; a failure names the step it stopped at (once)
  local rc=$?
  rm -f "$NEW_ENTRIES"
  if [ "$rc" != 0 ] && [ "$N" -gt 0 ] && [ "$REPORTED" = 0 ]; then
    echo "✗ install.sh failed at step [$N/$TOTAL] $STEP — the steps after it did not run" >&2
  fi
}
NEW_ENTRIES="$(mktemp)"; trap finish EXIT
ours() { [ -f "$MANIFEST" ] && cut -d' ' -f3- "$MANIFEST" | grep -qxF "$1"; }     # a path this installer wrote before
F_NEW=0; F_UPD=0; F_MINE=0; F_SAME=0
place() {   # place SRC DEST — a file of yours already at DEST (not one this installer put there) is saved first
  local src="$1" dest="$2"
  if [ ! -e "$dest" ]; then F_NEW=$((F_NEW + 1))
  elif cmp -s "$src" "$dest"; then F_SAME=$((F_SAME + 1))
  elif ours "$dest"; then F_UPD=$((F_UPD + 1))
  else
    F_MINE=$((F_MINE + 1))
    if [ "$DRY" = 1 ]; then note "your own $(basename "$dest") is there — it would be saved first"; else
      mkdir -p "$BACKUP_DIR" && cp -p "$dest" "$BACKUP_DIR/$(basename "$dest")"
      printf '%s\t%s\n' "$dest" "$BACKUP_DIR/$(basename "$dest")" >> "$BACKUPS"
      note "your own $(basename "$dest") was there — saved in $BACKUP_DIR (uninstall.sh puts it back)"
    fi
  fi
  [ "$DRY" != 1 ] || return 0
  cp -p "$src" "$dest"
  printf '%s  %s\n' "$(sum "$dest")" "$dest" >> "$NEW_ENTRIES"
}

begin "tools into $BIN"
run mkdir -p "$BIN"
[ "$DRY" = 1 ] || mkdir -p "$ROOT"
for f in "$HERE"/bin/*; do
  name="$(basename "$f")"
  case "$name" in
    browsers.json|__pycache__) continue ;;
  esac
  place "$f" "$BIN/$name"
done
FILES="$F_NEW new · $F_UPD updated · $F_MINE replaced, yours saved first · $F_SAME unchanged"
end "$WORD" "$FILES"

begin "the agent registry $BIN/browsers.json"
if [ -e "$BIN/browsers.json" ]; then
  SETTINGS="browsers.json: yours, kept as it is"
  [ -z "$CHANNEL" ] || note "--agent-chrome: add \"chrome\": \"$CHANNEL\" to each agent in it yourself (an existing registry is never rewritten)"
  REG_WORD=kept
else
  SETTINGS="browsers.json: a new one from the example${CHANNEL:+, every agent on Chrome $CHANNEL} — edit it: one row per agent"
  REG_WORD="$WORD"
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
    note "every agent's browser runs as Chrome $CHANNEL"
  fi
fi
if [ -n "$CHANNEL" ]; then
  case "$CHANNEL" in beta) APP="Google Chrome Beta" ;; dev) APP="Google Chrome Dev" ;; canary) APP="Google Chrome Canary" ;;
    cft) APP="Google Chrome for Testing" ;; esac
  if [ ! -d "/Applications/$APP.app" ]; then
    if [ "$CHANNEL" = cft ]; then HOW="npx @puppeteer/browsers install chrome@stable, then move it to /Applications"
    else HOW="google.com/chrome, or: brew install --cask google-chrome@$CHANNEL"; fi
    note "note: /Applications/$APP.app isn't installed yet — $HOW"
  fi
fi
end "$REG_WORD" "$SETTINGS"

if [ -n "$MIGRATE" ]; then
  begin "migrating $MIGRATE into $ROOT"
  if [ "$DRY" = 1 ]; then MOUT="$(python3 -I "$HERE/install/migrate.py" "$MIGRATE" "$ROOT" --registry "$BIN/browsers.json" --dry-run)"
  else MOUT="$(python3 -I "$HERE/install/migrate.py" "$MIGRATE" "$ROOT" --registry "$BIN/browsers.json")"; fi
  while IFS= read -r ln; do note "$ln"; done <<< "$MOUT"
  end "$WORD"
fi

begin "state in $ROOT"
run mkdir -p "$ROOT/logs" "$ROOT/state" "$ROOT/word-convert"
run chmod 700 "$ROOT"     # receipts, approvals and document copies: readable by you only
end "$WORD" "readable by you only"

job() {   # job <label> <what> — write the launchd job from install/<label>.plist with absolute paths, and load it
  local label="$1" what="$2" plist="$AGENTS_DIR/$1.plist"
  begin "$what job $label"
  JOBS="${JOBS:+$JOBS, }$label"
  if [ "$DRY" = 1 ]; then end would "write $plist, with absolute paths, and load it"; return; fi
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
  end "done" "$plist, with absolute paths — launchd does not expand ~"
}
JOBS=""
if [ "$SWEEP" = 1 ]; then job "$LABEL" sweep; fi
if [ "$HEAL" = 1 ]; then job com.rainbowomma.heal heal; fi
if [ "$TABS" = 1 ]; then job com.rainbowomma.tabs tab-sweep; fi

if [ "$MENUBAR" = 1 ]; then
  PLUGINS="$(defaults read com.ameba.SwiftBar PluginDirectory 2>/dev/null || true)"
  [ -n "$PLUGINS" ] || PLUGINS="$ROOT/swiftbar"
  begin "menu-bar item $PLUGINS/rainbowomma.10s.sh"
  if [ "$DRY" = 1 ]; then end would "SwiftBar runs it every 10 s"; else
    mkdir -p "$PLUGINS"
    printf '#!/bin/bash\n# <swiftbar.title>RainbowOMMA</swiftbar.title>\n# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>\nexec %q\n' \
      "$BIN/rainbowomma-menubar" > "$PLUGINS/rainbowomma.10s.sh"
    chmod +x "$PLUGINS/rainbowomma.10s.sh"
    printf '%s  %s\n' "$(sum "$PLUGINS/rainbowomma.10s.sh")" "$PLUGINS/rainbowomma.10s.sh" >> "$NEW_ENTRIES"
    if [ "$PLUGINS" = "$ROOT/swiftbar" ]; then
      note "install SwiftBar (brew install --cask swiftbar) and choose $PLUGINS as its plugin folder"
    fi
    end "done" "SwiftBar runs it every 10 s"
  fi
fi

set -f   # the names were checked above; no globbing of them
ADAPTER_LIST="$(echo $ADAPTERS | sed 's/ /, /g')"
[ -z "$ADAPTERS" ] || begin "adapters in $ROOT/adapters"
for A in $ADAPTERS; do
  SRC="$HERE/adapters/$A"
  if [ ! -d "$SRC" ]; then
    REPORTED=1; echo "✗ install.sh failed at step [$N/$TOTAL] $STEP: no adapter called $A — there are: $(ls "$HERE/adapters" | tr '\n' ' ')" >&2; exit 2
  fi
  DEST="$ROOT/adapters/$A"
  note "$A in $DEST (your paths filled in) — merge it into $A's settings as docs/AGENTS.md says"
  [ "$DRY" != 1 ] || continue
  mkdir -p "$DEST"
  ( cd "$SRC" && find . -type f ) | while IFS= read -r f; do
    mkdir -p "$DEST/$(dirname "$f")"
    sed -e "s|/Users/you/bin|$BIN|g" -e "s|/Users/you|$HOME|g" "$SRC/$f" > "$DEST/$f"
    if [ -x "$SRC/$f" ]; then chmod +x "$DEST/$f"; fi
  done
done
[ -z "$ADAPTERS" ] || end "$WORD" "$ADAPTER_LIST"
set +f

if [ "$DRY" != 1 ]; then          # the manifest: what is in it now, newest first for a path written again
  { [ -f "$MANIFEST" ] && cat "$MANIFEST"; cat "$NEW_ENTRIES"; } | awk '{ path = substr($0, index($0, "  ") + 2); last[path] = $0; order[path] = NR }
    END { for (p in last) print order[p] "\t" last[p] }' | sort -n | cut -f2- > "$MANIFEST.tmp" && mv "$MANIFEST.tmp" "$MANIFEST"
fi

# which release is in place — rainbowomma-doctor and a weekly "am I on the latest release?" check read it
VERSION="$(tr -d '[:space:]' < "$HERE/VERSION" 2>/dev/null || true)"
SOURCE="archive"
if [ -d "$HERE/.git" ] && command -v git >/dev/null 2>&1; then SOURCE="git $(git -C "$HERE" describe --tags --always --dirty 2>/dev/null || echo unknown)"
else case "$HERE" in */Cellar/rainbowomma/*) SOURCE="homebrew" ;; esac; fi
PREV="$(python3 -I -c 'import json, sys; print(json.load(open(sys.argv[1])).get("version", ""))' "$ROOT/installed-version" 2>/dev/null || true)"   # the release this replaces
begin "version ${VERSION:-unknown} ($SOURCE) recorded in $ROOT/installed-version"
if [ "$DRY" != 1 ]; then
  printf '{"version": "%s", "source": "%s", "bin": "%s", "at": "%s"}\n' "${VERSION:-unknown}" "$SOURCE" "$BIN" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$ROOT/installed-version"
fi
end "$WORD" "${PREV:+was $PREV}"

case ":$PATH:" in *":$BIN:"*) ;; *) echo "note: $BIN is not on your PATH — call the tools by their full path, or add it." ;; esac
if [ "$DRY" = 1 ]; then
  cat <<EOF

Dry run — nothing was changed. It would:
  files     $FILES
  jobs      ${JOBS:-none}
  settings  $SETTINGS
  adapters  ${ADAPTER_LIST:-none}${MIGRATE:+
  migrate   from $MIGRATE (what it would carry over is listed above)}
EOF
else
  cat <<EOF

Done. Next:
  \$EDITOR $BIN/browsers.json                  # port, profile, color, label per agent
  $BIN/browser-owner start alpha --by alpha     # paints and opens Alpha's browser
  $BIN/browser-owner list
  $HERE/install/make-desktop-apps.sh             # optional: colored open/close icons on the desktop
Language: English or Hebrew from your Mac's settings; force one with RAINBOW_LANG=en or RAINBOW_LANG=he.
The first Word → PDF conversion (office-owner pdf) shows a Word permission prompt once — allow it.
EOF
fi
# an upgrade: what changed since the release that was in place, and anything it needs from you
python3 -I "$HERE/install/changes.py" "$PREV" "${VERSION:-}" "$HERE/CHANGELOG.md" 2>/dev/null || true
