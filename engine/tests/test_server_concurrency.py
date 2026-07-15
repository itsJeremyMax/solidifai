"""Parent-owned reads stay responsive while a writer operation is occupied."""

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
            {"method": "execute_script", "params": {"code": "A"}, "_include_readiness": True},
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
        assert response == {"id": 1, "ok": False, "error": "invalid parameter", "field": "size"}
    finally:
        server.shutdown()


def test_sync_remote_session_business_error_remains_a_failed_result(tmp_path):
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
        assert server._dispatch("set_requirements", {"requirements": []}) == {
            "ok": False,
            "error": "ValueError: bad param",
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
