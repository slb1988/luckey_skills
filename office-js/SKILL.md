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

# Excel API (office_excel_execute)

Your code receives `context` (Excel.RequestContext). Key entry point: `context.workbook`.

## Object Model

```
context.workbook
  .worksheets                    → WorksheetCollection
    .getActiveWorksheet()        → Worksheet
    .getItem("Sheet1")           → Worksheet
    .add("NewSheet")             → Worksheet
  .tables                       → TableCollection
  .names                        → NamedItemCollection
  .getSelectedRange()           → Range
```

```
Worksheet
  .name, .id, .position, .visibility
  .getRange("A1:C10")           → Range
  .getUsedRange()               → Range
  .charts                       → ChartCollection
  .tables                       → TableCollection
  .delete()
  .activate()
```

```
Range
  .values          → any[][]      (read/write)
  .formulas        → string[][]   (read/write)
  .numberFormat    → string[][]   (read/write)
  .text            → string[][]   (read-only, formatted text)
  .address         → string
  .rowCount, .columnCount
  .format          → RangeFormat
    .font          → { bold, italic, color, size, name }
    .fill          → { color }
    .borders       → RangeBorderCollection
    .horizontalAlignment, .verticalAlignment
  .getCell(row, col)             → Range
  .getColumn(col)                → Range
  .getRow(row)                   → Range
  .getResizedRange(deltaRows, deltaCols) → Range
  .insert(shift)                 → Range
  .delete(shift)
  .merge(), .unmerge()
  .clear(applyTo?)
  .getEntireColumn(), .getEntireRow()
```

## Examples

### Read and write ranges

```javascript
const sheet = context.workbook.worksheets.getActiveWorksheet();
const range = sheet.getRange("A1:B3");
range.values = [
  ["Name", "Score"],
  ["Alice", 95],
  ["Bob", 87]
];
range.format.font.bold = true;
range.getRow(0).format.fill.color = "#4472C4";
range.getRow(0).format.font.color = "#FFFFFF";
await context.sync();
return "Data written";
```

### Read used range

```javascript
const sheet = context.workbook.worksheets.getActiveWorksheet();
const used = sheet.getUsedRange();
used.load("values,address,rowCount,columnCount");
await context.sync();
return JSON.stringify({
  address: used.address,
  rows: used.rowCount,
  cols: used.columnCount,
  data: used.values
});
```

### Create chart

```javascript
const sheet = context.workbook.worksheets.getActiveWorksheet();
const range = sheet.getRange("A1:B5");
const chart = sheet.charts.add(Excel.ChartType.columnClustered, range, Excel.ChartSeriesBy.columns);
chart.title.text = "Sales Report";
chart.setPosition("D1", "K15");
chart.legend.position = Excel.ChartLegendPosition.bottom;
await context.sync();
return "Chart created";
```

### Create table with formatting

```javascript
const sheet = context.workbook.worksheets.getActiveWorksheet();
const table = sheet.tables.add("A1:D1", true);
table.name = "SalesTable";
table.getHeaderRowRange().values = [["Product", "Q1", "Q2", "Q3"]];
table.rows.add(null, [["Widget A", 100, 150, 200]]);
table.rows.add(null, [["Widget B", 80, 120, 160]]);
table.style = "TableStyleMedium2";
sheet.getUsedRange().format.autofitColumns();
await context.sync();
return "Table created";
```

### Formulas and number formatting

```javascript
const sheet = context.workbook.worksheets.getActiveWorksheet();
sheet.getRange("A1").values = [["Revenue"]];
sheet.getRange("A2").values = [[50000]];
sheet.getRange("A3").values = [["Tax"]];
sheet.getRange("A4").formulas = [["=A2*0.1"]];
sheet.getRange("A2").numberFormat = [["$#,##0"]];
sheet.getRange("A4").numberFormat = [["$#,##0"]];
await context.sync();
return "Formulas set";
```

### Conditional formatting

```javascript
const sheet = context.workbook.worksheets.getActiveWorksheet();
const range = sheet.getRange("B2:B10");
const cf = range.conditionalFormats.add(Excel.ConditionalFormatType.cellValue);
cf.cellValue.format.font.color = "#FF0000";
cf.cellValue.rule = {
  formula1: "=0",
  operator: Excel.ConditionalCellValueOperator.lessThan
};
await context.sync();
return "Conditional format added";
```

### Iterate worksheets

```javascript
const sheets = context.workbook.worksheets;
sheets.load("items/name");
await context.sync();
const names = sheets.items.map(s => s.name);
return JSON.stringify(names);
```

### Auto-fit and freeze panes

```javascript
const sheet = context.workbook.worksheets.getActiveWorksheet();
sheet.getUsedRange().format.autofitColumns();
sheet.freezePanes.freezeRows(1);
await context.sync();
return "Done";
```

---

# Word API (office_word_execute)

Your code receives `context` (Word.RequestContext) and `Word` namespace. Key entry point: `context.document`.

## Object Model

```
context.document
  .body                          → Body
  .getSelection()                → Range
  .sections                     → SectionCollection
  .contentControls               → ContentControlCollection
  .properties                    → DocumentProperties
  .save()
```

```
Body / Range / Paragraph
  .text                          → string (read-only, load first)
  .font                          → Font { bold, italic, color, size, name, underline, highlightColor }
  .insertParagraph(text, loc)    → Paragraph     (loc: "Start"|"End"|"Before"|"After")
  .insertText(text, loc)         → Range
  .insertBreak(type, loc)
  .insertTable(rows, cols, loc, values?) → Table
  .insertHtml(html, loc)         → Range
  .insertInlinePictureFromBase64(base64, loc) → InlinePicture
  .search(text, opts)            → RangeCollection
  .paragraphs                    → ParagraphCollection
  .clear()
```

```
Paragraph
  .text, .font, .alignment
  .style                         → string (read/write, e.g. "Heading1")
  .insertText(), .insertParagraph(), .delete()
  .listItem                      → ListItem (for bulleted/numbered lists)
```

```
Table
  .rows                          → TableRowCollection
  .getCell(rowIndex, cellIndex)  → TableCell
  .addRows(loc, count, values?)
  .addColumns(loc, count, values?)
  .style                         → string
  .headerRowCount
```

## Insert Location Constants

Use `Word.InsertLocation`:
- `Word.InsertLocation.start` / `Word.InsertLocation.end`
- `Word.InsertLocation.before` / `Word.InsertLocation.after`
- `Word.InsertLocation.replace`

## Examples

### Insert formatted text

```javascript
const body = context.document.body;
const heading = body.insertParagraph("Quarterly Report", Word.InsertLocation.end);
heading.style = "Heading 1";
heading.font.color = "#2E74B5";

const para = body.insertParagraph("This report covers Q1-Q4 results.", Word.InsertLocation.end);
para.font.size = 12;
para.font.name = "Calibri";
await context.sync();
return "Text inserted";
```

### Create a table

```javascript
const body = context.document.body;
const data = [
  ["Product", "Revenue", "Growth"],
  ["Widget A", "$50,000", "+12%"],
  ["Widget B", "$35,000", "+8%"],
];
const table = body.insertTable(data.length, data[0].length, Word.InsertLocation.end, data);
table.style = "Grid Table 4 - Accent 1";
table.headerRowCount = 1;
table.getCell(0, 0).body.font.bold = true;
table.getCell(0, 1).body.font.bold = true;
table.getCell(0, 2).body.font.bold = true;
await context.sync();
return "Table created";
```

### Search and replace

```javascript
const body = context.document.body;
const results = body.search("old text", { matchCase: false, matchWholeWord: false });
results.load("items");
await context.sync();
for (const r of results.items) {
  r.insertText("new text", Word.InsertLocation.replace);
}
await context.sync();
return `Replaced ${results.items.length} occurrences`;
```

### Read document content

```javascript
const body = context.document.body;
body.load("text");
await context.sync();
return body.text.substring(0, 2000);
```

### Bullet list

```javascript
const body = context.document.body;
const items = ["First point", "Second point", "Third point"];
for (const item of items) {
  const p = body.insertParagraph(item, Word.InsertLocation.end);
  p.style = "List Bullet";
}
await context.sync();
return "Bullet list created";
```

### Insert page break

```javascript
const body = context.document.body;
body.insertBreak(Word.BreakType.page, Word.InsertLocation.end);
body.insertParagraph("New Page Content", Word.InsertLocation.end);
await context.sync();
return "Page break inserted";
```

---

# PowerPoint API (office_ppt_execute)

Your code receives `context` (PowerPoint.RequestContext) and `PowerPoint` namespace. Key entry point: `context.presentation`.

## Object Model

```
context.presentation
  .slides                        → SlideCollection
    .add(options?)               → Slide
    .getItem(id)                 → Slide
    .getItemAt(index)            → Slide
    .getCount()                  → ClientResult<number>
  .slideMasters                  → SlideMasterCollection
  .tags                          → TagCollection
  .getSelectedSlides()           → SlideScopedCollection
  .getSelectedShapes()           → ShapeScopedCollection
  .getSelectedTextRange()        → TextRange
  .setSelectedSlides(slideIds)
```

```
Slide
  .shapes                        → ShapeCollection
    .addTextBox(text)            → Shape
    .addGeometricShape(type)     → Shape
    .addLine(connectorType, opts) → Shape
    .addImage(options)           → Shape
    .getItem(id) / .getItemAt(i) → Shape
    .getCount()                  → ClientResult<number>
  .layout                        → SlideLayout
  .slideMaster                   → SlideMaster
  .tags                          → TagCollection
  .id                            → string
  .delete()
```

```
Shape
  .id, .name
  .left, .top, .width, .height  → number (points, read/write)
  .rotation                      → number (read/write)
  .fill                          → ShapeFill
    .setSolidColor(color)
    .foregroundColor              → string
  .lineFormat                    → ShapeLineFormat
    .color, .weight, .dashStyle, .style
  .textFrame                     → TextFrame
    .textRange                   → TextRange
    .autoSizeSetting
    .wordWrap
    .hasText                     → boolean
    .verticalAlignment
  .type                          → ShapeType
  .delete()
```

```
TextRange
  .text                          → string (read/write)
  .font                          → ShapeFont
    .bold, .italic, .underline   → boolean
    .color                       → string
    .size                        → number
    .name                        → string
  .paragraphFormat               → ParagraphFormat
    .horizontalAlignment         → ParagraphHorizontalAlignment
    .bulletFormat                 → BulletFormat
      .visible                   → boolean
      .style                     → BulletStyle
  .getSubstring(start, length)   → TextRange
```

```
ShapeType enum: unsupported, image, geometricShape, group, line, table, textBox, freeform, ...
GeometricShapeType enum: rectangle, roundedRectangle, ellipse, triangle, diamond, ...
```

## Important Notes

- **Units are in points** (1 inch = 72 points). Slide 16:9 = 720 x 405 points.
- **Adding slides**: `context.presentation.slides.add()` adds at the end. Use `{ layoutId }` to specify layout.
- **No slide.addText()** — add a text box shape first, then set its textFrame.textRange.text.
- **Colors**: Use hex without `#`, e.g. `"FF0000"` for red.

## Examples

### Add slide with title text box

```javascript
const slide = context.presentation.slides.add();
await context.sync();

const title = slide.shapes.addTextBox("Quarterly Results");
title.left = 36;   // 0.5 inch
title.top = 36;
title.width = 648;  // 9 inches
title.height = 54;  // 0.75 inch
title.textFrame.textRange.font.size = 28;
title.textFrame.textRange.font.bold = true;
title.textFrame.textRange.font.color = "2E74B5";
await context.sync();
return "Slide added";
```

### Add multiple text elements to a slide

```javascript
const slide = context.presentation.slides.add();
await context.sync();

// Title
const title = slide.shapes.addTextBox("Project Update");
title.left = 36; title.top = 24; title.width = 648; title.height = 50;
title.textFrame.textRange.font.size = 32;
title.textFrame.textRange.font.bold = true;

// Subtitle
const subtitle = slide.shapes.addTextBox("Sprint 14 Summary - Week of March 10");
subtitle.left = 36; subtitle.top = 80; subtitle.width = 648; subtitle.height = 30;
subtitle.textFrame.textRange.font.size = 14;
subtitle.textFrame.textRange.font.color = "888888";

// Body content
const body = slide.shapes.addTextBox(
  "Completed 12 user stories\nFixed 8 critical bugs\nDeployed v2.4 to production\nStarted performance optimization"
);
body.left = 36; body.top = 130; body.width = 648; body.height = 240;
body.textFrame.textRange.font.size = 18;
body.textFrame.textRange.paragraphFormat.bulletFormat.visible = true;

await context.sync();
return "Slide created with content";
```

### Add a colored rectangle shape

```javascript
const slides = context.presentation.slides;
slides.load("items");
await context.sync();
const slide = slides.items[0]; // first slide

const rect = slide.shapes.addGeometricShape(PowerPoint.GeometricShapeType.rectangle);
rect.left = 50;
rect.top = 50;
rect.width = 200;
rect.height = 100;
rect.fill.setSolidColor("4472C4");
rect.lineFormat.color = "2E5090";
rect.lineFormat.weight = 2;

const textRange = rect.textFrame.textRange;
textRange.text = "Key Metric: 95%";
textRange.font.color = "FFFFFF";
textRange.font.size = 16;
textRange.font.bold = true;

await context.sync();
return "Shape added";
```

### Read all slide text

```javascript
const slides = context.presentation.slides;
slides.load("items");
await context.sync();

const result = [];
for (let i = 0; i < slides.items.length; i++) {
  const shapes = slides.items[i].shapes;
  shapes.load("items/textFrame/textRange/text");
  await context.sync();

  const texts = shapes.items
    .filter(s => s.textFrame && s.textFrame.textRange && s.textFrame.textRange.text)
    .map(s => s.textFrame.textRange.text);
  result.push({ slide: i + 1, texts });
}
return JSON.stringify(result);
```

### Delete a slide by index

```javascript
const slides = context.presentation.slides;
slides.load("items");
await context.sync();

if (slides.items.length > 1) {
  slides.items[slides.items.length - 1].delete();
  await context.sync();
  return "Last slide deleted";
}
return "Cannot delete the only slide";
```

### Modify existing text

```javascript
const slides = context.presentation.slides;
slides.load("items");
await context.sync();

const shapes = slides.items[0].shapes;
shapes.load("items/name,items/textFrame/textRange/text");
await context.sync();

for (const shape of shapes.items) {
  if (shape.textFrame && shape.textFrame.textRange.text.includes("Draft")) {
    shape.textFrame.textRange.text = shape.textFrame.textRange.text.replace("Draft", "Final");
  }
}
await context.sync();
return "Text updated";
```

### Set slide background color

```javascript
const slides = context.presentation.slides;
slides.load("items");
await context.sync();

// Add a full-slide rectangle as background
const slide = slides.items[0];
const bg = slide.shapes.addGeometricShape(PowerPoint.GeometricShapeType.rectangle);
bg.left = 0; bg.top = 0; bg.width = 720; bg.height = 405;
bg.fill.setSolidColor("1E2761");
bg.lineFormat.weight = 0;
// Note: to send it behind other shapes, you may need to reorder
await context.sync();
return "Background set";
```

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
