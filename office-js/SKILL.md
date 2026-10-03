---
name: office-js
description: >
  Office JS API cookbook for writing code in office_excel_execute, office_word_execute, and office_ppt_execute tools.
  Use this skill whenever the AI needs to write Office.js code to manipulate Excel, Word, or PowerPoint documents
  through the Office Add-in. Covers the async request-context pattern, property loading, and common operations
  with working code examples.
---

# Office JS API Cookbook

**Prefer the dedicated Office tools when one fits** — they're more reliable than hand-written code:
`office_excel_insert_formula` / `office_excel_create_chart` / `office_excel_format_range` / `office_excel_add_worksheet`,
`office_word_insert_paragraph` / `office_word_replace_text` / `office_word_insert_table`,
`office_ppt_add_slide` / `office_ppt_insert_textbox` / `office_ppt_get_slide_count`.
Reach for `office_*_execute` (this cookbook) only for operations those tools don't cover.

This skill provides patterns and examples for writing code that runs inside `office_*_execute` tools.
Your code runs inside `*.run(async context => { ... })` — you receive `context` and must call `await context.sync()` before reading loaded properties.

## Critical Rules

1. **Always `load()` before reading** — properties are proxy objects until loaded
2. **Always `context.sync()` after load** — sends the request to Office
3. **Return a string** — the result must be a string (use `JSON.stringify` for objects)
4. **No top-level import/require** — you're inside a function body, not a module
5. **`context.sync()` is expensive** — batch operations, minimize sync calls

```javascript
// PATTERN: load → sync → read
const sheet = context.workbook.worksheets.getActiveWorksheet();
sheet.load("name");
await context.sync();
// NOW sheet.name is available
return sheet.name;
```

---

## Choose the application cookbook

Before writing execute-tool code, load only the matching reference. Each contains the full object model and working examples; the common rules above apply to all three.

| Tool | Entry point | Required reference |
|---|---|---|
| `office_excel_execute` | `context.workbook` | [Excel: ranges, tables, formulas, charts, formatting, worksheets](references/excel.md) |
| `office_word_execute` | `context.document` + `Word` namespace | [Word: insertion, formatting, tables, search/replace, page breaks](references/word.md) |
| `office_ppt_execute` | `context.presentation` + `PowerPoint` namespace | [PowerPoint: points, colors, slides, shapes and text](references/powerpoint.md) |

---

# Common Patterns

## Error Handling

```javascript
try {
  // your operations...
  await context.sync();
  return "Success";
} catch (error) {
  if (error instanceof OfficeExtension.Error) {
    return "Office error: " + error.code + " - " + error.message;
  }
  return "Error: " + error.message;
}
```

## Batch Operations (minimize sync calls)

```javascript
// BAD: sync inside loop
for (const name of names) {
  const sheet = context.workbook.worksheets.add(name);
  await context.sync(); // Don't do this!
}

// GOOD: batch then sync
for (const name of names) {
  context.workbook.worksheets.add(name);
}
await context.sync(); // One sync for all
```

## Loading Collection Items

```javascript
// Load collection
const items = context.workbook.worksheets;
items.load("items/name");  // Load name property of each item
await context.sync();

// Now iterate
for (const item of items.items) {
  console.log(item.name); // Available
}
```
