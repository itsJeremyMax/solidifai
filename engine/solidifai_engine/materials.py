"""Named material library + layered resolver.

A ``Material`` carries both physical density (for mass) and PBR appearance
(for the viewport). Materials are looked up through a ``MaterialResolver`` that
consults an ordered chain of ``MaterialSource``s — the built-in library ships
now; future global (~/.solidifai/materials.json) and per-workspace
(<workspace>/materials.json) sources slot in by registering another source,
with no change to render.py/props.py or the frontend (appearance travels as a
stable wire shape in model.json).

Source priority: later sources in the chain win (workspace > global > built-in).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol

# Canonical material ids are lowercase; resolve() is case-sensitive.
DEFAULT_MATERIAL = "pla"


PROCESS_FOR_BASE: Mapping[str, str] = {
    "pla": "fdm",
    "abs": "fdm",
    "petg": "fdm",
    "nylon": "fdm",
    "aluminum": "cnc",
    "steel": "cnc",
    "stainless": "cnc",
    "brass": "cnc",
    "copper": "cnc",
}


def process_for(base: str) -> str:
    """The manufacturing process implied by a base substance (default fdm)."""
    return PROCESS_FOR_BASE.get(base, "fdm")


FINISH_PRESETS: Mapping[str, dict] = {
    "matte": {
        "roughness": 0.85,
        "clearcoat": 0.0,
        "clearcoat_roughness": 0.0,
        "force_metal": False,
    },
    "satin": {
        "roughness": 0.55,
        "clearcoat": 0.1,
        "clearcoat_roughness": 0.3,
        "force_metal": False,
    },
    "gloss": {
        "roughness": 0.25,
        "clearcoat": 0.6,
        "clearcoat_roughness": 0.2,
        "force_metal": False,
    },
    "metallic": {
        "roughness": 0.35,
        "clearcoat": 0.0,
        "clearcoat_roughness": 0.0,
        "force_metal": True,
    },
}


def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(c: float) -> float:
    c = max(0.0, min(1.0, c))
    return c * 12.92 if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


def hex_to_linear(hex_color: str) -> tuple[float, float, float]:
    """`#rrggbb` (sRGB) -> linear-RGB triple in 0..1 (the engine wire space)."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"expected #rrggbb, got {hex_color!r}")
    srgb = tuple(int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    return tuple(round(_srgb_to_linear(c), 6) for c in srgb)  # type: ignore[return-value]


def linear_to_hex(color: tuple[float, float, float]) -> str:
    """Linear-RGB triple -> `#rrggbb` sRGB (for reporting built-ins to the UI)."""
    parts = [max(0, min(255, round(_linear_to_srgb(c) * 255))) for c in color]
    return "#" + "".join(f"{p:02x}" for p in parts)


@dataclass(frozen=True)
class Material:
    name: str  # canonical id, e.g. "aluminum"
    label: str  # display label, e.g. "Aluminum"
    density: float  # g/cm^3 — feeds mass
    base_color: tuple[float, float, float]  # linear RGB, 0..1
    metalness: float
    roughness: float
    clearcoat: float = 0.0
    clearcoat_roughness: float = 0.0


class MaterialSource(Protocol):
    def get(self, name: str) -> Material | None: ...
    def names(self) -> list[str]: ...


# name -> Material. Linear-RGB base colors; values are sensible starting points
# (tunable later). Metals: metalness 1.0; plastics: metalness 0.0.
BUILTIN: Mapping[str, Material] = {
    "pla": Material("pla", "PLA", 1.24, (0.52, 0.54, 0.57), 0.0, 0.62),
    "abs": Material("abs", "ABS", 1.04, (0.22, 0.23, 0.26), 0.0, 0.75),
    "petg": Material(
        "petg", "PETG", 1.27, (0.80, 0.84, 0.86), 0.0, 0.35, clearcoat=0.3, clearcoat_roughness=0.3
    ),
    "nylon": Material("nylon", "Nylon", 1.14, (0.90, 0.89, 0.85), 0.0, 0.55),
    "aluminum": Material("aluminum", "Aluminum", 2.70, (0.91, 0.92, 0.93), 1.0, 0.35),
    "steel": Material("steel", "Steel", 7.85, (0.56, 0.57, 0.60), 1.0, 0.45),
    "stainless": Material("stainless", "Stainless", 8.00, (0.69, 0.70, 0.72), 1.0, 0.30),
    "brass": Material("brass", "Brass", 8.50, (0.85, 0.67, 0.30), 1.0, 0.32),
    "copper": Material("copper", "Copper", 8.96, (0.85, 0.52, 0.38), 1.0, 0.34),
}


class BuiltinSource:
    """The shipped material layer (lowest priority)."""

    def __init__(self, table: Mapping[str, Material] = BUILTIN) -> None:
        self._table = table

    def get(self, name: str) -> Material | None:
        return self._table.get(name)

    def names(self) -> list[str]:
        return list(self._table)


def _validate_color(color: Any) -> tuple[float, float, float]:
    # color is arbitrary user input; the unpack + float() below validate it.
    try:
        r, g, b = color
    except (TypeError, ValueError):
        raise ValueError(f"color must be an (r, g, b) tuple in 0..1, got {color!r}") from None
    vals = (float(r), float(g), float(b))
    if any(v < 0.0 or v > 1.0 for v in vals):
        raise ValueError(f"color components must be in 0..1, got {vals!r}")
    return vals


def material_from_record(rec: Mapping) -> Material:
    """Build a render `Material` from a user material record."""
    base = rec.get("base", DEFAULT_MATERIAL)
    b = BUILTIN.get(base) or BUILTIN[DEFAULT_MATERIAL]
    preset = FINISH_PRESETS.get(rec.get("finish", "matte"), FINISH_PRESETS["matte"])
    color = rec.get("colorHex")
    base_color = hex_to_linear(color) if color else b.base_color
    metalness = 1.0 if preset["force_metal"] else b.metalness
    return Material(
        name=rec["id"],
        label=rec.get("label", rec["id"]),
        density=b.density,
        base_color=base_color,
        metalness=metalness,
        roughness=preset["roughness"],
        clearcoat=preset["clearcoat"],
        clearcoat_roughness=preset["clearcoat_roughness"],
    )


class JsonFileSource:
    """A material source backed by a `{default, materials:[...]}` JSON file.

    A missing or unparseable file yields an empty source (so a workspace with no
    materials.json simply contributes nothing to the chain).
    """

    def __init__(self, path: str) -> None:
        self._by_name: dict[str, Material] = {}
        self._records: dict[str, dict] = {}
        self._default: str | None = None
        try:
            data = json.loads(Path(path).read_text())
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        self._default = data.get("default")
        for rec in data.get("materials", []):
            try:
                mat = material_from_record(rec)
            except Exception:
                continue  # skip a malformed record, keep the rest
            self._by_name[mat.name] = mat
            self._records[mat.name] = dict(rec)

    def get(self, name: str) -> Material | None:
        return self._by_name.get(name)

    def names(self) -> list[str]:
        return list(self._by_name)

    @property
    def default(self) -> str | None:
        return self._default

    @property
    def records(self) -> dict[str, dict]:
        return self._records


class MaterialResolver:
    """Resolve a material name across an ordered source chain (later wins)."""

    def __init__(
        self, sources: Sequence[MaterialSource], default: str | None = DEFAULT_MATERIAL
    ) -> None:
        self._sources = list(sources)
        self._default = default or DEFAULT_MATERIAL

    def names(self) -> list[str]:
        out: set[str] = set()
        for s in self._sources:
            out.update(s.names())
        return sorted(out)

    def get(self, name: str) -> Material | None:
        for source in reversed(self._sources):  # highest priority last
            mat = source.get(name)
            if mat is not None:
                return mat
        return None

    def resolve(self, name: str | None = None, *, color=None) -> Material:
        key = name if name is not None else self._default
        mat = self.get(key)
        if mat is None:
            valid = ", ".join(self.names())
            raise ValueError(f"unknown material {key!r}; valid names: {valid}")
        if color is not None:
            mat = replace(mat, base_color=_validate_color(color))
        return mat

    def appearance(self, mat: Material) -> dict:
        """The per-object wire shape written into model.json (see render.py)."""
        return {
            "material": mat.name,
            "baseColor": [round(c, 4) for c in mat.base_color],
            "metalness": mat.metalness,
            "roughness": mat.roughness,
            "clearcoat": mat.clearcoat,
            "clearcoatRoughness": mat.clearcoat_roughness,
        }


# Default resolver: built-in only (workspaces reconfigure it at engine startup).
RESOLVER = MaterialResolver([BuiltinSource()])


def _global_materials_path() -> Path:
    # Shared app config dir (host-owned via SOLIDIFAI_CONFIG_DIR), beside destinations.json.
    from solidifai_engine import paths

    return Path(paths.app_config_dir()) / "materials.json"


def configure_resolver(workspace_root: str) -> None:
    """Rebuild the module RESOLVER for a workspace: builtin < global < workspace,
    with the effective default = workspace.default or global.default or pla."""
    global RESOLVER
    gsrc = JsonFileSource(str(_global_materials_path()))
    wsrc = JsonFileSource(str(Path(workspace_root) / "materials.json"))
    default = wsrc.default or gsrc.default or DEFAULT_MATERIAL
    RESOLVER = MaterialResolver([BuiltinSource(), gsrc, wsrc], default=default)


def _builtin_record(mat: Material) -> dict:
    """Represent a built-in substance as a user-facing record."""
    finish = "metallic" if mat.metalness >= 0.5 else "matte"
    return {
        "id": mat.name,
        "label": mat.label,
        "base": mat.name,
        "colorHex": linear_to_hex(mat.base_color),
        "finish": finish,
        "process": process_for(mat.name),
        "density": mat.density,
    }


def list_effective(workspace_root: str) -> dict:
    """The merged, user-facing material set (builtin < global < workspace) with a
    `process`, `density`, and `isDefault` flag on each. Powers `list_materials`."""
    gsrc = JsonFileSource(str(_global_materials_path()))
    wsrc = JsonFileSource(str(Path(workspace_root) / "materials.json"))
    default = wsrc.default or gsrc.default or DEFAULT_MATERIAL

    merged: dict[str, dict] = {}
    for name in BuiltinSource().names():
        merged[name] = _builtin_record(BUILTIN[name])
    for src in (gsrc, wsrc):  # later sources win
        for name, rec in src.records.items():
            base = rec.get("base", DEFAULT_MATERIAL)
            b = BUILTIN.get(base) or BUILTIN[DEFAULT_MATERIAL]
            merged[name] = {
                "id": name,
                "label": rec.get("label", name),
                "base": base,
                "colorHex": rec.get("colorHex") or linear_to_hex(b.base_color),
                "finish": rec.get("finish", "matte"),
                "process": rec.get("process") or process_for(base),
                "density": b.density,
            }

    materials = []
    for name in sorted(merged):
        entry = merged[name]
        entry["isDefault"] = name == default
        materials.append(entry)
    return {"default": default, "materials": materials}
