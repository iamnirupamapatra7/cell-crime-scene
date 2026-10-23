"""Image and mask loading/saving. Originals are never modified; derived files are written alongside."""
import hashlib
from pathlib import Path

import numpy as np
import tifffile
from PIL import Image
from skimage import measure
from skimage.segmentation import relabel_sequential


def _read(path: Path) -> np.ndarray:
    if path.suffix.lower() in (".tif", ".tiff"):
        return np.asarray(tifffile.imread(path))
    return np.asarray(Image.open(path))


def load_image(path) -> np.ndarray:
    """Load a microscopy image as float32 grayscale in [0, 1]."""
    arr = _read(Path(path)).astype(np.float32)
    if arr.ndim == 3:
        if arr.shape[-1] in (3, 4):
            arr = arr[..., :3].mean(axis=-1)
        else:  # channel-first stack: max projection
            arr = arr.max(axis=0)
    lo, hi = np.percentile(arr, (0.1, 99.9))
    if hi <= lo:
        hi = lo + 1.0
    return np.clip((arr - lo) / (hi - lo), 0, 1).astype(np.float32)


def load_labels(path) -> np.ndarray:
    """Load a segmentation mask as an int32 label image. Binary masks are split into connected components."""
    arr = _read(Path(path))
    if arr.ndim == 3:
        arr = arr[..., 0] if arr.shape[-1] in (3, 4) else arr[0]
    values = np.unique(arr)
    if len(values) <= 2:
        arr = measure.label(arr > 0)
    return relabel_sequential(arr.astype(np.int32))[0]


def save_labels(path, labels: np.ndarray) -> None:
    dtype = np.uint16 if labels.max() < 65535 else np.uint32
    tifffile.imwrite(path, labels.astype(dtype))


def save_png(path, array: np.ndarray) -> None:
    if array.dtype != np.uint8:
        array = (np.clip(array, 0, 1) * 255).astype(np.uint8)
    Image.fromarray(array).save(path)


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
