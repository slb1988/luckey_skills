#!/bin/bash
# git-tool-commit.sh — commit & push main repo + all changed submodules
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

MAIN_COMMITTED=false

# ============================================================
#  Step 1: commit main repo changes (tracked + untracked)
# ============================================================
SUB_PATHS=$(git config --file .gitmodules --get-regexp path 2>/dev/null | awk '{print $2}' || true)

info "checking main repo changes..."
ROOT_CHANGES=$(git status --porcelain || true)

if [[ -n "$ROOT_CHANGES" ]]; then
  # Exclude submodule pointer changes; keep everything else (including untracked ??)
  ROOT_OWN=$(echo "$ROOT_CHANGES" | { while IFS= read -r line; do
    p="${line:3}"
    [[ "$line" == '??'* ]] && { echo "$line"; continue; }
    is_sub=false
    for sp in $SUB_PATHS; do
      [[ "$p" == "$sp" ]] && { is_sub=true; break; }
    done
    $is_sub && continue
    echo "$line"
  done; })

  if [[ -n "$ROOT_OWN" ]]; then
    echo "$ROOT_OWN" | awk '{print "  " $0}'
    git add -A
    msg="update: $(git diff --cached --name-only | tr '\n' ' ' | sed 's/ *$//')"
    git commit -m "${msg:0:200}" || warn "nothing to commit in main repo"
    MAIN_COMMITTED=true
    ok "main repo committed"
  else
    info "  only submodule pointer changes, handled later"
  fi
else
  info "  no changes"
fi

# ============================================================
#  Step 2: commit all changed submodules
# ============================================================
COMMITTED_SUB=()
for subpath in $SUB_PATHS; do
  [[ ! -d "$subpath" ]] && continue

  has_changes=$(git -C "$subpath" status --porcelain 2>/dev/null || true)
  [[ -z "$has_changes" ]] && continue

  info "processing submodule $subpath..."

  sub_branch=$(git -C "$subpath" branch --show-current 2>/dev/null || true)
  if [[ -z "$sub_branch" ]]; then
    info "  detached HEAD -> checkout main"
    git -C "$subpath" checkout main 2>/dev/null || {
      warn "  no 'main' branch, skipping $subpath"; continue
    }
    sub_branch="main"
  fi

  git -C "$subpath" add -A
  msg="update: $(git -C "$subpath" diff --cached --name-only | head -5 | tr '\n' ' ' | sed 's/ *$//')"
  git -C "$subpath" commit -m "${msg:0:200}" || { warn "  nothing to commit"; continue; }
  sub_commit="$(git -C "$subpath" rev-parse --short HEAD)"

  if ! git -C "$subpath" push origin "$sub_branch" 2>/dev/null; then
    info "  non-fast-forward, rebasing..."
    git -C "$subpath" pull --rebase origin "$sub_branch"
    git -C "$subpath" push origin "$sub_branch"
  fi

  ok "  $subpath committed & pushed ($sub_commit)"
  COMMITTED_SUB+=("$subpath")
done

# ============================================================
#  Step 3: update main repo submodule pointers & push
# ============================================================
if [[ ${#COMMITTED_SUB[@]} -gt 0 ]]; then
  info "updating submodule pointers..."
  for subpath in "${COMMITTED_SUB[@]}"; do git add "$subpath"; done
  git commit -m "chore: update submodule pointers"
  MAIN_COMMITTED=true
fi

if $MAIN_COMMITTED; then
  git push origin "$BRANCH"
  echo ""
  ok "git-tool commit complete — pushed to $BRANCH"
  git log --oneline -1 --no-decorate | xargs -I{} echo "   HEAD: {}"
else
  echo ""
  ok "nothing to commit — main repo and all submodules up to date"
fi
