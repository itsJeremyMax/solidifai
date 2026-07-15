from solidifai_engine.export_policy import decide_export, verify_override


def test_legacy_export_is_unchanged_but_strict_export_blocks():
    readiness = {"level": "blocked", "findingIds": ["reference:board"]}
    assert decide_export(readiness, strict_readiness=False)["allowed"] is True
    assert decide_export(readiness, strict_readiness=True)["allowed"] is False


def test_verified_override_allows_one_strict_export_decision():
    assert (
        decide_export(
            {"level": "blocked", "findingIds": ["x"]}, strict_readiness=True, override=True
        )["allowed"]
        is True
    )


def test_override_verifier_receives_only_scoped_nonce_claims():
    received = {}

    def consume(nonce, *, workspace_id, build_id, format):
        received.update(
            nonce=nonce,
            workspace_id=workspace_id,
            build_id=build_id,
            format=format,
        )
        return {"ok": True, "nonceId": "host-issued"}

    assert verify_override(
        consume,
        "opaque-nonce",
        workspace_id="/workspace",
        build_id=4,
        format="stl",
    ) == {"ok": True, "nonceId": "host-issued"}
    assert received == {
        "nonce": "opaque-nonce",
        "workspace_id": "/workspace",
        "build_id": 4,
        "format": "stl",
    }
