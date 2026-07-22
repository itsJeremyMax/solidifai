"""Parent-owned reads stay responsive while a writer operation is occupied."""

import json
import threading
from contextlib import nullcontext

import pytest

from solidifai_engine.server import Server
from solidifai_engine.worker import RemoteSessionError


def test_protocol_metadata_bypasses_the_writer_lane(tmp_path):
    server = Server(str(tmp_path / "engine.sock"), str(tmp_path / "artifacts"))
    started = threading.Event()
    release = threading.Event()

    class SlowSession:
        def operation(self, _operation_id):
            return nullcontext()

        def execute_script(self, _code):
            started.set()
            release.wait(1)
            return {"ok": True}

        def cancel_current(self, _operation_id):
            release.set()
            return True

        def close(self):
            return None

    server._session = SlowSession()
    try:
        server._dispatch("submit_operation", {"method": "execute_script", "params": {"code": "x"}})
        assert started.wait(1)
        done = threading.Event()
        response = {}

        def read_protocol():
            response.update(server._handle_line(b'{"id":1,"method":"get_protocol_info"}'))
            done.set()

        thread = threading.Thread(target=read_protocol)
        thread.start()
        assert done.wait(0.2), "metadata reads must not wait for an occupied writer lane"
        assert response["ok"] is True
    finally:
        release.set()
        server.shutdown()


@pytest.mark.parametrize(
    ("request_bytes", "expected_schema"),
    [
        (b'{"id":1,"method":"get_build_brief"}', 1),
        (
            b'{"id":1,"method":"get_build_brief","client":{"protocol":13,'
            b'"capabilities":["build_brief_v2"]}}',
            2,
        ),
    ],
)
def test_public_get_build_brief_bypasses_the_writer_lane_and_honors_negotiation(
    tmp_path, request_bytes, expected_schema
):
    root = tmp_path / "workspace"
    artifacts = root / ".solidifai" / "artifacts"
    artifacts.mkdir(parents=True)
    (root / "build_brief.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "summary": "Bracket",
                "tier": "stream",
                "parts": [{"name": "Base", "role": "", "why": ""}],
                "key_dims": [],
                "interfaces": [],
                "make_real": "",
            }
        ),
        encoding="utf-8",
    )
    server = Server(
        str(tmp_path / "engine.sock"), str(artifacts), model_path=str(root / "model.py")
    )
    started = threading.Event()
    release = threading.Event()
    build_brief_called = threading.Event()

    class SlowSession:
        def operation(self, _operation_id):
            return nullcontext()

        def execute_script(self, _code):
            started.set()
            release.wait(1)
            return {"ok": True}

        def get_build_brief(self, target_schema=None):
            build_brief_called.set()
            assert release.wait(1)
            return {"ok": True, "brief": {"schema": target_schema}}

        def cancel_current(self, _operation_id):
            release.set()
            return True

        def close(self):
            return None

    server._session = SlowSession()
    try:
        server._dispatch("submit_operation", {"method": "execute_script", "params": {"code": "x"}})
        assert started.wait(1)
        done = threading.Event()
        response = {}

        def read_brief():
            response.update(server._handle_line(request_bytes))
            done.set()

        thread = threading.Thread(target=read_brief)
        thread.start()
        assert done.wait(0.2), "build brief reads must not wait for an occupied writer lane"
        assert response == {
            "id": 1,
            "ok": True,
            "result": {"ok": True, "brief": response["result"]["brief"]},
        }
        assert response["result"]["brief"]["summary"] == "Bracket"
        assert response["result"]["brief"]["schema"] == expected_schema
        if expected_schema == 1:
            assert "key_dims" in response["result"]["brief"]
            assert "dimensions" not in response["result"]["brief"]
        else:
            assert "dimensions" in response["result"]["brief"]
            assert "key_dims" not in response["result"]["brief"]
        assert build_brief_called.is_set() is False
    finally:
        release.set()
        server.shutdown()


def test_public_get_build_brief_uses_artifacts_grandparent_when_model_path_is_missing(tmp_path):
    root = tmp_path / "workspace"
    artifacts = root / ".solidifai" / "artifacts"
    artifacts.mkdir(parents=True)
    (root / "build_brief.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "summary": "Fallback root brief",
                "parts": [{"name": "Base", "role": "", "why": ""}],
                "key_dims": [],
                "interfaces": [],
                "make_real": "",
                "tier": "stream",
            }
        ),
        encoding="utf-8",
    )
    server = Server(str(tmp_path / "engine.sock"), str(artifacts))
    try:
        response = server._handle_line(b'{"id":1,"method":"get_build_brief"}')
        assert response == {
            "id": 1,
            "ok": True,
            "result": {
                "ok": True,
                "brief": {
                    "schema": 1,
                    "summary": "Fallback root brief",
                    "parts": [{"name": "Base", "role": "", "why": ""}],
                    "key_dims": [],
                    "interfaces": [],
                    "make_real": "",
                    "tier": "stream",
                },
            },
        }
    finally:
        server.shutdown()


def test_operation_state_reaches_publishing_from_session_progress(tmp_path):
    server = Server(str(tmp_path / "engine.sock"), str(tmp_path / "artifacts"))
    publishing = threading.Event()
    release = threading.Event()

    class PublishingSession:
        def operation(self, _operation_id):
            return nullcontext()

        def execute_script(self, _code):
            self._operation_heartbeat(0.9, "publishing")
            publishing.set()
            assert release.wait(1)
            return {"ok": True, "buildId": 1}

        def cancel_current(self, _operation_id):
            release.set()
            return True

        def close(self):
            return None

    server._session = PublishingSession()
    try:
        operation = server._dispatch(
            "submit_operation", {"method": "execute_script", "params": {"code": "x"}}
        )
        assert publishing.wait(1)
        assert server._operations.get(operation["operationId"])["state"] == "publishing"
        release.set()
        assert server._operations.wait(operation["operationId"], timeout=1)["state"] == "succeeded"
    finally:
        release.set()
        server.shutdown()


def test_async_readiness_is_calculated_for_the_published_operation_not_the_next_one(tmp_path):
    server = Server(str(tmp_path / "engine.sock"), str(tmp_path / "artifacts"))
    first_returned = threading.Event()
    allow_readiness = threading.Event()
    second_started = threading.Event()

    class ReadinessSession:
        def __init__(self):
            self.current = None

        def operation(self, _operation_id):
            return nullcontext()

        def execute_script(self, code):
            self.current = code
            if code == "B":
                second_started.set()
            return {"ok": True, "buildId": code}

        def get_readiness(self):
            first_returned.set()
            assert allow_readiness.wait(1)
            return {"forBuild": self.current}

        def cancel_current(self, _operation_id):
            allow_readiness.set()
            return True

        def close(self):
            return None

    server._session = ReadinessSession()
    try:
        first = server._dispatch(
            "submit_operation",
            {
                "method": "execute_script",
                "params": {"code": "A"},
                "_operation_policy": {"include_readiness": True},
            },
        )
        second = server._dispatch(
            "submit_operation", {"method": "execute_script", "params": {"code": "B"}}
        )
        assert first_returned.wait(1)
        assert not second_started.is_set()
        allow_readiness.set()
        assert server._operations.wait(first["operationId"], timeout=1)["result"]["readiness"] == {
            "forBuild": "A"
        }
        assert server._operations.wait(second["operationId"], timeout=1)["state"] == "succeeded"
    finally:
        allow_readiness.set()
        server.shutdown()


@pytest.mark.parametrize("method", ["get_conformance", "get_readiness"])
def test_live_planning_reads_stay_serialized_when_a_build_is_blocked(tmp_path, method):
    server = Server(str(tmp_path / "engine.sock"), str(tmp_path / "artifacts"))
    build_started = threading.Event()
    release_build = threading.Event()
    read_started = threading.Event()
    done = threading.Event()
    response = {}

    class SlowSession:
        def operation(self, _operation_id):
            return nullcontext()

        def execute_script(self, _code):
            build_started.set()
            assert release_build.wait(1)
            return {"ok": True}

        def get_conformance(self):
            read_started.set()
            return {"readiness": {"level": "ready", "findingIds": []}}

        def get_readiness(self):
            read_started.set()
            return {"level": "ready", "findingIds": []}

        def cancel_current(self, _operation_id):
            release_build.set()
            return True

        def close(self):
            return None

    server._session = SlowSession()
    try:
        server._dispatch("submit_operation", {"method": "execute_script", "params": {"code": "x"}})
        assert build_started.wait(1)

        def read_planning_state():
            response.update(server._dispatch(method, {}))
            done.set()

        thread = threading.Thread(target=read_planning_state)
        thread.start()
        assert not done.wait(0.05), f"{method} must stay on the serialized writer lane"
        assert not read_started.is_set()
        release_build.set()
        assert done.wait(1)
        assert read_started.is_set()
    finally:
        release_build.set()
        server.shutdown()


def test_parent_owned_writes_share_the_writer_lane_with_builds(tmp_path, monkeypatch):
    server = Server(str(tmp_path / "engine.sock"), str(tmp_path / "artifacts"))
    build_started = threading.Event()
    release_build = threading.Event()
    write_started = threading.Event()

    class SlowSession:
        def operation(self, _operation_id):
            return nullcontext()

        def execute_script(self, _code):
            build_started.set()
            assert release_build.wait(1)
            return {"ok": True}

        def cancel_current(self, _operation_id):
            release_build.set()
            return True

        def close(self):
            return None

    def write(*_args, **_kwargs):
        write_started.set()

    monkeypatch.setattr("solidifai_engine.control.write", write)
    server._session = SlowSession()
    try:
        server._dispatch("submit_operation", {"method": "execute_script", "params": {"code": "x"}})
        assert build_started.wait(1)
        writer = threading.Thread(
            target=server._dispatch,
            args=("set_manufacturing_profile", {"scope": "workspace", "values": {}}),
        )
        writer.start()
        assert not write_started.wait(0.05)
        release_build.set()
        assert write_started.wait(1)
        writer.join(1)
    finally:
        release_build.set()
        server.shutdown()


@pytest.mark.parametrize("method", ["set_manufacturing_profile", "save_reference"])
def test_parent_owned_writers_reject_async_submission_before_enqueue(tmp_path, method):
    server = Server(str(tmp_path / "engine.sock"), str(tmp_path / "artifacts"))
    try:
        with pytest.raises(ValueError, match="synchronous-only"):
            server._dispatch("submit_operation", {"method": method, "params": {}})
        assert not server._operations._operations
    finally:
        server.shutdown()


def test_submit_operation_rejects_unknown_target_before_enqueue(tmp_path):
    server = Server(str(tmp_path / "engine.sock"), str(tmp_path / "artifacts"))
    try:
        response = server._handle_line(
            b'{"id":1,"method":"submit_operation","params":{"method":"not_a_method"},'
            b'"client":{"capabilities":["operations"]}}'
        )
        assert response == {
            "id": 1,
            "ok": False,
            "error": "ValueError: unknown method: 'not_a_method'",
        }
        assert not server._operations._operations
    finally:
        server.shutdown()


@pytest.mark.parametrize(
    "method",
    [
        "set_workspace_name",
        "dismiss_proposed_name",
        "set_part_material",
        "set_destinations",
        "set_workspace_meta",
        "get_conformance",
    ],
)
def test_submit_operation_rejects_internal_ui_and_read_targets(tmp_path, method):
    server = Server(str(tmp_path / "engine.sock"), str(tmp_path / "artifacts"))
    try:
        with pytest.raises(ValueError, match="not an asynchronous operation"):
            server._dispatch("submit_operation", {"method": method, "params": {}})
        assert not server._operations._operations
    finally:
        server.shutdown()


def test_submit_operation_rejects_caller_supplied_private_params(tmp_path):
    server = Server(str(tmp_path / "engine.sock"), str(tmp_path / "artifacts"))
    try:
        with pytest.raises(ValueError, match="private operation parameter"):
            server._dispatch(
                "submit_operation",
                {
                    "method": "export",
                    "params": {"format": "stl", "_strict_export": False},
                },
            )
        assert not server._operations._operations
    finally:
        server.shutdown()


def test_submit_operation_rejects_oversized_params_before_enqueue(tmp_path):
    server = Server(str(tmp_path / "engine.sock"), str(tmp_path / "artifacts"))
    try:
        with pytest.raises(ValueError, match="operation params are too large"):
            server._dispatch(
                "submit_operation",
                {"method": "execute_script", "params": {"code": "x" * 300_000}},
            )
        assert not server._operations._operations
    finally:
        server.shutdown()


def test_submit_operation_rejects_oversized_replace_key_before_enqueue(tmp_path):
    server = Server(str(tmp_path / "engine.sock"), str(tmp_path / "artifacts"))
    try:
        with pytest.raises(ValueError, match="replaceKey must be at most"):
            server._dispatch(
                "submit_operation",
                {
                    "method": "execute_script",
                    "params": {"code": "x"},
                    "replaceKey": "x" * 129,
                },
            )
        assert not server._operations._operations
    finally:
        server.shutdown()


@pytest.mark.parametrize(
    ("method", "params"),
    [
        ("check_motion", {"part": "Arm", "steps": 257}),
        ("optimize", {"param": "size", "steps": 257}),
        ("sweep", {"param": "size", "values": list(range(257))}),
        ("optimize", {"param": "size", "values": list(range(257))}),
        ("sweep", {"param": "size", "values": "not-a-list"}),
        ("optimize", {"param": "size", "values": {"not": "a-list"}}),
    ],
)
def test_submit_operation_rejects_excessive_sampling_before_enqueue(tmp_path, method, params):
    server = Server(str(tmp_path / "engine.sock"), str(tmp_path / "artifacts"))
    try:
        with pytest.raises(ValueError, match="must contain at most|must be at most|must be a list"):
            server._dispatch("submit_operation", {"method": method, "params": params})
        assert not server._operations._operations
    finally:
        server.shutdown()


def test_submit_operation_applies_strict_export_to_the_nested_target(tmp_path):
    server = Server(str(tmp_path / "engine.sock"), str(tmp_path / "artifacts"))
    strict_values = []

    class ExportSession:
        def operation(self, _operation_id):
            return nullcontext()

        def export(self, _format, _path, _options, *, strict_export, override_nonce):
            strict_values.append(strict_export)
            if strict_export:
                return {"ok": False, "error": "export blocked by readiness"}
            return {"ok": True}

        def close(self):
            return None

    server._session = ExportSession()
    try:
        response = server._handle_line(
            b'{"id":1,"method":"submit_operation","params":{"method":"export",'
            b'"params":{"format":"stl"}},"client":{"protocol":13,'
            b'"capabilities":["operations","strict_export"]}}'
        )
        assert response["ok"] is True
        operation_id = response["result"]["operationId"]
        terminal = server._operations.wait(operation_id, timeout=1)
        assert terminal["state"] == "failed"
        assert strict_values == [True]
    finally:
        server.shutdown()


def test_server_domain_failures_are_classified_publicly_and_internal_markers_do_not_leak(tmp_path):
    server = Server(str(tmp_path / "engine.sock"), str(tmp_path / "artifacts"))

    class FailingSession:
        def operation(self, _operation_id):
            return nullcontext()

        def set_params(self, _values):
            return {
                "ok": False,
                "error": "invalid parameter",
                "field": "size",
                "_error_envelope": True,
            }

        def close(self):
            return None

    server._session = FailingSession()
    try:
        response = server._handle_line(b'{"id":1,"method":"set_params","params":{"values":{}}}')
        assert response == {
            "id": 1,
            "ok": False,
            "error": "invalid parameter",
            "failureKind": "domain",
            "field": "size",
        }
        assert "_error_envelope" not in response
    finally:
        server.shutdown()


def test_sync_failed_handler_envelope_remains_an_rpc_failure(tmp_path):
    server = Server(str(tmp_path / "engine.sock"), str(tmp_path / "artifacts"))

    class FailingSession:
        def operation(self, _operation_id):
            return nullcontext()

        def set_params(self, _values):
            return {"ok": False, "error": "invalid parameter", "field": "size"}

        def close(self):
            return None

    server._session = FailingSession()
    try:
        response = server._handle_line(b'{"id":1,"method":"set_params","params":{"values":{}}}')
        assert response == {
            "id": 1,
            "ok": False,
            "error": "invalid parameter",
            "failureKind": "domain",
            "field": "size",
        }
    finally:
        server.shutdown()


def test_handler_cannot_spoof_unclassified_failure_as_domain(tmp_path):
    server = Server(str(tmp_path / "engine.sock"), str(tmp_path / "artifacts"))

    class SpoofingServer(Server):
        def _dispatch(self, method: str, params: dict):
            raise RemoteSessionError("ValueError: bad param")

    server = SpoofingServer(str(tmp_path / "engine.sock"), str(tmp_path / "artifacts"))
    try:
        response = server._handle_line(b'{"id":1,"method":"set_params","params":{"values":{}}}')
        assert response == {
            "id": 1,
            "ok": False,
            "error": "ValueError: bad param",
        }
        assert "failureKind" not in response
    finally:
        server.shutdown()


def test_sync_remote_session_error_remains_an_unclassified_transport_failure(tmp_path):
    server = Server(str(tmp_path / "engine.sock"), str(tmp_path / "artifacts"))

    class FailingSession:
        def operation(self, _operation_id):
            return nullcontext()

        def set_requirements(self, _requirements):
            raise RemoteSessionError("ValueError: bad param")

        def close(self):
            return None

    server._session = FailingSession()
    try:
        with pytest.raises(RemoteSessionError, match="ValueError: bad param"):
            server._dispatch("set_requirements", {"requirements": []})
    finally:
        server.shutdown()


def test_async_operation_does_not_retain_internal_only_traceback(tmp_path):
    server = Server(str(tmp_path / "engine.sock"), str(tmp_path / "artifacts"))

    class FailingSession:
        def operation(self, _operation_id):
            return nullcontext()

        def set_params(self, _values):
            return {
                "ok": False,
                "error": "internal failure",
                "traceback": (
                    "Traceback (most recent call last):\n"
                    '  File "/app/solidifai_engine/session.py", '
                    'line 8, in set_params\n    raise RuntimeError("boom")\nRuntimeError: boom\n'
                ),
            }

        def close(self):
            return None

    server._session = FailingSession()
    try:
        operation = server._dispatch(
            "submit_operation", {"method": "set_params", "params": {"values": {}}}
        )
        terminal = server._operations.wait(operation["operationId"], timeout=1)
        assert terminal["state"] == "failed"
        assert "traceback" not in (terminal["details"] or {})
        assert "_error_envelope" not in (terminal["details"] or {})
    finally:
        server.shutdown()


def test_operation_polling_filters_nested_result_by_the_polling_clients_capabilities(tmp_path):
    server = Server(str(tmp_path / "engine.sock"), str(tmp_path / "artifacts"))

    class PublishingSession:
        def operation(self, _operation_id):
            return nullcontext()

        def execute_script(self, _code):
            return {
                "ok": True,
                "buildId": 1,
                "publicationId": "pub-1",
                "sourceHash": "hash-1",
            }

        def get_readiness(self):
            return {"level": "ready", "findingIds": []}

        def close(self):
            return None

    server._session = PublishingSession()
    try:
        submitted = server._handle_line(
            b'{"id":1,"method":"submit_operation","params":{"method":"execute_script",'
            b'"params":{"code":"x"}},"client":{"protocol":13,"capabilities":['
            b'"operations","publication_metadata","readiness"]}}'
        )
        operation_id = submitted["result"]["operationId"]
        server._operations.wait(operation_id, timeout=1)

        limited = server._handle_line(
            json.dumps(
                {
                    "id": 2,
                    "method": "get_operation",
                    "params": {"operationId": operation_id},
                    "client": {"protocol": 13, "capabilities": ["operations"]},
                }
            ).encode()
        )
        assert limited["result"]["result"] == {"ok": True, "buildId": 1}

        capable = server._handle_line(
            json.dumps(
                {
                    "id": 3,
                    "method": "get_operation",
                    "params": {"operationId": operation_id},
                    "client": {
                        "protocol": 13,
                        "capabilities": ["operations", "publication_metadata", "readiness"],
                    },
                }
            ).encode()
        )
        assert capable["result"]["result"] == {
            "ok": True,
            "buildId": 1,
            "publicationId": "pub-1",
            "sourceHash": "hash-1",
            "readiness": {"level": "ready", "findingIds": []},
        }
    finally:
        server.shutdown()


def test_sync_scalar_handler_value_is_returned_exactly(tmp_path):
    server = Server(str(tmp_path / "engine.sock"), str(tmp_path / "artifacts"))

    class ScalarSession:
        def operation(self, _operation_id):
            return nullcontext()

        def execute_script(self, _code):
            return "ok"

        def cancel_current(self, _operation_id):
            return True

        def close(self):
            return None

    server._session = ScalarSession()
    try:
        assert server._dispatch("execute_script", {"code": "x"}) == "ok"
    finally:
        server.shutdown()
