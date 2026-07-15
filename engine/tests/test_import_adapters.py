"""Capability-aware import adapter registry."""

import pytest

from solidifai_engine.import_adapters import (
    get_adapter,
    import_capabilities,
    unsupported_diagnostic,
)


def test_registry_reports_supported_roles():
    caps = import_capabilities()

    assert caps["step"]["roleCapability"] == "modifiable_solid"
    assert caps["stl"]["roleCapability"] == "reference_mesh"
    assert ".step" in caps["step"]["extensions"]


def test_registry_does_not_advertise_unavailable_adapters():
    caps = import_capabilities()

    assert "iges" not in caps
    assert "obj" not in caps
    assert "dxf" not in caps


def test_unsupported_format_has_actionable_diagnostic():
    diagnostic = unsupported_diagnostic("part.iges")

    assert diagnostic["code"] == "unsupported_format"
    assert diagnostic["format"] == "iges"
    assert "step" in diagnostic["recommendedFormats"]
    with pytest.raises(ValueError, match="unsupported import format"):
        get_adapter("part.iges")
