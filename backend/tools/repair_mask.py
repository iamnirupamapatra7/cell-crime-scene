"""Repair tools. Each returns a new label image plus a summary; inputs are never mutated."""
import numpy as np
from scipy import ndimage as ndi
from skimage import filters, measure, morphology, segmentation
from skimage.feature import peak_local_max
from skimage.segmentation import relabel_sequential

from tools.segment_cells import remove_small, threshold_segment


def _target_labels(labels, target, suspicious_labels):
    if target == "all":
        return set(np.unique(labels[labels > 0]).tolist())
    return set(suspicious_labels)


def _split_regions(labels, targets, split_fn):
    """Apply split_fn(region_slice_index) to each target region and write sub-labels back."""
    out = labels.copy()
    next_label = int(labels.max()) + 1
    split = 0
    created = 0
    for p in measure.regionprops(labels):
        if p.label not in targets:
            continue
        sl = p.slice
        region = labels[sl] == p.label
        parts = split_fn(region, sl)
        n = int(parts.max())
        if n < 2:
            continue
        split += 1
        sub = out[sl]
        for k in range(2, n + 1):
            sub[parts == k] = next_label
            next_label += 1
            created += 1
    return relabel_sequential(out)[0], {"regions_split": split, "objects_added": created}


def _padded_edt(region):
    return ndi.distance_transform_edt(np.pad(region, 1))[1:-1, 1:-1]


def watershed_split(img, labels, min_distance=7, sigma=1.0, landscape="distance",
                    target="suspicious", suspicious_labels=()):
    """Split merged objects with marker-controlled watershed on a distance or intensity landscape."""
    def split(region, sl):
        if landscape == "intensity":
            surface = filters.gaussian(img[sl], max(sigma, 0.5))
        else:
            surface = _padded_edt(region)
            if sigma > 0:
                surface = filters.gaussian(surface, sigma)
        surface = np.where(region, surface, 0)
        peaks = peak_local_max(surface, min_distance=int(min_distance), labels=region.astype(int),
                               exclude_border=False)
        if len(peaks) < 2:
            return np.zeros(region.shape, int)
        markers = np.zeros(region.shape, int)
        markers[tuple(peaks.T)] = np.arange(1, len(peaks) + 1)
        return segmentation.watershed(-surface, markers, mask=region)

    return _split_regions(labels, _target_labels(labels, target, suspicious_labels), split)


def erosion_split(img, labels, radius=3, target="suspicious", suspicious_labels=()):
    """Erode to break thin bridges between nuclei, then grow the cores back within the original outline."""
    footprint = morphology.disk(int(radius))

    def split(region, sl):
        cores = measure.label(ndi.binary_erosion(np.pad(region, radius + 1), footprint)[
            radius + 1:-radius - 1, radius + 1:-radius - 1])
        if cores.max() < 2:
            return np.zeros(region.shape, int)
        return segmentation.watershed(-_padded_edt(region), cores, mask=region)

    return _split_regions(labels, _target_labels(labels, target, suspicious_labels), split)


def remove_small_objects(img, labels, min_size=30, **_):
    out = remove_small(labels, int(min_size))
    return out, {"objects_removed": int(labels.max() - out.max())}


def resegment_threshold(img, labels, method="otsu", sigma=1.0, min_size=30, **_):
    out = threshold_segment(img, method=method, sigma=sigma, min_size=int(min_size))
    return out, {"objects": int(out.max())}
