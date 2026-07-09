"""Export the current model to any supported 3D format.

The model is the current ``solidifai`` registry combined into one ``Compound``.
``exports.py`` is the single source of truth for export: it owns the format
registry, the per-format option schema, option validation, and the writer
functions that wrap build123d. Both the UI (via Tauri) and the MCP tool route
through ``export`` so option handling lives in exactly one place.
"""

from __future__ import annotations

import os
import uuid as _uuid
from typing import Any

from build123d import (
    Compound,
    Mesher,
    MeshType,
    PrecisionMode,
    Unit,
    export_brep,
    export_gltf,
    export_step,
    export_stl,
)

from solidifai import _registry
from solidifai_engine.render import compound_of

# -- enum maps (engine string -> build123d enum) ---------------------------

UNITS = {
    "micron": Unit.MC,
    "mm": Unit.MM,
    "cm": Unit.CM,
    "m": Unit.M,
    "in": Unit.IN,
    "ft": Unit.FT,
}
PRECISION = {
    "average": PrecisionMode.AVERAGE,
    "greatest": PrecisionMode.GREATEST,
    "least": PrecisionMode.LEAST,
    "session": PrecisionMode.SESSION,
}
MESH_TYPES = {
    "model": MeshType.MODEL,
    "support": MeshType.SUPPORT,
    "solid_support": MeshType.SOLIDSUPPORT,
    "other": MeshType.OTHER,
}

# Quality preset -> linear tolerance / deflection (millimeters), per format.
QUALITY = {
    "stl": {"draft": 0.05, "standard": 0.01, "fine": 0.001},
    "gltf": {"draft": 0.01, "standard": 0.001, "fine": 0.0005},
    "3mf": {"draft": 0.01, "standard": 0.001, "fine": 0.0005},
}

_LABELS = {
    "step": "STEP",
    "stl": "STL",
    "glb": "GLB",
    "gltf": "glTF",
    "brep": "BREP",
    "3mf": "3MF",
}

_UNIT_CHOICES = list(UNITS)
_MESH_QUALITY = ["draft", "standard", "fine", "custom"]


def _f(t, default, **extra):
    """Build a field spec."""
    return {"type": t, "default": default, **extra}


# Field specs per format. ``glb`` and ``gltf`` share the same fields; the format
# string carries the binary/text container choice (glb = binary, gltf = text).
_GLTF_FIELDS = {
    "unit": _f("enum", "mm", choices=_UNIT_CHOICES),
    "quality": _f("enum", "standard", choices=_MESH_QUALITY),
    "linear_deflection": _f("float", 0.001, min=1e-5, max=10.0),
    "angular_deflection": _f("float", 0.1, min=1e-3, max=3.1416),
}

# Per-format spec: each value mixes a str "ext" with a "fields" dict.
_SCHEMA: dict[str, dict[str, Any]] = {
    "step": {
        "ext": "step",
        "fields": {
            "unit": _f("enum", "mm", choices=_UNIT_CHOICES),
            "precision_mode": _f("enum", "average", choices=list(PRECISION)),
            "write_pcurves": _f("bool", True),
            # "current" -> build123d default (now); any other string -> fixed.
            "timestamp": _f("str", "current"),
        },
    },
    "stl": {
        "ext": "stl",
        "fields": {
            "ascii": _f("bool", False),
            "quality": _f("enum", "standard", choices=_MESH_QUALITY),
            "tolerance": _f("float", 0.01, min=1e-5, max=10.0),
            "angular_tolerance": _f("float", 0.1, min=1e-3, max=3.1416),
        },
    },
    "glb": {"ext": "glb", "fields": _GLTF_FIELDS},
    "gltf": {"ext": "gltf", "fields": _GLTF_FIELDS},
    "brep": {"ext": "brep", "fields": {}},
    "3mf": {
        "ext": "3mf",
        "fields": {
            "unit": _f("enum", "mm", choices=_UNIT_CHOICES),
            "quality": _f("enum", "standard", choices=_MESH_QUALITY),
            "linear_deflection": _f("float", 0.001, min=1e-5, max=10.0),
            "angular_deflection": _f("float", 0.1, min=1e-3, max=3.1416),
            "mesh_type": _f("enum", "model", choices=list(MESH_TYPES)),
            "part_number": _f("str", ""),
            "uuid": _f("str", ""),
        },
    },
}

SUPPORTED = tuple(_SCHEMA)


def options_schema(format: str | None = None) -> dict:
    """Return the option field specs for one format, or all formats keyed by
    format string when ``format`` is None. JSON-serializable."""
    if format is None:
        return {k: v["fields"] for k, v in _SCHEMA.items()}
    fmt = format.lower()
    if fmt not in _SCHEMA:
        raise ValueError(f"Unsupported format {format!r}.")
    return _SCHEMA[fmt]["fields"]


def _coerce(name: str, spec: dict, val: Any):
    t = spec["type"]
    if t == "enum":
        if val not in spec["choices"]:
            raise ValueError(f"{name} must be one of {', '.join(spec['choices'])}.")
        return val
    if t == "bool":
        if not isinstance(val, bool):
            raise ValueError(f"{name} must be true or false.")
        return val
    if t == "float":
        try:
            f = float(val)
        except (TypeError, ValueError):
            raise ValueError(f"{name} must be a number.") from None
        if "min" in spec and f < spec["min"]:
            raise ValueError(f"{name} must be at least {spec['min']}.")
        if "max" in spec and f > spec["max"]:
            raise ValueError(f"{name} must be at most {spec['max']}.")
        return f
    return str(val)


def _qmap_key(fmt: str) -> str:
    return "gltf" if fmt in ("glb", "gltf") else fmt


def validate_options(format: str, options: dict | None) -> dict:
    """Fill defaults, coerce types, reject unknown keys / bad values, and expand
    the quality preset into the concrete tolerance. Returns clean kwargs."""
    fmt = format.lower()
    if fmt not in _SCHEMA:
        raise ValueError(f"Unsupported format {format!r}.")
    fields = _SCHEMA[fmt]["fields"]
    options = options or {}
    for key in options:
        if key not in fields:
            raise ValueError(f"Unknown option {key!r} for {_LABELS[fmt]}.")
    out = {name: spec["default"] for name, spec in fields.items()}
    for name, spec in fields.items():
        if name in options:
            out[name] = _coerce(name, spec, options[name])
    if "quality" in fields:
        tol = "tolerance" if "tolerance" in fields else "linear_deflection"
        if tol in options:
            out["quality"] = "custom"
        elif out["quality"] != "custom":
            out[tol] = QUALITY[_qmap_key(fmt)][out["quality"]]
    return out


# -- writers ---------------------------------------------------------------


def _timestamp(value: str):
    return None if value in (None, "", "current") else value


def _write_step(shape, path, o):
    export_step(
        shape,
        path,
        unit=UNITS[o["unit"]],
        write_pcurves=o["write_pcurves"],
        precision_mode=PRECISION[o["precision_mode"]],
        timestamp=_timestamp(o["timestamp"]),
    )


def _write_stl(shape, path, o):
    export_stl(
        shape,
        path,
        tolerance=o["tolerance"],
        angular_tolerance=o["angular_tolerance"],
        ascii_format=o["ascii"],
    )


def _write_gltf(shape, path, o, binary):
    export_gltf(
        shape,
        path,
        unit=UNITS[o["unit"]],
        binary=binary,
        linear_deflection=o["linear_deflection"],
        angular_deflection=o["angular_deflection"],
    )


def _write_brep(shape, path, o):
    export_brep(shape, path)


def _write_3mf(shape, path, o):
    mesher = Mesher(unit=UNITS[o["unit"]])
    uid = _uuid.UUID(o["uuid"]) if o["uuid"] else None
    mesher.add_shape(
        shape,
        linear_deflection=o["linear_deflection"],
        angular_deflection=o["angular_deflection"],
        mesh_type=MESH_TYPES[o["mesh_type"]],
        part_number=o["part_number"] or None,
        uuid_value=uid,
    )
    mesher.write(path)


_WRITERS = {
    "step": _write_step,
    "stl": _write_stl,
    "glb": lambda s, p, o: _write_gltf(s, p, o, True),
    "gltf": lambda s, p, o: _write_gltf(s, p, o, False),
    "brep": _write_brep,
    "3mf": _write_3mf,
}


def _compound_from_objects(objects) -> Compound:
    """Build the export compound from a ShownObject list, dropping references and
    validating there is printable geometry. Wraps COPIES so exporting never steals
    the shapes out of the caller's live snapshot compound."""
    objects = list(objects)
    if not objects:
        raise ValueError("nothing to export: registry is empty (did you call show()?)")
    # Reference imports are fixtures you fit around, not your part -- never export them.
    shapes = [o.shape for o in objects if getattr(o, "role", "part") != "reference"]
    if not shapes:
        raise ValueError("nothing to export: the model is only reference imports")
    return compound_of(shapes)


def _current_compound() -> Compound:
    return _compound_from_objects(_registry())


def export(
    format: str,
    path: str,
    options: dict | None = None,
    shape: Any | None = None,
    objects: list | None = None,
) -> str:
    """Export ``shape`` (or the current model) to ``path`` in ``format`` using
    ``options``. ``format`` is one of ``SUPPORTED``. Returns ``path``.

    Pass ``objects`` (a ShownObject snapshot) to export the last-good model rather
    than the live global registry, which a failed build can leave holding partial
    geometry. When both are omitted the live registry is used."""
    fmt = format.lower()
    if fmt not in _SCHEMA:
        raise ValueError(f"Unsupported format {format!r}; expected one of {', '.join(SUPPORTED)}.")
    resolved = validate_options(fmt, options)
    if shape is not None:
        target = shape
    elif objects is not None:
        target = _compound_from_objects(objects)
    else:
        target = _current_compound()
    # Normalize once so the directory we create and the file the writer opens
    # agree; otherwise a '..' path writes through a still-missing dir and fails
    # silently. Ensure the parent exists (e.g. a fresh "exports" folder) too.
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _WRITERS[fmt](target, path, resolved)
    # build123d's stl/brep/gltf writers return False rather than raising on a
    # failed write, so a missing or empty file would otherwise pass as success.
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        raise RuntimeError(f"export failed: {_LABELS[fmt]} writer produced no file at {path}")
    return path
