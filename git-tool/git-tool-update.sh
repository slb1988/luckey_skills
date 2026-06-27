#!/bin/bash
# git-tool-update.sh — sync main repo + all submodules in one shot
# Usage: bash .claude/skills/git-tool/git-tool-update.sh
set -euo pipefail

ROOT="$(cd "$(git rev-parse --show-toplevel 2>/dev/null)" && pwd)" || {
  echo "[ERROR] not in a git repo"; exit 1
}
cd "$ROOT"
REPO="$(git rev-parse --short HEAD 2>/dev/null)"
BRANCH="$(git branch --show-current 2>/dev/null)" || BRANCH="main"

info()  { echo "[INFO] $*"; }
ok()    { echo "[ OK ] $*"; }
warn()  { echo "[WARN] $*"; }

# ---- Step 1: stash tracked changes (if any) ----
info "check main repo working tree..."
STASHED=false
SUB_PATHS=$(git config --file .gitmodules --get-regexp path 2>/dev/null | awk '{print $2}' || true)

HAS_TRACKED=false
while IFS= read -r line; do
  [[ -z "$line" || "$line" =~ ^\?\? ]] && continue
  p="${line:3}"
  echo "$SUB_PATHS" | grep -qxF "$p" && continue
  HAS_TRACKED=true
  break
done < <(git status --porcelain)

if $HAS_TRACKED; then
  warn "tracked changes found, auto-stashing..."
  git stash push --include-untracked -m "git-tool-update auto-stash $(date +%Y%m%d-%H%M%S)"
  STASHED=true
else
  ok "working tree clean"
fi

# ---- Step 2: pull main repo ----
info "pulling $BRANCH..."
if git pull --rebase origin "$BRANCH" 2>/dev/null; then
  ok "main repo updated (rebase)"
else
  warn "rebase failed, retrying with --no-rebase..."
  git pull --no-rebase origin "$BRANCH"
  ok "main repo updated (no-rebase)"
fi

# ---- Step 3: init + update submodules ----
info "initializing submodules..."
git submodule update --init --recursive

info "updating all submodules to latest remote..."
if ! git submodule update --remote --merge --recursive 2>/dev/null; then
  warn "partial failure, retrying nested submodules..."
  for parent in .claude/skills; do
    [[ -d "$parent" ]] && git -C "$parent" submodule update --init --recursive 2>/dev/null || true
  done
  git submodule update --remote --merge --recursive
fi
ok "all submodules updated"

# ---- Step 4: commit pointer changes ----
POINTER_CHANGED=false
for subpath in $SUB_PATHS; do
  [[ ! -d "$subpath" ]] && continue

  # warn if submodule has internal tracked changes (user must handle)
  dirty=$(git -C "$subpath" status --porcelain | grep -v '^??' || true)
  if [[ -n "$dirty" ]]; then
    warn "submodule $subpath has tracked changes (handle manually):"
    echo "$dirty" | sed 's/^/  /'
  fi

  recorded=$(git ls-tree HEAD "$subpath" 2>/dev/null | awk '{print $3}' || true)
  current=$(git -C "$subpath" rev-parse HEAD 2>/dev/null || true)
  [[ -z "$recorded" || -z "$current" || "$recorded" == "$current" ]] && continue

  git add "$subpath"
  POINTER_CHANGED=true
  ok "submodule $subpath pointer: ${recorded:0:7} -> ${current:0:7}"
done

# ---- Step 5: commit + push ----
if $POINTER_CHANGED; then
  git commit -m "chore: update submodules to latest"
  git push origin "$BRANCH"
  ok "submodule pointers committed and pushed to $BRANCH"
else
  ok "all submodules up to date, nothing to commit"
fi

# ---- Step 6: restore stash ----
if $STASHED; then
  info "restoring stash..."
  git stash pop
  ok "stash restored"
fi

echo ""
ok "git-tool update complete (HEAD: $(git log --oneline -1 --no-decorate 2>/dev/null || true))"
