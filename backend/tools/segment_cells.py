"""Threshold-based nucleus segmentation (the kind of pipeline that under-segments touching nuclei)."""
import numpy as np
from scipy import ndimage as ndi
from skimage import filters, measure
from skimage.segmentation import relabel_sequential


def remove_small(labels: np.ndarray, min_size: int) -> np.ndarray:
    sizes = np.bincount(labels.ravel())
    small = sizes < min_size
    small[0] = False
    out = labels.copy()
    out[small[labels]] = 0
    return relabel_sequential(out)[0]


def threshold_segment(img: np.ndarray, method: str = "otsu", sigma: float = 1.0,
                      min_size: int = 30) -> np.ndarray:
    smooth = filters.gaussian(img, sigma) if sigma > 0 else img
    if method == "li":
        fg = smooth > filters.threshold_li(smooth)
    elif method == "local":
        local = filters.threshold_local(smooth, block_size=51, offset=-0.01)
        fg = (smooth > local) & (smooth > 0.5 * filters.threshold_otsu(smooth))
    else:
        fg = smooth > filters.threshold_otsu(smooth)
    fg = ndi.binary_fill_holes(fg)
    return remove_small(measure.label(fg).astype(np.int32), min_size)
