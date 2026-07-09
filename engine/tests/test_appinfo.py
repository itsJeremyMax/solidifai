"""The single engine accessor for the app version: env-propagated, dev fallback."""

from __future__ import annotations

from solidifai_engine import appinfo


def test_reads_injected_env(monkeypatch):
    monkeypatch.setenv(appinfo.ENV_APP_VERSION, "0.5.0")
    assert appinfo.app_version() == "0.5.0"


def test_falls_back_to_dev_sentinel(monkeypatch):
    monkeypatch.delenv(appinfo.ENV_APP_VERSION, raising=False)
    assert appinfo.app_version() == appinfo.DEV_VERSION


def test_blank_env_is_treated_as_absent(monkeypatch):
    monkeypatch.setenv(appinfo.ENV_APP_VERSION, "   ")
    assert appinfo.app_version() == appinfo.DEV_VERSION
