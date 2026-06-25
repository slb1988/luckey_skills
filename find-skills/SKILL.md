---
name: find-skills
description: Helps users discover and install agent skills from the open ecosystem. Use when users ask how to do X, want to find a skill, or want to extend capabilities.
---

# Find Skills

This skill helps you discover and install skills from the open agent skills ecosystem.

## When to Use This Skill

Use this skill when the user:

- Asks "how do I do X" where X might be a common task with an existing skill
- Says "find a skill for X" or "is there a skill for X"
- Asks "can you do X" where X is a specialized capability
- Wants to search for tools, templates, or workflows

## Skills CLI

The Skills CLI (`npx skills`) is the package manager for the open agent skills ecosystem.

**Key commands:**

- `npx skills find [query]` - Search for skills by keyword
- `npx skills add <package>` - Install a skill from GitHub or other sources
- `npx skills add <package> -g -y` - Install globally without confirmation
- `npx skills check` - Check for skill updates
- `npx skills update` - Update all installed skills

**Browse skills at:** https://skills.sh/

## How to Help Users Find Skills

### Step 1: Understand What They Need

Identify the domain (e.g., React, testing, deployment) and specific task.

### Step 2: Search for Skills

```bash
npx skills find [query]
```

Examples:
- "make React app faster" -> `npx skills find react performance`
- "help with PR reviews" -> `npx skills find pr review`
- "create a changelog" -> `npx skills find changelog`

### Step 3: Present and Install

When you find relevant skills, present them with the install command:

```bash
npx skills add <owner/repo@skill> -g -y
```

### When No Skills Are Found

1. Acknowledge no existing skill was found
2. Offer to help directly with general capabilities
3. Suggest creating a custom skill: `npx skills init my-skill`
