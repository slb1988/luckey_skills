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
