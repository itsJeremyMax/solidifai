"""Single-writer operation queue with observable, stable lifecycle records."""

from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

OperationState = Literal[
    "queued", "running", "publishing", "succeeded", "failed", "cancelled", "timed_out"
]
_TERMINAL = frozenset({"succeeded", "failed", "cancelled", "timed_out"})
_LONG_RUNNING_METHODS = frozenset({"sweep", "optimize", "converge_to_spec", "check_motion"})
_NORMAL_SOFT_TIMEOUT = 180.0
_NORMAL_HARD_TIMEOUT = 210.0
_LONGRUN_SOFT_TIMEOUT = 1200.0
_LONGRUN_HARD_TIMEOUT = 1200.0


class OperationTimeout(RuntimeError):
    """A worker or scheduler deadline expired; this is never a generic failure."""


# Lifecycle state machine (only _finish enters a terminal state):
#
# queued -> running -> publishing -> succeeded
#             |            |            |
#             +----------> failed <-----+
#             +----------> cancelled
#             +----------> timed_out


@dataclass
class OperationRecord:
    operation_id: str
    method: str
    params: dict[str, Any]
    state: OperationState = "queued"
    queue_position: int | None = None
    progress: float | None = None
    phase: str | None = None
    elapsed_ms: int = 0
    result: dict | None = None
    error: str | None = None
    replace_key: str | None = None
    started_at: float | None = None
    finished_at: float | None = None
    last_heartbeat: float = field(default_factory=time.monotonic)
    waiters: int = 0
    cancellation: str | None = None
    cancellation_claim: object | None = None
    details: dict[str, Any] | None = None


class OperationQueue:
    """Runs one operation at a time and keeps terminal status addressable.

    ``execute`` owns the writer/worker call.  It receives the method, parameters,
    and heartbeat callback; ``cancel_running`` must synchronously stop that call's
    worker and roll it back when the current operation is cancelled or expires.
    """

    def __init__(
        self,
        execute: Callable[[str, dict[str, Any], Callable[[float | None, str | None], None]], dict],
        cancel_running: Callable[[OperationRecord], bool] | None = None,
        *,
        begin_cancel: Callable[[OperationRecord], object] | None = None,
        finish_cancel: Callable[[object], bool] | None = None,
        release_cancel_claim: Callable[[object], bool | None] | None = None,
        soft_timeout: float = _NORMAL_SOFT_TIMEOUT,
        hard_timeout: float = _NORMAL_HARD_TIMEOUT,
        longrun_soft_timeout: float = _LONGRUN_SOFT_TIMEOUT,
        longrun_hard_timeout: float = _LONGRUN_HARD_TIMEOUT,
        max_terminal: int = 256,
        terminal_max_age: float = 3600.0,
        max_queued: int = 64,
    ):
        if hard_timeout < soft_timeout:
            raise ValueError("hard_timeout must be at least soft_timeout")
        if longrun_hard_timeout < longrun_soft_timeout:
            raise ValueError("longrun hard_timeout must be at least longrun soft_timeout")
        if max_queued < 1:
            raise ValueError("max_queued must be at least 1")
        self._execute = execute
        self._cancel_running = cancel_running
        self._begin_cancel = begin_cancel
        self._finish_cancel = finish_cancel
        self._release_cancel_claim = release_cancel_claim
        self._soft_timeout = soft_timeout
        self._hard_timeout = hard_timeout
        self._longrun_soft_timeout = longrun_soft_timeout
        self._longrun_hard_timeout = longrun_hard_timeout
        self._max_terminal = max_terminal
        self._terminal_max_age = terminal_max_age
        self._max_queued = max_queued
        self._operations: dict[str, OperationRecord] = {}
        self._queued: deque[OperationRecord] = deque()
        self._running: OperationRecord | None = None
        self._stop = False
        self._condition = threading.Condition()
        self._thread = threading.Thread(
            target=self._run, name="engine-operation-writer", daemon=True
        )
        self._thread.start()

    def submit(
        self, method: str, params: dict[str, Any], *, replace_key: str | None = None
    ) -> dict:
        cancel: OperationRecord | None = None
        with self._condition:
            if self._stop:
                raise RuntimeError("operation queue is closed")
            self._prune_terminals(target_count=self._max_terminal - 1)
            if replace_key is not None:
                for existing in tuple(self._queued):
                    if existing.replace_key == replace_key:
                        self._queued.remove(existing)
                        self._finish(existing, "cancelled", error="superseded by replacement")
                if self._running is not None and self._running.replace_key == replace_key:
                    cancel = self._running
            if len(self._queued) >= self._max_queued:
                raise RuntimeError(f"operation queue is full (maximum {self._max_queued} pending)")
            record = OperationRecord(
                uuid.uuid4().hex, method, dict(params), replace_key=replace_key
            )
            self._operations[record.operation_id] = record
            self._queued.append(record)
            self._update_positions()
            self._condition.notify_all()
            snapshot = self._snapshot(record)
        if cancel is not None:
            self._request_cancel(cancel, "cancelling")
        return snapshot

    def get(self, operation_id: str) -> dict:
        with self._condition:
            record = self._operations.get(operation_id)
            if record is None:
                raise ValueError(f"unknown operation: {operation_id!r}")
            self._refresh_elapsed(record)
            return self._snapshot(record)

    def wait(self, operation_id: str, timeout: float | None = None) -> dict:
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._condition:
            record = self._operations.get(operation_id)
            if record is None:
                raise ValueError(f"unknown operation: {operation_id!r}")
            record.waiters += 1
            try:
                while record.state not in _TERMINAL:
                    remaining = None if deadline is None else deadline - time.monotonic()
                    if remaining is not None and remaining <= 0:
                        raise TimeoutError(f"operation {operation_id} did not finish in time")
                    self._condition.wait(remaining)
                return self._snapshot(record)
            finally:
                record.waiters -= 1

    def cancel(self, operation_id: str) -> dict:
        cancel: OperationRecord | None = None
        with self._condition:
            record = self._operations.get(operation_id)
            if record is None:
                raise ValueError(f"unknown operation: {operation_id!r}")
            if record.state in _TERMINAL:
                return self._snapshot(record)
            if record.state == "queued":
                self._queued.remove(record)
                self._finish(record, "cancelled")
            else:
                cancel = record
            self._condition.notify_all()
            snapshot = self._snapshot(record)
        if cancel is not None:
            self._request_cancel(cancel, "cancelling")
            with self._condition:
                snapshot = self._snapshot(record)
        return snapshot

    def close(self) -> None:
        cancel: OperationRecord | None = None
        with self._condition:
            self._stop = True
            for record in tuple(self._queued):
                self._queued.remove(record)
                self._finish(record, "cancelled", error="engine shutting down")
            if self._running is not None:
                cancel = self._running
            self._condition.notify_all()
        if cancel is not None:
            outcome = self._request_cancel(cancel, "cancelling")
            claimed = outcome == "claimed"
            with self._condition:
                if claimed and cancel.state not in _TERMINAL:
                    self._finish(cancel, "cancelled", error="engine shutting down")
                self._condition.notify_all()
        hard_timeout = self._budget(cancel.method)[1] if cancel is not None else self._hard_timeout
        deadline = time.monotonic() + hard_timeout
        self._thread.join(timeout=max(0.0, deadline - time.monotonic()))
        if self._thread.is_alive() and cancel is not None:
            with self._condition:
                if cancel.state not in _TERMINAL:
                    self._finish(cancel, "failed", error="engine shutdown hard deadline reached")
                self._condition.notify_all()

    def _run(self) -> None:
        while True:
            with self._condition:
                while not self._queued and not self._stop:
                    self._condition.wait()
                if self._stop:
                    return
                record = self._queued.popleft()
                self._running = record
                record.state = "running"
                record.queue_position = None
                record.started_at = record.last_heartbeat = time.monotonic()
                self._update_positions()

            threading.Thread(
                target=self._watch,
                args=(record,),
                name=f"engine-operation-watch-{record.operation_id[:8]}",
                daemon=True,
            ).start()

            def heartbeat(
                progress: float | None = None,
                phase: str | None = None,
                record: OperationRecord = record,
            ) -> None:
                with self._condition:
                    if record.state not in _TERMINAL:
                        record.last_heartbeat = time.monotonic()
                        record.progress = progress
                        # A cancellation claim owns the terminal intent. A late
                        # worker heartbeat may report its last work phase, but it
                        # cannot turn a timeout or cancellation back into a build.
                        if record.phase not in {"timing_out", "cancelling"}:
                            record.phase = phase
                        if phase == "publishing" and record.phase not in {
                            "timing_out",
                            "cancelling",
                        }:
                            record.state = "publishing"
                        self._refresh_elapsed(record)
                        self._condition.notify_all()

            heartbeat.operation_id = record.operation_id  # type: ignore[attr-defined]

            try:
                result = self._execute(record.method, record.params, heartbeat)
            except Exception as exc:  # The RPC layer formats engine failures.
                with self._condition:
                    state: OperationState = (
                        "timed_out"
                        if record.phase == "timing_out" or isinstance(exc, OperationTimeout)
                        else "cancelled"
                        if record.phase == "cancelling"
                        else "failed"
                    )
                    error = "operation cancelled" if state == "cancelled" else str(exc)
                    self._finish(record, state, error=error)
            else:
                with self._condition:
                    if isinstance(result, dict) and result.get("ok") is False:
                        domain_envelope = bool(result.get("_error_envelope"))
                        details = {
                            key: value
                            for key, value in result.items()
                            if key not in {"ok", "error", "_error_envelope"}
                        }
                        self._finish(
                            record,
                            "failed",
                            error=str(result.get("error", "operation failed")),
                            details=details if domain_envelope or details else None,
                        )
                    else:
                        state = (
                            "timed_out"
                            if record.phase == "timing_out"
                            else "cancelled"
                            if record.phase == "cancelling"
                            else "succeeded"
                        )
                        self._finish(record, state, result=result)
            finally:
                with self._condition:
                    self._running = None
                    self._condition.notify_all()

    def _watch(self, record: OperationRecord) -> None:
        soft_timeout, hard_timeout = self._budget(record.method)
        while True:
            time.sleep(min(0.05, soft_timeout / 4))
            with self._condition:
                if record.state in _TERMINAL or self._running is not record:
                    return
                now = time.monotonic()
                assert record.started_at is not None
                hard_expired = now - record.started_at >= hard_timeout
                soft_expired = now - record.last_heartbeat >= soft_timeout
                if not hard_expired and not soft_expired:
                    continue
            outcome = self._request_cancel(record, "timing_out")
            if outcome in {"claimed", "too_late"}:
                return
            with self._condition:
                if record.state in _TERMINAL or self._running is not record:
                    return
                if now - record.started_at >= hard_timeout:
                    # Parent-owned writers have no worker to kill. The hard ceiling
                    # still wins deterministically if their callback later returns.
                    record.phase = "timing_out"
                    self._condition.notify_all()
                    return

    def _budget(self, method: str) -> tuple[float, float]:
        if method in _LONG_RUNNING_METHODS:
            return self._longrun_soft_timeout, self._longrun_hard_timeout
        return self._soft_timeout, self._hard_timeout

    def _request_cancel(self, record: OperationRecord, phase: str) -> str:
        """Install terminal intent before a claimed worker can be torn down.

        The two-phase proxy API makes the active call cancellation-pending first.
        Only after this queue records the terminal intent can it kill that same
        call.  Thus a completion and cancellation claim have one lock-protected
        winner, and publication can reject claims as too late.
        """
        if self._begin_cancel is not None and self._finish_cancel is not None:
            outcome = self._begin_cancel(record)
            status = getattr(outcome, "status", "claimed" if outcome is not None else "not_active")
            claim = getattr(outcome, "claim", outcome)
            if status == "too_late":
                with self._condition:
                    record.cancellation = "too_late"
                    self._condition.notify_all()
                return "too_late"
            if status != "claimed":
                return "not_active"
            with self._condition:
                if record.state in _TERMINAL or self._running is not record:
                    self._release_claim(claim)
                    return "not_active"
                record.cancellation_claim = claim
                record.phase = phase
                self._condition.notify_all()
            finished = self._finish_cancel(claim)
            with self._condition:
                record.cancellation_claim = None
            if finished:
                return "claimed"
            self._release_claim(claim)
            return "not_active"

        # Backwards-compatible callback path for queue-only callers. The server
        # always uses the two-phase path above.
        claimed = self._cancel_running(record) if self._cancel_running is not None else True
        if claimed is False:
            return "lost"
        with self._condition:
            if record.state in _TERMINAL or self._running is not record:
                return "lost"
            record.phase = phase
            self._condition.notify_all()
        return "claimed"

    def _finish(
        self,
        record: OperationRecord,
        state: OperationState,
        *,
        result: dict | None = None,
        error: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if record.state in _TERMINAL:
            return
        claim = record.cancellation_claim
        record.cancellation_claim = None
        if claim is not None:
            self._release_claim(claim)
        record.state = state
        record.queue_position = None
        record.result = result
        record.error = error
        record.details = details
        record.finished_at = time.monotonic()
        self._refresh_elapsed(record)
        # Do not evict the just-finished result before a legacy submit-and-wait
        # caller can observe it. The next submission enforces the bounded cache.

    def _release_claim(self, claim: object) -> None:
        if self._release_cancel_claim is not None:
            self._release_cancel_claim(claim)

    def _prune_terminals(self, *, target_count: int) -> None:
        now = time.monotonic()
        candidates = [
            record
            for record in self._operations.values()
            if record.state in _TERMINAL
            and record.waiters == 0
            and record.finished_at is not None
            and now - record.finished_at >= self._terminal_max_age
        ]
        for record in candidates:
            self._operations.pop(record.operation_id, None)
        excess = len(self._operations) - target_count
        if excess > 0:
            evictable = sorted(
                (
                    record
                    for record in self._operations.values()
                    if record.state in _TERMINAL and record.waiters == 0
                ),
                key=lambda record: record.finished_at or now,
            )
            for record in evictable[:excess]:
                self._operations.pop(record.operation_id, None)

    def _update_positions(self) -> None:
        for position, record in enumerate(self._queued, start=1):
            record.queue_position = position

    @staticmethod
    def _refresh_elapsed(record: OperationRecord) -> None:
        if record.started_at is not None:
            until = record.finished_at if record.finished_at is not None else time.monotonic()
            record.elapsed_ms = int((until - record.started_at) * 1000)

    @staticmethod
    def _snapshot(record: OperationRecord) -> dict:
        return {
            "operationId": record.operation_id,
            "method": record.method,
            "state": record.state,
            "queuePosition": record.queue_position,
            "progress": record.progress,
            "phase": record.phase,
            "elapsedMs": record.elapsed_ms,
            "result": record.result,
            "error": record.error,
            "cancellation": record.cancellation,
            "details": record.details,
        }
