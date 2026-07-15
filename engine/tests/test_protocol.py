from solidifai_engine.protocol import (
    CAP_READINESS,
    CAPABILITIES,
    MIN_COMPATIBLE_PROTOCOL,
    PROTOCOL_VERSION,
    negotiate,
    protocol_info,
)


def test_protocol_info_advertises_the_supported_range_and_capabilities():
    assert protocol_info() == {
        "minProtocol": 12,
        "maxProtocol": 13,
        "capabilities": sorted(CAPABILITIES),
    }
    assert MIN_COMPATIBLE_PROTOCOL == 12
    assert PROTOCOL_VERSION == 13


def test_protocol_12_client_is_compatible_but_has_no_new_capabilities():
    result = negotiate(12, [])

    assert result["compatible"] is True
    assert result["enabledCapabilities"] == []


def test_unknown_optional_client_capabilities_are_ignored():
    result = negotiate(PROTOCOL_VERSION, [CAP_READINESS, "future_capability"])

    assert result["compatible"] is True
    assert result["enabledCapabilities"] == [CAP_READINESS]


def test_non_overlapping_protocol_range_is_incompatible():
    result = negotiate(11, [])

    assert result["compatible"] is False
    assert result["enabledCapabilities"] == []


def test_missing_required_capability_is_actionable():
    result = negotiate(PROTOCOL_VERSION, [], required=[CAP_READINESS])

    assert result["compatible"] is False
    assert result["missingCapabilities"] == [CAP_READINESS]


def test_unavailable_required_capability_is_not_satisfied_by_client_claim():
    result = negotiate(PROTOCOL_VERSION, ["future_capability"], required=["future_capability"])

    assert result["compatible"] is False
    assert result["missingCapabilities"] == ["future_capability"]
