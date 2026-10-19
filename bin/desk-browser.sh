#!/bin/bash
# What the desktop icons and the Dock tray run: open|close <agent> (any agent in browsers.json), open|close human, close agents.
# open <agent> on a browser that is already open brings it to the front, un-minimized. Exit 1 (message on stderr) on failure.
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
OWNER="$DIR/browser-owner"
I18N="$DIR/rainbow_i18n.py"
ACT="${1:-}"; WHO="${2:-}"
py() {   # the first python3 that works — never macOS's stub, which only asks to install the developer tools
  for p in /opt/homebrew/bin/python3 /usr/bin/python3 /usr/local/bin/python3; do
    [ -x "$p" ] || continue
    [ "$p" = /usr/bin/python3 ] && [ "$(uname -s)" = Darwin ] && ! xcode-select -p >/dev/null 2>&1 && continue
    "$p" "$@"; return
  done
  return 127
}
msg() { py -I "$I18N" "$@" 2>/dev/null || echo "$1"; }
field() { py -I -c 'import json,sys
try: d=json.loads(sys.stdin.read().strip().splitlines()[-1])
except Exception: d={}
print(d.get(sys.argv[1]) or "")' "$1"; }
nm() { [ "$1" = human ] && { msg desk.name.human; return; }
       L=$("$OWNER" status "$1" 2>/dev/null | field label); echo "${L:-$1}"; }
fail() { "$@" >&2; exit 1; }   # a failure: the message on stderr and exit 1 (the icons and the Dock tray show it)
is_agent() { case " $("$OWNER" names 2>/dev/null) " in *" $1 "*) return 0 ;; esac; return 1; }

case "$ACT:$WHO" in
  open:human)
    "$DIR/human-chrome.sh" >/dev/null 2>&1 && msg desk.human_open || fail msg desk.human_open_failed ;;
  close:human)
    # the personal Chrome and the background leftovers (headless instances); kill-chrome.sh spares every agent browser
    "$DIR/kill-chrome.sh" 2>&1 | head -3 ;;
  close:agents)
    MSG=""
    for a in $("$OWNER" names 2>/dev/null); do
      ST=$("$OWNER" stop "$a" --by human 2>&1 | field status)
      MSG="$MSG$(nm "$a"): $([ "$ST" = stopped ] && msg desk.closed_word || echo "$ST") · "
    done
    echo "${MSG:-$(msg desk.owner_silent)} — $(msg desk.all_closed_tail)" ;;
  open:?*)
    is_agent "$WHO" || { msg desk.usage; exit 2; }
    OUT=$("$OWNER" start "$WHO" --by human 2>&1); ST=$(echo "$OUT" | field status)
    case "$ST" in
      started) msg desk.opened name="$(nm "$WHO")" ;;
      already-up)   # open, perhaps minimized or behind other windows: bring it to the front
        if [ "$("$OWNER" front "$WHO" 2>/dev/null | field status)" = front ]; then msg desk.in_front name="$(nm "$WHO")"
        else msg desk.already_open name="$(nm "$WHO")"; fi ;;
      *) fail msg desk.not_opened name="$(nm "$WHO")" status="$ST" why="$(echo "$OUT" | field why)" ;;
    esac ;;
  close:?*)
    is_agent "$WHO" || { msg desk.usage; exit 2; }
    OUT=$("$OWNER" stop "$WHO" --by human 2>&1); ST=$(echo "$OUT" | field status)
    [ "$ST" = "stopped" ] && msg desk.closed name="$(nm "$WHO")" \
                          || fail msg desk.not_closed name="$(nm "$WHO")" status="$ST" why="$(echo "$OUT" | field why)" ;;
  *) msg desk.usage ; exit 2 ;;
esac
