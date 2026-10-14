#!/bin/bash
set -u
OWNER="$HOME/bin/browser-owner"
I18N="$(cd "$(dirname "$0")" && pwd)/rainbow_i18n.py"
ACT="${1:-}"; WHO="${2:-}"
msg() { /usr/bin/python3 -I "$I18N" "$@"; }
nm() { case "$1" in alpha|bravo|charlie|human) msg "desk.name.$1";; *) echo "$1";; esac; }
field() { /usr/bin/python3 -I -c 'import json,sys
try: d=json.loads(sys.stdin.read().strip().splitlines()[-1])
except Exception: d={}
print(d.get(sys.argv[1]) or "")' "$1"; }

case "$ACT:$WHO" in
  open:human)
    "$HOME/bin/human-chrome.sh" >/dev/null 2>&1 && msg desk.human_open || msg desk.human_open_failed ;;
  open:alpha|open:bravo|open:charlie)
    OUT=$("$OWNER" start "$WHO" --by human 2>&1); ST=$(echo "$OUT" | field status)
    case "$ST" in
      started) msg desk.opened name="$(nm "$WHO")" ;;
      already-up) msg desk.already_open name="$(nm "$WHO")" ;;
      *) msg desk.not_opened name="$(nm "$WHO")" status="$ST" why="$(echo "$OUT" | field why)" ;;
    esac ;;
  close:alpha|close:bravo|close:charlie)
    OUT=$("$OWNER" stop "$WHO" --by human 2>&1); ST=$(echo "$OUT" | field status)
    [ "$ST" = "stopped" ] && msg desk.closed name="$(nm "$WHO")" \
                          || msg desk.not_closed name="$(nm "$WHO")" status="$ST" why="$(echo "$OUT" | field why)" ;;
  close:agents)
    MSG=""
    for a in $("$OWNER" names 2>/dev/null); do
      ST=$("$OWNER" stop "$a" --by human 2>&1 | field status)
      MSG="$MSG$(nm "$a"): $([ "$ST" = stopped ] && msg desk.closed_word || echo "$ST") · "
    done
    echo "${MSG:-$(msg desk.owner_silent)} — $(msg desk.all_closed_tail)" ;;
  close:human)
    # the personal Chrome and the background leftovers (headless instances); kill-chrome.sh spares every agent browser
    "$HOME/bin/kill-chrome.sh" 2>&1 | head -3 ;;
  *) msg desk.usage ; exit 2 ;;
esac
