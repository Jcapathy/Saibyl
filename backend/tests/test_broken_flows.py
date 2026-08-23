"""Flows that completed successfully while doing the wrong thing.

Three defects, one shape: a value that means "nothing configured" and a value
that means "one of something" were indistinguishable, so the code took the
happy path and reported success.

* A run priced for four variants with no variant copy executed one arena and
  charged for four. `load_arenas` returns the single default arena for both
  "no variants" and "variants with nothing in them".
* `GET /simulations` computed an exact count and returned bare rows, so a page
  of twenty and a total of twenty were the same response.
* Report chat sliced `markdown_content` before it existed. NULL content is both
  "still generating" and "generation failed", and it was neither — it was a 500.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from structlog.testing import capture_logs

from app.api import simulations as simulations_api
from app.services.billing import agent_pricing, stripe_service
from app.services.intelligence import report_chat

ORG = "11111111-1111-4111-8111-111111111111"
SIM = "22222222-2222-4222-8222-222222222222"
REPORT = "33333333-3333-4333-8333-333333333333"
AUTH = {"org_id": ORG, "user": {"id": "44444444-4444-4444-8444-444444444444"}}


# ── Supabase stubs ───────────────────────────────────────

class _TableStub:
    def __init__(self, rows, count, touched, name):
        self._rows = rows
        self._count = count
        self._single = False
        self._update: dict | None = None
        self._in: dict[str, tuple] = {}
        touched.append(name)

    def select(self, *_a, **_k):
        return self

    def update(self, payload):
        # `POST /simulations/{id}/start` claims the run with a compare-and-set
        # before it deducts, so the stub has to be able to answer one.
        self._update = payload
        return self

    def eq(self, *_a, **_k):
        return self

    def in_(self, column, values):
        self._in[column] = tuple(values)
        return self

    def order(self, *_a, **_k):
        return self

    def range(self, *_a, **_k):
        return self

    def single(self):
        self._single = True
        return self

    def execute(self):
        if self._update is not None:
            matched = [
                row for row in self._rows
                if all(row.get(k) in v for k, v in self._in.items())
            ]
            for row in matched:
                row.update(self._update)
            return SimpleNamespace(data=[dict(r) for r in matched], count=None)
        if self._single:
            return SimpleNamespace(data=self._rows[0] if self._rows else None)
        return SimpleNamespace(data=list(self._rows), count=self._count)


class _AdminStub:
    """Serves canned rows per table and records which tables were read."""

    def __init__(self, tables: dict[str, tuple[list[dict], int | None]]):
        self._tables = tables
        self.touched: list[str] = []

    def table(self, name: str):
        rows, count = self._tables.get(name, ([], None))
        return _TableStub(rows, count, self.touched, name)


def _simulation(**overrides) -> dict:
    row = {
        "id": SIM,
        "status": "ready",
        "agent_count": 50,
        "max_rounds": 5,
        "platforms": ["twitter_x"],
        "variants": 1,
        "parent_simulation_id": None,
        "inoculation_asset_ids": None,
    }
    row.update(overrides)
    return row


class _Recorder:
    def __init__(self):
        self.calls: list[tuple] = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))


@pytest.fixture
def billing(monkeypatch):
    """Stub the whole charge path so a started run costs nothing and is visible."""
    deducted = _Recorder()
    monkeypatch.setattr(agent_pricing, "deduct_credits", deducted)
    monkeypatch.setattr(
        agent_pricing,
        "check_credit_budget",
        lambda *_a, **_k: SimpleNamespace(
            allowed=True, credits_required=42, message=None
        ),
    )

    async def _quota_ok(_org_id):
        return True

    monkeypatch.setattr(stripe_service, "check_simulation_quota", _quota_ok)

    async def _run(_sim_id):
        return None

    monkeypatch.setattr(simulations_api, "run_simulation", _run)
    return deducted


# ── Item 34: variants billed but never executed ──────────

@pytest.mark.asyncio
async def test_a_multi_variant_run_with_no_copy_is_refused_before_it_is_charged(
    monkeypatch, billing
):
    """The defect verbatim: `variants=4`, zero variant rows, one arena, 4x price."""
    admin = _AdminStub({
        "simulations": ([_simulation(variants=4)], None),
        "simulation_variants": ([], None),
    })
    monkeypatch.setattr(simulations_api, "get_supabase_admin", lambda: admin)

    with capture_logs() as logs:
        with pytest.raises(HTTPException) as exc:
            await simulations_api.start_simulation(SIM, None, auth=AUTH)

    assert exc.value.status_code == 409
    assert "priced for 4 variants but only 0 carry copy" in exc.value.detail
    assert not billing.calls, "credits are taken at start; the guard must precede them"
    assert "start_refused_variants_without_copy" in {e["event"] for e in logs}


@pytest.mark.asyncio
async def test_a_variant_whose_copy_is_blank_does_not_count_as_an_arena(
    monkeypatch, billing
):
    """`load_arenas` falls back to `prediction_goal` for blank copy, so a blank
    variant runs the control a second time and is scored as an alternative.
    `VariantInput` validates min_length before stripping, so "   " reaches the
    column as ""."""
    admin = _AdminStub({
        "simulations": ([_simulation(variants=2)], None),
        "simulation_variants": (
            [
                {"variant_key": "a", "content": "Ship faster."},
                {"variant_key": "b", "content": "   "},
            ],
            None,
        ),
    })
    monkeypatch.setattr(simulations_api, "get_supabase_admin", lambda: admin)

    with pytest.raises(HTTPException) as exc:
        await simulations_api.start_simulation(SIM, None, auth=AUTH)

    assert exc.value.status_code == 409
    assert "only 1 carry copy" in exc.value.detail
    assert not billing.calls


@pytest.mark.asyncio
async def test_a_fully_configured_multi_variant_run_still_starts(monkeypatch, billing):
    """The guard must refuse the overcharge, not the feature."""
    admin = _AdminStub({
        "simulations": ([_simulation(variants=2)], None),
        "simulation_variants": (
            [
                {"variant_key": "a", "content": "Ship faster."},
                {"variant_key": "b", "content": "Ship safer."},
            ],
            None,
        ),
    })
    monkeypatch.setattr(simulations_api, "get_supabase_admin", lambda: admin)

    result = await simulations_api.start_simulation(SIM, None, auth=AUTH)
    await asyncio.sleep(0)

    assert result == {"status": "started"}
    assert billing.calls, "a run that executes every arena it was priced for is charged"


@pytest.mark.asyncio
async def test_an_ordinary_single_arena_run_is_not_made_to_pay_for_the_guard(
    monkeypatch, billing
):
    """Every Founder- and Crisis-lens run is single-arena. The guard must not
    add a query to the start path for all of them."""
    admin = _AdminStub({"simulations": ([_simulation(variants=1)], None)})
    monkeypatch.setattr(simulations_api, "get_supabase_admin", lambda: admin)

    await simulations_api.start_simulation(SIM, None, auth=AUTH)
    await asyncio.sleep(0)

    assert "simulation_variants" not in admin.touched


@pytest.mark.asyncio
async def test_a_failed_variant_lookup_is_raised_rather_than_read_as_zero(
    monkeypatch, billing
):
    """`load_arenas` swallows this failure downstream by design. Swallowing it
    here too would leave an overcharge with no witness at either end."""
    class _Exploding(_AdminStub):
        def table(self, name):
            if name == "simulation_variants":
                raise RuntimeError("postgrest unreachable")
            return super().table(name)

    admin = _Exploding({"simulations": ([_simulation(variants=3)], None)})
    monkeypatch.setattr(simulations_api, "get_supabase_admin", lambda: admin)

    with pytest.raises(RuntimeError):
        await simulations_api.start_simulation(SIM, None, auth=AUTH)

    assert not billing.calls


# ── Starting and preparing are single-use, and the guard is a CAS ──

@pytest.mark.asyncio
async def test_two_starts_in_one_window_charge_once_and_run_one_engine(
    monkeypatch, billing
):
    """The full run is the most expensive charge in the product, ~17,000 credits.

    The quote path is guarded — `load_quote` refuses a quote whose `consumed_at`
    is set — and the no-quote branch had **nothing**: it checked the budget and
    deducted, with the plain read at the top of the handler as its only
    protection and the database status not written until `run_simulation` ran
    inside the spawned task. Two POSTs landing in the same window (a
    double-click, or a client retry on a slow response — this handler awaits
    `check_simulation_quota` over the network before deducting) each deducted and
    each spawned an engine on the same run. Two engines writing into one
    `simulation_events` doubles every count and draws `mean_interval`'s bands
    from duplicated observations.

    Re-simulations are *forced* onto that branch: a `quote_id` is refused with
    409 on a run with a `parent_simulation_id`, which is the inoculation loop and
    the website-room "prove" leg.

    The quota stub here holds both requests until both have read `status='ready'`
    — the window a double-click actually lands in, which a read-then-write guard
    cannot see.
    """
    admin = _AdminStub({
        "simulations": ([_simulation()], None),
        "simulation_variants": ([], None),
    })
    monkeypatch.setattr(simulations_api, "get_supabase_admin", lambda: admin)

    both_arrived = asyncio.Event()
    arrivals: list[int] = []

    async def _quota_after_both_read(_org_id):
        arrivals.append(1)
        if len(arrivals) < 2:
            await both_arrived.wait()
        else:
            both_arrived.set()
        return True

    monkeypatch.setattr(stripe_service, "check_simulation_quota", _quota_after_both_read)

    outcomes = await asyncio.gather(
        simulations_api.start_simulation(SIM, None, auth=AUTH),
        simulations_api.start_simulation(SIM, None, auth=AUTH),
        return_exceptions=True,
    )
    await asyncio.sleep(0)

    started = [o for o in outcomes if o == {"status": "started"}]
    refused = [o for o in outcomes if isinstance(o, HTTPException)]
    assert len(started) == 1, outcomes
    assert len(refused) == 1, outcomes
    assert refused[0].status_code == 409
    assert "already been started" in refused[0].detail
    assert len(billing.calls) == 1, (
        f"one run, charged {len(billing.calls)} times: {billing.calls}"
    )


@pytest.mark.asyncio
async def test_a_run_already_prepared_is_not_prepared_a_second_time(monkeypatch):
    """A double-click on `/prepare` built a second swarm on top of the first.

    `run_prepare_agents` makes one `llm_fast` call per agent — up to 1,000 at
    enterprise — and inserted the new batch with no prior DELETE, with
    `seen_usernames` local to one invocation. So a second call re-emitted the
    first call's handles: on migration 019 the first 20-row batch trips
    `idx_simulation_agents_unique_username` and `_mark_simulation_failed` then
    writes "This run stopped before it finished" onto a run that was prepared and
    fine; without 019, a second full swarm lands and `run_simulation` reads every
    row, so the run executes with twice the agents the org was quoted for.
    """
    prepared: list[str] = []

    async def _prepare(sim_id):
        prepared.append(sim_id)

    monkeypatch.setattr(simulations_api, "run_prepare_agents", _prepare)
    admin = _AdminStub({"simulations": ([_simulation(status="draft")], None)})
    monkeypatch.setattr(simulations_api, "get_supabase_admin", lambda: admin)

    first = await simulations_api.prepare_simulation(SIM, auth=AUTH)
    await asyncio.sleep(0)

    assert first == {"status": "started"}
    assert prepared == [SIM]

    with capture_logs() as logs:
        with pytest.raises(HTTPException) as exc:
            await simulations_api.prepare_simulation(SIM, auth=AUTH)
    await asyncio.sleep(0)

    assert exc.value.status_code == 409
    assert "would build a second room" in exc.value.detail
    assert prepared == [SIM], "a second swarm was built for one run"
    assert "prepare_refused_not_preparable" in {e["event"] for e in logs}


@pytest.mark.asyncio
async def test_a_prepared_run_waiting_to_start_is_not_re_prepared(monkeypatch):
    """`ready` is the state the founder is looking at when they click twice.

    **No second room, and no error either.** This asserted a 409, and that
    broke the only control the founder has: the Start button posts `/prepare`
    and then `/start` unconditionally, and it renders for draft, ready and
    failed. A 409 on `ready` made the frontend's catch fire, so `/start` was
    never called and a prepared run could not be started at all.

    The guard exists to stop a second swarm being built, not to refuse the
    caller — so the room is left exactly as it is, `run_prepare_agents` is
    never spawned, and the caller gets a 200 it can carry on from.
    """
    prepared: list[str] = []

    async def _prepare(sim_id):
        prepared.append(sim_id)

    monkeypatch.setattr(simulations_api, "run_prepare_agents", _prepare)
    admin = _AdminStub({"simulations": ([_simulation(status="ready")], None)})
    monkeypatch.setattr(simulations_api, "get_supabase_admin", lambda: admin)

    result = await simulations_api.prepare_simulation(SIM, auth=AUTH)
    await asyncio.sleep(0)

    assert result["status"] == "ready"
    assert prepared == [], "a second room was built for an already-prepared run"


@pytest.mark.asyncio
async def test_a_run_whose_preparation_died_can_be_prepared_again(monkeypatch):
    """The guard must refuse the duplicate, not the retry. `_mark_simulation_
    failed` writes `failed`, and that is the state a founder retries from."""
    prepared: list[str] = []

    async def _prepare(sim_id):
        prepared.append(sim_id)

    monkeypatch.setattr(simulations_api, "run_prepare_agents", _prepare)
    admin = _AdminStub({"simulations": ([_simulation(status="failed")], None)})
    monkeypatch.setattr(simulations_api, "get_supabase_admin", lambda: admin)

    result = await simulations_api.prepare_simulation(SIM, auth=AUTH)
    await asyncio.sleep(0)

    assert result == {"status": "started"}
    assert prepared == [SIM]


# ── Item 38: a pager that could never reach page two ─────

@pytest.mark.asyncio
async def test_listing_simulations_returns_the_total_it_already_computed(monkeypatch):
    page = [{"id": f"sim-{i}"} for i in range(20)]
    admin = _AdminStub({"simulations": (page, 50)})
    monkeypatch.setattr(simulations_api, "get_supabase_admin", lambda: admin)

    result = await simulations_api.list_simulations(
        limit=20, offset=0, project_id=None, auth=AUTH
    )

    assert result["total"] == 50, "50 simulations must not render as one page"
    assert result["limit"] == 20
    assert result["offset"] == 0
    assert [row["id"] for row in result["items"]] == [row["id"] for row in page]


@pytest.mark.asyncio
async def test_an_unavailable_count_is_null_and_logged_not_guessed(monkeypatch):
    """`len(page)` would report "one page" for an unknown total — the same
    number for a fact and its opposite."""
    admin = _AdminStub({"simulations": ([{"id": "sim-1"}], None)})
    monkeypatch.setattr(simulations_api, "get_supabase_admin", lambda: admin)

    with capture_logs() as logs:
        result = await simulations_api.list_simulations(
            limit=20, offset=0, project_id=None, auth=AUTH
        )

    assert result["total"] is None
    assert "simulation_count_unavailable" in {e["event"] for e in logs}


# ── Item 35: chatting with a report that has no body ─────

def _report_admin(monkeypatch, row):
    admin = _AdminStub({"reports": ([row] if row else [], None)})
    monkeypatch.setattr(report_chat, "get_supabase_admin", lambda: admin)

    def _no_redis():
        raise AssertionError("a refused chat must not touch the history cache")

    async def _no_llm(**_kwargs):
        raise AssertionError("a refused chat must not reach the model")

    monkeypatch.setattr(report_chat, "_get_redis", _no_redis)
    monkeypatch.setattr(report_chat, "llm_complete", _no_llm)
    return admin


@pytest.mark.asyncio
@pytest.mark.parametrize("content", [None, "", "   "])
async def test_chatting_with_a_generating_report_is_a_409_not_a_500(
    monkeypatch, content
):
    _report_admin(monkeypatch, {
        "markdown_content": content,
        "simulation_id": SIM,
        "status": "generating",
    })

    with pytest.raises(report_chat.ReportNotReadyError) as exc:
        await report_chat.chat_with_report(REPORT, "What did the swarm think?")

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "report_not_ready"
    assert exc.value.detail["status"] == "generating"
    assert "still being written" in exc.value.detail["message"]


@pytest.mark.asyncio
async def test_a_failed_report_says_so_rather_than_inviting_another_poll(monkeypatch):
    """NULL content is the same value for "wait" and "never". The status is what
    lets the client stop polling."""
    _report_admin(monkeypatch, {
        "markdown_content": None,
        "simulation_id": SIM,
        "status": "failed",
    })

    with pytest.raises(report_chat.ReportNotReadyError) as exc:
        await report_chat.chat_with_report(REPORT, "Why did it fail?")

    assert exc.value.detail["status"] == "failed"
    assert "failed to generate" in exc.value.detail["message"]


@pytest.mark.asyncio
async def test_a_missing_report_is_a_404_not_an_unhandled_key_error(monkeypatch):
    _report_admin(monkeypatch, None)

    with pytest.raises(HTTPException) as exc:
        await report_chat.chat_with_report(REPORT, "Anything there?")

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_a_finished_report_still_answers(monkeypatch):
    """The guard must gate on an empty body, not on being called at all."""
    _report_admin(monkeypatch, {
        "markdown_content": "# Findings\nThe swarm split 60/40.",
        "simulation_id": SIM,
        "status": "complete",
    })

    saved: list[list[dict]] = []
    monkeypatch.setattr(report_chat, "_get_redis", lambda: object())
    monkeypatch.setattr(report_chat, "_load_history", lambda _r, _k: [])
    monkeypatch.setattr(
        report_chat, "_save_history", lambda _r, _k, history: saved.append(history)
    )

    captured: dict = {}

    async def _llm(messages, **_kwargs):
        captured["messages"] = messages
        return "They split 60/40."

    monkeypatch.setattr(report_chat, "llm_complete", _llm)

    result = await report_chat.chat_with_report(REPORT, "How did they split?")

    assert result.answer == "They split 60/40."
    assert "The swarm split 60/40." in captured["messages"][1]["content"]
    assert saved, "the exchange is persisted"
