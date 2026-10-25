"""Typed specification registry.

Products store specs as typed values (numbers stay numbers). This module knows the label, unit and *direction* of each
well-known spec, so comparison, SmartMatch and Value Lens only ever compare like with like:
  better = "higher" | "lower"  -> can be ranked and scored
  better = None                -> informational only (never scored, never drawn on a radar)
Unknown keys are allowed; they are shown but treated as informational.
"""
SPEC_DEFS: dict[str, dict] = {
    # audio / electronics
    "battery_hours": {"label": "Battery life", "unit": "hours", "kind": "number", "better": "higher"},
    "charge_time_min": {"label": "Charging time", "unit": "min", "kind": "number", "better": "lower"},
    "weight_g": {"label": "Weight", "unit": "g", "kind": "number", "better": "lower"},
    "driver_mm": {"label": "Driver size", "unit": "mm", "kind": "number", "better": None},
    "bluetooth": {"label": "Bluetooth", "kind": "text", "better": None},
    "noise_cancellation": {"label": "Active noise cancellation", "kind": "bool", "better": "present"},
    "water_resistance": {"label": "Water resistance", "kind": "text", "better": None},
    "capacity_mah": {"label": "Battery capacity", "unit": "mAh", "kind": "number", "better": "higher"},
    "output_w": {"label": "Power output", "unit": "W", "kind": "number", "better": "higher"},
    "ports": {"label": "Ports", "kind": "number", "better": "higher"},
    "microphone": {"label": "Built-in microphone", "kind": "bool", "better": "present"},
    "wireless": {"label": "Wireless", "kind": "bool", "better": "present"},
    # apparel
    "cotton_pct": {"label": "Cotton content", "unit": "%", "kind": "number", "better": "higher"},
    "fabric_gsm": {"label": "Fabric weight", "unit": "GSM", "kind": "number", "better": None},
    "machine_washable": {"label": "Machine washable", "kind": "bool", "better": "present"},
    "fit": {"label": "Fit", "kind": "text", "better": None},
    # footwear
    "cushioning": {"label": "Cushioning", "kind": "text", "better": None},
    "drop_mm": {"label": "Heel-to-toe drop", "unit": "mm", "kind": "number", "better": None},
    # home / kitchen
    "capacity_ml": {"label": "Capacity", "unit": "ml", "kind": "number", "better": None},
    "insulation_hours": {"label": "Keeps cold/hot", "unit": "hours", "kind": "number", "better": "higher"},
    "power_w": {"label": "Power", "unit": "W", "kind": "number", "better": None},
    "dishwasher_safe": {"label": "Dishwasher safe", "kind": "bool", "better": "present"},
    "induction_compatible": {"label": "Induction compatible", "kind": "bool", "better": "present"},
    "bpa_free": {"label": "BPA free", "kind": "bool", "better": "present"},
    "brightness_lumens": {"label": "Brightness", "unit": "lumens", "kind": "number", "better": "higher"},
    # beauty
    "volume_ml": {"label": "Volume", "unit": "ml", "kind": "number", "better": None},
    "spf": {"label": "SPF", "kind": "number", "better": "higher"},
    "fragrance_free": {"label": "Fragrance free", "kind": "bool", "better": "present"},
    "runtime_min": {"label": "Cordless runtime", "unit": "min", "kind": "number", "better": "higher"},
    # sports
    "thickness_mm": {"label": "Thickness", "unit": "mm", "kind": "number", "better": None},
    "max_load_kg": {"label": "Maximum load", "unit": "kg", "kind": "number", "better": "higher"},
    "length_m": {"label": "Length", "unit": "m", "kind": "number", "better": None},
    "non_slip": {"label": "Non-slip surface", "kind": "bool", "better": "present"},
    # stationery / books
    "pages": {"label": "Pages", "kind": "number", "better": None},
    "paper_gsm": {"label": "Paper weight", "unit": "GSM", "kind": "number", "better": "higher"},
    "refillable": {"label": "Refillable", "kind": "bool", "better": "present"},
    # bags
    "volume_l": {"label": "Volume", "unit": "L", "kind": "number", "better": None},
    "laptop_max_inch": {"label": "Fits laptop up to", "unit": "inch", "kind": "number", "better": "higher"},
    "water_resistant": {"label": "Water resistant", "kind": "bool", "better": "present"},
    "compartments": {"label": "Compartments", "kind": "number", "better": None},
}


def label(key: str) -> str:
    d = SPEC_DEFS.get(key)
    return d["label"] if d else key.replace("_", " ").strip().capitalize()


def unit(key: str) -> str:
    return (SPEC_DEFS.get(key) or {}).get("unit", "")


def better(key: str):
    return (SPEC_DEFS.get(key) or {}).get("better")


def is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def fmt(key: str, value) -> str:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if is_number(value):
        u = unit(key)
        return f"{value:g} {u}".strip()
    return str(value)


def display_attributes(specs: dict, extra: dict | None = None) -> dict[str, str]:
    """Human-readable attribute dict (string -> string) used by the grounded assistant and evidence panels."""
    out = {label(k): fmt(k, v) for k, v in (specs or {}).items() if v not in (None, "")}
    for k, v in (extra or {}).items():
        out.setdefault(str(k), str(v))
    return out


def numeric_keys(specs: dict) -> list[str]:
    return [k for k, v in (specs or {}).items() if is_number(v) and better(k) in ("higher", "lower")]
