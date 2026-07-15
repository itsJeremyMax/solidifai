"""Private override bootstrap transport tests."""

from __future__ import annotations

import io

import pytest

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
