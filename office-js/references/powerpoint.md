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
