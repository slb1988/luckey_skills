#!/bin/bash
# git-tool-upcommit.sh — one-shot "update & commit" for a single submodule (default: the skills repo containing this script)
# Flow: commit local TRACKED changes -> rebase onto remote -> push -> update superproject pointer (pathspec commit) -> push superproject
# Untracked files are never auto-committed; they are listed so you can `git add` them and re-run.
# Usage: bash <skills_repo>/git-tool/git-tool-upcommit.sh [submodule_path]
set -euo pipefail

info() { echo "[INFO] $*"; }
ok()   { echo "[ OK ] $*"; }
warn() { echo "[WARN] $*"; }
die()  { echo "[ERROR] $*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---- locate submodule ----
# default: the git repo containing this script (git-tool/ sits at <submodule>/git-tool/)
if [[ -n "${1:-}" ]]; then
  SUB="$1"
else
  SUB="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null)" \
    || die "cannot locate submodule from script dir; pass path explicitly"
fi
SUB="$(cd "$SUB" && pwd)"

# superproject (empty for standalone clones such as ~/.pi/skills — pointer step then skipped)
MAIN="$(git -C "$SUB" rev-parse --show-superproject-working-tree 2>/dev/null || true)"

info "submodule:    $SUB"
if [[ -n "$MAIN" ]]; then info "superproject: $MAIN"; else warn "no superproject — pointer step will be skipped"; fi

# ---- Step 1: detached HEAD -> main (no pull yet: network issues must not block) ----
BRANCH="$(git -C "$SUB" branch --show-current 2>/dev/null || true)"
if [[ -z "$BRANCH" ]]; then
  warn "detached HEAD -> checkout main"
  git -C "$SUB" checkout main >/dev/null 2>&1 || die "no 'main' branch in $SUB"
  BRANCH="main"
fi

# ---- Step 2: commit local tracked changes (untracked left alone) ----
if [[ -n "$(git -C "$SUB" status --porcelain | grep -v '^??' || true)" ]]; then
  git -C "$SUB" add -u
  msg="update: $(git -C "$SUB" diff --cached --name-only | head -5 | tr '\n' ' ' | sed 's/ *$//')"
  git -C "$SUB" commit -m "${msg:0:200}"
  ok "committed local changes: ${msg:0:120}"
else
  ok "submodule clean, nothing to commit"
fi

UNTRACKED="$(git -C "$SUB" status --porcelain | grep '^??' || true)"
if [[ -n "$UNTRACKED" ]]; then
  warn "untracked files NOT committed (git add them first, then re-run):"
  echo "$UNTRACKED" | sed 's/^?? /  /'
fi

# ---- Step 3: rebase onto remote + push ----
git -C "$SUB" fetch origin "$BRANCH"
if ! git -C "$SUB" rebase "origin/$BRANCH" >/dev/null; then
  git -C "$SUB" rebase --abort >/dev/null 2>&1 || true
  die "rebase onto origin/$BRANCH failed — resolve manually in $SUB"
fi
git -C "$SUB" push origin "$BRANCH"
ok "submodule pushed ($BRANCH: $(git -C "$SUB" rev-parse --short HEAD))"

# ---- Step 4: superproject pointer (pathspec commit — never sweeps unrelated staged files) ----
if [[ -n "$MAIN" ]]; then
  REL="$(realpath --relative-to="$MAIN" "$SUB")"
  RECORDED="$(git -C "$MAIN" ls-tree HEAD "$REL" 2>/dev/null | awk '{print $3}')"
  CURRENT="$(git -C "$SUB" rev-parse HEAD)"
  if [[ "$RECORDED" == "$CURRENT" ]]; then
    ok "superproject pointer already current"
  else
    git -C "$MAIN" add "$REL"
    git -C "$MAIN" commit -m "chore: update $REL submodule to latest" -- "$REL"
    MBRANCH="$(git -C "$MAIN" branch --show-current)"
    if ! git -C "$MAIN" push origin "$MBRANCH"; then
      warn "superproject push rejected, pull --rebase then retry..."
      if ! git -C "$MAIN" pull --rebase origin "$MBRANCH"; then
        git -C "$MAIN" rebase --abort >/dev/null 2>&1 || true
        die "superproject pull --rebase failed — resolve manually in $MAIN"
      fi
      git -C "$MAIN" push origin "$MBRANCH"
    fi
    ok "superproject pointer committed & pushed (${RECORDED:0:7} -> ${CURRENT:0:7})"
  fi
fi

echo ""
ok "git-tool upcommit complete"
