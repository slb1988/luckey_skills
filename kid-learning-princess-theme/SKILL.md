---
name: kid-learning-princess-theme
description: Design or implement child-facing kid-learning-journey interfaces with the approved fresh princess-castle visual system, including character/UI integration, responsive behavior, and learning-focused motion. Use for its Web, Pad, phone, Android, prototype, and visual-asset work; do not apply this theme to parent/admin or Memory Hub infrastructure screens.
metadata:
  short-description: 同步公主学习产品的视觉、角色、组件与响应式动效语言
---

# Kid Learning Princess Theme

Preserve the approved A v3 direction: a fresh morning princess-castle world that feels polished, playful, feminine, and inviting without turning study into a noisy toy or reward economy.

Before creating, changing, or reviewing a child-facing visual, read [references/theme-system.md](references/theme-system.md). It is the canonical source for tokens, character composition, page-specific decoration levels, motion, responsive behavior, and acceptance checks.

## Scope

Apply this theme to the child experience of `kid-learning-journey`: today/home, math practice, phonics, story reading, word collection, mistake review, progress celebrations, and related visual assets.

Do not automatically apply it to parent dashboards, content administration, observability, A2A ingestion, Flask APIs, or Memory Hub interfaces. Those surfaces may share product naming but need a denser adult-facing system.

## Non-negotiable decisions

- Treat characters as layout participants, not rectangular illustrations pasted into cards. Use separate background and transparent character layers; connect a pose, gaze, or movement to a nearby action.
- Keep learning content primary. Home and completion may be expressive; math questions become quiet and high-contrast; reading companions stay near the story or word card.
- Use rewards only to explain genuine learning progress. Do not add coins, diamonds, random chests, energy, streak pressure, rankings, or attention traps.
- Preserve readability and reachability: child-facing body text is at least 16 px, important targets are at least 44×44 px, and decorative layers do not intercept pointer events.
- Support desktop, Pad, and 390×844 mobile layouts. Reposition characters instead of merely shrinking the desktop composition; never crop a face or cover a label, answer, or button.
- Respect `prefers-reduced-motion`; interaction must remain understandable with animation disabled.

## Working agreement

Use the current A v3 prototype and screenshots as the visual baseline when they exist in the workspace. Preserve an approved version before a substantial redesign. For implementation work, expose the theme through shared tokens/components rather than duplicating ad-hoc color and spacing values across pages.

When visual behavior changes, verify the relevant interaction states and capture both desktop and mobile output. A passing DOM test does not replace visual inspection of character overlap, cropping, contrast, or focus density.
