"""slicers override store + OrcaProvider honoring the host-configured binary."""

from __future__ import annotations

import json

from solidifai_engine import slicers
from solidifai_engine.fabrication.orca import OrcaProvider


def _write_override(config_dir, path: str) -> None:
    (config_dir / "slicers.json").write_text(
        json.dumps({"schema": 1, "slicers": {"orca": {"executablePath": path}}})
    )


def test_override_executable_reads_slicers_json(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLIDIFAI_CONFIG_DIR", str(tmp_path))
    _write_override(tmp_path, "/x/orca")
    assert slicers.override_executable("orca") == "/x/orca"
    assert slicers.override_executable("prusa") is None  # unknown provider


def test_override_missing_or_blank_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLIDIFAI_CONFIG_DIR", str(tmp_path))
    assert slicers.override_executable("orca") is None  # no file
    _write_override(tmp_path, "   ")
    assert slicers.override_executable("orca") is None  # blank is not an override


def test_orca_detect_honors_override(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLIDIFAI_CONFIG_DIR", str(tmp_path))
    fake = tmp_path / "my-orca"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    _write_override(tmp_path, str(fake))

    info = OrcaProvider(version_runner=lambda _exe: "9.9.9").detect()
    assert info.found is True
    assert info.executable == str(fake)
    assert info.version == "9.9.9"
