# shellcheck shell=bash
# Shared Node/nvm bootstrap — source this, never execute it.
#
#   source "$(dirname "$0")/nvm_env.sh"
#   load_nvm            # loads nvm-managed Node into the current shell
#
# Why this exists: scripts invoked as `bash foo.sh` run in a non-login,
# non-interactive shell that does NOT source ~/.bashrc, so the nvm setup the
# installer appended there is never applied. Without it, `npm`/`npx` resolve to
# the Windows Node leaked into PATH via WSL interop (/mnt/c/Program Files/nodejs),
# which cannot run the Linux-native binaries in frontend/node_modules.

# Load nvm-managed Node into the current shell. Idempotent. Returns non-zero if
# nvm is not installed so callers can decide whether to install it.
load_nvm() {
  export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
  if [ ! -s "$NVM_DIR/nvm.sh" ]; then
    return 1
  fi
  # nvm.sh is not `set -eu` clean — under a caller running `set -euo pipefail`
  # it can abort the whole script. Relax errexit/nounset only while sourcing,
  # then restore whatever the caller had set.
  local had_e=0 had_u=0
  case $- in *e*) had_e=1 ;; esac
  case $- in *u*) had_u=1 ;; esac
  set +eu
  # shellcheck disable=SC1091
  \. "$NVM_DIR/nvm.sh"
  # Activate the default/LTS version so `node`/`npm`/`npx` are on PATH.
  nvm use --lts >/dev/null 2>&1 || nvm use default >/dev/null 2>&1 || true
  [ "$had_e" = 1 ] && set -e
  [ "$had_u" = 1 ] && set -u
  return 0
}

# Install nvm (pinned version) if it isn't already present, then load it.
install_and_load_nvm() {
  export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
  if [ ! -s "$NVM_DIR/nvm.sh" ]; then
    local nvm_version="v0.40.1"
    local nvm_url="https://raw.githubusercontent.com/nvm-sh/nvm/${nvm_version}/install.sh"
    if command -v curl >/dev/null 2>&1; then
      curl -o- "$nvm_url" | bash
    elif command -v wget >/dev/null 2>&1; then
      wget -qO- "$nvm_url" | bash
    else
      echo "ERROR: neither curl nor wget available to install nvm." >&2
      return 1
    fi
  fi
  load_nvm
}
