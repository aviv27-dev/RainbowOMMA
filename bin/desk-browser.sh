#!/bin/bash
set -u
OWNER="$HOME/bin/browser-owner"
ACT="${1:-}"; WHO="${2:-}"
he() { case "$1" in alpha) echo "אלפא";; bravo) echo "בראבו";; charlie) echo "צ׳רלי";; *) echo "$1";; esac; }
field() { /usr/bin/python3 -I -c 'import json,sys
try: d=json.loads(sys.stdin.read().strip().splitlines()[-1])
except Exception: d={}
print(d.get(sys.argv[1]) or "")' "$1"; }

case "$ACT:$WHO" in
  open:human)
    "$HOME/bin/human-chrome.sh" >/dev/null 2>&1 && echo "Chrome של האדם פתוח" || echo "לא הצלחתי לפתוח את Chrome של האדם" ;;
  open:alpha|open:bravo|open:charlie)
    OUT=$("$OWNER" start "$WHO" --by human 2>&1); ST=$(echo "$OUT" | field status)
    case "$ST" in
      started) echo "הדפדפן של $(he "$WHO") נפתח" ;;
      already-up) echo "הדפדפן של $(he "$WHO") כבר פתוח" ;;
      *) echo "הדפדפן של $(he "$WHO") לא נפתח: $ST — $(echo "$OUT" | field why)" ;;
    esac ;;
  close:alpha|close:bravo|close:charlie)
    OUT=$("$OWNER" stop "$WHO" --by human 2>&1); ST=$(echo "$OUT" | field status)
    [ "$ST" = "stopped" ] && echo "הדפדפן של $(he "$WHO") נסגר — לא ייפתח לבד עד לפתיחה ידנית מהקיצור" \
                          || echo "הדפדפן של $(he "$WHO") לא נסגר: $ST — $(echo "$OUT" | field why)" ;;
  close:agents)
    MSG=""
    for a in $("$OWNER" names 2>/dev/null); do
      ST=$("$OWNER" stop "$a" --by human 2>&1 | field status)
      MSG="$MSG$(he "$a"): $([ "$ST" = stopped ] && echo נסגר || echo "$ST") · "
    done
    echo "${MSG:-browser-owner לא ענה} — לא ייפתחו לבד עד לפתיחה ידנית" ;;
  close:human)
    # the personal Chrome and the background leftovers (headless instances); kill-chrome.sh spares every agent browser
    "$HOME/bin/kill-chrome.sh" 2>&1 | head -3 ;;
  *) echo "שימוש: desk-browser.sh open|close alpha|bravo|charlie|human|agents" ; exit 2 ;;
esac
