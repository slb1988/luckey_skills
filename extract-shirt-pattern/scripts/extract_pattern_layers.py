#!/usr/bin/env python3
"""Extract a photographed garment print into transparent PNG layers and basic PSDs."""

from __future__ import annotations

import argparse
from pathlib import Path
import struct

import numpy as np
from PIL import Image, ImageFilter


def parse_crop(value: str) -> tuple[int, int, int, int]:
    parts = [int(p.strip()) for p in value.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("crop must be left,top,right,bottom")
    left, top, right, bottom = parts
    if right <= left or bottom <= top:
        raise argparse.ArgumentTypeError("crop right/bottom must be greater than left/top")
    return left, top, right, bottom


def save_png(out_dir: Path, name: str, image: Image.Image) -> Path:
    path = out_dir / name
    image.save(path)
    return path


def soft_mask(mask: np.ndarray, radius: float = 1.2) -> np.ndarray:
    img = Image.fromarray(np.clip(mask, 0, 255).astype(np.uint8), "L")
    if radius:
        img = img.filter(ImageFilter.GaussianBlur(radius))
    return np.asarray(img, dtype=np.uint8)


def largest_bbox(alpha: np.ndarray, pad: int = 16) -> tuple[int, int, int, int]:
    ys, xs = np.where(alpha > 10)
    if len(xs) == 0:
        return (0, 0, alpha.shape[1], alpha.shape[0])
    left = max(0, int(xs.min()) - pad)
    top = max(0, int(ys.min()) - pad)
    right = min(alpha.shape[1], int(xs.max()) + pad + 1)
    bottom = min(alpha.shape[0], int(ys.max()) + pad + 1)
    return (left, top, right, bottom)


def keep_components(mask: np.ndarray, min_area: int) -> np.ndarray:
    h, w = mask.shape
    src = mask > 0
    seen = np.zeros((h, w), dtype=bool)
    out = np.zeros((h, w), dtype=np.uint8)
    stack: list[tuple[int, int]] = []
    for y in range(h):
        candidates = np.where(src[y] & ~seen[y])[0]
        for x0 in candidates:
            if seen[y, x0] or not src[y, x0]:
                continue
            stack.append((x0, y))
            seen[y, x0] = True
            pts: list[tuple[int, int]] = []
            while stack:
                x, yy = stack.pop()
                pts.append((x, yy))
                for nx, ny in ((x - 1, yy), (x + 1, yy), (x, yy - 1), (x, yy + 1)):
                    if 0 <= nx < w and 0 <= ny < h and src[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((nx, ny))
            if len(pts) >= min_area:
                for x, yy in pts:
                    out[yy, x] = 255
    return out


def make_rgba(rgb: np.ndarray, alpha: np.ndarray) -> Image.Image:
    return Image.fromarray(np.dstack([rgb, alpha]).astype(np.uint8), "RGBA")


def pascal_name(name: str) -> bytes:
    raw = name.encode("macroman", "replace")[:255]
    data = bytes([len(raw)]) + raw
    data += b"\0" * ((4 - (len(data) % 4)) % 4)
    return data


def write_psd(path: Path, size: tuple[int, int], layers: list[dict], composite_rgb: Image.Image) -> None:
    width, height = size
    header = b"8BPS" + struct.pack(">H6sHIIHH", 1, b"\0" * 6, 3, height, width, 8, 3)
    color_mode = struct.pack(">I", 0)
    resources = struct.pack(">I", 0)

    records = bytearray()
    channel_payloads = []
    for layer in layers:
        name = layer["name"]
        visible = layer.get("visible", True)
        rgba = layer["rgba"].resize((width, height), Image.Resampling.LANCZOS)
        arr = np.asarray(rgba, dtype=np.uint8)
        channels = [
            (0, arr[:, :, 0].tobytes()),
            (1, arr[:, :, 1].tobytes()),
            (2, arr[:, :, 2].tobytes()),
            (-1, arr[:, :, 3].tobytes()),
        ]
        records += struct.pack(">iiiiH", 0, 0, height, width, len(channels))
        for channel_id, data in channels:
            records += struct.pack(">hI", channel_id, 2 + len(data))
        flags = 0 if visible else 2
        records += b"8BIM" + b"norm"
        records += struct.pack(">BBBB", 255, 0, 0, flags)
        extra = struct.pack(">I", 0) + struct.pack(">I", 0) + pascal_name(name)
        records += struct.pack(">I", len(extra)) + extra
        channel_payloads.extend(channels)

    channel_data = bytearray()
    for _, data in channel_payloads:
        channel_data += struct.pack(">H", 0) + data

    layer_info_body = struct.pack(">h", len(layers)) + records + channel_data
    if len(layer_info_body) % 2:
        layer_info_body += b"\0"
    layer_and_mask_body = struct.pack(">I", len(layer_info_body)) + layer_info_body + struct.pack(">I", 0)
    layer_and_mask = struct.pack(">I", len(layer_and_mask_body)) + layer_and_mask_body

    comp = np.asarray(composite_rgb.resize((width, height), Image.Resampling.LANCZOS).convert("RGB"), dtype=np.uint8)
    image_data = struct.pack(">H", 0) + comp[:, :, 0].tobytes() + comp[:, :, 1].tobytes() + comp[:, :, 2].tobytes()

    path.write_bytes(header + color_mode + resources + layer_and_mask + image_data)


def extract(args: argparse.Namespace) -> None:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    img = Image.open(args.input).convert("RGB")
    crop_box = args.crop or (0, 0, img.width, img.height)
    crop = img.crop(crop_box)
    rgb = np.asarray(crop, dtype=np.uint8)
    h, w = rgb.shape[:2]

    r = rgb[:, :, 0].astype(np.int16)
    g = rgb[:, :, 1].astype(np.int16)
    b = rgb[:, :, 2].astype(np.int16)
    gray = (0.299 * r + 0.587 * g + 0.114 * b).astype(np.int16)
    mx = np.maximum.reduce([r, g, b])
    mn = np.minimum.reduce([r, g, b])
    sat = mx - mn

    yy, xx = np.mgrid[0:h, 0:w]
    cx, cy = int(w * 0.52), int(h * 0.52)
    ellipse = (((xx - cx) / (w * 0.47)) ** 2 + ((yy - cy) / (h * 0.50)) ** 2) <= 1.0
    wide_ellipse = (((xx - cx) / (w * 0.53)) ** 2 + ((yy - cy) / (h * 0.54)) ** 2) <= 1.0

    red_mask = (r > args.red_min) & (r - g > args.red_delta) & (r - b > args.red_delta - 6) & (sat > 34) & ellipse
    white_mask = (gray > args.white_min) & (sat < args.white_sat_max) & (r > 135) & (g > 130) & (b > 120) & ellipse
    dark_mask = (gray < args.dark_max) & wide_ellipse

    dark_u8 = dark_mask.astype(np.uint8) * 255
    dark_clean = Image.fromarray(dark_u8, "L").filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
    dark_mask = np.asarray(dark_clean) > 0

    sparkle_mask = (gray > args.sparkle_min) & (sat < args.sparkle_sat_max) & wide_ellipse
    sparkle_u8 = keep_components(sparkle_mask.astype(np.uint8) * 255, min_area=args.sparkle_min_area)
    sparkle_mask = sparkle_u8 > 0

    base_mask = red_mask | white_mask | dark_mask | sparkle_mask
    base_mask_u8 = keep_components(base_mask.astype(np.uint8) * 255, min_area=args.min_area)
    base_mask_img = Image.fromarray(base_mask_u8, "L").filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(1.0))
    base_alpha = np.asarray(base_mask_img, dtype=np.uint8)
    base_alpha = np.where(wide_ellipse, base_alpha, 0).astype(np.uint8)

    left, top, right, bottom = largest_bbox(base_alpha, pad=args.pad)

    def crop_layer(mask_bool: np.ndarray, solid: tuple[int, int, int] | None = None, blur: float = 0.8) -> Image.Image:
        alpha = soft_mask(mask_bool.astype(np.uint8) * 255, blur)
        alpha = np.minimum(alpha, base_alpha)
        layer_rgb = rgb.copy()
        if solid is not None:
            layer_rgb[:, :, 0] = solid[0]
            layer_rgb[:, :, 1] = solid[1]
            layer_rgb[:, :, 2] = solid[2]
        return make_rgba(layer_rgb, alpha).crop((left, top, right, bottom))

    full_rgba = make_rgba(rgb, base_alpha).crop((left, top, right, bottom))
    black_rgba = crop_layer(dark_mask, solid=(18, 18, 18), blur=0.65)
    red_rgba = crop_layer(red_mask, solid=(150, 15, 45), blur=1.0)
    white_rgba = crop_layer(white_mask, solid=(238, 232, 220), blur=1.0)
    sparkle_rgba = crop_layer(sparkle_mask, solid=(245, 245, 238), blur=0.5)

    canvas_w = right - left
    canvas_h = bottom - top
    composite = Image.new("RGBA", (canvas_w, canvas_h), (255, 255, 255, 0))
    for layer in (black_rgba, white_rgba, red_rgba, sparkle_rgba):
        composite.alpha_composite(layer)

    layers = [
        ("rebuilt_composite", composite),
        ("full_color_cutout", full_rgba),
        ("black_linework", black_rgba),
        ("white_ink", white_rgba),
        ("red_heart", red_rgba),
        ("rhinestone_highlights", sparkle_rgba),
    ]
    for name, layer in layers:
        save_png(out_dir, f"{name}.png", layer)
        if args.rotate_upright:
            rotated = layer.rotate(90, expand=True, resample=Image.Resampling.BICUBIC)
            save_png(out_dir, f"{name}_rotated.png", rotated)

    if not args.no_psd:
        write_psd(
            out_dir / "shirt_pattern_layers_clean.psd",
            (canvas_w, canvas_h),
            [
                {"name": "black_linework", "rgba": black_rgba},
                {"name": "white_ink", "rgba": white_rgba},
                {"name": "red_heart", "rgba": red_rgba},
                {"name": "rhinestone_highlights", "rgba": sparkle_rgba},
                {"name": "rebuilt_composite", "rgba": composite},
            ],
            Image.alpha_composite(Image.new("RGBA", (canvas_w, canvas_h), (255, 255, 255, 255)), composite).convert("RGB"),
        )
        write_psd(
            out_dir / "shirt_pattern_layers_photo_orientation.psd",
            (canvas_w, canvas_h),
            [
                {"name": "source_photo_reference_hidden", "rgba": full_rgba, "visible": False},
                {"name": "black_linework", "rgba": black_rgba},
                {"name": "white_ink", "rgba": white_rgba},
                {"name": "red_heart", "rgba": red_rgba},
                {"name": "rhinestone_highlights", "rgba": sparkle_rgba},
                {"name": "rebuilt_composite", "rgba": composite},
            ],
            Image.alpha_composite(Image.new("RGBA", (canvas_w, canvas_h), (255, 255, 255, 255)), composite).convert("RGB"),
        )
        if args.rotate_upright:
            rot_layers = [
                {"name": "black_linework", "rgba": black_rgba.rotate(90, expand=True, resample=Image.Resampling.BICUBIC)},
                {"name": "white_ink", "rgba": white_rgba.rotate(90, expand=True, resample=Image.Resampling.BICUBIC)},
                {"name": "red_heart", "rgba": red_rgba.rotate(90, expand=True, resample=Image.Resampling.BICUBIC)},
                {"name": "rhinestone_highlights", "rgba": sparkle_rgba.rotate(90, expand=True, resample=Image.Resampling.BICUBIC)},
                {"name": "rebuilt_composite", "rgba": composite.rotate(90, expand=True, resample=Image.Resampling.BICUBIC)},
            ]
            rot_w, rot_h = rot_layers[0]["rgba"].size
            write_psd(
                out_dir / "shirt_pattern_layers_rotated.psd",
                (rot_w, rot_h),
                rot_layers,
                Image.alpha_composite(Image.new("RGBA", (rot_w, rot_h), (255, 255, 255, 255)), rot_layers[-1]["rgba"]).convert("RGB"),
            )

    print(f"output={out_dir}")
    print(f"crop_box={crop_box}")
    print(f"cutout_size={canvas_w}x{canvas_h}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract a clothing print into PNG layers and basic PSD files.")
    parser.add_argument("--input", required=True, help="Input garment photo")
    parser.add_argument("--out-dir", required=True, help="Output directory")
    parser.add_argument("--crop", type=parse_crop, help="Crop box as left,top,right,bottom in source pixels")
    parser.add_argument("--rotate-upright", action="store_true", help="Also output 90-degree rotated assets")
    parser.add_argument("--no-psd", action="store_true", help="Skip PSD writing")
    parser.add_argument("--red-min", type=int, default=105)
    parser.add_argument("--red-delta", type=int, default=24)
    parser.add_argument("--white-min", type=int, default=145)
    parser.add_argument("--white-sat-max", type=int, default=82)
    parser.add_argument("--dark-max", type=int, default=92)
    parser.add_argument("--sparkle-min", type=int, default=178)
    parser.add_argument("--sparkle-sat-max", type=int, default=70)
    parser.add_argument("--sparkle-min-area", type=int, default=4)
    parser.add_argument("--min-area", type=int, default=18)
    parser.add_argument("--pad", type=int, default=18)
    args = parser.parse_args()
    extract(args)


if __name__ == "__main__":
    main()
