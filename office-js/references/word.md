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
