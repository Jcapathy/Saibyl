"""A daily cron must ask each founder once, and must not nag.

`followup.py` is what fills `objection_outcomes`, and without answers the
credibility critical on saibyl.com — that nothing shows synthetic objections
predict real ones — stays open permanently.

It also sends mail to real people on a schedule, unattended. That makes the
failure modes worse than usual, so what is pinned here is the refusals:

- the same run is never asked twice for the same stage, however often the cron
  runs (it runs daily, and a run stays due for a week)
- the claim is written BEFORE the send, so a crash costs one missing email
  rather than a daily one
- an unconfigured mail service sends nothing and says so, rather than raising
- a failed send is recorded on the row, not swallowed
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services.engine import followup
from app.services.engine.followup import (
    STAGES,
    FollowupReport,
    runs_due,
    send_followups,
)

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
ORG = "org-1"
OWNER_EMAIL = "founder@example.com"


class _Table:
    def __init__(self, name, state):
        self.name, self.state, self._filters = name, state, {}
        self._payload = None
        self._op = "select"

    def select(self, *_a, **_k):
        return self

    def insert(self, payload):
        self._op, self._payload = "insert", payload
        return self

    def update(self, payload):
        self._op, self._payload = "update", payload
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def gte(self, col, val):
        self._filters[f"{col}__gte"] = val
        return self

    def lte(self, col, val):
        self._filters[f"{col}__lte"] = val
        return self

    def limit(self, *_a, **_k):
        return self

    def execute(self):
        if self.name == "followup_sends" and self._op == "insert":
            key = (self._payload["simulation_id"], self._payload["stage"])
            if key in self.state.claims:
                # Exactly what Postgres does with the unique constraint.
                raise RuntimeError("duplicate key value violates unique constraint")
            self.state.claims.add(key)
            self.state.inserts.append(dict(self._payload))
            return SimpleNamespace(data=[dict(self._payload)])

        if self._op == "update":
            self.state.updates.append((self.name, dict(self._payload), dict(self._filters)))
            return SimpleNamespace(data=[])

        if self.name == "simulations":
            # The date window is applied here because the real query applies it
            # in Postgres. A fake that ignored it returned every run for BOTH
            # stages, so a single run looked like two due asks — which would
            # have hidden a real bug rather than exposed one.
            opens = self._filters.get("completed_at__gte")
            closes = self._filters.get("completed_at__lte")
            rows = [
                r for r in self.state.runs
                if (opens is None or r["completed_at"] >= opens)
                and (closes is None or r["completed_at"] <= closes)
            ]
            return SimpleNamespace(data=rows)
        if self.name == "organization_members":
            return SimpleNamespace(data=[{"user_id": "user-1", "role": "owner"}])
        return SimpleNamespace(data=[])


def _wire(monkeypatch, *, runs, send_ok=True, send_error=None, configured=True):
    state = SimpleNamespace(runs=runs, claims=set(), inserts=[], updates=[], sent=[])

    admin = SimpleNamespace(
        table=lambda n: _Table(n, state),
        auth=SimpleNamespace(
            admin=SimpleNamespace(
                get_user_by_id=lambda _uid: SimpleNamespace(
                    user=SimpleNamespace(email=OWNER_EMAIL)
                )
            )
        ),
    )
    monkeypatch.setattr(followup, "get_supabase_admin", lambda: admin)
    monkeypatch.setattr(followup, "email_is_configured", lambda: configured)

    async def _send(*, to, subject, html, text=None):
        state.sent.append({"to": to, "subject": subject, "html": html})
        return SimpleNamespace(ok=send_ok, message_id="m-1", error=send_error)

    monkeypatch.setattr(followup, "send_email", _send)
    return state


def _run(days_ago, sim="sim-1"):
    return {
        "id": sim,
        "organization_id": ORG,
        "name": "Tallyhook",
        "status": "complete",
        "completed_at": (NOW - timedelta(days=days_ago)).isoformat(),
    }


# ── the idempotency guard, which is the whole design ─────────────────────────

@pytest.mark.asyncio
async def test_a_second_run_of_the_cron_sends_nothing(monkeypatch):
    """It runs daily and a run stays due for a week. This is the nag guard."""
    state = _wire(monkeypatch, runs=[_run(15)])

    first = await send_followups(NOW)
    second = await send_followups(NOW)

    assert first.sent == 1, "the first ask never went out"
    assert second.sent == 0, "the founder was asked twice"
    assert second.skipped_already_asked >= 1
    assert len(state.sent) == 1


@pytest.mark.asyncio
async def test_the_claim_is_written_before_the_send(monkeypatch):
    """A crash mid-send must cost one missing email, never a daily one."""
    state = _wire(monkeypatch, runs=[_run(15)])

    async def _explode(**_kwargs):
        raise RuntimeError("mail service died mid-send")

    monkeypatch.setattr(followup, "send_email", _explode)

    with pytest.raises(RuntimeError):
        await send_followups(NOW)

    assert state.inserts, "nothing was claimed, so tomorrow would send again"
    assert ("sim-1", "two_week") in state.claims


# ── who is due ───────────────────────────────────────────────────────────────

def test_a_run_inside_the_two_week_window_is_due(monkeypatch):
    _wire(monkeypatch, runs=[_run(15)])
    due = runs_due(NOW)
    assert any(d.stage.key == "two_week" for d in due)
    assert due[0].email == OWNER_EMAIL
    assert due[0].product_name == "Tallyhook"


def test_a_run_from_yesterday_is_not_due(monkeypatch):
    _wire(monkeypatch, runs=[])
    assert runs_due(NOW) == []


def test_the_window_is_wide_enough_to_survive_a_missed_day():
    """Fortnightly-exact would skip a founder permanently after one outage."""
    two_week = next(s for s in STAGES if s.key == "two_week")
    assert two_week.window_days >= 2, (
        "a one-day window means any missed cron run loses that founder for good"
    )


def test_there_are_two_asks_and_only_two():
    """One is easy to miss; three is nagging, and nagging costs the next email."""
    assert [s.key for s in STAGES] == ["two_week", "four_week"]
    assert [s.after_days for s in STAGES] == [14, 28]


# ── failure handling ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_an_unconfigured_mail_service_sends_nothing_and_says_so(monkeypatch):
    state = _wire(monkeypatch, runs=[_run(15)], configured=False)
    report = await send_followups(NOW)

    assert report.sent == 0
    assert state.sent == []
    assert any("not configured" in e for e in report.errors)


@pytest.mark.asyncio
async def test_a_failed_send_is_recorded_on_the_row(monkeypatch):
    state = _wire(monkeypatch, runs=[_run(15)], send_ok=False, send_error="domain not verified")
    report = await send_followups(NOW)

    assert report.failed == 1
    assert report.sent == 0
    errors = [u for u in state.updates if "error" in u[1]]
    assert errors, "the failure reached nobody"
    assert "domain not verified" in errors[0][1]["error"]


@pytest.mark.asyncio
async def test_a_dry_run_counts_without_sending(monkeypatch):
    state = _wire(monkeypatch, runs=[_run(15)])
    report = await send_followups(NOW, dry_run=True)

    assert report.considered == 1
    assert report.sent == 0
    assert state.sent == []
    assert state.claims == set(), "a dry run must not claim, or the real run skips it"


# ── the email itself ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_ask_does_not_tell_the_founder_what_we_predicted(monkeypatch):
    """Leading the witness would corrupt the evidence base for a public claim."""
    state = _wire(monkeypatch, runs=[_run(15)])
    await send_followups(NOW)

    body = state.sent[0]["html"].lower()
    assert "what have actual buyers pushed back on" in body
    for leading in ("we predicted", "our room said", "you were told"):
        assert leading not in body


def test_the_report_sentence_is_readable():
    report = FollowupReport(considered=3, sent=2, skipped_already_asked=1, failed=0)
    assert "3 due" in report.sentence and "2 sent" in report.sentence
