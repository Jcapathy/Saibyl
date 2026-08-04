"""A user's stop must not be lost because Redis was unreachable.

Audit item 20. `_check_stop_signal` returned `False` on **any** exception, so an
unreachable Redis meant "keep going" — while `POST /simulations/{id}/stop` had
already written `status = 'stopped'` and the UI was showing the run as stopped.
The run kept burning credits the user had explicitly asked to stop spending, and
every surface the user could see agreed with them.

The stop is written to two places by the same request. Reading only the fragile
one is what made the failure invisible.
"""
from __future__ import annotations

import pytest

from app.workers import simulation_tasks


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    def __init__(self, status: str | None, fail: bool):
        self._status, self._fail = status, fail

    def select(self, *_a, **_kw):
        return self

    def eq(self, *_a, **_kw):
        return self

    def single(self):
        return self

    def execute(self):
        if self._fail:
            raise RuntimeError("database unreachable")
        return _FakeResult({"status": self._status} if self._status else None)


class _FakeAdmin:
    def __init__(self, status: str | None = None, fail: bool = False):
        self._status, self._fail = status, fail

    def table(self, _name):
        return _FakeTable(self._status, self._fail)


def _break_redis(monkeypatch):
    """Redis unreachable, at the point `_check_stop_signal` constructs it."""
    import redis

    def _boom(*_a, **_kw):
        raise ConnectionError("redis unreachable")

    monkeypatch.setattr(redis, "from_url", _boom)


def _redis_returning(monkeypatch, value):
    import redis

    class _FakeRedis:
        def get(self, _key):
            return value

    monkeypatch.setattr(redis, "from_url", lambda *_a, **_kw: _FakeRedis())


def test_a_redis_flag_stops_the_run(monkeypatch):
    _redis_returning(monkeypatch, "1")
    assert simulation_tasks._check_stop_signal("sim-1", _FakeAdmin()) is True


def test_no_flag_and_a_running_row_does_not_stop_the_run(monkeypatch):
    _redis_returning(monkeypatch, None)
    assert simulation_tasks._check_stop_signal("sim-1", _FakeAdmin("running")) is False


def test_an_unreachable_redis_falls_back_to_the_stopped_row(monkeypatch):
    """The defect. Before the fix this returned False and the run continued."""
    _break_redis(monkeypatch)
    assert simulation_tasks._check_stop_signal("sim-1", _FakeAdmin("stopped")) is True


def test_an_unreachable_redis_does_not_invent_a_stop(monkeypatch):
    """The fallback must read the instruction, not assume one."""
    _break_redis(monkeypatch)
    assert simulation_tasks._check_stop_signal("sim-1", _FakeAdmin("running")) is False


def test_both_sources_unreachable_keeps_the_run_alive(monkeypatch):
    """No evidence either way. Killing a paid run on no evidence is the worse
    error — but this path leaves two exception traces behind, where the original
    left none."""
    _break_redis(monkeypatch)
    assert simulation_tasks._check_stop_signal("sim-1", _FakeAdmin(fail=True)) is False


@pytest.mark.parametrize("status", ["stopped", "running", None])
def test_the_db_fallback_only_reports_a_stopped_row(status):
    assert simulation_tasks._stopped_in_db("sim-1", _FakeAdmin(status)) is (
        status == "stopped"
    )
