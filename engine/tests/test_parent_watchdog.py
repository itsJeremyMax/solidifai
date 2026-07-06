"""Cross-platform dispatch of the engine's parent-death watchdog.

Windows getppid() keeps returning the original creator PID after the parent
exits, so ppid polling never fires there; the watchdog must wait on a process
handle instead. These tests pin the per-platform strategy choice and the
fallback wiring without needing a Windows host.
"""

import logging
import os
import sys
import threading

import solidifai_engine.server as server_mod
from solidifai_engine.server import Server


def _bare_server() -> Server:
    # _start_parent_watchdog only touches self._stop; skip the heavy __init__.
    srv = Server.__new__(Server)
    srv._stop = threading.Event()
    return srv


def test_strategy_is_handle_wait_on_nt_and_poll_elsewhere(monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    assert server_mod._watchdog_strategy() == "handle-wait"
    monkeypatch.setattr(os, "name", "posix")
    assert server_mod._watchdog_strategy() == "ppid-poll"


def test_posix_watchdog_never_probes_a_process_handle(monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    opened: list[int] = []

    def fake_open(ppid: int) -> tuple[int | None, int]:
        opened.append(ppid)
        return None, 0

    monkeypatch.setattr(server_mod, "_open_parent_handle", fake_open)
    srv = _bare_server()
    srv._start_parent_watchdog()
    srv._stop.set()
    assert opened == []


def test_nt_without_a_handle_falls_back_to_polling_with_warning(monkeypatch, caplog):
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(server_mod, "_open_parent_handle", lambda ppid: (None, 0))
    srv = _bare_server()
    with caplog.at_level(logging.WARNING, logger="solidifai_engine.server"):
        srv._start_parent_watchdog()
    srv._stop.set()
    assert "falling back to ppid polling" in caplog.text


def test_nt_with_a_handle_exits_when_the_parent_signals(monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(server_mod, "_open_parent_handle", lambda ppid: (1234, 0))
    waited: list[int] = []

    def fake_wait(handle: int) -> bool:
        waited.append(handle)
        return True

    monkeypatch.setattr(server_mod, "_wait_for_parent_exit", fake_wait)
    exited = threading.Event()
    monkeypatch.setattr(server_mod.os, "_exit", lambda code: exited.set())
    srv = _bare_server()
    srv._start_parent_watchdog()
    assert exited.wait(5.0)
    assert waited == [1234]
    srv._stop.set()


def test_nt_failed_wait_degrades_to_polling_not_exit(monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(server_mod, "_open_parent_handle", lambda ppid: (1234, 0))
    entered_wait = threading.Event()

    def fake_wait(handle: int) -> bool:
        entered_wait.set()
        return False  # WAIT_FAILED must never count as parent death

    monkeypatch.setattr(server_mod, "_wait_for_parent_exit", fake_wait)
    exited = threading.Event()
    monkeypatch.setattr(server_mod.os, "_exit", lambda code: exited.set())
    srv = _bare_server()
    srv._start_parent_watchdog()
    assert entered_wait.wait(5.0)
    assert not exited.wait(0.2)
    srv._stop.set()


def test_nt_parent_already_gone_at_startup_exits_instead_of_lingering(monkeypatch, caplog):
    # The shell died in the spawn->watchdog window: OpenProcess says the PID no
    # longer exists, and the ppid fallback never fires on Windows, so the only
    # correct move is to exit immediately.
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(
        server_mod,
        "_open_parent_handle",
        lambda ppid: (None, server_mod._ERROR_INVALID_PARAMETER),
    )
    exited = threading.Event()
    monkeypatch.setattr(server_mod.os, "_exit", lambda code: exited.set())
    srv = _bare_server()
    with caplog.at_level(logging.WARNING, logger="solidifai_engine.server"):
        srv._start_parent_watchdog()
    srv._stop.set()
    assert exited.is_set()
    assert "already gone at startup" in caplog.text


def test_win32_helpers_are_inert_off_windows():
    if sys.platform == "win32":
        return
    assert server_mod._open_parent_handle(os.getpid()) == (None, 0)
    assert server_mod._wait_for_parent_exit(1234) is False
