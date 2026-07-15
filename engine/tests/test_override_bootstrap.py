"""Private override bootstrap transport tests."""

from __future__ import annotations

import io

import pytest

from solidifai_engine.__main__ import build_override_verifier
from solidifai_engine.control import OverrideBootstrapError, read_override_bootstrap


def frame(payload: bytes) -> io.BytesIO:
    return io.BytesIO(len(payload).to_bytes(4, "big") + payload)


def test_reads_one_private_bootstrap_frame():
    payload = b'{"transport":{"kind":"unix","path":"private-endpoint"}}'
    assert read_override_bootstrap(frame(payload)) == {
        "kind": "unix",
        "path": "private-endpoint",
    }


@pytest.mark.parametrize("stream", [io.BytesIO(), io.BytesIO(b"\x00\x00\x00\x10{}")])
def test_missing_or_truncated_bootstrap_frame_fails_without_waiting(stream):
    with pytest.raises(OverrideBootstrapError):
        read_override_bootstrap(stream)


@pytest.mark.parametrize(
    "payload",
    [
        b"not-json",
        b"[]",
        b"{}",
        b'{"transport": {"kind": "unix", "path": 1}}',
        b'{"transport": {"kind": "tcp", "address": "127.0.0.1:1"}}',
        b'{"transport": {"kind": "unknown", "path": "x"}}',
    ],
)
def test_malformed_bootstrap_frame_is_rejected(payload):
    with pytest.raises(OverrideBootstrapError):
        read_override_bootstrap(frame(payload))


def test_eval_test_mode_skips_bootstrap_and_rejects_overrides():
    verifier, close = build_override_verifier(
        "eval-test",
        bootstrap_factory=lambda: (_ for _ in ()).throw(AssertionError("bootstrap used")),
    )
    try:
        assert verifier("opaque", workspace_id="/ws", build_id=1, format="stl") == {"ok": False}
    finally:
        close()


def test_host_mode_requires_bootstrap_factory():
    class _Channel:
        def consume(self, nonce, **claims):
            return {"ok": True, "nonce": nonce, **claims}

        def close(self):
            return None

    verifier, close = build_override_verifier("host", bootstrap_factory=_Channel)
    try:
        assert verifier("opaque", workspace_id="/ws", build_id=1, format="stl")["ok"] is True
    finally:
        close()
