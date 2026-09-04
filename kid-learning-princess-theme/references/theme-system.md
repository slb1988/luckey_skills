# Princess Learning Theme System

## 1. Approved direction

The child experience is a fresh daytime princess learning castle: sky blue, cherry pink, lavender, mint, cream, sunlit gardens, friendly original storybook characters, and a small amount of jewel-like detail. The intended feeling is polished animated-family storytelling rather than a generic pink dashboard, a dark fantasy game, or a preschool toy shelf.

The theme should appeal to a girl who enjoys princess stories and beautiful objects while remaining usable through primary school. Avoid baby talk, visual clutter, and decoration that competes with a problem or sentence.

Within the ObsidianVault planning workspace, the selected visual references are:

- Interactive baseline: `.claude/plans/memory-design/kid-learning-journey/design-demos/01-princess-magic-school-v3.html`
- Desktop baseline: `.claude/plans/memory-design/kid-learning-journey/design-demos/screenshots/01-princess-magic-school-v3-desktop.png`
- Mobile baseline: `.claude/plans/memory-design/kid-learning-journey/design-demos/screenshots/01-princess-magic-school-v3-mobile.png`
- Direction approval: `.claude/plans/memory-design/kid-learning-journey/direction-approved.md`

These files demonstrate the direction; they are not a requirement to copy the prototype DOM or fixed pixel positions into production.

## 2. Color roles

Use role-based tokens. Small hue adjustments are allowed for a new medium, but preserve the hierarchy and contrast.

```css
:root {
  --kl-canvas: #f9fdff;
  --kl-sky: #eefaff;
  --kl-surface: #fffefd;
  --kl-ink: #453657;
  --kl-muted: #75677f;

  --kl-pink: #ff6faf;
  --kl-pink-strong: #d94c8d;
  --kl-pink-soft: #ffe1ef;
  --kl-violet: #8b69d9;
  --kl-violet-soft: #eee7ff;
  --kl-mint: #65cdb7;
  --kl-mint-soft: #def8f1;
  --kl-sun: #ffd66e;
  --kl-line: #dbeaf2;

  --kl-shadow-card: 0 22px 55px rgba(68, 111, 144, 0.16);
  --kl-shadow-action: 0 8px 0 #c6407f, 0 15px 26px rgba(217, 76, 141, 0.22);
}
```

- Use pink for the principal action, progress, selected word, and celebratory emphasis—not for every surface.
- Use violet for navigation and learning structure; mint for reading, correct answers, and calm support; yellow for small achievement cues.
- Keep long text on `--kl-surface` or another pale background using `--kl-ink`/`--kl-muted`. Never put essential pale-pink text on white.
- Avoid full-screen purple–pink–blue gradients. Gradients may add subtle material depth inside one button or card.

## 3. Typography, shape, and spacing

- Display text: a licensed rounded Chinese face or system fallback with friendly shapes. Use roughly 800–900 weight, tight but not touching letter spacing, and 1.1–1.2 line height.
- Body text: a clear screen sans-serif. Child-facing normal text starts at 16 px; supporting metadata may be 12–14 px when it is not instructional.
- Numeric problems: large, stable tabular numerals. A primary equation should be the strongest object in a practice screen.
- Hero radius: 32–36 px desktop, 26–28 px mobile. Task card radius: about 28 px with one subtly asymmetric corner. Primary button radius: about 18–20 px.
- Prefer one clear card shadow and a small pressed-button lower edge. Avoid glass effects on reading and practice content.
- Maintain generous whitespace around equations and sentences. Decoration may occupy empty space but must not reduce the content measure.

## 4. Character and layout integration

Build a scene from layers whenever characters are used:

1. Environment/background: castle, garden, sky, book room, or an abstract learning room.
2. Interface/content: headings, progress, task cards, questions, and controls.
3. Transparent character/prop cutouts: anchored to a particular container or control.
4. Short-lived effect layer: stars, glow, or ribbon motion triggered by a real interaction.

Character placement should satisfy at least one concrete relationship:

- A hand, gaze, wand, or trail guides attention to the next action.
- A companion grips or peeks over a task/story card edge.
- A character carries an earned sticker into the collection area.
- A hint character occupies the explanation rail while leaving the question area untouched.

Practical rules:

- Put decorative cutouts on `pointer-events: none` and provide meaningful alt text only when the role conveys information; otherwise use an empty alt.
- Anchor cutouts to the component they interact with, not to the viewport. Allow about 8–20% boundary overlap when it improves depth.
- Give faces, hands, and important props clean silhouettes. Do not crop a crown, eyes, fingers that indicate an action, or the item being carried.
- Recompose at breakpoints. On mobile, move a hero character below the copy/CTA or to a safe lower corner; reduce secondary decorations before shrinking instructional content.
- Do not repeat the same full character several times on one screen. One leading character plus one small companion is normally enough.
- Original generic fairytale characters and environments are the production-safe default. Never add an official logo or present the product as an authorized Disney product; reassess all assets before public or commercial release.

## 5. Decoration level by learning state

| State | Character presence | Background/detail | Primary goal |
|---|---:|---:|---|
| Today/home | High | Cinematic but airy | Invite the first action and show the short journey |
| Math/quiz | Low | Quiet white focus card | Make the problem and answer choices dominant |
| Phonics | Medium-low | Color may explain sounds | Connect sound, mouth/ear cue, and grapheme |
| Story/word card | Medium | Warm page plus mint drawer | Keep sentence context and word action together |
| Mistake review | Low | Calm, non-punitive | Explain the misconception and next practice |
| Completion/growth | High for a short moment | Castle/collection visible | Name the mastered skill and why the reward unlocked |

Do not treat an error as a sad character event. Give an actionable hint, preserve dignity, and keep language neutral: “差一点，看看 8 还差几个变成 10？” rather than a failure label.

## 6. Motion language

- Hover/press response: 150–250 ms using transform, opacity, or shadow.
- Character acknowledgement: 250–400 ms, typically a 4–8 px lean, rise, or turn tied to the associated control.
- Correct answer or collected word: one 500–800 ms pop/bounce plus a concise text response.
- Completion celebration: below 1.5 seconds and never required before continuing.
- Do not move a click target after the user begins aiming at it. Avoid looping motion near an active equation or sentence.
- With reduced motion, keep state color, icon, and text feedback while collapsing animation duration.

## 7. Content and gamification tone

- Speak warmly and specifically: “你让 8 先变成了 10” is better than “太棒了！+100”.
- Make time estimates small and non-threatening. Accuracy and understanding outrank speed comparisons.
- Unlock a room, window, illustration, or sticker only when a named skill or reading action is completed; explain the reason.
- Use story metaphors to organize learning, not to conceal the task. A child should always know whether she is doing math, phonics, reading, or review.

## 8. Responsive and accessibility checks

At minimum, inspect 1440×900 desktop and 390×844 mobile. Include a Pad-width check when the layout or character composition changes.

- No horizontal overflow.
- No character covers a heading, answer, word, progress value, or button label.
- Faces and action-signaling hands remain visible.
- Tap targets are at least 44×44 px with visible keyboard focus.
- Text and status do not depend only on color.
- Bottom navigation does not permanently hide the next actionable content; reserve safe-area/padding space.
- The page remains understandable with images unavailable and with reduced motion enabled.

## 9. Implementation and review checklist

- Use shared theme tokens and reusable child-facing components; avoid page-local copies of the palette.
- Keep the Flask/API layer independent of visual theme choices.
- For generated art, retain the final prompt and project-local asset path. Prefer transparent PNG/WebP character cutouts and a separate background.
- Preserve the last approved prototype before a major visual revision.
- Exercise the primary journey: today → task → answer/read → feedback → collection/completion.
- Capture desktop and mobile results after transitions finish, then visually inspect them; zero runtime errors alone is insufficient.
