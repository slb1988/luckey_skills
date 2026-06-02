---
name: skill-harvest
title: Post-Task Knowledge Harvest
description: 任务结束后，从会话中提取结构性/架构性知识（继承链、正确 API、配置配对、扩展点模式）并写入对应 SKILL.md。用户说"整理到SKILL.md"、"document this"、"add to skill"、"总结一下"时触发；也在发现类层次、API 表面、配置耦合等知识后主动触发。只捕获"系统如何工作"，不记录错误日志或调试过程。
tags: [Documentation, SKILL-md, Knowledge-Management, ProjectLungfish, Workflow, Post-Task]
disable-model-invocation: true
---

# Post-Task Knowledge Harvest

## The core filter

Before writing anything, ask: **"Does this describe how the system works?"**

If yes → harvest it.
If it describes what went wrong and how it was fixed → skip it.

The fix that forced a discovery is not the knowledge. The system property that made the fix necessary is.

| Harvest (knowledge) | Skip (experience) |
|---|---|
| `UDynamicEntryBoxBase` inherits `UWidget`, not `UPanelWidget`; children via `GetAllEntries()` | "Got C2027 because the container header only forward-declares the type" |
| CommonUI must appear in both `Build.cs` AND `.uplugin` `"Plugins"` array | "Had to p4 edit before writing" |
| `UCommonActivatableWidgetStack` only activates the top entry; `IsVisible()` returns false for the rest | "First tried Cast<UPanelWidget>, it didn't work" |
| Branch table showing all 4 `ForWidgetAndChildren` cases and their APIs | "Tried a few approaches before landing on this" |

## What belongs (harvest these)

- **Inheritance chains** that aren't obvious from the type name — especially when the natural assumption is wrong
- **The correct API** for a container type and why the obvious one doesn't apply
- **Configuration pairings** that must stay in sync (Build.cs + .uplugin, includes that must come as a pair, etc.)
- **Extension point shapes** — "to add a 5th case to this pattern, follow this structure"
- **Design intent** — why a subsystem works a certain way; what constraint drives a non-obvious API choice

## What to skip

- Error messages and their resolution steps
- Debugging dead ends
- Operational friction (file checkout, permission issues, etc.)
- Generic UE knowledge covered in official docs
- Anything directly readable from the current code without context

**Second test:** "Would a new engineer reading only this section understand how this subsystem works?" If the answer is "they'd understand what to avoid but not how it works" — rewrite from the system's perspective.

## Thematic alignment

Only harvest knowledge directly related to the session's main topic. A session about widget tree traversal → document the widget container type hierarchy. Tangential modules briefly touched → skip unless the discovery is substantial and standalone.

## Finding the right SKILL.md

Check `SKILL.index.json` for the tightest-fit file. Write at the narrowest scope that applies; don't duplicate across tiers.

| Scope | File |
|---|---|
| Specific plugin | `Main/Plugins/<Plugin>/SKILL.md` |
| Cross-plugin UMG/UI pattern | `Main/Plugins/SKILL.md` |
| Engine or Marketplace code | `Engine/SKILL.md` |
| Game-level pattern | `Main/SKILL.md` |

## Format patterns

Choose the format that makes the knowledge most skimmable:

**API/branch table** — for "which API to use for which type":
```markdown
| Branch | Cast target | API | Covers |
|---|---|---|---|
| 3 | `UDynamicEntryBoxBase` | `GetAllEntries()` | UUIExtensionPointWidget, any dynamic entry box |
| 4 | `UCommonActivatableWidgetContainerBase` | `GetWidgetList()` | Stack, Queue |
```

**Inheritance note** — for non-obvious class relationships:
```markdown
`UDynamicEntryBoxBase` → `UWidget` (not `UPanelWidget`). Active entries live in a
private `FUserWidgetPool`; use `GetAllEntries()` — `GetChildAt()` doesn't exist.
```

**Configuration pairing** — for deps that must stay in sync:
```markdown
Build.cs dep: `"CommonUI"`. Also required in `.uplugin` `"Plugins"` array — plugin-level
dependency wiring is separate from module-level. Missing either causes a warning or load failure.
```

**Include chain** — when two headers are needed for one type:
```cpp
#include "Widgets/FooContainer.h"  // UFooContainer (forward-declares UFooItem)
#include "FooItem.h"               // Full definition needed to call UFooItem methods
```

## Workflow

1. **Identify the session topic** and what structural knowledge it revealed
2. **Draft in bullet form**, then compress into the right format above
3. **Check out and update**: `p4 edit "<path>"`, append to the most relevant existing section (or add a new "Patterns" / "Architecture" section)
4. **Include SKILL.md in the same P4 CL as the code changes** (CLAUDE.md Rule 5)

## SKILL.md Length Budget

Target SKILL.md files to **≤ 200 lines**. When a file approaches this limit:

- Move large reference sections (detailed API tables, extended examples, full command lists) to `references/<topic>.md` in the same directory
- Keep a one-line pointer in SKILL.md: `> 详细参考：[topic](references/topic.md)`
- The SKILL.md body must stay skimmable at a glance — if reading it takes more than 2 minutes, it's too long

If a file already exceeds 200 lines when you harvest, split it as part of the harvest commit rather than making it longer.
