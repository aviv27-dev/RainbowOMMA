#!/bin/bash
# What the desktop icons run: open|close <agent> (any agent in browsers.json), open|close human, close agents.
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
OWNER="$DIR/browser-owner"
I18N="$DIR/rainbow_i18n.py"
ACT="${1:-}"; WHO="${2:-}"
msg() { /usr/bin/python3 -I "$I18N" "$@"; }
field() { /usr/bin/python3 -I -c 'import json,sys
try: d=json.loads(sys.stdin.read().strip().splitlines()[-1])
except Exception: d={}
print(d.get(sys.argv[1]) or "")' "$1"; }
nm() { [ "$1" = human ] && { msg desk.name.human; return; }
       L=$("$OWNER" status "$1" 2>/dev/null | field label); echo "${L:-$1}"; }
is_agent() { case " $("$OWNER" names 2>/dev/null) " in *" $1 "*) return 0 ;; esac; return 1; }

case "$ACT:$WHO" in
  open:human)
    "$DIR/human-chrome.sh" >/dev/null 2>&1 && msg desk.human_open || msg desk.human_open_failed ;;
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
      already-up) msg desk.already_open name="$(nm "$WHO")" ;;
      *) msg desk.not_opened name="$(nm "$WHO")" status="$ST" why="$(echo "$OUT" | field why)" ;;
    esac ;;
  close:?*)
    is_agent "$WHO" || { msg desk.usage; exit 2; }
    OUT=$("$OWNER" stop "$WHO" --by human 2>&1); ST=$(echo "$OUT" | field status)
    [ "$ST" = "stopped" ] && msg desk.closed name="$(nm "$WHO")" \
                          || msg desk.not_closed name="$(nm "$WHO")" status="$ST" why="$(echo "$OUT" | field why)" ;;
  *) msg desk.usage ; exit 2 ;;
esac
