#!/bin/bash
set -u

PATTERN='(Google Chrome|Chromium|Google Chrome Helper|Google Chrome for Testing)( \([^)]*\))?\.app/Contents/MacOS/'

KILL_CDP="${KILL_CDP:-0}"
[ "${1:-}" = "--all" ] && KILL_CDP=1

CDP_MARK='(^| )--remote-debugging-port=92(2[2-9]|[3-9][0-9])( |$)'

OWNER_NOTE=""
KEEP_PORTS=""
if [ "$KILL_CDP" = "1" ]; then
  NAMES=""
  if [ -x "$HOME/bin/browser-owner" ]; then
    NAMES=$("$HOME/bin/browser-owner" names 2>/dev/null) || NAMES=""
  fi
  if [ -z "$NAMES" ]; then
    OWNER_NOTE="
browser-owner לא ענה — דפדפני הסוכנים לא נסגרו (נסגר רק השאר). לסגור אותם: לתקן את browser-owner, או לסגור ידנית."
    KILL_CDP=0
  fi
  for NAME in $NAMES; do
    RC=1
    for _ in 1 2 3 4 5 6 7; do
      OWNER_OUT=$("$HOME/bin/browser-owner" stop "$NAME" --by human 2>&1); RC=$?
      case "$OWNER_OUT" in *'"busy"'*) sleep 10 ;; *) break ;; esac
    done
    if [ "$RC" -eq 0 ]; then
      case "$OWNER_OUT" in *'"processes": 0'*) ;; *) OWNER_NOTE="$OWNER_NOTE
הדפדפן של $NAME נסגר דרך browser-owner ונרשם 'נסגר ע\"י האדם' — הוא לא ייפתח לבד." ;; esac
    else
      PORT=$("$HOME/bin/browser-owner" status "$NAME" 2>/dev/null | sed -n 's/.*"port": \([0-9]*\).*/\1/p')
      [ -n "$PORT" ] && KEEP_PORTS="$KEEP_PORTS $PORT"
      OWNER_NOTE="$OWNER_NOTE
browser-owner לא סגר את הדפדפן של $NAME ($OWNER_OUT) — הוא נשאר פתוח (לא נסגר כאן ישירות, כדי שלא ייפתח מחדש בלי רישום)."
    fi
  done
fi

spare_pids() {
  # PIDs of the CDP browser and every descendant of it. With --all: only browsers whose owner stop failed (KEEP_PORTS).
  local roots kids mark="$CDP_MARK"
  if [ "$KILL_CDP" = "1" ]; then
    [ -z "${KEEP_PORTS// }" ] && return 0
    mark="(^| )--remote-debugging-port=($(echo $KEEP_PORTS | tr ' ' '|'))( |$)"
  fi
  roots=$(pgrep -f -- "$mark" 2>/dev/null | tr '\n' ' ')
  [ -z "${roots// }" ] && return 0
  kids="$roots"
  for _ in 1 2 3; do
    for p in $kids; do
      c=$(pgrep -P "$p" 2>/dev/null | tr '\n' ' ')
      [ -n "${c// }" ] && kids="$kids $c"
    done
  done
  echo "$kids" | tr ' ' '\n' | sort -u | grep -v '^$'
}

targets() {
  local all spare
  all=$(pgrep -f "$PATTERN" 2>/dev/null | sort -u)
  spare=$(spare_pids)
  [ -z "${spare// }" ] && { echo "$all"; return; }
  comm -23 <(echo "$all") <(echo "$spare" | sort -u)
}

BEFORE=$(targets | grep -c '^[0-9]' || true)
SPARED=$(spare_pids | grep -c '^[0-9]' || true)

if [ "$BEFORE" -eq 0 ]; then
  if [ "$SPARED" -gt 0 ]; then
    echo "אין תהליכי Chrome לסגירה. מה שפתוח הם דפדפני ה-CDP של הסוכנים ($SPARED תהליכים), והם מוחרגים בכוונה (כדי לא לאבד התחברויות פעילות של הסוכנים). לסגור גם אותם: kill-chrome.sh --all"
  else
    echo "לא נמצאו תהליכי Chrome פתוחים.$OWNER_NOTE"
  fi
  exit 0
fi

# Ask the visible browser to quit first. A graceful quit lets a real browsing session flush its
# state, so the next launch does not offer to restore pages or warn that Chrome closed unexpectedly.
# Skipped when the CDP browser is being spared: `tell application "Google Chrome" to quit` addresses
# the application, not a process, and would take the spared browser down with everything else.
if [ "$SPARED" -eq 0 ]; then
  osascript -e 'tell application "System Events" to (name of processes) contains "Google Chrome"' >/dev/null 2>&1 \
    && osascript -e 'tell application "Google Chrome" to quit' >/dev/null 2>&1
  for _ in 1 2 3 4 5 6; do
    [ "$(targets | grep -c '^[0-9]' || true)" -eq 0 ] && break
    sleep 0.5
  done
fi

# Everything still standing is either headless, wedged, or a helper whose parent is gone. TERM
# first so anything with a shutdown path can take it; KILL only for what ignores that. Signals go
# to an explicit PID list rather than `pkill -f` so the spared processes are never in range.
kill_list() { local p; for p in $(targets); do kill "-$1" "$p" 2>/dev/null; done; }

kill_list TERM
for _ in 1 2 3 4 5 6; do
  [ "$(targets | grep -c '^[0-9]' || true)" -eq 0 ] && break
  sleep 0.5
done
kill_list KILL
sleep 1

AFTER=$(targets | grep -c '^[0-9]' || true)
CLOSED=$((BEFORE - AFTER))
SUFFIX=""
[ "$SPARED" -gt 0 ] && SUFFIX="

לא כולל את דפדפני ה-CDP של הסוכנים ($SPARED תהליכים) — הם נשארו פתוחים בכוונה (כדי לא לאבד התחברויות פעילות של הסוכנים)."

if [ "$AFTER" -eq 0 ]; then
  echo "נסגרו $CLOSED תהליכי Chrome.$SUFFIX$OWNER_NOTE"
else
  echo "נסגרו $CLOSED מתוך $BEFORE. נשארו $AFTER שלא נענו.$SUFFIX$OWNER_NOTE"
fi
