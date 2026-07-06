# engine/solidifai_engine/fabrication/slicedata.py
"""Parse an OrcaSlicer-exported .3mf into a slice Estimate.

Field names verified against a real headless slice (spike 2026-06-07): time comes
from slice_info's ``prediction`` (seconds), weight from ``weight`` (g), per-filament
length from ``used_m`` (metres). The gcode footer carries ``total layer number``,
``max_z_height``, and the filament's ``filament_cost`` (price per kg). There is no
total-cost line, so total cost is computed weight * price.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile

_LAYER_RE = re.compile(r";\s*total layer number:\s*(\d+)", re.IGNORECASE)
_ZHEIGHT_RE = re.compile(r";\s*max_z_height:\s*([\d.]+)", re.IGNORECASE)
_PRICE_RE = re.compile(r";\s*filament_cost\s*=\s*([\d.]+)", re.IGNORECASE)


def read_3mf(path: str) -> tuple[str, str]:
    """Return (slice_info xml, plate gcode text) from the .3mf. Empty on absence."""
    info, gcode = "", ""
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            if "Metadata/slice_info.config" in names:
                info = z.read("Metadata/slice_info.config").decode("utf-8", "ignore")
            # Plate gcode is plate_1.gcode for a single-plate job.
            gname = next((n for n in names if re.fullmatch(r"Metadata/plate_\d+\.gcode", n)), None)
            if gname:
                gcode = z.read(gname).decode("utf-8", "ignore")
    except (OSError, zipfile.BadZipFile):
        pass
    return info, gcode


def parse_slice_info(xml: str) -> dict:
    """Pull time/weight/length/support/fits from slice_info.config. Tolerant."""
    out: dict = {}
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return out
    md = {m.get("key"): m.get("value") for m in root.iter("metadata")}

    prediction = md.get("prediction")
    if prediction:
        out["timeSeconds"] = int(float(prediction))
    weight = md.get("weight")
    if weight:
        out["filamentGrams"] = float(weight)
    if md.get("support_used") is not None:
        out["supportUsed"] = md["support_used"] == "true"
    if md.get("outside") is not None:
        out["fitsBed"] = md["outside"] != "true"

    fil = root.find(".//filament")
    used_m = fil.get("used_m") if fil is not None else None
    if used_m:
        out["filamentLengthMm"] = float(used_m) * 1000.0
    return out


def parse_gcode_footer(gcode: str) -> dict:
    """Pull layer count, height, and price-per-kg from gcode comments. Tolerant."""
    out: dict = {}
    if m := _LAYER_RE.search(gcode):
        out["layerCount"] = int(m.group(1))
    if m := _ZHEIGHT_RE.search(gcode):
        out["heightMm"] = float(m.group(1))
    if m := _PRICE_RE.search(gcode):
        out["pricePerKg"] = float(m.group(1))
    return out


def build_estimate(slice_info: dict, footer: dict, price_fallback: float) -> dict:
    """Merge parsed fields into an Estimate-shaped dict (source='slice').

    Price precedence: the filament's own ``filament_cost`` (footer) then
    ``price_fallback``. Cost = grams/1000 * price. Drops keys with no value.
    """
    est: dict = {"source": "slice", "currency": "USD"}
    for k in ("timeSeconds", "filamentGrams", "filamentLengthMm", "supportUsed", "fitsBed"):
        if k in slice_info:
            est[k] = slice_info[k]
    for k in ("layerCount", "heightMm"):
        if k in footer:
            est[k] = footer[k]

    grams = slice_info.get("filamentGrams")
    if grams is not None:
        price = footer.get("pricePerKg", price_fallback)
        est["cost"] = grams / 1000.0 * price
    return est
