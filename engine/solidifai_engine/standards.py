"""Standard-part dimensions + named real-world reference dims (mm).

The data SSOT for standard hardware: model scripts consume it via the
``solidifai.std`` facade, geometry builders in ``solidifai/hardware.py`` read
their tables from here, and Sol queries it through the ``lookup_standard`` /
``lookup_reference`` MCP tools. This module never imports build123d.

``lookup_reference`` layers the user library (<config-dir>/reference-library.json,
written by the host) over the packaged seed so learned entries resolve by id or
alias; user entries shadow seed entries on id collision.

``clearance_hole``/``pilot_hole`` resolve the manufacturing profile's fit
setting (tight/normal/loose -> ISO 273 close/medium/coarse) when no explicit
fit is given. All dimensions verified against the cited standard or vendor
datasheet at authoring time; unit tests in tests/test_standards.py pin them.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_REFERENCE_ASSET = Path(__file__).with_name("reference_dims.json")

# Profile fit vocabulary -> ISO 273 hole series.
FIT_TO_SERIES = {"tight": "close", "normal": "medium", "loose": "coarse"}

# ISO 273 clearance holes (close / medium / coarse), mm.
# Source: ISO 273 tables, e.g. https://amesweb.info/Screws/Clearance-Holes-Metric.aspx
ISO273_CLEARANCE: dict[str, dict[str, float]] = {
    "M2": {"close": 2.2, "medium": 2.4, "coarse": 2.6},
    "M2.5": {"close": 2.7, "medium": 2.9, "coarse": 3.1},
    "M3": {"close": 3.2, "medium": 3.4, "coarse": 3.6},
    "M4": {"close": 4.3, "medium": 4.5, "coarse": 4.8},
    "M5": {"close": 5.3, "medium": 5.5, "coarse": 5.8},
    "M6": {"close": 6.4, "medium": 6.6, "coarse": 7.0},
    "M8": {"close": 8.4, "medium": 9.0, "coarse": 10.0},
}

# Coarse-pitch tap drill (= d - pitch), mm. Standard tapping charts; in printed
# plastic this is also the thread-forming pilot for a machine screw.
TAP_DRILL: dict[str, float] = {
    "M2": 1.6,  # pitch 0.4
    "M2.5": 2.05,  # pitch 0.45
    "M3": 2.5,  # pitch 0.5
    "M4": 3.3,  # pitch 0.7
    "M5": 4.2,  # pitch 0.8
    "M6": 5.0,  # pitch 1.0
    "M8": 6.8,  # pitch 1.25
}

# Socket head cap screws, ISO 4762: head dia dk(max), head height k(max),
# hex socket s(nom). Source: fasteners.eu ISO 4762 table.
ISO4762_CAP: dict[str, dict[str, float]] = {
    "M2": {"head_dia": 3.8, "head_height": 2.0, "socket": 1.5},
    "M2.5": {"head_dia": 4.5, "head_height": 2.5, "socket": 2.0},
    "M3": {"head_dia": 5.5, "head_height": 3.0, "socket": 2.5},
    "M4": {"head_dia": 7.0, "head_height": 4.0, "socket": 3.0},
    "M5": {"head_dia": 8.5, "head_height": 5.0, "socket": 4.0},
    "M6": {"head_dia": 10.0, "head_height": 6.0, "socket": 5.0},
    "M8": {"head_dia": 13.0, "head_height": 8.0, "socket": 6.0},
}

# Button head screws, ISO 7380-1 (standard starts at M3).
# Source: https://www.fasteners.eu/standards/iso/7380/
ISO7380_BUTTON: dict[str, dict[str, float]] = {
    "M3": {"head_dia": 5.7, "head_height": 1.65, "socket": 2.0},
    "M4": {"head_dia": 7.6, "head_height": 2.2, "socket": 2.5},
    "M5": {"head_dia": 9.5, "head_height": 2.75, "socket": 3.0},
    "M6": {"head_dia": 10.5, "head_height": 3.3, "socket": 4.0},
    "M8": {"head_dia": 14.0, "head_height": 4.4, "socket": 5.0},
}

# Countersunk socket screws, ISO 10642, 90 deg head (standard starts at M3).
# head_dia is dk actual (max). Source: https://www.fasteners.eu/standards/ISO/10642/
ISO10642_CSK: dict[str, dict[str, float]] = {
    "M3": {"head_dia": 6.0, "head_height": 1.7, "socket": 2.0},
    "M4": {"head_dia": 8.0, "head_height": 2.3, "socket": 2.5},
    "M5": {"head_dia": 10.0, "head_height": 2.8, "socket": 3.0},
    "M6": {"head_dia": 12.0, "head_height": 3.3, "socket": 4.0},
    "M8": {"head_dia": 16.0, "head_height": 4.4, "socket": 5.0},
}

# Hex nuts, ISO 4032 style 1: width across flats s, thickness m(max).
# Source: https://www.fasteners.eu/standards/ISO/4032/ (NOTE: ISO 4032, not the
# thinner DIN 934 -- M5/M6/M8 thicknesses are 4.7/5.2/6.8, not 4.0/5.0/6.5).
ISO4032_NUT: dict[str, dict[str, float]] = {
    "M2": {"width_af": 4.0, "thickness": 1.6},
    "M2.5": {"width_af": 5.0, "thickness": 2.0},
    "M3": {"width_af": 5.5, "thickness": 2.4},
    "M4": {"width_af": 7.0, "thickness": 3.2},
    "M5": {"width_af": 8.0, "thickness": 4.7},
    "M6": {"width_af": 10.0, "thickness": 5.2},
    "M8": {"width_af": 13.0, "thickness": 6.8},
}

# Plain washers, ISO 7089 normal series: od, id, thickness.
ISO7089_WASHER: dict[str, dict[str, float]] = {
    "M2": {"od": 5.0, "id": 2.2, "thickness": 0.3},
    "M2.5": {"od": 6.0, "id": 2.7, "thickness": 0.5},
    "M3": {"od": 7.0, "id": 3.2, "thickness": 0.5},
    "M4": {"od": 9.0, "id": 4.3, "thickness": 0.8},
    "M5": {"od": 10.0, "id": 5.3, "thickness": 1.0},
    "M6": {"od": 12.0, "id": 6.4, "thickness": 1.6},
    "M8": {"od": 16.0, "id": 8.4, "thickness": 1.6},
}

# Brass heat-set inserts, standard length, Ruthex-class (CNC Kitchen inserts use
# the same install holes). hole_dia per the Ruthex HSS drill set (3.2/4.0/4.0/
# 5.6/6.4 for M2..M5); length per product code (RX-M2x4, RX-M2.5x5.7, RX-M3x5.7,
# RX-M4x8.1, RX-M5x9.5). min_hole_depth = length + 1.0 melt-flow relief.
# Source: ruthex.de product pages + drill-set page.
HEAT_SET_INSERTS: dict[str, dict[str, float]] = {
    "M2": {"hole_dia": 3.2, "length": 4.0, "min_hole_depth": 5.0},
    "M2.5": {"hole_dia": 4.0, "length": 5.7, "min_hole_depth": 6.7},
    "M3": {"hole_dia": 4.0, "length": 5.7, "min_hole_depth": 6.7},
    "M4": {"hole_dia": 5.6, "length": 8.1, "min_hole_depth": 9.1},
    "M5": {"hole_dia": 6.4, "length": 9.5, "min_hole_depth": 10.5},
}

# Deep-groove ball bearings: bore, od, width. Source: any bearing catalog
# (SKF/NSK designations are dimensionally identical).
BEARINGS: dict[str, dict[str, float]] = {
    "608": {"bore": 8.0, "od": 22.0, "width": 7.0},
    "625": {"bore": 5.0, "od": 16.0, "width": 5.0},
    "6201": {"bore": 12.0, "od": 32.0, "width": 10.0},
}

_HEAD_TABLES = {
    "cap": (ISO4762_CAP, "ISO 4762"),
    "button": (ISO7380_BUTTON, "ISO 7380-1"),
    "countersunk": (ISO10642_CSK, "ISO 10642"),
}


def sizes() -> list[str]:
    """Supported metric size designations (M2 .. M8)."""
    return list(ISO273_CLEARANCE)


def _check_size(size: str) -> str:
    if size not in ISO273_CLEARANCE:
        raise ValueError(f"unknown size {size!r}; supported: {', '.join(sizes())}")
    return size


def _thread_dia(size: str) -> float:
    return float(size[1:])


def screw(size: str, head: str = "cap") -> dict:
    """Head + thread dims for a metric screw. head = cap | button | countersunk."""
    _check_size(size)
    if head not in _HEAD_TABLES:
        raise ValueError(f"unknown head {head!r}; expected cap, button, or countersunk")
    table, standard = _HEAD_TABLES[head]
    if size not in table:
        raise ValueError(
            f"{standard} has no {size} (the standard starts at {min(table, key=_thread_dia)})"
        )
    out: dict[str, Any] = dict(table[size])
    out.update(thread_dia=_thread_dia(size), standard=standard, head=head)
    if head == "countersunk":
        out["angle_deg"] = 90
    return out


def _resolve_fit(fit: str | None, workspace_root: str | None) -> tuple[str, str]:
    """Return (profile_fit_name, iso273_series). fit may be a profile name
    (tight/normal/loose), a series name (close/medium/coarse), or None to read
    the manufacturing profile (workspace overrides when a root is known)."""
    if fit in ("close", "medium", "coarse"):
        inverse = {v: k for k, v in FIT_TO_SERIES.items()}
        return inverse[fit], fit
    if fit in FIT_TO_SERIES:
        return fit, FIT_TO_SERIES[fit]
    if fit is not None:
        raise ValueError(
            f"unknown fit {fit!r}; expected tight/normal/loose (profile) or "
            "close/medium/coarse (ISO 273)"
        )
    from solidifai_engine import manufacturing_profile

    if workspace_root is None:
        prof = manufacturing_profile.builtin_defaults()
    else:
        prof = manufacturing_profile.resolve(workspace_root)
    name = (prof.get("design") or {}).get("fit", "normal")
    return name, FIT_TO_SERIES.get(name, "medium")


def clearance_hole(
    size: str, fit: str | None = None, *, workspace_root: str | None = None
) -> float:
    """Clearance-hole diameter (mm) for a metric screw. With fit=None the
    manufacturing profile's fit setting decides (tight->close, normal->medium,
    loose->coarse, per ISO 273)."""
    _check_size(size)
    _, series = _resolve_fit(fit, workspace_root)
    return ISO273_CLEARANCE[size][series]


def pilot_hole(size: str) -> float:
    """Pilot/tap-drill diameter (mm): the coarse-pitch tapping drill, also the
    thread-forming pilot for a machine screw driven into printed plastic."""
    _check_size(size)
    return TAP_DRILL[size]


def nut(size: str) -> dict:
    _check_size(size)
    return dict(ISO4032_NUT[size], thread_dia=_thread_dia(size), standard="ISO 4032")


def washer(size: str) -> dict:
    _check_size(size)
    return dict(ISO7089_WASHER[size], standard="ISO 7089")


def insert(size: str) -> dict:
    """Heat-set insert install dims (standard-length brass, Ruthex/CNC Kitchen class)."""
    if size not in HEAT_SET_INSERTS:
        raise ValueError(
            f"no heat-set insert data for {size!r}; supported: {', '.join(HEAT_SET_INSERTS)}"
        )
    return dict(HEAT_SET_INSERTS[size], standard="Ruthex-class brass insert")


def bearing(code: str) -> dict:
    if code not in BEARINGS:
        raise ValueError(f"unknown bearing {code!r}; supported: {', '.join(BEARINGS)}")
    return dict(BEARINGS[code], designation=code)


# -- lookup tools (the MCP surface) -------------------------------------------

_SIZE_RE = re.compile(r"\bm\s?(\d+(?:[.,]\d+)?)\b", re.IGNORECASE)


def _normalize_size(text: str) -> str:
    """'3' -> 'M3'; '2,5'/'2.5'/'2.50' -> 'M2.5'; '3.0' -> 'M3'."""
    num = text.replace(",", ".")
    if "." in num:
        num = num.rstrip("0").rstrip(".")
    return f"M{num}"


_KIND_WORDS = {
    "screw_heads": ("screw", "bolt", "cap", "button", "countersunk", "csk", "head"),
    "clearance_hole": ("clearance", "through"),
    "pilot_hole": ("pilot", "tap", "thread-forming", "tapping"),
    "nut": ("nut",),
    "washer": ("washer",),
    "heat_set_insert": ("insert", "heat-set", "heatset", "heat set", "threaded insert"),
}


def lookup_standard(query: str, workspace_root: str | None = None) -> dict:
    """Answer a hardware-dimension query ("M3 clearance", "M4 heat-set insert",
    "608 bearing"). Returns the relevant table entries; a bare size returns
    everything known for it. Clearance answers include the profile-resolved fit."""
    q = query.strip().lower()
    out: dict[str, Any] = {"query": query, "units": "mm"}

    code = next((c for c in BEARINGS if re.search(rf"\b{c}\b", q)), None)
    if code is not None:
        out["bearing"] = bearing(code)
        return out

    m = _SIZE_RE.search(q)
    if m is None:
        return {
            "query": query,
            "error": "no metric size or bearing designation recognized",
            "supported": {"sizes": sizes(), "bearings": list(BEARINGS)},
        }
    size = _normalize_size(m.group(1))
    if size not in ISO273_CLEARANCE:
        return {
            "query": query,
            "error": f"unknown size {size!r}",
            "supported": {"sizes": sizes(), "bearings": list(BEARINGS)},
        }
    out["size"] = size

    asked = {k for k, words in _KIND_WORDS.items() if any(w in q for w in words)} or set(
        _KIND_WORDS
    )

    if "screw_heads" in asked:
        heads = {}
        for head in ("cap", "button", "countersunk"):
            try:
                heads[head] = screw(size, head=head)
            except ValueError as exc:
                heads[head] = {"unavailable": str(exc)}
        out["screw_heads"] = heads
    if "clearance_hole" in asked:
        fit_name, series = _resolve_fit(None, workspace_root)
        out["clearance_hole"] = {
            "fit": fit_name,
            "dia": ISO273_CLEARANCE[size][series],
            "series": dict(ISO273_CLEARANCE[size]),
            "note": "fit resolved from the manufacturing profile; ISO 273 series",
        }
    if "pilot_hole" in asked:
        out["pilot_hole"] = pilot_hole(size)
    if "nut" in asked:
        out["nut"] = nut(size)
    if "washer" in asked:
        out["washer"] = washer(size)
    if "heat_set_insert" in asked:
        out["heat_set_insert"] = (
            insert(size)
            if size in HEAT_SET_INSERTS
            else {"unavailable": f"insert data covers {', '.join(HEAT_SET_INSERTS)}"}
        )
    return out


_reference_cache: dict | None = None


def _reference_data() -> dict:
    global _reference_cache
    if _reference_cache is None:
        _reference_cache = json.loads(_REFERENCE_ASSET.read_text(encoding="utf-8"))
    return _reference_cache


_USER_LIBRARY_CACHE: tuple[str, float, list] | None = None  # (path, mtime, objects)


def _user_objects() -> list[dict]:
    """Entries from the user's reference library (<config-dir>/reference-library.json,
    written only by the host). Mtime-cached; malformed or absent reads as empty
    so lookup never breaks."""
    global _USER_LIBRARY_CACHE
    from solidifai_engine import paths

    path = Path(paths.app_config_dir()) / "reference-library.json"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return []
    # (path, mtime) keying: a same-second host rewrite can serve one stale read;
    # acceptable since a lookup that matters happens a build round later, not in
    # the same tick as the save.
    cached = _USER_LIBRARY_CACHE
    if cached is not None and cached[0] == str(path) and cached[1] == mtime:
        return cached[2]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        objects = [e for e in data.get("objects", []) if isinstance(e, dict) and e.get("id")]
    except (OSError, ValueError):
        objects = []
    _USER_LIBRARY_CACHE = (str(path), mtime, objects)
    return objects


def _all_reference_objects() -> list[dict]:
    """User library first (it shadows the seed on id collision), then seed."""
    user = _user_objects()
    shadowed = {e["id"] for e in user}
    return user + [e for e in _reference_data()["objects"] if e["id"] not in shadowed]


def lookup_reference(object_name: str) -> dict:
    """Find a named real-world object's verified dims (boards, cells, port
    cutouts, display modules). Matches id or alias, case-insensitive; a miss
    lists everything available so the agent can pick or fall back to the web."""
    q = " ".join(object_name.strip().lower().split())
    entries = _all_reference_objects()
    best = None
    for entry in entries:
        names = [entry["id"].replace("-", " ")] + [a.lower() for a in entry.get("aliases", [])]
        if q in (entry["id"], *names):
            best = entry
            break
        if best is None and any(q in n or n in q for n in names):
            best = entry
    if best is None:
        return {
            "query": object_name,
            "match": None,
            "available": [e["id"] for e in entries],
            "note": "no entry; verify dims by web search, say which source you used, "
            "then save_reference so it's known next time",
        }
    return {"query": object_name, "match": best, "units": "mm"}
