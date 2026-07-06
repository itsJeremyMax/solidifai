"""app_config_dir: honors the host-provided SOLIDIFAI_CONFIG_DIR override."""

from __future__ import annotations

from solidifai_engine import paths


def test_app_config_dir_honors_env_override(tmp_path, monkeypatch):
    target = tmp_path / "shared-config"
    monkeypatch.setenv("SOLIDIFAI_CONFIG_DIR", str(target))
    got = paths.app_config_dir()
    assert got == str(target)
    assert target.is_dir()  # created lazily


def test_app_config_dir_falls_back_without_env(tmp_path, monkeypatch):
    monkeypatch.delenv("SOLIDIFAI_CONFIG_DIR", raising=False)
    got = paths.app_config_dir()
    # Standalone fallback ends in the app-name dir, not the host override.
    assert got.endswith("solidifai")
