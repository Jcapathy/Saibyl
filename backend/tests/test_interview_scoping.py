"""An interview reaches only the run it names.

Found while fixing something else, and more serious than the thing being
fixed. `POST /simulations/{id}/interview` and `/interview/batch` check that the
**simulation** belongs to the caller, then hand the engine `agent_id`s that
nobody validates. The engine selected on the agent id alone.

So an attacker with a run of their own could name any agent id from any other
organisation's run, and the reply came back with that persona's username, type
and an in-character answer to the attacker's prompt — a cross-tenant read
through a route the caller is fully entitled to use.

The backend holds the service-role client, which **bypasses RLS**, so there is
no database-level second line. The `.eq("simulation_id", ...)` filter is the
whole defence, which is why it is asserted here rather than assumed.
"""
from __future__ import annotations

import pytest

from app.services.engine.personas import interview_engine as engine

MINE = "11111111-1111-1111-1111-111111111111"
THEIRS = "22222222-2222-2222-2222-222222222222"
THEIR_AGENT = "33333333-3333-3333-3333-333333333333"
MY_AGENT = "44444444-4444-4444-4444-444444444444"

_ROWS = [
    {"id": MY_AGENT, "simulation_id": MINE, "username": "mine", "persona_type": "a"},
    {"id": THEIR_AGENT, "simulation_id": THEIRS, "username": "theirs",
     "persona_type": "b"},
]


class _Query:
    def __init__(self, rows):
        self._rows = rows
        self._f: list[tuple] = []

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._f.append(("eq", col, str(val)))
        return self

    def in_(self, col, vals):
        self._f.append(("in", col, [str(v) for v in vals]))
        return self

    def limit(self, _n):
        return self

    def execute(self):
        rows = self._rows
        for kind, col, val in self._f:
            if kind == "eq":
                rows = [r for r in rows if str(r.get(col)) == val]
            else:
                rows = [r for r in rows if str(r.get(col)) in val]
        return type("R", (), {"data": rows})()


class _Admin:
    def table(self, _name):
        return _Query(list(_ROWS))


@pytest.fixture(autouse=True)
def _wired(monkeypatch):
    monkeypatch.setattr(engine, "get_supabase_admin", lambda: _Admin())

    async def _run(agent, simulation_id, prompt, _sem):
        return {"agent": agent, "simulation_id": str(simulation_id)}

    monkeypatch.setattr(engine, "_run_interview", _run)


@pytest.mark.asyncio
async def test_another_orgs_agent_cannot_be_interviewed_through_my_run():
    """The attack, directly: my simulation id, their agent id."""
    with pytest.raises(ValueError) as exc:
        await engine.interview_agent(MINE, THEIR_AGENT, "who are you?")

    message = str(exc.value)
    assert "isn't part of this run" in message
    assert THEIR_AGENT not in message, "the refusal echoed the id back"
    assert "theirs" not in message, "the refusal leaked the persona"


@pytest.mark.asyncio
async def test_a_missing_agent_and_a_foreign_agent_are_indistinguishable():
    """Telling them apart tells a prober which ids are real."""
    missing = "99999999-9999-9999-9999-999999999999"

    with pytest.raises(ValueError) as absent:
        await engine.interview_agent(MINE, missing, "hello")
    with pytest.raises(ValueError) as foreign:
        await engine.interview_agent(MINE, THEIR_AGENT, "hello")

    assert str(absent.value) == str(foreign.value)


@pytest.mark.asyncio
async def test_my_own_agent_still_answers():
    """The fix must not close the route it is protecting."""
    result = await engine.interview_agent(MINE, MY_AGENT, "hello")

    assert result["agent"]["id"] == MY_AGENT


@pytest.mark.asyncio
async def test_a_batch_silently_drops_agents_from_other_runs():
    """A batch is a best-effort fan-out, so a foreign id is absent from the
    result rather than raising — but it must never be *answered*."""
    results = await engine.interview_batch(
        MINE, [MY_AGENT, THEIR_AGENT], "what worries you?"
    )

    returned = [r["agent"]["id"] for r in results]
    assert returned == [MY_AGENT]
    assert THEIR_AGENT not in returned


@pytest.mark.asyncio
async def test_a_batch_of_entirely_foreign_ids_answers_nothing():
    results = await engine.interview_batch(MINE, [THEIR_AGENT], "hello")

    assert results == []


def test_both_engine_reads_filter_on_the_simulation():
    """Pinned on the source too. The filter is the whole defence — the
    service-role client bypasses RLS, so nothing else would catch its removal.
    """
    import inspect

    for fn in (engine.interview_agent, engine.interview_batch):
        source = inspect.getsource(fn)
        assert '.eq("simulation_id"' in source, (
            f"{fn.__name__} no longer scopes its read to the simulation, so any "
            f"organisation's agent id can be interviewed through it"
        )
