"""Reference imports + reverse engineering of external CAD: stage a file into the
workspace, register/remove it as a ghosted reference fixture, list the manifest,
re-apply references into the live registry, and measure an import for rebuild.

Collaborator of :class:`solidifai_engine.session.Session`; holds a back-reference
to read session state and call the build/render lifecycle helpers that stay on
Session (e.g. ``self.s._rebuild_preserving_params()``).
"""

from __future__ import annotations

import logging
import os
import shutil
from typing import TYPE_CHECKING

import solidifai
from solidifai_engine import imports_manifest, paths
from solidifai_engine import reverse as reverse_mod

if TYPE_CHECKING:
    from solidifai_engine.session import Session


class ImportManager:
    def __init__(self, s: Session):
        self.s = s

    def analyze_import(self, name=None) -> dict:
        """Measure an imported (or shown) part into dimensions + detected round
        features, so the agent can rebuild it as a clean parametric model. Targets
        the named part, else the first reference import, else the first part.
        Read-only."""
        objs = self.s._objects
        if not objs:
            return {"ok": False, "error": "no model or import to analyze"}
        target = None
        if name:
            target = next((o for o in objs if o.name == name), None)
        if target is None:
            target = next((o for o in objs if getattr(o, "role", "part") == "reference"), None)
        if target is None:
            target = objs[0]
        return {
            "ok": True,
            "name": target.name,
            "role": getattr(target, "role", "part"),
            **reverse_mod.analyze_shape(target.shape),
        }

    def _apply_references(self) -> None:
        """Refresh MANIFEST-derived references in the live registry from the
        workspace imports manifest. Best-effort per entry: a missing/bad file is
        skipped (logged), never failing the build. Called after the parametric
        build and before render, so references render and snapshot but never
        touch model.py. Script-shown references (``show(..., role="reference")``,
        the inside-out-packaging convention) are NOT manifest entries and must
        survive — only objects this refresh itself added are swept."""
        if self.s.root is None:
            return
        reg = solidifai._registry()
        reg[:] = [o for o in reg if not getattr(o, "_from_manifest", False)]
        solidifai.set_workspace_root(self.s.root)
        for e in imports_manifest.load(self.s.root):
            try:
                shape = solidifai.import_cad(e["path"])
                obj = solidifai.show(shape, name=e.get("name") or e["id"], role="reference")
                obj._from_manifest = True
            except Exception:  # noqa: BLE001 - a bad reference never breaks the build
                logging.getLogger(__name__).warning(
                    "reference %r skipped", e.get("id"), exc_info=True
                )

    @staticmethod
    def _dedupe_dest(directory: str, filename: str) -> str:
        """A non-colliding path in ``directory`` for ``filename`` (``x.stl`` ->
        ``x-1.stl`` if taken)."""
        dest = os.path.join(directory, filename)
        if not os.path.exists(dest):
            return dest
        stem, ext = os.path.splitext(filename)
        n = 1
        while os.path.exists(os.path.join(directory, f"{stem}-{n}{ext}")):
            n += 1
        return os.path.join(directory, f"{stem}-{n}{ext}")

    def stage_import(self, source_path: str) -> dict:
        """Copy ``source_path`` into the workspace ``assets/`` dir and return its
        workspace-relative path. The foundation for the modify workflow: the
        agent then calls ``import_cad(<path>)`` in model.py. Does NOT register a
        reference."""
        if self.s.root is None:
            return {"ok": False, "error": "imports need a saved workspace"}
        if not os.path.exists(source_path):
            return {"ok": False, "error": f"file not found: {source_path!r}"}
        ext = os.path.splitext(source_path)[1].lower()
        if ext not in (".step", ".stp", ".brep", ".stl"):
            return {
                "ok": False,
                "error": f"unsupported import format {ext!r}; expected .step/.stp/.brep/.stl",
            }
        assets = paths.assets_dir(self.s.root)
        os.makedirs(assets, exist_ok=True)
        dest = self._dedupe_dest(assets, os.path.basename(source_path))
        shutil.copy(source_path, dest)
        return {
            "ok": True,
            "path": os.path.join("assets", os.path.basename(dest)),
            "format": ext.lstrip("."),
        }

    def import_reference(self, source_path: str, name: str | None = None) -> dict:
        """Bring an external file in as a ghosted reference fixture: copy it into
        ``assets/``, record it in ``imports.json``, and re-render. References are
        shown and measurable but never exported or DFM-checked."""
        staged = self.stage_import(source_path)
        if not staged.get("ok") or self.s.root is None:
            return staged
        label = name or os.path.splitext(os.path.basename(staged["path"]))[0]
        entry = imports_manifest.add(
            self.s.root,
            {"name": label, "path": staged["path"], "format": staged["format"]},
        )
        res = self.s._rebuild_preserving_params()
        if not res.get("ok"):
            return res
        return {"ok": True, "buildId": self.s.build_id, "import": entry}

    def remove_import(self, import_id: str) -> dict:
        """Drop a reference import from the manifest and re-render."""
        if self.s.root is None:
            return {"ok": False, "error": "no workspace"}
        if not imports_manifest.remove(self.s.root, import_id):
            return {"ok": False, "error": f"unknown import {import_id!r}"}
        res = self.s._rebuild_preserving_params()
        if not res.get("ok"):
            return res
        return {"ok": True, "buildId": self.s.build_id}

    def list_imports(self) -> dict:
        """Return the workspace's reference imports (manifest entries)."""
        if self.s.root is None:
            return {"imports": []}
        return {"imports": imports_manifest.load(self.s.root)}
