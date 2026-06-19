---
name: extract-shirt-pattern
description: Extract printed graphics from clothing photos into transparent PNGs and Photoshop-readable layered PSD files. Use when the user provides a T-shirt/hoodie/garment photo and asks to isolate the chest/back print, remove fabric/background, create PSD layers, split colors such as black ink/white ink/red fills/rhinestone highlights, or make a Photoshop-editable graphic from a photographed clothing pattern.
---

# Extract Shirt Pattern

## Overview

Use this skill to turn a photographed clothing print into editable raster assets. The bundled script produces transparent PNG layers and basic PSD files that Photoshop can open.

Set expectations clearly: this is a photo-based bitmap extraction, not a factory vector file. Fabric ribs, wrinkles, reflections, compression artifacts, and occluded details may require manual cleanup or redraw in Photoshop/Illustrator.

## Workflow

1. Inspect the input image visually before processing.
2. Identify the graphic area and decide whether the user needs the original photo orientation, a rotated upright version, or both.
3. Prefer a manual crop box around the print when the garment photo includes collars, seams, watermarks, table/background, or large empty fabric areas.
4. Run `scripts/extract_pattern_layers.py` with the image path, output directory, and crop box.
5. Inspect `rebuilt_composite.png` and the key layer PNGs. If the extraction includes too much fabric, tighten the crop or raise thresholds; if details are missing, loosen thresholds.
6. Deliver the output folder path and name the recommended PSD.

## Script

Use the bundled script:

```powershell
python <skill-dir>\scripts\extract_pattern_layers.py `
  --input <photo.jpg> `
  --out-dir <output-folder> `
  --crop left,top,right,bottom `
  --rotate-upright
```

If `python` is ambiguous on Windows, use the discovered Python executable, such as `C:\Python311\python.exe`.

Important options:

- `--crop left,top,right,bottom`: crop in source-image pixels. Strongly recommended.
- `--rotate-upright`: also generate `_rotated.png` files and `shirt_pattern_layers_rotated.psd`.
- `--no-psd`: generate PNGs only when PSD writing is not needed.
- `--red-min`, `--dark-max`, `--white-min`: tune color separation thresholds.

Main outputs:

- `shirt_pattern_layers_clean.psd`: recommended PSD with separated color layers and a rebuilt composite.
- `shirt_pattern_layers_photo_orientation.psd`: PSD in photo orientation with a hidden source-photo reference layer.
- `shirt_pattern_layers_rotated.psd`: upright rotated PSD when `--rotate-upright` is used.
- `rebuilt_composite.png`: transparent composite built from separated layers.
- `black_linework.png`, `white_ink.png`, `red_heart.png`, `rhinestone_highlights.png`: transparent PNG layers.
- `full_color_cutout.png`: reference cutout from the photo; may retain fabric texture.

## Quality Notes

Use `rebuilt_composite.png` or `shirt_pattern_layers_clean.psd` as the normal deliverable. `full_color_cutout.png` is useful for reference but often preserves fabric texture.

For better results:

- Crop tightly enough to exclude watermarks, collars, garment seams, and table/background.
- Keep some padding around the graphic so flourishes and shadows are not cut off.
- Use the clean PSD when the user wants a Photoshop-editable graphic.
- Mention that fine lettering, rhinestones, and printed distress textures may need hand cleanup.

Do not claim the output is vector, print-ready, or perfectly separated unless it has been manually redrawn or verified.
