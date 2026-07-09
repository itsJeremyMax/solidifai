"""Reporting + output composition: geometric diff against a checkpoint, the
printable build report (report.html), and the dimensioned technical drawing.

Collaborator of :class:`solidifai_engine.session.Session`; holds a back-reference
to read session state and call the build/render/measure helpers that stay on
Session (e.g. ``self.s._build_compound()``, ``self.s.measure()``). All methods
here are read-only on the model.
"""

from __future__ import annotations

import contextlib
import json
import os
from typing import TYPE_CHECKING, Any

from solidifai_engine import dfm as dfm_rules
from solidifai_engine import materials as _materials
from solidifai_engine import paths, scratch

if TYPE_CHECKING:
    from solidifai_engine.session import Session


def _req_color(passed) -> str:
    if passed is True:
        return "#22863a"
    return "#c0392b" if passed is False else "#888"


def _req_label(passed) -> str:
    if passed is True:
        return "pass"
    return "fail" if passed is False else "unknown"


class Reporting:
    def __init__(self, s: Session):
        self.s = s

    # -- history: geometric diff + build report -----------------------------

    @staticmethod
    def _region(diff) -> dict:
        """Volume + bbox of a boolean-difference region (empty when negligible)."""
        try:
            v = float(diff.volume)
        except Exception:  # noqa: BLE001
            v = 0.0
        if v < 1e-6:
            return {"volume": 0.0, "bbox": None}
        bb = diff.bounding_box()
        return {
            "volume": round(v, 4),
            "bbox": {
                "size": [round(bb.size.X, 4), round(bb.size.Y, 4), round(bb.size.Z, 4)],
                "min": [round(bb.min.X, 4), round(bb.min.Y, 4), round(bb.min.Z, 4)],
                "max": [round(bb.max.X, 4), round(bb.max.Y, 4), round(bb.max.Z, 4)],
            },
        }

    def diff_against(self, index: int) -> dict:
        """Compare the current model to the checkpoint at history ``index``.

        Single-model: material added and removed (best-effort boolean) plus scalar
        volume/bbox deltas (always); non-destructive (reconstructs the checkpoint
        from its snapshotted code+params, then restores the live registry).

        Assembly: a STRUCTURAL diff separating manifest (children added / removed /
        rewired), skeleton (params), and per-part source changes."""
        if self.s.history is None or not self.s.history.enabled():
            return {"ok": False, "error": "history not available"}
        entries = self.s.history.entries()
        if not (0 <= index < len(entries)):
            return {"ok": False, "error": f"no checkpoint at index {index}"}
        if self.s._is_assembly_mode():
            return self._structural_diff_against(index, entries)
        if self.s._model is None or self.s.code is None:
            return {"ok": False, "error": "no current model to diff"}
        sha = self.s.history.commits[index]
        code_blob = self.s.history._blob_at(sha, "model.py")
        if code_blob is None:
            return {"ok": False, "error": "checkpoint has no model"}
        settings_blob = self.s.history._blob_at(sha, "settings.json")
        old_params = {}
        if settings_blob:
            try:
                old_params = json.loads(settings_blob.decode("utf-8")).get("params", {})
            except (ValueError, AttributeError):
                old_params = {}
        try:
            other = self.s._build_compound(code_blob.decode("utf-8"), old_params)
        except Exception as exc:  # noqa: BLE001
            self._restore_live_registry()
            return {"ok": False, "error": f"couldn't rebuild checkpoint: {exc}"}
        finally:
            self._restore_live_registry()

        current = self.s._model  # not None (guarded above; the snapshot is intact)
        assert current is not None
        cur_v, other_v = float(current.volume), float(other.volume)
        cb, ob = current.bounding_box(), other.bounding_box()
        bbox_delta = [
            round(cb.size.X - ob.size.X, 4),
            round(cb.size.Y - ob.size.Y, 4),
            round(cb.size.Z - ob.size.Z, 4),
        ]
        out: dict[str, Any] = {
            "ok": True,
            "against": {"index": index, "message": entries[index]["message"]},
            "volumeDelta": round(cur_v - other_v, 4),
            "bboxDelta": bbox_delta,
            "currentVolume": round(cur_v, 4),
            "checkpointVolume": round(other_v, 4),
        }
        try:
            out["added"] = self._region(current - other)
            out["removed"] = self._region(other - current)
            out["geometric"] = True
            out["changed"] = out["added"]["volume"] > 1e-6 or out["removed"]["volume"] > 1e-6
        except Exception as exc:  # noqa: BLE001 - boolean can choke on bad geometry
            out["geometric"] = False
            out["note"] = (
                f"geometric diff unavailable ({type(exc).__name__}); showing scalar deltas"
            )
            out["changed"] = abs(out["volumeDelta"]) > 1e-6 or any(
                abs(d) > 1e-6 for d in bbox_delta
            )
        out["compliance"] = self._compliance_diff(sha)
        return out

    def _structural_diff_against(self, index: int, entries: list) -> dict:
        """Structural diff of the live assembly fileset against the snapshot at
        ``index``: which children were added / removed / rewired, whether the
        skeleton (params) changed, and which part sources changed. Reads the old
        snapshot from the commit tree and the current one from the working tree."""
        from solidifai_engine.assembly import diff as diff_mod
        from solidifai_engine.history import _assembly_fileset

        hist = self.s.history
        # diff_against() gates on history being present/enabled before delegating here,
        # and an assembly with history always has a root on disk.
        assert hist is not None and self.s.root is not None
        root = self.s.root
        sha = hist.commits[index]
        old_blobs = hist._tree_blobs(sha)
        old_files = {path: data.decode("utf-8", "replace") for path, data in old_blobs.items()}
        new_files: dict[str, str] = {}
        for rel in _assembly_fileset(root):
            abspath = os.path.join(root, rel)
            try:
                with open(abspath, encoding="utf-8") as f:
                    new_files[rel] = f.read()
            except OSError:
                continue
        result = diff_mod.structural_diff(root, old_files, new_files)
        return {
            "ok": True,
            "against": {"index": index, "message": entries[index]["message"]},
            **result,
        }

    def _compliance_diff(self, checkpoint_sha: str) -> dict:
        """Compare the checkpoint's stored compliance to the current check_requirements.

        Returns {checkpoint, current, newly_passing, newly_failing}. The
        checkpoint side is None when no compliance was snapped at that time.
        """
        stored = self.s.history.read_compliance(checkpoint_sha) if self.s.history else None
        try:
            cr = self.s.check_requirements()
            cur_summary = cr.get("summary", {})
            cur_pass_map: dict = {
                r["id"]: r.get("pass") for r in cr.get("requirements", []) if "id" in r
            }
            current: dict | None = {
                "met": cur_summary.get("met", 0),
                "total": cur_summary.get("total", 0),
                "allMet": cur_summary.get("allMet", True),
                "pass_map": cur_pass_map,
            }
        except Exception:  # noqa: BLE001
            current = None

        newly_passing: list[str] = []
        newly_failing: list[str] = []
        if stored and current:
            old_map: dict = stored.get("pass_map", {})
            new_map: dict = current.get("pass_map", {})
            for req_id, new_pass in new_map.items():
                old_pass = old_map.get(req_id)
                if old_pass is not True and new_pass is True:
                    newly_passing.append(req_id)
                elif old_pass is not False and new_pass is False:
                    newly_failing.append(req_id)

        return {
            "checkpoint": stored,
            "current": current,
            "newly_passing": newly_passing,
            "newly_failing": newly_failing,
        }

    def _restore_live_registry(self) -> None:
        """Rebuild the live model into the registry (after a non-destructive diff
        left a checkpoint's geometry there). The self._model snapshot is intact."""
        if self.s.code is None:
            return
        # Live params built fine once already; restoring is best-effort.
        with contextlib.suppress(Exception):
            self.s._build_compound(self.s.code, self.s._param_values)

    def build_report(self, views=None) -> dict:
        """Compose a printable spec sheet (report.html) from the current model:
        a rendered view grid plus mass, dimensions, material, and the DFM summary.
        Read-only. Degrades gracefully if a sub-step fails."""
        if not self.s._objects:
            return {"ok": False, "error": "no model -- run execute_script first"}
        m = self.s.measure()
        info = self.s.get_model_info()
        try:
            dfm = self.s.analyze_dfm()
            dfm_sum = dfm["summary"] if dfm.get("ok") else None
        except Exception:  # noqa: BLE001
            dfm_sum = None
        try:
            cap = self.s.capture_views(views or ["iso", "front", "top", "right"], layout="grid")
            sheet = cap["views"][0]["path"] if cap.get("ok") and cap.get("views") else None
        except Exception:  # noqa: BLE001
            sheet = None
        mass = info.get("mass") or {}
        try:
            compliance = self.s.check_requirements()
        except Exception:  # noqa: BLE001
            compliance = None
        summary = {
            "mass": (m.get("total") or {}).get("mass", mass.get("value", 0)),
            "bbox": (info.get("bbox") or {}).get("size"),
            "material": mass.get("material", ""),
            "dfm": dfm_sum,
            "compliance": compliance,
        }
        path = os.path.join(self.s.artifacts_dir, "report.html")
        tmp = paths.write_temp_text(path, self._report_html(summary, info, sheet))
        paths.atomic_finalize(tmp, path)
        return {"ok": True, "path": path, "summary": summary}

    @staticmethod
    def _report_html(summary, info, sheet) -> str:
        import html as _html

        rows = [
            ("Mass", f"{summary['mass']} g  ({summary['material']})"),
            ("Bounding box", " x ".join(str(v) for v in (summary["bbox"] or [])) + " mm"),
            ("Watertight", "yes" if info.get("manifold") else "no"),
        ]
        if summary["dfm"]:
            d = summary["dfm"]
            rows.append(
                (
                    "DFM",
                    f"{d.get('critical', 0)} critical, {d.get('warning', 0)} warning, "
                    f"{d.get('advisory', 0)} advisory",
                )
            )
        table = "".join(
            f"<tr><th>{_html.escape(k)}</th><td>{_html.escape(str(v))}</td></tr>" for k, v in rows
        )
        img = f'<img src="file://{sheet}" alt="views">' if sheet else ""

        # Spec compliance section: only rendered when requirements exist.
        compliance_html = ""
        cr = summary.get("compliance")
        if cr and cr.get("ok") and cr.get("requirements"):
            s = cr["summary"]
            met, total = s.get("met", 0), s.get("total", 0)
            status = "All requirements met" if s.get("allMet") else f"{met} of {total} met"
            req_rows = "".join(
                "<tr>"
                f"<td>{_html.escape(r.get('id', ''))}</td>"
                f"<td style='color:{_req_color(r.get('pass'))}'>"
                f"{_req_label(r.get('pass'))}</td>"
                f"<td>{_html.escape(r.get('detail', '') or '')}</td>"
                "</tr>"
                for r in cr["requirements"]
            )
            compliance_html = (
                f"<h2>Spec compliance</h2><p>{_html.escape(status)}</p><table>{req_rows}</table>"
            )

        return (
            "<!doctype html><meta charset=utf-8><title>solidifai report</title>"
            "<style>body{font:14px -apple-system,system-ui,sans-serif;margin:40px;color:#1a1a1a}"
            "h1{font-weight:600}h2{font-size:1em;font-weight:600;margin-top:28px}"
            "table{border-collapse:collapse;margin-top:16px}"
            "th{text-align:left;padding:6px 18px 6px 0;color:#666;font-weight:500}"
            "td{padding:6px 0}img{max-width:100%;margin-top:20px;border:1px solid #eee}"
            "@media print{body{margin:0}}</style>"
            f"<h1>solidifai build report</h1>{img}<table>{table}</table>"
            f"{compliance_html}"
        )

    # -- technical drawing --------------------------------------------------

    def create_drawing(self, path: str | None = None, options: dict | None = None) -> dict:
        """Generate a dimensioned multi-view drawing + spec sheet (SVG + PDF) of
        the current model. References are excluded (a manufacturing drawing shows
        your parts only). Writes into the workspace ``exports/`` (or ``path``) and
        returns the file paths + chosen scale. Read-only on the model."""
        from solidifai_engine.render import compound_of

        if not self.s._objects:
            return {"ok": False, "error": "no model -- run execute_script first"}
        objects = [o for o in self.s._objects if getattr(o, "role", "part") != "reference"]
        if not objects:
            return {"ok": False, "error": "nothing to draw: the model is only reference imports"}

        compound = compound_of([o.shape for o in objects])
        spec = self._drawing_spec(objects, compound)
        groups = spec.get("groups") or []
        try:
            from solidifai_engine.drawing import backends as dwg_backends
            from solidifai_engine.drawing import sheet as dwg_sheet

            pages, meta = dwg_sheet.compose_document(groups, compound, spec, options or {})
            svg = dwg_backends.to_svg_document(pages)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"drawing failed ({type(exc).__name__}): {exc}"}

        base = (
            os.path.join(self.s.root, "exports")
            if self.s.root
            else scratch.exports_dir(self.s.artifacts_dir)
        )
        os.makedirs(base, exist_ok=True)
        slug = scratch.slug(os.path.basename(self.s.root) if self.s.root else "model")
        if path:
            pdf_path = path if os.path.isabs(path) else os.path.join(base, path)
            stem = os.path.splitext(pdf_path)[0]
        else:
            stem = os.path.join(base, f"{slug}-drawing")
            pdf_path = stem + ".pdf"
        svg_path = stem + ".svg"

        files = []
        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(svg)
        files.append(svg_path)
        note = None
        try:
            produced = dwg_backends.to_pdf_document(pages, pdf_path)
        except Exception as exc:  # noqa: BLE001 - PDF is best-effort
            produced = None
            note = f"PDF skipped ({type(exc).__name__}); wrote SVG."
        if produced:
            files.append(produced)
        elif note is None:
            note = "PDF unavailable (fpdf2 not installed); wrote SVG only."
        return {"ok": True, "files": files, "scale": meta.get("scaleLabel"), "note": note}

    def _drawing_spec(self, objects, compound) -> dict:
        """Gather the title-block / spec-sheet / dimension data from the parts."""
        import datetime

        bb = compound.bounding_box()
        bbox = (round(bb.size.X, 2), round(bb.size.Y, 2), round(bb.size.Z, 2))

        # Group identical parts (pose-invariant) so the BOM and the per-part detail
        # sheets collapse duplicates (4 identical Feet -> one row/sheet, qty 4).
        from solidifai_engine.drawing import features

        groups = features.group_parts(objects)
        bom, total_mass, labels, process = [], 0.0, set(), "fdm"
        for g in groups:
            rep = g["rep"]
            try:
                mat = _materials.RESOLVER.resolve(rep.material, color=rep.color)
            except Exception:  # noqa: BLE001
                mat = _materials.RESOLVER.resolve(None)
            mass_each = (float(rep.shape.volume) / 1000.0) * mat.density
            qty = g["qty"]
            total_mass += mass_each * qty
            labels.add(mat.label)
            process = _materials.process_for(mat.name)
            g["shape"] = rep.shape
            g["spec"] = self._part_spec(g, mat, mass_each, process)
            bom.append(
                {
                    "name": g["name"],
                    "qty": qty,
                    "material": mat.label,
                    "mass_each_g": round(mass_each, 2),
                    "mass_total_g": round(mass_each * qty, 2),
                    "mass_g": round(mass_each, 2),
                }
            )
        material = next(iter(labels)) if len(labels) == 1 else "mixed"

        # Hole schedule: count cylindrical hole faces directly (robust axis-based
        # classification), deduped so a through-hole split into half-cylinders is
        # one hole. Coarse feature inference under-counted off-center holes.
        holes: dict = {}
        try:
            seen: set = set()
            for f in compound.faces():
                if "CYLINDER" not in str(f.geom_type) or not dfm_rules._is_hole(f):
                    continue
                r = dfm_rules._cylinder_radius(f)
                if not r:
                    continue
                c = f.center()
                key = (round(c.X, 1), round(c.Y, 1), round(c.Z, 1), round(r, 2))
                if key in seen:
                    continue
                seen.add(key)
                dia = round(r * 2.0, 1)
                holes[dia] = holes.get(dia, 0) + 1
        except Exception:  # noqa: BLE001 - hole schedule is best-effort enrichment
            holes = {}

        sev = {"critical": 0, "warning": 0, "advisory": 0}
        for o in objects:
            if self.s._infer_process(o.material) != "fdm":
                continue
            try:
                for v in dfm_rules.analyze_part(o.shape, process="fdm")["violations"]:
                    sev[v["severity"]] = sev.get(v["severity"], 0) + 1
            except Exception:  # noqa: BLE001
                pass
        total_sev = sum(sev.values())
        dfm_summary = (
            "No issues"
            if total_sev == 0
            else f"{sev['critical']} crit, {sev['warning']} warn, {sev['advisory']} adv"
        )

        return {
            "bbox": bbox,
            "material": material,
            "process": process.upper(),
            "mass_g": round(total_mass, 2),
            "volume_cm3": round(float(compound.volume) / 1000.0, 2),
            "part_count": len(objects),
            "bom": bom,
            "groups": groups,
            "holes": holes,
            "dfm_summary": dfm_summary,
            "name": os.path.basename(self.s.root) if self.s.root else "model",
            "units": "mm",
            "generated_at": datetime.date.today().isoformat(),
        }

    def _part_spec(self, group, mat, mass_each, process) -> dict:
        """Per-part detail-sheet spec: own bbox, qty, located holes, per-part DFM."""
        import datetime

        from solidifai_engine.drawing import features

        shape = group["rep"].shape
        bb = shape.bounding_box()
        sev = {"critical": 0, "warning": 0, "advisory": 0}
        if str(process).lower() == "fdm":
            try:
                for v in dfm_rules.analyze_part(shape, process="fdm")["violations"]:
                    sev[v["severity"]] = sev.get(v["severity"], 0) + 1
            except Exception:  # noqa: BLE001 - per-part DFM is best-effort enrichment
                pass
        total_sev = sum(sev.values())
        dfm_summary = (
            "No issues"
            if total_sev == 0
            else f"{sev['critical']} crit, {sev['warning']} warn, {sev['advisory']} adv"
        )
        return {
            "bbox": (round(bb.size.X, 2), round(bb.size.Y, 2), round(bb.size.Z, 2)),
            "name": group["name"],
            "qty": group["qty"],
            "material": mat.label,
            "process": str(process).upper(),
            "mass_g": round(mass_each, 2),
            "holes": features.extract_holes(shape),
            "dfm_summary": dfm_summary,
            "units": "mm",
            "generated_at": datetime.date.today().isoformat(),
        }
