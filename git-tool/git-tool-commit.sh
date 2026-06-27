#!/bin/bash
# git-tool-commit.sh — commit & push all changed submodules, then update main repo
# Usage: bash .claude/skills/git-tool/git-tool-commit.sh
set -euo pipefail

ROOT="$(cd "$(git rev-parse --show-toplevel 2>/dev/null)" && pwd)" || {
  echo "[ERROR] not in a git repo"; exit 1
}
cd "$ROOT"
BRANCH="$(git branch --show-current)"

info()  { echo "[INFO] $*"; }
ok()    { echo "[ OK ] $*"; }
warn()  { echo "[WARN] $*"; }

# ---- Find all submodules with changes ----
SUB_PATHS=$(git config --file .gitmodules --get-regexp path 2>/dev/null | awk '{print $2}' || true)
[[ -z "$SUB_PATHS" ]] && { warn "no submodules found"; exit 0; }

COMMITTED=()
for subpath in $SUB_PATHS; do
  [[ ! -d "$subpath" ]] && continue

  # Check if submodule has any changes (including untracked)
  has_changes=$(git -C "$subpath" status --porcelain 2>/dev/null || true)
  [[ -z "$has_changes" ]] && continue

  info "processing $subpath..."

  # Step 1: ensure on a branch (not detached HEAD)
  sub_branch=$(git -C "$subpath" branch --show-current 2>/dev/null || true)
  if [[ -z "$sub_branch" ]]; then
    info "  detached HEAD -> checkout main"
    git -C "$subpath" checkout main 2>/dev/null || {
      warn "  no 'main' branch, skipping $subpath"; continue
    }
    sub_branch="main"
  fi

  # Step 2: add & commit
  git -C "$subpath" add -A
  commit_msg="update: $(git -C "$subpath" diff --cached --name-only | head -5 | tr '\n' ' ' | sed 's/ *$//')"
  commit_msg="${commit_msg:-update}"
  git -C "$subpath" commit -m "$commit_msg" || {
    warn "  nothing to commit in $subpath"; continue
  }
  sub_commit="$(git -C "$subpath" rev-parse --short HEAD)"

  # Step 3: push (handle non-fast-forward)
  if ! git -C "$subpath" push origin "$sub_branch" 2>/dev/null; then
    info "  non-fast-forward, rebasing..."
    git -C "$subpath" pull --rebase origin "$sub_branch"
    git -C "$subpath" push origin "$sub_branch"
  fi

  ok "  $subpath committed & pushed ($sub_commit)"
  COMMITTED+=("$subpath")
done

# ---- Update main repo submodule pointers ----
if [[ ${#COMMITTED[@]} -eq 0 ]]; then
  echo ""
  ok "no submodules with changes to commit"
  exit 0
fi

info "updating main repo submodule pointers..."
for subpath in "${COMMITTED[@]}"; do
  git add "$subpath"
done
git commit -m "chore: update submodule pointers"
git push origin "$BRANCH"

echo ""
ok "git-tool commit complete — updated: ${COMMITTED[*]}"
git log --oneline -1 --no-decorate 2>/dev/null | xargs -I{} echo "   main repo: {}"
