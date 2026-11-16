#!/usr/bin/env python3
"""Compare paired Switch gameplay screenshots for visual regressions.

Keeps core pixel metrics in pure Python so tests run everywhere without optional
dependencies, while using Pillow on the host to decode JPEG/PNG screenshots and
write side-by-side + amplified diff PNG artifacts.
"""

from __future__ import annotations

import argparse
import io
import json
import math
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # Docker toolchain image lacks Pillow; host runs SysBot with Pillow.
    Image = None


def viewport_box(width: int, height: int) -> tuple[int, int, int, int]:
    """Return central 3D gameplay crop matching autorun.py (excludes Status Monitor/HUD)."""
    return (width * 2 // 5, height // 7, width * 9 // 10, height * 6 // 7)


def decode_image_bytes(data: bytes) -> tuple[int, int, bytes]:
    """Decode image bytes into (width, height, rgb_bytes)."""
    if data.startswith(b'P6'):
        return _decode_ppm_p6(data)
    if Image is None:
        raise RuntimeError('Pillow is required to decode non-PPM images')
    with Image.open(io.BytesIO(data)) as img:
        rgb = img.convert('RGB')
        return rgb.width, rgb.height, rgb.tobytes()


def _decode_ppm_p6(data: bytes) -> tuple[int, int, bytes]:
    pos = 0
    tokens: list[bytes] = []
    while len(tokens) < 4:
        while pos < len(data) and data[pos] in b' \t\r\n':
            pos += 1
        if pos < len(data) and data[pos] == ord('#'):
            while pos < len(data) and data[pos] not in b'\r\n':
                pos += 1
            continue
        start = pos
        while pos < len(data) and data[pos] not in b' \t\r\n':
            pos += 1
        if pos == start:
            raise ValueError('truncated PPM header')
        tokens.append(data[start:pos])
    if tokens[0] != b'P6':
        raise ValueError('unsupported PPM magic')
    width, height, maxval = int(tokens[1]), int(tokens[2]), int(tokens[3])
    if maxval != 255 or width <= 0 or height <= 0:
        raise ValueError('unsupported PPM dimensions or maxval')
    # PPM specifies exactly one whitespace byte between maxval and pixel payload.
    payload = data[pos + 1:]
    expected = width * height * 3
    if len(payload) < expected:
        raise ValueError('truncated PPM payload')
    return width, height, payload[:expected]


def crop_rgb(width: int, height: int, rgb: bytes, box: tuple[int, int, int, int]) -> tuple[int, int, bytes]:
    """Extract an (x0, y0, x1, y1) RGB slice cleanly."""
    x0, y0, x1, y1 = box
    if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
        raise ValueError(f'invalid crop box {box} for {width}x{height}')
    row_stride = width * 3
    out = bytearray((x1 - x0) * (y1 - y0) * 3)
    dst = 0
    span = (x1 - x0) * 3
    s0 = x0 * 3
    for y in range(y0, y1):
        off = y * row_stride + s0
        out[dst:dst + span] = rgb[off:off + span]
        dst += span
    return x1 - x0, y1 - y0, bytes(out)


def region_metrics(width: int, height: int, ref_rgb: bytes, cand_rgb: bytes) -> dict:
    """Compute channel-averaged MAE, RMSE, changed pixel fractions, and mean luma."""
    pixels = width * height
    if pixels <= 0 or len(ref_rgb) != pixels * 3 or len(cand_rgb) != pixels * 3:
        raise ValueError('image dimensions or RGB lengths do not match')
    abs_sum = 0
    sq_sum = 0
    max_diff = 0
    changed_gt8 = 0
    changed_gt24 = 0
    ref_luma_sum = 0.0
    cand_luma_sum = 0.0
    for i in range(0, pixels * 3, 3):
        dr = abs(ref_rgb[i] - cand_rgb[i])
        dg = abs(ref_rgb[i + 1] - cand_rgb[i + 1])
        db = abs(ref_rgb[i + 2] - cand_rgb[i + 2])
        abs_sum += dr + dg + db
        sq_sum += dr * dr + dg * dg + db * db
        px_max = max(dr, dg, db)
        if px_max > max_diff:
            max_diff = px_max
        if px_max > 8:
            changed_gt8 += 1
        if px_max > 24:
            changed_gt24 += 1
        ref_luma_sum += 0.299 * ref_rgb[i] + 0.587 * ref_rgb[i + 1] + 0.114 * ref_rgb[i + 2]
        cand_luma_sum += 0.299 * cand_rgb[i] + 0.587 * cand_rgb[i + 1] + 0.114 * cand_rgb[i + 2]
    return {
        'width': width,
        'height': height,
        'mae_rgb': round(abs_sum / (pixels * 3), 3),
        'rmse_rgb': round(math.sqrt(sq_sum / (pixels * 3)), 3),
        'max_channel_diff': max_diff,
        'pct_pixels_gt_8': round(100.0 * changed_gt8 / pixels, 3),
        'pct_pixels_gt_24': round(100.0 * changed_gt24 / pixels, 3),
        'ref_mean_luma': round(ref_luma_sum / pixels, 2),
        'cand_mean_luma': round(cand_luma_sum / pixels, 2),
    }


def compare_images(ref_bytes: bytes, cand_bytes: bytes, *,
                   max_viewport_mae: float = 12.0,
                   max_viewport_gt24_pct: float = 15.0,
                   min_mean_luma: float = 20.0) -> dict:
    """Evaluate visual similarity across both central gameplay viewport and full frame."""
    rw, rh, ref_rgb = decode_image_bytes(ref_bytes)
    cw, ch, cand_rgb = decode_image_bytes(cand_bytes)
    if (rw, rh) != (cw, ch):
        raise ValueError(f'resolution mismatch: ref {rw}x{rh} vs cand {cw}x{ch}')
    vw, vh, v_ref = crop_rgb(rw, rh, ref_rgb, viewport_box(rw, rh))
    _, _, v_cand = crop_rgb(cw, ch, cand_rgb, viewport_box(cw, ch))
    viewport = region_metrics(vw, vh, v_ref, v_cand)
    full = region_metrics(rw, rh, ref_rgb, cand_rgb)
    # Gate only catches severe corruption/blackout; dynamic traffic/tod still varies slightly.
    passed = (
        viewport['ref_mean_luma'] >= min_mean_luma
        and viewport['cand_mean_luma'] >= min_mean_luma
        and viewport['mae_rgb'] <= max_viewport_mae
        and viewport['pct_pixels_gt_24'] <= max_viewport_gt24_pct
    )
    return {
        'status': 'parity_ok' if passed else 'parity_drift_or_blackout',
        'passed': passed,
        'thresholds': {
            'max_viewport_mae': max_viewport_mae,
            'max_viewport_gt24_pct': max_viewport_gt24_pct,
            'min_mean_luma': min_mean_luma,
        },
        'viewport': viewport,
        'full': full,
    }


def save_side_by_side_diff(ref_bytes: bytes, cand_bytes: bytes, out_path: Path, gain: int = 4) -> None:
    """Save a 3-panel (ref | cand | amplified diff) PNG artifact when Pillow is available."""
    if Image is None:
        raise RuntimeError('Pillow is required to render PNG comparison sheets')
    w, h, ref_rgb = decode_image_bytes(ref_bytes)
    cw, ch, cand_rgb = decode_image_bytes(cand_bytes)
    if (w, h) != (cw, ch):
        raise ValueError(f'resolution mismatch: ref {w}x{h} vs cand {cw}x{ch}')
    diff_rgb = bytearray(len(ref_rgb))
    for i, (a, b) in enumerate(zip(ref_rgb, cand_rgb)):
        diff_rgb[i] = min(255, abs(a - b) * gain)
    sheet = Image.new('RGB', (w * 3, h))
    sheet.paste(Image.frombytes('RGB', (w, h), ref_rgb), (0, 0))
    sheet.paste(Image.frombytes('RGB', (w, h), cand_rgb), (w, 0))
    sheet.paste(Image.frombytes('RGB', (w, h), bytes(diff_rgb)), (w * 2, 0))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path, format='PNG')


def main() -> int:
    ap = argparse.ArgumentParser(description='Compare Switch reference and candidate screenshots.')
    ap.add_argument('reference', type=Path)
    ap.add_argument('candidate', type=Path)
    ap.add_argument('--diff-out', type=Path)
    ap.add_argument('--max-viewport-mae', type=float, default=12.0)
    ap.add_argument('--max-viewport-gt24-pct', type=float, default=15.0)
    args = ap.parse_args()
    ref_bytes = args.reference.read_bytes()
    cand_bytes = args.candidate.read_bytes()
    report = compare_images(
        ref_bytes, cand_bytes,
        max_viewport_mae=args.max_viewport_mae,
        max_viewport_gt24_pct=args.max_viewport_gt24_pct,
    )
    if args.diff_out is not None:
        save_side_by_side_diff(ref_bytes, cand_bytes, args.diff_out)
        report['diff_sheet'] = str(args.diff_out)
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
