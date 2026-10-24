#!/bin/bash
# isolate-agent.sh — an agent of its own macOS user: the hard boundary one shared user can't give (docs/ISOLATION.md).
#
#   install/isolate-agent.sh create AGENT [--apply]   a hidden standard user rainbow-AGENT, a sudoers rule that lets YOU (only
#                                                     you) run commands as it, a shared work folder, RainbowOMMA in its home
#   install/isolate-agent.sh run AGENT -- COMMAND …   run the agent as that user (as-agent AGENT COMMAND, in its home)
#   install/isolate-agent.sh status [AGENT]           what exists
#   install/isolate-agent.sh remove AGENT [--apply]   the user, its home, the sudoers rule — the shared folder stays
#
# Without --apply nothing is changed: every command is printed. --apply asks for your password (sudo) once.
# Another user's processes can't read your files, your Chrome profile, your Keychain or other agents' state, and you can
# still see and stop them. They also can't open windows on your screen: its browser runs headless (or only in its own
# login session), and computer use stays with agents of your own user.
set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
APPLY=0
ARGS=()
CMD=()
while [ $# -gt 0 ]; do
  case "$1" in
    --apply) APPLY=1; shift ;;
    --) shift; CMD=("$@"); break ;;
    -h|--help) sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) ARGS+=("$1"); shift ;;
  esac
done
WHAT="${ARGS[0]:-}"
AGENT="${ARGS[1]:-}"
ME="$(id -un)"
SHARED_ROOT="${RAINBOW_ISOLATE_SHARED:-/Users/Shared/rainbowomma}"
SUDOERS_DIR="${RAINBOW_ISOLATE_SUDOERS:-/etc/sudoers.d}"

case "$WHAT" in create|run|status|remove) ;; *) echo "usage: isolate-agent.sh create|run|status|remove AGENT [--apply]" >&2; exit 2 ;; esac
if [ "$WHAT" != status ] || [ -n "$AGENT" ]; then
  # letters spelled out: in macOS's bash 3.2 a range like a-z follows the locale and lets capitals through
  case "$AGENT" in [abcdefghijklmnopqrstuvwxyz]*) ;; *) echo "an agent name: a-z, 0-9, - (alpha, bravo …)" >&2; exit 2 ;; esac
  case "$AGENT" in *[!abcdefghijklmnopqrstuvwxyz0123456789-]*|human|human-*) echo "not an agent name: $AGENT" >&2; exit 2 ;; esac
  [ "${#AGENT}" -le 24 ] || { echo "an agent name of at most 24 characters (macOS short names)" >&2; exit 2; }
fi
USER_NAME="rainbow-$AGENT"
HOME_DIR="/Users/$USER_NAME"
WORK="$SHARED_ROOT/$AGENT"
RULE="$SUDOERS_DIR/rainbowomma-$AGENT"

do_() {   # the change, or what it would be
  if [ "$APPLY" = 1 ]; then "$@"; else printf 'would: %s\n' "$*"; fi
}
exists() { id "$USER_NAME" >/dev/null 2>&1; }
if [ "$WHAT" != status ] && [ "$WHAT" != run ] && [ "$(uname -s)" != Darwin ] && [ "${RAINBOW_ISOLATE_ANY_OS:-0}" != 1 ]; then
  echo "macOS only (sysadminctl, dscl)" >&2; exit 1
fi

if [ "$WHAT" = create ] && [ "$ME" = root ]; then
  echo "run it as yourself, not with sudo: the rule lets YOU run commands as the agent's user (it asks for sudo itself)" >&2; exit 2
fi
case "$WHAT" in
create)
  [ "$APPLY" = 1 ] || echo "dry run — nothing changes; --apply to do it"
  if exists; then echo "→ $USER_NAME exists — kept"; else
    echo "→ user $USER_NAME: standard (not an admin), hidden from the login window, no password to log in with"
    if [ "$APPLY" = 1 ]; then          # a random password nobody keeps: the user is reached through sudo only, never a login
      PW="$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom 2>/dev/null | head -c 32 || true)"
      sudo sysadminctl -addUser "$USER_NAME" -fullName "RainbowOMMA $AGENT" -home "$HOME_DIR" -password "$PW"; PW=""
    else
      echo "would: sudo sysadminctl -addUser $USER_NAME -fullName \"RainbowOMMA $AGENT\" -home $HOME_DIR -password <random, not kept>"
    fi
    do_ sudo dscl . create "/Users/$USER_NAME" IsHidden 1
    do_ sudo createhomedir -c -u "$USER_NAME"
  fi
  echo "→ $RULE: $ME (only) may run commands as $USER_NAME, without a password"
  if [ "$APPLY" = 1 ]; then
    T="$(mktemp)"; printf '%s ALL=(%s) NOPASSWD: ALL\n' "$ME" "$USER_NAME" > "$T"
    sudo visudo -cf "$T" >/dev/null && sudo install -m 0440 -o root -g wheel "$T" "$RULE"; rm -f "$T"
  else
    echo "would: write '$ME ALL=($USER_NAME) NOPASSWD: ALL' to $RULE (checked with visudo -cf, mode 0440)"
  fi
  echo "→ $WORK: the agent's work folder — the agent and you read and write it, nobody else"
  do_ sudo mkdir -p "$WORK"
  do_ sudo chown "$USER_NAME" "$WORK"
  do_ sudo chmod 0700 "$WORK"
  do_ sudo chmod +a "user:$ME allow list,add_file,search,add_subdirectory,delete_child,readattr,writeattr,readextattr,writeextattr,readsecurity,file_inherit,directory_inherit" "$WORK"
  echo "→ RainbowOMMA in $HOME_DIR/bin (from a copy it can read — your home is yours)"
  if [ "$APPLY" = 1 ]; then
    SRC="$(mktemp -d)"; cp -R "$HERE/bin" "$HERE/install" "$HERE/examples" "$HERE/adapters" "$HERE/install.sh" "$SRC/"; chmod -R a+rX "$SRC"
    sudo -u "$USER_NAME" -H "$SRC/install.sh" --bin "$HOME_DIR/bin"; rm -rf "$SRC"
  else
    echo "would: copy RainbowOMMA to a temporary folder and run its install.sh as $USER_NAME --bin $HOME_DIR/bin"
  fi
  echo "Then: install/isolate-agent.sh run $AGENT -- claude   (its browsers.json profile goes under $HOME_DIR)"
  ;;
run)
  [ ${#CMD[@]} -gt 0 ] || { echo "usage: isolate-agent.sh run $AGENT -- COMMAND …" >&2; exit 2; }
  exists || { echo "no user $USER_NAME — install/isolate-agent.sh create $AGENT --apply" >&2; exit 1; }
  cd "$WORK" 2>/dev/null || cd /
  exec sudo -u "$USER_NAME" -H "$HOME_DIR/bin/as-agent" "$AGENT" "${CMD[@]}"
  ;;
status)
  for u in $(dscl . list /Users 2>/dev/null | grep '^rainbow-' || true); do
    a="${u#rainbow-}"
    [ -z "$AGENT" ] || [ "$a" = "$AGENT" ] || continue
    printf '%s  user %s  rule %s  work %s\n' "$a" "$u" "$([ -e "$SUDOERS_DIR/rainbowomma-$a" ] && echo yes || echo no)" \
      "$([ -d "$SHARED_ROOT/$a" ] && echo "$SHARED_ROOT/$a" || echo none)"
  done
  ;;
remove)
  [ "$APPLY" = 1 ] || echo "dry run — nothing changes; --apply to do it"
  echo "→ the sudoers rule, then the user $USER_NAME and its home (its processes stop first)"
  do_ sudo rm -f "$RULE"
  if exists || [ "$APPLY" != 1 ]; then
    do_ sudo pkill -u "$USER_NAME"
    do_ sudo sysadminctl -deleteUser "$USER_NAME"
  fi
  echo "kept: $WORK (the agent's work) — delete it yourself when you don't need it"
  ;;
esac
