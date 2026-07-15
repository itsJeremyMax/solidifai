"""Operation scheduling contracts independent of the CAD kernel."""

import threading
import time
from types import SimpleNamespace

from solidifai_engine.operations import OperationQueue, OperationTimeout


def test_queue_resolves_explicit_normal_and_long_running_budgets():
    queue = OperationQueue(lambda _method, _params, _heartbeat: {"ok": True})
    try:
        assert queue._budget("execute_script") == (180.0, 210.0)
        assert queue._budget("sweep") == (1200.0, 1200.0)
        assert queue._budget("optimize") == (1200.0, 1200.0)
        assert queue._budget("converge_to_spec") == (1200.0, 1200.0)
        assert queue._budget("check_motion") == (1200.0, 1200.0)
    finally:
        queue.close()


def test_proxy_timeout_is_always_a_timed_out_operation():
    started = threading.Event()

    def execute(_method, _params, _heartbeat):
        started.set()
        raise OperationTimeout("the build exceeded its deadline")

    queue = OperationQueue(execute)
    try:
        operation = queue.submit("execute_script", {})
        assert started.wait(1)
        terminal = queue.wait(operation["operationId"], timeout=1)
        assert terminal["state"] == "timed_out"
        assert terminal["error"] == "the build exceeded its deadline"
    finally:
        queue.close()


def test_watchdog_and_proxy_timeout_race_has_one_timed_out_winner():
    started = threading.Event()
    stopped = threading.Event()

    def execute(_method, _params, _heartbeat):
        started.set()
        assert stopped.wait(1)
        raise OperationTimeout("the build exceeded its deadline")

    queue = OperationQueue(
        execute,
        begin_cancel=lambda _record: SimpleNamespace(status="claimed", claim="claim"),
        finish_cancel=lambda _claim: stopped.set() or True,
        soft_timeout=0.01,
        hard_timeout=0.02,
    )
    try:
        operation = queue.submit("execute_script", {})
        assert started.wait(1)
        terminal = queue.wait(operation["operationId"], timeout=1)
        assert terminal["state"] == "timed_out"
    finally:
        stopped.set()
        queue.close()


def test_submit_runs_one_writer_and_retains_terminal_result():
    started = threading.Event()
    release = threading.Event()

    def execute(method, params, heartbeat):
        started.set()
        release.wait(2)
        heartbeat(1.0, "published")
        return {"method": method, "params": params}

    queue = OperationQueue(execute)
    try:
        operation = queue.submit("execute_script", {"code": "show(x)"})
        assert operation["state"] == "queued"
        assert started.wait(2)
        assert queue.get(operation["operationId"])["state"] == "running"

        release.set()
        assert queue.wait(operation["operationId"])["state"] == "succeeded"
        assert queue.get(operation["operationId"])["result"] == {
            "method": "execute_script",
            "params": {"code": "show(x)"},
        }
    finally:
        queue.close()


def test_soft_timeout_uses_heartbeat_but_hard_ceiling_stops_operation():
    started = threading.Event()
    stopped = threading.Event()

    def execute(_method, _params, heartbeat):
        started.set()
        while not stopped.wait(0.01):
            heartbeat(0.5, "building")
        raise RuntimeError("worker stopped")

    def begin_cancel(_record):
        return object()

    def finish_cancel(_claim):
        stopped.set()
        return True

    queue = OperationQueue(
        execute,
        begin_cancel=begin_cancel,
        finish_cancel=finish_cancel,
        soft_timeout=0.03,
        hard_timeout=0.08,
    )
    try:
        operation = queue.submit("execute_script", {})
        assert started.wait(1)
        assert queue.wait(operation["operationId"], timeout=1)["state"] == "timed_out"
    finally:
        queue.close()


def test_heartbeat_cannot_overwrite_timeout_intent_before_worker_raises():
    entered = threading.Event()
    release = threading.Event()

    def execute(_method, _params, heartbeat):
        heartbeat(0.5, "building")
        entered.set()
        release.wait(1)
        heartbeat(0.5, "building")
        raise RuntimeError("worker stopped")

    queue = OperationQueue(
        execute,
        begin_cancel=lambda _record: object(),
        finish_cancel=lambda _claim: release.set() or True,
        soft_timeout=0.01,
        hard_timeout=0.2,
    )
    try:
        operation = queue.submit("execute_script", {})
        assert entered.wait(1)
        assert queue.wait(operation["operationId"], timeout=1)["state"] == "timed_out"
    finally:
        queue.close()


def test_replacement_key_supersedes_the_running_operation():
    started = threading.Event()
    stopped = threading.Event()
    calls = 0

    def execute(_method, _params, _heartbeat):
        nonlocal calls
        calls += 1
        if calls == 2:
            return {"replacement": True}
        started.set()
        stopped.wait(1)
        raise RuntimeError("worker stopped")

    queue = OperationQueue(execute, lambda _record: stopped.set())
    try:
        first = queue.submit("execute_script", {}, replace_key="viewport")
        assert started.wait(1)
        second = queue.submit("execute_script", {}, replace_key="viewport")

        assert queue.wait(first["operationId"], timeout=1)["state"] == "cancelled"
        assert queue.wait(second["operationId"], timeout=1)["state"] == "succeeded"
    finally:
        queue.close()


def test_watchdog_never_reports_a_late_result_as_success():
    def execute(_method, _params, _heartbeat):
        time.sleep(0.08)
        return {"late": True}

    queue = OperationQueue(execute, soft_timeout=0.02, hard_timeout=0.04)
    try:
        operation = queue.submit("execute_script", {})
        assert queue.wait(operation["operationId"], timeout=1)["state"] == "timed_out"
    finally:
        queue.close()


def test_shutdown_terminalizes_running_and_queued_waiters():
    started = threading.Event()
    release = threading.Event()

    def execute(_method, _params, _heartbeat):
        started.set()
        release.wait(1)
        return {"late": True}

    queue = OperationQueue(execute, lambda _record: release.set())
    first = queue.submit("execute_script", {})
    second = queue.submit("render", {})
    assert started.wait(1)

    queue.close()

    assert queue.wait(first["operationId"], timeout=1)["state"] == "cancelled"
    assert queue.wait(second["operationId"], timeout=1)["error"] == "engine shutting down"


def test_retention_releases_wait_protection_after_wait_returns():
    queue = OperationQueue(lambda _method, _params, _heartbeat: {"ok": True}, max_terminal=1)
    try:
        first = queue.submit("one", {})
        assert queue.wait(first["operationId"], timeout=1)["state"] == "succeeded"
        second = queue.submit("two", {})
        assert queue.wait(second["operationId"], timeout=1)["state"] == "succeeded"
        try:
            queue.get(first["operationId"])
        except ValueError:
            pass
        else:
            raise AssertionError("returned waiters must not pin terminal records")
    finally:
        queue.close()


def test_thousands_of_synchronous_waits_remain_bounded():
    queue = OperationQueue(lambda _method, _params, _heartbeat: {"ok": True}, max_terminal=8)
    try:
        for _ in range(1000):
            operation = queue.submit("execute_script", {})
            assert queue.wait(operation["operationId"], timeout=1)["state"] == "succeeded"
        assert len(queue._operations) <= 9
    finally:
        queue.close()


def test_cancel_that_loses_worker_claim_preserves_completed_success():
    started = threading.Event()
    finish = threading.Event()
    cancel_entered = threading.Event()
    allow_cancel_return = threading.Event()

    def execute(_method, _params, _heartbeat):
        started.set()
        assert finish.wait(1)
        return {"published": "A"}

    def cancel(_record):
        cancel_entered.set()
        assert allow_cancel_return.wait(1)
        return False

    queue = OperationQueue(execute, cancel)
    try:
        operation = queue.submit("execute_script", {})
        assert started.wait(1)
        cancelling = threading.Thread(target=queue.cancel, args=(operation["operationId"],))
        cancelling.start()
        assert cancel_entered.wait(1)

        finish.set()
        assert queue.wait(operation["operationId"], timeout=1)["state"] == "succeeded"
        allow_cancel_return.set()
        cancelling.join(1)

        final = queue.get(operation["operationId"])
        assert final["state"] == "succeeded"
        assert final["result"] == {"published": "A"}
        assert final["phase"] != "cancelling"
    finally:
        allow_cancel_return.set()
        queue.close()


def test_late_cancel_cannot_kill_the_next_operation():
    first_started = threading.Event()
    finish_first = threading.Event()
    cancel_entered = threading.Event()
    allow_cancel_return = threading.Event()
    second_started = threading.Event()
    release_second = threading.Event()
    cancelled_ids = []

    def execute(method, _params, _heartbeat):
        if method == "first":
            first_started.set()
            assert finish_first.wait(1)
            return {"published": "A"}
        second_started.set()
        assert release_second.wait(1)
        return {"published": "B"}

    def cancel(record):
        cancel_entered.set()
        assert allow_cancel_return.wait(1)
        cancelled_ids.append(record.operation_id)
        return False

    queue = OperationQueue(execute, cancel)
    try:
        first = queue.submit("first", {})
        second = queue.submit("second", {})
        assert first_started.wait(1)
        cancelling = threading.Thread(target=queue.cancel, args=(first["operationId"],))
        cancelling.start()
        assert cancel_entered.wait(1)

        finish_first.set()
        assert queue.wait(first["operationId"], timeout=1)["state"] == "succeeded"
        assert second_started.wait(1)
        allow_cancel_return.set()
        cancelling.join(1)

        assert cancelled_ids == [first["operationId"]]
        assert queue.get(second["operationId"])["state"] == "running"
        release_second.set()
        assert queue.wait(second["operationId"], timeout=1)["state"] == "succeeded"
    finally:
        finish_first.set()
        allow_cancel_return.set()
        release_second.set()
        queue.close()


def test_publishing_heartbeat_exposes_publication_state_before_success():
    publishing = threading.Event()
    release = threading.Event()

    def execute(_method, _params, heartbeat):
        heartbeat(0.9, "publishing")
        publishing.set()
        assert release.wait(1)
        return {"published": True}

    queue = OperationQueue(execute)
    try:
        operation = queue.submit("execute_script", {})
        assert publishing.wait(1)
        assert queue.get(operation["operationId"])["state"] == "publishing"
        release.set()
        assert queue.wait(operation["operationId"], timeout=1)["state"] == "succeeded"
    finally:
        release.set()
        queue.close()


def test_cancel_after_publishing_is_too_late_and_operation_succeeds():
    publishing = threading.Event()
    release = threading.Event()

    def execute(_method, _params, heartbeat):
        heartbeat(0.9, "publishing")
        publishing.set()
        assert release.wait(1)
        return {"publicationId": "A"}

    queue = OperationQueue(
        execute,
        begin_cancel=lambda _record: SimpleNamespace(status="too_late", claim=None),
        finish_cancel=lambda _claim: True,
    )
    try:
        operation = queue.submit("execute_script", {})
        assert publishing.wait(1)
        cancelled = queue.cancel(operation["operationId"])
        assert cancelled["state"] == "publishing"
        assert cancelled["cancellation"] == "too_late"
        release.set()
        assert queue.wait(operation["operationId"], timeout=1)["state"] == "succeeded"
    finally:
        release.set()
        queue.close()


def test_cancellation_installs_terminal_intent_before_worker_teardown():
    started = threading.Event()
    intent_installed = threading.Event()
    allow_teardown = threading.Event()
    stopped = threading.Event()

    class Claim:
        pass

    def execute(_method, _params, _heartbeat):
        started.set()
        assert stopped.wait(1)
        raise RuntimeError("worker stopped")

    def begin_cancel(_record):
        return Claim()

    def finish_cancel(_claim):
        assert intent_installed.wait(1)
        allow_teardown.wait(1)
        stopped.set()
        return True

    queue = OperationQueue(execute, begin_cancel=begin_cancel, finish_cancel=finish_cancel)
    try:
        operation = queue.submit("execute_script", {})
        assert started.wait(1)
        cancelling = threading.Thread(target=queue.cancel, args=(operation["operationId"],))
        cancelling.start()
        while queue.get(operation["operationId"])["phase"] != "cancelling":
            time.sleep(0.001)
        intent_installed.set()
        allow_teardown.set()
        cancelling.join(1)
        assert queue.wait(operation["operationId"], timeout=1)["state"] == "cancelled"
    finally:
        intent_installed.set()
        allow_teardown.set()
        stopped.set()
        queue.close()


def test_timeout_that_loses_worker_claim_preserves_committed_publication():
    started = threading.Event()
    finish = threading.Event()
    cancel_entered = threading.Event()
    allow_cancel_return = threading.Event()

    def execute(_method, _params, _heartbeat):
        started.set()
        assert finish.wait(1)
        return {"publicationId": "A"}

    def cancel(_record):
        cancel_entered.set()
        assert allow_cancel_return.wait(1)
        return False

    queue = OperationQueue(execute, cancel)
    try:
        operation = queue.submit("execute_script", {})
        assert started.wait(1)
        record = queue._operations[operation["operationId"]]
        timing_out = threading.Thread(target=queue._request_cancel, args=(record, "timing_out"))
        timing_out.start()
        assert cancel_entered.wait(1)

        finish.set()
        assert queue.wait(operation["operationId"], timeout=1)["result"] == {"publicationId": "A"}
        allow_cancel_return.set()
        timing_out.join(1)
        assert queue.get(operation["operationId"])["state"] == "succeeded"
    finally:
        finish.set()
        allow_cancel_return.set()
        queue.close()


def test_unobserved_terminal_records_are_evicted_on_the_next_submission():
    queue = OperationQueue(lambda _method, _params, _heartbeat: {"ok": True}, max_terminal=1)
    try:
        first = queue.submit("one", {})
        with queue._condition:
            while queue._operations[first["operationId"]].state not in {
                "succeeded",
                "failed",
                "cancelled",
                "timed_out",
            }:
                assert queue._condition.wait(1)

        second = queue.submit("two", {})
        assert queue.wait(second["operationId"], timeout=1)["state"] == "succeeded"
        try:
            queue.get(first["operationId"])
        except ValueError:
            pass
        else:
            raise AssertionError("unobserved terminal record was retained past max_terminal")
    finally:
        queue.close()


def test_cancel_in_publication_ack_to_heartbeat_gap_is_too_late():
    started = threading.Event()
    release = threading.Event()

    def execute(_method, _params, heartbeat):
        started.set()
        assert release.wait(1)
        heartbeat(0.9, "publishing")
        return {"publicationId": "A"}

    queue = OperationQueue(
        execute,
        begin_cancel=lambda _record: SimpleNamespace(status="too_late", claim=None),
        finish_cancel=lambda _claim: True,
    )
    try:
        operation = queue.submit("execute_script", {})
        assert started.wait(1)
        cancelled = queue.cancel(operation["operationId"])
        assert cancelled["cancellation"] == "too_late"
        assert cancelled["state"] == "running"
        release.set()
        assert queue.wait(operation["operationId"], timeout=1)["state"] == "succeeded"
    finally:
        release.set()
        queue.close()


def test_watchdog_retries_not_active_gap_until_cancellation_is_claimed():
    started = threading.Event()
    first_attempt = threading.Event()
    active = threading.Event()
    stopped = threading.Event()
    attempts = 0

    def execute(_method, _params, _heartbeat):
        started.set()
        assert stopped.wait(1)
        raise RuntimeError("stopped")

    def begin_cancel(_record):
        nonlocal attempts
        attempts += 1
        if not active.is_set():
            first_attempt.set()
            return SimpleNamespace(status="not_active", claim=None)
        return SimpleNamespace(status="claimed", claim="claim")

    def finish_cancel(claim):
        assert claim == "claim"
        stopped.set()
        return True

    queue = OperationQueue(
        execute,
        begin_cancel=begin_cancel,
        finish_cancel=finish_cancel,
        soft_timeout=0.01,
        hard_timeout=0.2,
    )
    try:
        operation = queue.submit("execute_script", {})
        assert started.wait(1)
        assert first_attempt.wait(1)
        active.set()
        assert queue.wait(operation["operationId"], timeout=1)["state"] == "timed_out"
        assert attempts >= 2
    finally:
        stopped.set()
        queue.close()


def test_hard_timeout_installs_intent_when_parent_writer_is_not_killable():
    started = threading.Event()
    release = threading.Event()
    timing_out = threading.Event()

    def execute(_method, _params, _heartbeat):
        started.set()
        assert release.wait(1)
        return {"saved": True}

    def begin_cancel(_record):
        return SimpleNamespace(status="not_active", claim=None)

    queue = OperationQueue(
        execute,
        begin_cancel=begin_cancel,
        finish_cancel=lambda _claim: True,
        soft_timeout=0.01,
        hard_timeout=0.05,
    )
    try:
        operation = queue.submit("set_manufacturing_profile", {})
        assert started.wait(1)
        deadline = time.monotonic() + 1
        while queue.get(operation["operationId"])["phase"] != "timing_out":
            assert time.monotonic() < deadline, "hard timeout intent was not installed"
            time.sleep(0.001)
        timing_out.set()
        release.set()
        assert queue.wait(operation["operationId"], timeout=1)["state"] == "timed_out"
    finally:
        release.set()
        queue.close()


def test_completion_winner_releases_unfinished_cancellation_claim():
    started = threading.Event()
    finish = threading.Event()
    begin_entered = threading.Event()
    allow_begin_return = threading.Event()
    claim = object()
    released = []

    def execute(_method, _params, _heartbeat):
        started.set()
        assert finish.wait(1)
        return {"ok": True}

    def begin_cancel(_record):
        begin_entered.set()
        assert allow_begin_return.wait(1)
        return SimpleNamespace(status="claimed", claim=claim)

    queue = OperationQueue(
        execute,
        begin_cancel=begin_cancel,
        finish_cancel=lambda _claim: True,
        release_cancel_claim=released.append,
    )
    try:
        operation = queue.submit("execute_script", {})
        assert started.wait(1)
        cancelling = threading.Thread(target=queue.cancel, args=(operation["operationId"],))
        cancelling.start()
        assert begin_entered.wait(1)
        finish.set()
        assert queue.wait(operation["operationId"], timeout=1)["state"] == "succeeded"
        allow_begin_return.set()
        cancelling.join(1)
        assert released == [claim]
    finally:
        finish.set()
        allow_begin_return.set()
        queue.close()


def test_failed_result_envelope_is_terminal_failed_with_stable_details():
    queue = OperationQueue(
        lambda _method, _params, _heartbeat: {
            "ok": False,
            "error": "invalid value",
            "field": "size",
        }
    )
    try:
        operation = queue.submit("set_params", {"values": {"size": -1}})
        terminal = queue.wait(operation["operationId"], timeout=1)
        assert terminal["state"] == "failed"
        assert terminal["error"] == "invalid value"
        assert terminal["details"] == {"field": "size"}
        assert queue.get(operation["operationId"])["state"] == "failed"
    finally:
        queue.close()


def test_close_waits_for_too_late_publication_to_finish():
    publishing = threading.Event()
    release = threading.Event()

    def execute(_method, _params, heartbeat):
        heartbeat(0.9, "publishing")
        publishing.set()
        assert release.wait(1)
        return {"publicationId": "A"}

    queue = OperationQueue(
        execute,
        begin_cancel=lambda _record: SimpleNamespace(status="too_late", claim=None),
        finish_cancel=lambda _claim: True,
        soft_timeout=1,
        hard_timeout=1,
    )
    try:
        operation = queue.submit("execute_script", {})
        assert publishing.wait(1)
        closer = threading.Thread(target=queue.close)
        closer.start()
        assert queue.get(operation["operationId"])["state"] == "publishing"
        release.set()
        closer.join(1)
        assert queue.wait(operation["operationId"], timeout=1)["state"] == "succeeded"
    finally:
        release.set()
        queue.close()
