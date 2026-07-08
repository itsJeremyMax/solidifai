"""Fabrication subsystem tests — Tasks 1–4 + 7 (session wiring).

Tasks 1+2: types and geometric estimate.
Tasks 3+4: OrcaProvider detection, profile reading, preset flattening, quote.
Task  7:   Session.fab_* facade methods + Fabrication collaborator.

No OrcaSlicer process is ever launched — detection uses injectable candidates,
shell-out uses an injected runner fixture.
"""

import subprocess
import types

from solidifai_engine.fabrication import base, estimate, orca

# --- Task 1: provider protocol + types ----------------------------------------


def test_install_info_and_estimate_defaults():
    info = base.InstallInfo(found=False)
    assert info.found is False and info.version is None

    est = base.Estimate(source="approx", filamentGrams=40.0, cost=2.0, currency="USD")
    assert est.timeSeconds is None and est.to_dict()["source"] == "approx"


def test_estimate_to_dict_drops_nones():
    est = base.Estimate(source="approx", filamentGrams=12.5)
    d = est.to_dict()
    # None fields must be absent — callers depend on this for clean JSON
    assert "timeSeconds" not in d
    assert "cost" not in d
    assert "filamentLengthMm" not in d
    assert "note" not in d
    assert d["filamentGrams"] == 12.5


def test_estimate_to_dict_includes_set_values():
    est = base.Estimate(
        source="slice",
        timeSeconds=3600,
        filamentGrams=38.4,
        filamentLengthMm=12880.0,
        cost=1.15,
        currency="USD",
        note="from orca",
    )
    d = est.to_dict()
    assert d["timeSeconds"] == 3600
    assert d["filamentLengthMm"] == 12880.0
    assert d["note"] == "from orca"


def test_install_info_with_version():
    info = base.InstallInfo(found=True, version="2.1.0", executable="/usr/bin/orca")
    assert info.version == "2.1.0"
    assert info.executable == "/usr/bin/orca"


def test_capabilities_fields():
    cap = base.Capabilities(
        processes=["FDM", "SLA"],
        materials=["PLA", "PETG"],
        maxBuildSize=(256.0, 256.0, 256.0),
    )
    assert cap.processes == ["FDM", "SLA"]
    assert cap.maxBuildSize == (256.0, 256.0, 256.0)


def test_destination_fields():
    dest = base.Destination(id="d1", name="Garage", kind="local", provider="orca")
    assert dest.printerProfile is None
    assert dest.connection is None

    dest2 = base.Destination(
        id="d2",
        name="Office",
        kind="local",
        provider="orca",
        printerProfile="X1C",
        filamentProfile="PLA",
    )
    assert dest2.filamentProfile == "PLA"


def test_estimate_new_fields_roundtrip_and_drop_none():
    from solidifai_engine.fabrication import base

    est = base.Estimate(
        source="slice",
        timeSeconds=1685,
        filamentGrams=3.95,
        layerCount=100,
        supportUsed=False,
        heightMm=20.0,
        fitsBed=True,
    )
    d = est.to_dict()
    assert d["layerCount"] == 100 and d["supportUsed"] is False
    assert d["heightMm"] == 20.0 and d["fitsBed"] is True
    # Unset optionals are dropped.
    bare = base.Estimate(source="approx", filamentGrams=1.0)
    assert "layerCount" not in bare.to_dict() and "fitsBed" not in bare.to_dict()


def test_destination_has_process_profile():
    from solidifai_engine.fabrication import base

    d = base.Destination(
        id="d1",
        name="X",
        kind="local",
        provider="orca",
        processProfile="0.20mm Optimized PETG @BBL X1C",
    )
    assert d.processProfile == "0.20mm Optimized PETG @BBL X1C"


# --- Task 2: geometric fallback estimate --------------------------------------


def test_geometric_estimate_weight_and_cost():
    # 10 cm^3 solid, PLA density 1.24 g/cm^3, wall+infill model, price 25 $/kg
    est = estimate.geometric(
        volume_mm3=10_000,
        density_g_cm3=1.24,
        wall_mm=1.2,
        surface_mm2=6_000,
        infill=0.2,
        price_per_kg=25.0,
    )
    assert est.source == "approx" and est.timeSeconds is None
    assert 2.0 < est.filamentGrams < 12.0
    assert round(est.cost, 2) == round(est.filamentGrams / 1000 * 25.0, 2)


def test_geometric_estimate_note():
    est = estimate.geometric(
        volume_mm3=5_000,
        density_g_cm3=1.24,
        wall_mm=1.2,
        surface_mm2=3_000,
        infill=0.15,
        price_per_kg=25.0,
    )
    assert est.note is not None and "OrcaSlicer" in est.note


def test_geometric_estimate_solid_clamps_wall_volume():
    # wall_volume > volume: must clamp so eff == volume (infill=1.0 case)
    est = estimate.geometric(
        volume_mm3=1_000,
        density_g_cm3=1.24,
        wall_mm=10.0,  # wall_volume would exceed volume
        surface_mm2=5_000,
        infill=1.0,
        price_per_kg=25.0,
    )
    # eff should equal volume_mm3 (fully solid)
    expected_grams = 1_000 / 1000 * 1.24
    assert abs(est.filamentGrams - expected_grams) < 0.001


def test_geometric_estimate_zero_infill():
    # infill=0: only wall contributes
    volume_mm3 = 8_000
    surface_mm2 = 4_000
    wall_mm = 1.2
    wall_vol = min(surface_mm2 * wall_mm, volume_mm3)
    expected_grams = wall_vol / 1000 * 1.24
    est = estimate.geometric(
        volume_mm3=volume_mm3,
        density_g_cm3=1.24,
        wall_mm=wall_mm,
        surface_mm2=surface_mm2,
        infill=0.0,
        price_per_kg=25.0,
    )
    assert abs(est.filamentGrams - expected_grams) < 0.001


# --- Task 3: OrcaProvider detection + profile reading -------------------------


def test_detect_found_via_candidate(tmp_path):
    exe = tmp_path / "OrcaSlicer"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    p = orca.OrcaProvider(candidates=[str(exe)], version_runner=lambda e: "1.9.0")
    info = p.detect()
    assert info.found
    assert info.version == "1.9.0"
    assert info.executable == str(exe)


def test_detect_absent():
    p = orca.OrcaProvider(candidates=["/nope/OrcaSlicer"])
    assert p.detect().found is False


def test_detect_caches_result(tmp_path):
    # detect() called twice returns the same object (cached)
    exe = tmp_path / "OrcaSlicer"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    p = orca.OrcaProvider(candidates=[str(exe)], version_runner=lambda e: "2.0.0")
    first = p.detect()
    second = p.detect()
    assert first is second


def test_detect_skips_non_executable(tmp_path):
    # A file that exists but is not executable should not count as found
    exe = tmp_path / "OrcaSlicer"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o644)  # readable but not executable
    p = orca.OrcaProvider(candidates=[str(exe)])
    assert p.detect().found is False


def test_profiles_reads_real_layout(tmp_path):
    import json

    from solidifai_engine.fabrication.orca import OrcaProvider

    def w(rel, data):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data), encoding="utf-8")

    w("system/BBL/machine/X1C.json", {"type": "machine", "from": "system", "name": "X1C"})
    w("user/default/process/PETG.json", {"from": "User", "name": "PETG"})
    w("user/482203983/filament/My PLA.json", {"from": "User", "name": "My PLA"})

    p = OrcaProvider(config_dir=str(tmp_path))
    out = p.profiles()
    assert out["printers"] == ["X1C"]
    assert out["processes"] == ["PETG"]
    assert out["filaments"] == ["My PLA"]


def test_profiles_absent_returns_empty(tmp_path, monkeypatch):
    # When the Orca config dir doesn't exist, profiles() returns empty lists
    monkeypatch.setattr(orca, "_orca_config_dir", lambda: str(tmp_path / "nonexistent"))
    p = orca.OrcaProvider(candidates=[])
    result = p.profiles()
    assert result == {"printers": [], "filaments": [], "processes": []}


def test_profiles_reads_names(tmp_path):
    import json

    def w(rel, data):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data), encoding="utf-8")

    w("user/default/machine/Voron 0.2.json", {"from": "User", "name": "Voron 0.2"})
    w("user/default/filament/prusament_pla.json", {"from": "User", "name": "prusament_pla"})

    out = orca.OrcaProvider(config_dir=str(tmp_path)).profiles()
    assert "Voron 0.2" in out["printers"]
    assert "prusament_pla" in out["filaments"]


def test_orca_provider_satisfies_protocol():
    p = orca.OrcaProvider(candidates=[])
    assert isinstance(p, base.FabricationProvider)


def test_submit_returns_not_enabled():
    p = orca.OrcaProvider(candidates=[])
    dest = base.Destination(id="d1", name="x", kind="local", provider="orca")
    result = p.submit("/some/model.3mf", dest, {})
    assert result["ok"] is False
    assert "not enabled" in result["reason"].lower()


# --- Task 4: slice quote -------------------


def test_quote_nonzero_exit_returns_failure(tmp_path):
    from solidifai_engine.fabrication.orca import OrcaProvider

    def fake_runner(args, **kw):
        class R:
            returncode = 1
            stdout = "boom"

        return R()  # writes no .3mf

    p = OrcaProvider(
        candidates=["/fake/orca"],
        version_runner=lambda _e: "2.3",
        runner=fake_runner,
        config_dir=str(tmp_path),
    )
    out = p.quote("/tmp/m.3mf", {"printer": None, "filament": None, "process": None}, {})
    assert out["ok"] is False


def test_quote_flattens_and_parses_real_bundle(tmp_path):
    import json
    import shutil
    from pathlib import Path

    from solidifai_engine.fabrication.orca import OrcaProvider

    fixture = Path(__file__).parent / "fixtures" / "orca" / "sliced_cube_petg.3mf"

    def w(rel, data):
        p = tmp_path / "cfg" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data), encoding="utf-8")

    w("system/BBL/machine/X1C.json", {"type": "machine", "from": "system", "name": "X1C"})
    w("system/BBL/process/Std.json", {"type": "process", "from": "system", "name": "Std"})
    w("user/default/process/PETG.json", {"from": "User", "inherits": "Std", "name": "PETG"})
    w(
        "system/BBL/filament/PETG Basic.json",
        {"type": "filament", "from": "system", "name": "PETG Basic"},
    )

    captured = {}

    def fake_runner(args, **kw):
        captured["args"] = args
        # Find the --export-3mf target and drop the real fixture there.
        i = args.index("--export-3mf")
        shutil.copy(fixture, args[i + 1])

        class R:  # mimic subprocess.CompletedProcess
            returncode = 0
            stdout = ""

        return R()

    p = OrcaProvider(
        candidates=["/fake/orca"],
        version_runner=lambda _e: "2.3",
        runner=fake_runner,
        config_dir=str(tmp_path / "cfg"),
    )
    profile = {"printer": "X1C", "filament": "PETG Basic", "process": "PETG"}
    result = p.quote("/tmp/model.3mf", profile, {"price_per_kg": 99.0})

    assert result["ok"] is True
    est = result["estimate"]
    assert est["source"] == "slice"
    assert est["timeSeconds"] == 1685
    assert est["layerCount"] == 100
    # Real filament price (24.99 from the bundle) wins over the 99.0 fallback.
    assert round(est["cost"], 4) == round(3.95 / 1000 * 24.99, 4)

    # CLI shape: machine before process in --load-settings, filament loaded, export-3mf.
    args = captured["args"]
    assert "--datadir" in args and "--slice" in args and "--export-3mf" in args
    ls = args[args.index("--load-settings") + 1]
    machine_path, process_path = ls.split(";")
    assert machine_path.endswith(".json") and process_path.endswith(".json")
    assert "--load-filaments" in args
    assert "--outputdir" not in args  # absolute export path; never combine


def test_open_in_app_uses_launcher_not_runner(tmp_path):
    # open_in_app must use the injectable launcher (non-blocking Popen seam),
    # never _run_orca / subprocess.run, so it returns immediately without waiting.
    model = tmp_path / "model.3mf"
    model.write_text("fake 3mf")
    launched_with = []
    runner_called = []

    def capture_launcher(args, **kwargs):
        # Must NOT receive a .wait() call — just record args and return a stub
        launched_with.extend(args)
        return types.SimpleNamespace()  # no .wait() method needed

    def spy_runner(args, **kwargs):
        runner_called.append(args)
        result = types.SimpleNamespace()
        result.returncode = 0
        result.stdout = ""
        return result

    exe = tmp_path / "OrcaSlicer"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    p = orca.OrcaProvider(
        candidates=[str(exe)],
        version_runner=lambda e: "2.0.0",
        runner=spy_runner,
        launcher=capture_launcher,
    )
    result = p.open_in_app(str(model))
    assert result["ok"] is True
    # Launched via the non-blocking launcher seam
    assert str(exe) in launched_with
    assert str(model) in launched_with
    # _run_orca / runner must NOT have been called for the open handoff
    assert not runner_called


def test_capabilities_returns_fdm():
    p = orca.OrcaProvider(candidates=[])
    cap = p.capabilities()
    assert "FDM" in cap.processes
    assert len(cap.materials) > 0
    assert len(cap.maxBuildSize) == 3


# --- Task 7: Session.fab_* facade + Fabrication collaborator -----------------
# Build a tiny box model to exercise the session-level methods.

_BOX_SCRIPT = """
from build123d import Box
from solidifai import show
show(Box(20, 20, 20), name="Cube")
"""


def _make_session(tmp_path):
    """Return a Session with a built single-box model."""
    from solidifai_engine.session import Session

    sess = Session(str(tmp_path))
    res = sess.execute_script(_BOX_SCRIPT)
    assert res["ok"], f"test model failed to build: {res}"
    return sess


def test_fab_detect_returns_dict_with_found(tmp_path):
    """fab_detect() must return a dict with at least 'ok' and 'found' keys."""
    sess = _make_session(tmp_path)
    result = sess.fab_detect()
    assert "ok" in result
    assert "found" in result
    # found is a bool regardless of whether OrcaSlicer happens to be installed
    assert isinstance(result["found"], bool)


def test_fab_detect_with_fake_provider(tmp_path):
    """Injectable provider lets tests exercise the found=True path."""
    from solidifai_engine.fabrication.service import Fabrication
    from solidifai_engine.session import Session

    fake_info = base.InstallInfo(found=True, version="9.9.9", executable="/fake/orca")

    class FakeProvider:
        def detect(self):
            return fake_info

        def profiles(self):
            return {"printers": ["X1C"], "filaments": ["PLA"]}

        def quote(self, model_path, profile, options=None):
            return {"ok": True, "estimate": {"source": "slice", "filamentGrams": 30.0}}

        def open_in_app(self, model_path, destination=None):
            return {"ok": True}

        def capabilities(self):
            return base.Capabilities(
                processes=["FDM"], materials=["PLA"], maxBuildSize=(256, 256, 256)
            )

        def submit(self, model_path, destination, options):
            return {"ok": False, "reason": "not enabled"}

    sess = Session(str(tmp_path))
    sess.execute_script(_BOX_SCRIPT)
    sess._fabrication = Fabrication(sess, provider=FakeProvider())

    result = sess.fab_detect()
    assert result["ok"] is True
    assert result["found"] is True
    assert result["version"] == "9.9.9"


def test_fab_profiles_no_slicer(tmp_path):
    """fab_profiles() returns ok=True with empty lists when no slicer installed."""
    sess = _make_session(tmp_path)
    result = sess.fab_profiles()
    assert result["ok"] is True
    assert isinstance(result["printers"], list)
    assert isinstance(result["filaments"], list)


def test_fab_estimate_geometric_fallback(tmp_path):
    """fab_estimate() without a destination falls back to geometric approx."""
    sess = _make_session(tmp_path)
    result = sess.fab_estimate(destination_id=None)
    assert result["ok"] is True
    assert result["estimate"]["source"] == "approx"
    assert result["source"] == "approx"
    assert result["estimate"]["filamentGrams"] > 0


def test_fab_estimate_geometric_counts_surface_shell(tmp_path):
    """The fallback must read measure()'s surfaceArea so the shell contributes.

    A 20x20x20 box has surfaceArea 2400; the shell (surface x wall) dominates
    the printed volume. If the shell is dropped, filamentGrams collapses to the
    infill-only figure (~1.984) instead of the correct ~4.841.
    """
    sess = _make_session(tmp_path)
    result = sess.fab_estimate(destination_id=None)
    grams = result["estimate"]["filamentGrams"]
    assert grams > 3.0, f"shell not counted — got {grams}"
    assert 4.83 < grams < 4.85, f"expected ~4.841, got {grams}"


def test_fab_estimate_no_model_returns_error(tmp_path):
    """fab_estimate() with no model built returns ok=False."""
    from solidifai_engine.session import Session

    sess = Session(str(tmp_path))
    result = sess.fab_estimate()
    assert result["ok"] is False
    assert "no model" in result["error"].lower()


def test_fab_estimate_slice_path_with_fake_provider(tmp_path, monkeypatch):
    """With a detected provider + matching destination, fab_estimate calls quote."""
    from solidifai_engine import destinations as dst
    from solidifai_engine.fabrication.service import Fabrication
    from solidifai_engine.session import Session

    cfg = tmp_path / "cfg"
    cfg.mkdir()
    monkeypatch.setattr(dst, "config_dir", lambda: str(cfg))

    dest = {
        "id": "local1",
        "name": "Test Printer",
        "kind": "local",
        "provider": "orca",
        "printerProfile": "X1C",
        "filamentProfile": "PLA",
    }
    dst.write([dest])

    fake_info = base.InstallInfo(found=True, version="2.0.0", executable="/fake/orca")

    class FakeProvider:
        def detect(self):
            return fake_info

        def profiles(self):
            return {"printers": ["X1C"], "filaments": ["PLA"]}

        def quote(self, model_path, profile, options=None):
            return {
                "ok": True,
                "estimate": {"source": "slice", "filamentGrams": 38.4, "cost": 0.96},
            }

        def open_in_app(self, model_path, destination=None):
            return {"ok": True}

        def capabilities(self):
            return base.Capabilities(
                processes=["FDM"], materials=["PLA"], maxBuildSize=(256, 256, 256)
            )

        def submit(self, model_path, destination, options):
            return {"ok": False, "reason": "not enabled"}

    sess = Session(str(tmp_path / "ws"))
    sess.execute_script(_BOX_SCRIPT)
    sess._fabrication = Fabrication(sess, provider=FakeProvider())

    result = sess.fab_estimate(destination_id="local1")
    assert result["ok"] is True
    assert result["source"] == "slice"
    assert result["estimate"]["filamentGrams"] == 38.4


def test_fab_orient_returns_rotation(tmp_path):
    """fab_orient() returns a rotation list + support metrics."""
    sess = _make_session(tmp_path)
    result = sess.fab_orient()
    assert result["ok"] is True
    assert "rotation" in result
    assert isinstance(result["rotation"], list)
    assert len(result["rotation"]) == 3
    assert "supportArea" in result


def test_fab_orient_no_model_returns_error(tmp_path):
    """fab_orient() with no model built returns ok=False."""
    from solidifai_engine.session import Session

    sess = Session(str(tmp_path))
    result = sess.fab_orient()
    assert result["ok"] is False


def test_fab_open_no_slicer_returns_error(tmp_path):
    """fab_open() with no slicer detected returns ok=False (injectable provider)."""
    from solidifai_engine.fabrication.service import Fabrication
    from solidifai_engine.session import Session

    class NoSlicerProvider:
        def detect(self):
            return base.InstallInfo(found=False)

        def profiles(self):
            return {"printers": [], "filaments": []}

        def open_in_app(self, model_path, destination=None):
            raise AssertionError("should not be called when slicer absent")

        def capabilities(self):
            return base.Capabilities(processes=[], materials=[], maxBuildSize=(0, 0, 0))

        def submit(self, *a, **kw):
            return {"ok": False, "reason": "not enabled"}

        def quote(self, *a, **kw):
            return {"ok": False, "reason": "n/a"}

    sess = Session(str(tmp_path))
    sess.execute_script(_BOX_SCRIPT)
    sess._fabrication = Fabrication(sess, provider=NoSlicerProvider())

    result = sess.fab_open(destination_id=None)
    assert result["ok"] is False
    assert "slicer" in result["error"].lower()


def test_fab_open_with_fake_provider(tmp_path):
    """fab_open() with a detected fake provider returns ok=True + a persistent path."""
    import os

    from solidifai_engine.fabrication.service import Fabrication
    from solidifai_engine.session import Session

    opened_paths = []

    class FakeProvider:
        def detect(self):
            return base.InstallInfo(found=True, version="2.0.0", executable="/fake/orca")

        def profiles(self):
            return {"printers": [], "filaments": []}

        def open_in_app(self, model_path, destination=None):
            # Non-blocking: record path and return immediately (no .wait())
            opened_paths.append(model_path)
            return {"ok": True}

        def capabilities(self):
            return base.Capabilities(processes=["FDM"], materials=[], maxBuildSize=(256, 256, 256))

        def submit(self, *a, **kw):
            return {"ok": False, "reason": "not enabled"}

        def quote(self, *a, **kw):
            return {"ok": False, "reason": "n/a"}

    sess = Session(str(tmp_path))
    sess.execute_script(_BOX_SCRIPT)
    sess._fabrication = Fabrication(sess, provider=FakeProvider())

    result = sess.fab_open(destination_id=None)
    assert result["ok"] is True
    # The persistent export path is included so callers can log/display it
    assert "path" in result
    assert result["path"].endswith(".3mf")
    # The exported file must exist on disk (not deleted after launch)
    assert os.path.exists(result["path"]), "export file must persist for the slicer to read"
    # open_in_app received the same path
    assert len(opened_paths) == 1
    assert opened_paths[0] == result["path"]


def test_list_and_set_destinations_round_trip(tmp_path, monkeypatch):
    """set_destinations + list_destinations persists and retrieves correctly."""
    from solidifai_engine import destinations as dst
    from solidifai_engine.session import Session

    cfg = tmp_path / "cfg"
    cfg.mkdir()
    monkeypatch.setattr(dst, "config_dir", lambda: str(cfg))

    sess = Session(str(tmp_path / "ws"))
    dests = [
        {"id": "d1", "name": "Garage", "provider": "orca", "kind": "local"},
    ]
    set_result = sess.set_destinations(dests)
    assert set_result["ok"] is True
    assert set_result["count"] == 1

    list_result = sess.list_destinations()
    assert list_result["ok"] is True
    assert len(list_result["destinations"]) == 1
    assert list_result["destinations"][0]["name"] == "Garage"


def test_set_destinations_rejects_malformed(tmp_path, monkeypatch):
    """set_destinations rejects entries missing required id/name/provider keys."""
    from solidifai_engine import destinations as dst
    from solidifai_engine.session import Session

    cfg = tmp_path / "cfg"
    cfg.mkdir()
    monkeypatch.setattr(dst, "config_dir", lambda: str(cfg))

    sess = Session(str(tmp_path / "ws"))
    result = sess.set_destinations([{"name": "Missing id and provider"}])
    assert result["ok"] is False


def test_slice_estimate_forwards_process_and_price(monkeypatch, tmp_path):
    from solidifai_engine.fabrication import service as service_mod
    from solidifai_engine.fabrication.base import InstallInfo

    captured = {}

    class FakeProvider:
        def detect(self):
            return InstallInfo(found=True, version="2.3", executable="/x")

        def quote(self, model_path, profile, options):
            captured["profile"] = profile
            captured["options"] = options
            return {"ok": True, "estimate": {"source": "slice", "currency": "USD"}}

    # Minimal session stub with one printable object and an export path.
    class S:
        _objects = [object()]
        root = str(tmp_path)
        artifacts_dir = str(tmp_path)

    fab = service_mod.Fabrication(S(), provider=FakeProvider())
    monkeypatch.setattr(fab, "_export_temp_3mf", lambda: str(tmp_path / "m.3mf"))
    monkeypatch.setattr(
        service_mod.destinations_mod,
        "load",
        lambda: [
            {
                "id": "d1",
                "printerProfile": "X1C",
                "filamentProfile": "PETG Basic",
                "processProfile": "PETG",
            }
        ],
    )
    # Manufacturing profile supplies the fallback price.
    import solidifai_engine.manufacturing_profile as mp

    monkeypatch.setattr(mp, "effective", lambda root: {"fabrication": {"filamentCostPerKg": 42.0}})

    out = fab.fab_estimate("d1")
    assert out["ok"] is True
    assert captured["profile"]["process"] == "PETG"
    assert captured["profile"]["printer"] == "X1C"
    assert captured["options"]["price_per_kg"] == 42.0


def test_fab_profiles_includes_processes():
    from solidifai_engine.fabrication import service as service_mod

    class FakeProvider:
        def profiles(self):
            return {"printers": ["X1C"], "filaments": ["PLA"], "processes": ["Std"]}

    class S:
        pass

    fab = service_mod.Fabrication(S(), provider=FakeProvider())
    out = fab.fab_profiles()
    assert out["processes"] == ["Std"]
