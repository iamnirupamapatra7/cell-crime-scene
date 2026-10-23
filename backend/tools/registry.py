"""The allowlist of repair tools the agent may call, with bounded parameters.

The agent cannot run arbitrary code: it names a tool from this table, and every parameter
is validated and clamped here before execution.
"""
from tools import repair_mask

TOOLS = {
    "watershed_split": {
        "fn": repair_mask.watershed_split,
        "description": "Split merged nuclei with marker-controlled watershed. landscape='distance' uses the "
                       "distance transform (good for round touching nuclei); 'intensity' uses brightness "
                       "(good when there is a dim seam between nuclei). Smaller min_distance = more splits.",
        "params": {
            "min_distance": {"type": "int", "min": 3, "max": 25, "default": 7},
            "sigma": {"type": "float", "min": 0.0, "max": 3.0, "default": 1.0},
            "landscape": {"type": "enum", "values": ["distance", "intensity"], "default": "distance"},
            "target": {"type": "enum", "values": ["suspicious", "all"], "default": "suspicious"},
        },
    },
    "erosion_split": {
        "fn": repair_mask.erosion_split,
        "description": "Erode objects to break thin bridges, then regrow the separated cores inside the "
                       "original outline. Larger radius breaks thicker bridges but may erase small nuclei.",
        "params": {
            "radius": {"type": "int", "min": 1, "max": 8, "default": 3},
            "target": {"type": "enum", "values": ["suspicious", "all"], "default": "suspicious"},
        },
    },
    "remove_small_objects": {
        "fn": repair_mask.remove_small_objects,
        "description": "Remove objects smaller than min_size pixels (debris / noise fragments).",
        "params": {"min_size": {"type": "int", "min": 5, "max": 500, "default": 30}},
    },
    "resegment_threshold": {
        "fn": repair_mask.resegment_threshold,
        "description": "Discard the mask and re-segment the image by thresholding (otsu, li or local). "
                       "Use when the foreground itself looks wrong, not for merges.",
        "params": {
            "method": {"type": "enum", "values": ["otsu", "li", "local"], "default": "otsu"},
            "sigma": {"type": "float", "min": 0.0, "max": 4.0, "default": 1.0},
            "min_size": {"type": "int", "min": 5, "max": 500, "default": 30},
        },
    },
}

BASES = ["baseline", "best"]


def validate_params(tool: str, raw: dict) -> tuple[dict, list[str]]:
    """Return (clean params, notes about anything that was clamped or defaulted)."""
    if tool not in TOOLS:
        raise ValueError(f"tool '{tool}' is not in the allowlist")
    clean, notes = {}, []
    for name, spec in TOOLS[tool]["params"].items():
        value = raw.get(name)
        if value is None:
            clean[name] = spec["default"]
            continue
        if spec["type"] == "enum":
            if value not in spec["values"]:
                notes.append(f"{name}={value!r} not allowed; used {spec['default']!r}")
                value = spec["default"]
        else:
            cast = int if spec["type"] == "int" else float
            try:
                value = cast(value)
            except (TypeError, ValueError):
                notes.append(f"{name}={value!r} invalid; used {spec['default']}")
                value = spec["default"]
            bounded = min(max(value, spec["min"]), spec["max"])
            if bounded != value:
                notes.append(f"{name}={value} clamped to {bounded}")
            value = bounded
        clean[name] = value
    return clean, notes


def catalog() -> dict:
    return {name: {"description": t["description"], "params": t["params"]} for name, t in TOOLS.items()}
