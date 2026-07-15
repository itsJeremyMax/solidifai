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

_CATALOG_ASSET = Path(__file__).with_name("standards_catalog.json")
_PROVIDER_FILE = "standards-provider.json"
_catalog = json.loads(_CATALOG_ASSET.read_text(encoding="utf-8"))["standards"]
ISO273_CLEARANCE = _catalog["iso-273-clearance"]["values"]
TAP_DRILL = _catalog["tap-drill-coarse"]["values"]
ISO261_COARSE_PITCH = _catalog["iso-261-pitch"]["values"]
ISO4762_CAP = _catalog["iso-4762-cap"]["values"]
ISO7380_BUTTON = _catalog["iso-7380-button"]["values"]
ISO10642_CSK = _catalog["iso-10642-countersunk"]["values"]
ISO4032_NUT = _catalog["iso-4032-nut"]["values"]
ISO7089_WASHER = _catalog["iso-7089-washer"]["values"]
HEAT_SET_INSERTS = _catalog["ruthex-insert"]["values"]
BEARINGS = _catalog["bearing-deep-groove"]["values"]
_HEAD_TABLES = {
    "cap": ("iso-4762-cap", "ISO 4762"),
    "button": ("iso-7380-button", "ISO 7380-1"),
    "countersunk": ("iso-10642-countersunk", "ISO 10642"),
}


def _standard(key: str, workspace_root: str | None = None, required: tuple[str, ...] = ()) -> dict:
    entry = _catalog[key]
    from solidifai_engine import paths

    provider_paths = [Path(paths.app_config_dir()) / _PROVIDER_FILE]
    if workspace_root:
        provider_paths.append(Path(workspace_root) / _PROVIDER_FILE)
    for path in provider_paths:
        if path.exists():
            try:
                candidate = (
                    json.loads(path.read_text(encoding="utf-8")).get("standards", {}).get(key)
                )
            except (OSError, ValueError):
                candidate = None
            if candidate is not None:
                source, values = candidate.get("source"), candidate.get("values")
                valid_source = isinstance(source, dict) and set(source) == {
                    "sourceTitle",
                    "revision",
                    "table",
                    "units",
                    "verifiedDate",
                }
                valid_values = isinstance(values, dict) and all(
                    (
                        isinstance(row, dict)
                        and all(isinstance(row.get(field), (int, float)) for field in required)
                    )
                    if required
                    else isinstance(row, (int, float))
                    for row in values.values()
                )
                if not valid_source or source.get("units") != "mm" or not valid_values:
                    dimensions = ", ".join(required)
                    raise ValueError(
                        f"invalid provider standard {key!r}: required dimensions are {dimensions}"
                    )
                entry = {**entry, **candidate, "values": {**entry["values"], **values}}
    return entry


def _provenance(entry: dict) -> dict:
    return dict(entry["source"])


def sizes() -> list[str]:
    """Supported metric size designations (M2 .. M8)."""
    return list(ISO273_CLEARANCE)


def _check_size(size: str) -> str:
    if size not in ISO273_CLEARANCE:
        raise ValueError(f"unknown size {size!r}; supported: {', '.join(sizes())}")
    return size


def _thread_dia(size: str) -> float:
    return float(size[1:])


def screw(size: str, head: str = "cap", *, workspace_root: str | None = None) -> dict:
    """Head + thread dims for a metric screw. head = cap | button | countersunk."""
    _check_size(size)
    if head not in _HEAD_TABLES:
        raise ValueError(f"unknown head {head!r}; expected cap, button, or countersunk")
    key, standard = _HEAD_TABLES[head]
    entry = _standard(key, workspace_root, ("head_dia", "head_height", "socket"))
    table = entry["values"]
    if size not in table:
        raise ValueError(
            f"{standard} has no {size} (the standard starts at {min(table, key=_thread_dia)})"
        )
    out: dict[str, Any] = dict(table[size])
    out.update(
        thread_dia=_thread_dia(size), standard=standard, head=head, provenance=_provenance(entry)
    )
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
    entry = _standard("iso-273-clearance", workspace_root, ("close", "medium", "coarse"))
    return entry["values"][size][series]


def pilot_hole(size: str, *, workspace_root: str | None = None) -> float:
    """Pilot/tap-drill diameter (mm): the coarse-pitch tapping drill, also the
    thread-forming pilot for a machine screw driven into printed plastic."""
    _check_size(size)
    return _standard("tap-drill-coarse", workspace_root)["values"][size]


def thread_pitch(size: str, *, workspace_root: str | None = None) -> float:
    """Coarse thread pitch (mm) for a metric size, per ISO 261. This is the axial
    advance per turn used by a modeled helical thread (see hardware.external_thread)."""
    _check_size(size)
    return _standard("iso-261-pitch", workspace_root)["values"][size]


def nut(size: str, *, workspace_root: str | None = None) -> dict:
    _check_size(size)
    entry = _standard("iso-4032-nut", workspace_root, ("width_af", "thickness"))
    return dict(
        entry["values"][size],
        thread_dia=_thread_dia(size),
        standard="ISO 4032",
        provenance=_provenance(entry),
    )


def washer(size: str, *, workspace_root: str | None = None) -> dict:
    _check_size(size)
    entry = _standard("iso-7089-washer", workspace_root, ("od", "id", "thickness"))
    return dict(entry["values"][size], standard="ISO 7089", provenance=_provenance(entry))


def insert(size: str, *, workspace_root: str | None = None) -> dict:
    """Heat-set insert install dims (standard-length brass, Ruthex/CNC Kitchen class)."""
    if size not in HEAT_SET_INSERTS:
        raise ValueError(
            f"no heat-set insert data for {size!r}; supported: {', '.join(HEAT_SET_INSERTS)}"
        )
    entry = _standard("ruthex-insert", workspace_root, ("hole_dia", "length", "min_hole_depth"))
    return dict(
        entry["values"][size],
        standard="Ruthex-class brass insert",
        provenance=_provenance(entry),
    )


def bearing(code: str, *, workspace_root: str | None = None) -> dict:
    if code not in BEARINGS:
        raise ValueError(f"unknown bearing {code!r}; supported: {', '.join(BEARINGS)}")
    entry = _standard("bearing-deep-groove", workspace_root, ("bore", "od", "width"))
    return dict(entry["values"][code], designation=code, provenance=_provenance(entry))


# -- lookup tools (the MCP surface) -------------------------------------------

# No trailing \b: a size is often glued to more text ("M8x20", "M2.5mm"), where
# a word boundary after the digits either fails to match (M8x20 -> no size) or
# backtracks to a shorter, wrong number (M2.5mm -> M2). The leading \bm still
# anchors it to a real size token (not the m in "beam5").
_SIZE_RE = re.compile(r"\bm\s?(\d+(?:[.,]\d+)?)", re.IGNORECASE)


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
        out["bearing"] = bearing(code, workspace_root=workspace_root)
        return out

    m = _SIZE_RE.search(q)
    if m is None:
        return {
            "query": query,
            "status": "unknown",
            "action": "request_dimensions",
            "requiredDimensions": ["designation", "bore", "od", "width"],
            "error": "no metric size or bearing designation recognized",
            "supported": {"sizes": sizes(), "bearings": list(BEARINGS)},
        }
    size = _normalize_size(m.group(1))
    if size not in ISO273_CLEARANCE:
        return {
            "query": query,
            "status": "unknown",
            "action": "request_dimensions",
            "requiredDimensions": ["thread_dia", "head_dia", "head_height", "socket"],
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
                heads[head] = screw(size, head=head, workspace_root=workspace_root)
            except ValueError as exc:
                heads[head] = {"unavailable": str(exc)}
        out["screw_heads"] = heads
    if "clearance_hole" in asked:
        fit_name, series = _resolve_fit(None, workspace_root)
        clearance = _standard("iso-273-clearance", workspace_root, ("close", "medium", "coarse"))
        out["clearance_hole"] = {
            "fit": fit_name,
            "dia": clearance["values"][size][series],
            "series": dict(clearance["values"][size]),
            "note": "fit resolved from the manufacturing profile; ISO 273 series",
            "provenance": _provenance(clearance),
        }
    if "pilot_hole" in asked:
        out["pilot_hole"] = pilot_hole(size, workspace_root=workspace_root)
    if "nut" in asked:
        out["nut"] = nut(size, workspace_root=workspace_root)
    if "washer" in asked:
        out["washer"] = washer(size, workspace_root=workspace_root)
    if "heat_set_insert" in asked:
        out["heat_set_insert"] = (
            insert(size, workspace_root=workspace_root)
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
    fuzzy = None  # (matched-alias length, entry): most specific fuzzy match wins
    for entry in entries:
        eid = entry["id"] if isinstance(entry["id"], str) else str(entry["id"])
        names = [eid.replace("-", " ")] + [
            a.lower() for a in entry.get("aliases", []) if isinstance(a, str)
        ]
        if q in (eid, *names):
            best = entry
            break
        # Fuzzy fallback: q contains a full alias (word-bounded so a short alias
        # can't match mid-word), or an alias contains the whole query. Keep the
        # entry with the longest matched alias so a specific one beats a generic.
        matched = [n for n in names if q in n or re.search(rf"\b{re.escape(n)}\b", q)]
        if matched:
            span = max(len(n) for n in matched)
            if fuzzy is None or span > fuzzy[0]:
                fuzzy = (span, entry)
    if best is None and fuzzy is not None:
        best = fuzzy[1]
    if best is None:
        return {
            "query": object_name,
            "match": None,
            "available": [e["id"] for e in entries],
            "note": "no entry; verify dims by web search, say which source you used, "
            "then save_reference so it's known next time",
        }
    return {"query": object_name, "match": best, "units": "mm"}
