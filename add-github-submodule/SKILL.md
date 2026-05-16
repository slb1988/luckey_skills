---
name: add-github-submodule
title: Add GitHub Submodule
description: Adds a GitHub repository as a git submodule to the luckey_skills repo root, then commits the result. Use this skill whenever the user provides a GitHub URL and asks to add it as a submodule, clone it into the repo, or reference it as a sub-repo. Triggers on phrases like "添加子仓库", "添加 github 子仓库引用", "add submodule", "git clone into repo", "add this GitHub repo", or any GitHub URL accompanied by an intent to track it in this repo.
tags: [git, submodule, github, workflow]
---

# Add GitHub Submodule

> Layer: Tier 2 (Workflow Skill)

## Purpose

Adds a GitHub repo as a tracked git submodule at the root of `luckey_skills`, keeps `.gitmodules` and `submodules.md` in sync, and commits atomically.

---

## When to Use

- User pastes a GitHub URL and says to add / clone / reference it
- Phrases: "添加子仓库", "添加 github 子仓库引用", "add submodule", "add this repo"

---

## Workflow

### Step 1 — Derive local name

Extract the repo name from the URL: last path segment, strip `.git` suffix if present.

```
https://github.com/EA-Studio-SHARK/ai-morning-brief  →  ai-morning-brief
https://github.com/foo/bar.git                        →  bar
```

### Step 2 — Check for conflicts

```bash
ls <repo-name>
```

If the directory already exists as a stale leftover, clean it up first:

```bash
git submodule deinit <repo-name>   # may error if not registered — that's fine
git rm <repo-name>                 # may error if not staged — that's fine
rm -rf <repo-name>
```

### Step 3 — Add submodule

```bash
git submodule add <url> <repo-name>
```

### Step 4 — Verify staging

```bash
git status
```

Confirm `.gitmodules` and `<repo-name>` both appear under "Changes to be committed".

### Step 5 — Update submodules.md

Append a row to the table in `submodules.md`:

```
| `<repo-name>` | <url> |
```

### Step 6 — Commit

```bash
git commit -m "$(cat <<'EOF'
add <repo-name> submodule

Co-Authored-By: Claude Sonnet 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Rules

- **Root only**: always add to the repo root unless the user explicitly specifies a different path. Never use `.claude/skills/` or any subdirectory by default.
- **Sync submodules.md**: always update the table in `submodules.md` in the same commit.
- **One commit**: stage `.gitmodules`, `<repo-name>`, and `submodules.md` together before committing.
- **Co-author footer**: always include the `Co-Authored-By` line in the commit message.

---

## Example

User says:
> 添加 github 子仓库引用 git clone https://github.com/EA-Studio-SHARK/ai-morning-brief

Steps executed:
```bash
git submodule add https://github.com/EA-Studio-SHARK/ai-morning-brief ai-morning-brief
# → update submodules.md table
git commit -m "add ai-morning-brief submodule

Co-Authored-By: Claude Sonnet 4.6 (1M context) <noreply@anthropic.com>"
```
