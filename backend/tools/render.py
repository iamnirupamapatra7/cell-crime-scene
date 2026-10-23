"""Overlay rendering for the review dashboard."""
import colorsys

import numpy as np
from skimage.segmentation import find_boundaries


def _palette(n: int) -> np.ndarray:
    lut = np.zeros((n + 1, 3), np.float32)
    for i in range(1, n + 1):
        lut[i] = colorsys.hsv_to_rgb((i * 0.618034) % 1.0, 0.75, 1.0)
    return lut


def overlay(img: np.ndarray, labels: np.ndarray, boxes=None, scale: int = 2) -> np.ndarray:
    gray = np.clip(img, 0, 1)
    rgb = np.repeat(gray[..., None], 3, axis=-1)
    lut = _palette(int(labels.max()))
    colors = lut[labels]
    fg = labels > 0
    rgb[fg] = 0.65 * rgb[fg] + 0.35 * colors[fg]
    edges = find_boundaries(labels, mode="inner")
    rgb[edges] = colors[edges]
    out = (rgb * 255).astype(np.uint8)
    if scale > 1:
        out = out.repeat(scale, axis=0).repeat(scale, axis=1)
    for minr, minc, maxr, maxc in boxes or []:
        r0, c0 = max(minr * scale - 3, 0), max(minc * scale - 3, 0)
        r1, c1 = min(maxr * scale + 2, out.shape[0] - 1), min(maxc * scale + 2, out.shape[1] - 1)
        red = np.array([255, 40, 60], np.uint8)
        out[r0:r0 + 2, c0:c1] = red
        out[r1 - 1:r1 + 1, c0:c1] = red
        out[r0:r1, c0:c0 + 2] = red
        out[r0:r1, c1 - 1:c1 + 1] = red
    return out


def grayscale(img: np.ndarray, scale: int = 2) -> np.ndarray:
    out = (np.clip(img, 0, 1) * 255).astype(np.uint8)
    return out.repeat(scale, axis=0).repeat(scale, axis=1)
