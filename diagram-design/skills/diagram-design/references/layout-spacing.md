# Layout, spacing and summary cards

Read before positioning nodes or adding summary cards. Complexity budgets and the taste gate remain in [SKILL.md](../SKILL.md).

### 4px grid

**Primary node frames, layout padding and inter-node gaps use a 4px grid.** Typography and primitive geometry have explicit exceptions; do not change the approved style to force every number onto the grid.

| Category | Allowed values |
|---|---|
| Font sizes | Follow [style-guide.md](style-guide.md) and the selected output size; includes 7px tags, 9px sublabels and 14px asides |
| Node width / height | 80, 96, 112, 120, 128, 140, 144, 160, 180, 200, 240, 320 |
| Primary node x / y coordinates | multiples of 4 |
| Gap between nodes | 20, 24, 32, 40, 48 |
| Padding inside boxes | 8, 12, 16 |
| Border radius (exception) | 4, 6, 8; tag/mask rx=2 |

Exempt: typography, text baselines and optical centering, label masks and the mandatory 6–10px connector gap, markers, fan-out attachment calculations, legend offsets, card dots, stroke widths (0.8, 1, 1.2), opacity values, and the 22×22 dot-pattern. These follow their own rules in [SVG primitives](svg-primitives.md) and [SKILL.md §6](../SKILL.md#6-core-svg-primitives).

Quick check: for a primary node frame coordinate or dimension, use `value % 4 == 0`; do not apply this test to the exceptions above.

### Page layout

1. **Header** — eyebrow (Geist Mono), title (Instrument Serif), optional subtitle (Geist muted).
2. **Diagram container** — default: **clean, borderless**, no background — the SVG sits directly on the page paper. Optional *framed* variant (for card-heavy layouts or hero placements): `paper-2` bg + 1px `rule` border + 8px radius + `1.5rem` padding + `overflow-x: auto`.
3. **Summary cards** — 2–3 col grid with *varied* widths (e.g., `1.1fr 1fr 0.9fr`).
4. **Footer** — colophon in Geist Mono, muted, hairline top border.

---

## 8. Summary Card Pattern

Don't use 3 identical generic cards. Vary the treatment:

```html
<div class="card">
  <p class="eyebrow">SECTION LABEL</p>
  <div class="card-header">
    <span class="card-dot coral"></span>
    <h3>Card Title</h3>
  </div>
  <ul><li>Item</li></ul>
</div>
```

Rules:

- `background: #ffffff` (not paper — slight lift without shadow)
- `border: 1px solid rgba(45,49,66,0.12)`
- `border-radius: 6px`, `padding: 1.25rem`
- **No `box-shadow`**
- Card dots: 7px, `border-radius: 50%` — ink / muted / coral / link / soft variants
