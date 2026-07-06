"""Per-workspace + global manufacturing profile.

Configurable design/process defaults (fit, wall, fillet, min-feature, an
FDM-leaning process, advisory fabrication temps/cost) layered
builtin <= global <= workspace, mirroring materials.py's resolver.

The built-in defaults live in a shared JSON asset
(``manufacturing_profile_defaults.json``) read by BOTH this module and the Rust
provisioner, so the two surfaces never drift. The on-disk files
(``<config>/manufacturing-profile.json`` and ``<workspace>/manufacturing-profile.json``)
hold SPARSE OVERRIDES only.

The default *material* is NOT stored here; ``effective()`` echoes it read-only
from the materials library so Sol sees one unified view.

Writes are delegated to the Rust host via ``control.py``; this module is
read-only from the engine side.
"""

from __future__ import annotations

import copy
import json
import logging
from pathlib import Path

from solidifai_engine import paths

PROFILE_NAME = "manufacturing-profile.json"
SCHEMA = 1
_ASSET = Path(__file__).with_name("manufacturing_profile_defaults.json")
_LOG = logging.getLogger(__name__)


def builtin_defaults() -> dict:
    """The shipped defaults (the real values), from the shared asset."""
    return json.loads(_ASSET.read_text(encoding="utf-8"))


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _load_overrides(path: Path) -> dict:
    """Sparse overrides from a profile file; ``{}`` if missing/malformed."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _LOG.debug("ignoring unreadable manufacturing profile %s: %s", path, exc)
        return {}
    if not isinstance(data, dict):
        return {}
    data.pop("schema", None)
    return data


def _global_path() -> Path:
    return Path(paths.app_config_dir()) / PROFILE_NAME


def resolve(workspace_root: str) -> dict:
    """builtin <= global <= workspace, deep-merged. Never raises."""
    merged = builtin_defaults()
    merged.pop("schema", None)
    for p in (_global_path(), Path(workspace_root) / PROFILE_NAME):
        merged = _deep_merge(merged, _load_overrides(p))
    merged["schema"] = SCHEMA
    return merged


def fit_clearance(profile: dict) -> float:
    """Clearance (mm) for the profile's selected fit class."""
    fit = (profile.get("design") or {}).get("fit", "normal")
    fits = profile.get("fits") or {}
    return float(fits.get(f"{fit}Mm", fits.get("normalMm", 0.2)))


def effective(workspace_root: str) -> dict:
    """The resolved profile with the default material echoed in read-only
    (composed from the materials library; the profile never stores material)."""
    prof = resolve(workspace_root)
    from solidifai_engine import materials

    eff = materials.list_effective(workspace_root)
    default_id = eff.get("default")
    label = next(
        (m["label"] for m in eff.get("materials", []) if m.get("id") == default_id),
        default_id,
    )
    prof["material"] = {"id": default_id, "label": label}
    return prof
