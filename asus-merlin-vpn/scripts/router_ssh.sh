#!/usr/bin/env bash
set -euo pipefail

skill_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
repo_root="${ASUS_MERLIN_REPO_ROOT:-$(cd "${skill_dir}/../../.." && pwd)}"

load_env() {
  local file
  for file in "${repo_root}/.env/asus-router.env" "${repo_root}/.env"; do
    if [[ -f "${file}" ]]; then
      set -a
      # shellcheck disable=SC1090
      source "${file}"
      set +a
      return 0
    fi
  done
  return 1
}

usage() {
  cat <<'USAGE'
Usage:
  scripts/router_ssh.sh '<remote command>'
  printf '%s\n' '<remote commands>' | scripts/router_ssh.sh

Required env:
  ASUS_ROUTER_HOST
  ASUS_ROUTER_USER
  ASUS_ROUTER_PASSWORD

Optional env:
  ASUS_ROUTER_KNOWN_HOSTS=/tmp/codex_router_known_hosts
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

load_env || {
  echo "Missing router env. Create ${repo_root}/.env or ${repo_root}/.env/asus-router.env." >&2
  exit 2
}

: "${ASUS_ROUTER_HOST:?Missing ASUS_ROUTER_HOST}"
: "${ASUS_ROUTER_USER:?Missing ASUS_ROUTER_USER}"
: "${ASUS_ROUTER_PASSWORD:?Missing ASUS_ROUTER_PASSWORD}"

if [[ "$#" -gt 0 ]]; then
  remote_cmd="$*"
else
  remote_cmd="$(cat)"
fi

if [[ -z "${remote_cmd}" ]]; then
  usage >&2
  exit 2
fi

export ASUS_ROUTER_HOST ASUS_ROUTER_USER ASUS_ROUTER_PASSWORD
export ASUS_ROUTER_KNOWN_HOSTS="${ASUS_ROUTER_KNOWN_HOSTS:-/tmp/codex_router_known_hosts}"
export ASUS_ROUTER_REMOTE_COMMAND="${remote_cmd}"

expect <<'EXPECT'
set timeout 180
log_user 1

set host $env(ASUS_ROUTER_HOST)
set user $env(ASUS_ROUTER_USER)
set password $env(ASUS_ROUTER_PASSWORD)
set known_hosts $env(ASUS_ROUTER_KNOWN_HOSTS)
set command $env(ASUS_ROUTER_REMOTE_COMMAND)

spawn ssh -tt \
  -o PreferredAuthentications=password,keyboard-interactive \
  -o PubkeyAuthentication=no \
  -o KbdInteractiveAuthentication=yes \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=$known_hosts \
  $user@$host sh -s

expect {
  -re "(?i)password.*:" { send "$password\r" }
  timeout { exit 124 }
  eof { exit 1 }
}

expect -re {[#>$] ?$}
send -- "$command\r"
send -- "echo __ASUS_MERLIN_DONE__\r"
send -- "exit\r"

expect {
  -re "__ASUS_MERLIN_DONE__" { exp_continue }
  eof { }
  timeout { exit 124 }
}
EXPECT
