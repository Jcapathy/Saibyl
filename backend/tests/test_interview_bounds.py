"""`POST /simulations/{id}/interview/batch` was an uncapped spend.

`BatchInterviewBody.agent_ids` had no length constraint, and
`interview_engine.interview_batch` builds one task per id and `asyncio.gather`s
them. The semaphore in that function limits *concurrency* — five at a time —
and nothing at all limited the total. Every interview is two model calls (the
answer, then the sentiment read) and none of it is metered: no quote, no
`deduct_credits`, no balance check.

**What it cost.** A single authenticated request carrying ten thousand ids
bought twenty thousand model calls on Saibyl's account, unbilled and
untraceable to any run's price. A `for` loop around that request is an
unbounded bill from one org, on a route the UI drives with five ids.

The prompt was the same defect on the other axis: it is re-sent in full to
every agent in the batch, so an unbounded string multiplied by the fan-out.

The cap is `MAX_AGENTS_ANY_TIER`, derived from `TIER_CAPS` rather than written
down — the largest swarm any plan can configure. The tests below pin both the
refusal and the derivation, because a cap that stops tracking the caps it came
from is a number somebody will later have to guess at.
"""
from __future__ import annotations

import pytest

from app.api import simulations as sims_api
from app.core.auth import get_current_org
from app.services.billing.agent_pricing import MAX_AGENTS_ANY_TIER, TIER_CAPS

ORG = "11111111-1111-1111-1111-111111111111"
SIM = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def authed_client(app):
    from fastapi.testclient import TestClient

    app.dependency_overrides[get_current_org] = lambda: {"org_id": ORG, "role": "owner"}
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_current_org, None)


class _Admin:
    """Records every query so a test can prove the guard fired before them."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def table(self, name: str):
        self.calls.append(name)
        return self

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def single(self):
        return self

    # What `core.database.maybe_one` calls. The real `.single()` raises on zero
    # rows; `.maybe_single()` is the one that answers with nothing.
    def maybe_single(self):
        return self

    def execute(self):
        from types import SimpleNamespace

        return SimpleNamespace(data={"id": SIM})


@pytest.fixture
def admin(monkeypatch) -> _Admin:
    stub = _Admin()
    monkeypatch.setattr(sims_api, "get_supabase_admin", lambda: stub)
    return stub


@pytest.fixture
def interviewed(monkeypatch) -> list:
    """Stand in for the engine, recording the ids it would have spent on."""
    calls: list[list[str]] = []

    async def _batch(simulation_id, agent_ids, prompt):
        calls.append(list(agent_ids))
        return []

    monkeypatch.setattr(sims_api, "interview_batch", _batch)
    return calls


def _ids(n: int) -> list[str]:
    return [f"{i:08d}-0000-0000-0000-000000000000" for i in range(n)]


# ---------------------------------------------------------------------------
# The cap itself
# ---------------------------------------------------------------------------

def test_the_cap_is_derived_from_the_tier_caps_not_written_down():
    """A restated cap is a cap that stops moving when the real one does.

    `MAX_AGENTS_ANY_TIER` is the ceiling of `TIER_CAPS`. If somebody raises
    enterprise to 2,000 agents, the batch limit follows without an edit here —
    and if somebody hardcodes a number instead, this fails.
    """
    assert MAX_AGENTS_ANY_TIER == max(c.max_agents for c in TIER_CAPS.values())
    assert sims_api.MAX_INTERVIEW_BATCH == MAX_AGENTS_ANY_TIER
    # The value today, so a silent change to the ceiling is visible in a diff.
    # Was 1,000 while `enterprise` existed; 250 since tiers were removed on
    # 2026-08-25 and one ceiling replaced the eight-tier table.
    assert sims_api.MAX_INTERVIEW_BATCH == 250


# ---------------------------------------------------------------------------
# The refusal
# ---------------------------------------------------------------------------

def test_ten_thousand_agent_ids_never_reach_the_model(
    authed_client, admin, interviewed
):
    """The defect, exactly as it was: ten thousand ids, twenty thousand calls.

    Refused at parse time, so neither the simulation lookup nor the engine is
    reached — nothing is queried and nothing is spent.
    """
    response = authed_client.post(
        f"/api/simulations/{SIM}/interview/batch",
        json={"agent_ids": _ids(10_000), "prompt": "What would make you buy this?"},
    )

    assert response.status_code == 422, response.text
    assert not interviewed, "the engine was handed a batch it should never see"
    assert not admin.calls, "the guard let a query through"


def test_the_refusal_tells_the_founder_the_limit_and_what_to_do(
    authed_client, admin, interviewed
):
    """A 422 that says "list too long" is a dead end; this one is an action."""
    response = authed_client.post(
        f"/api/simulations/{SIM}/interview/batch",
        json={"agent_ids": _ids(1_001), "prompt": "Would you pay for this?"},
    )

    assert response.status_code == 422, response.text
    message = " ".join(str(e.get("msg", "")) for e in response.json()["detail"])
    assert "250" in message, message
    assert "1,001" in message, "the founder is not told how far over they are"
    assert "persona group" in message, "the message offers no way forward"


def test_a_batch_at_the_cap_is_allowed(authed_client, admin, interviewed):
    """The cap is a ceiling on the impossible, not a squeeze on the real.

    A thousand ids is the biggest swarm any plan can hold, so it must pass —
    a cap that refuses a legitimate enterprise run would be traded away the
    first time somebody hit it.
    """
    response = authed_client.post(
        f"/api/simulations/{SIM}/interview/batch",
        json={"agent_ids": _ids(250), "prompt": "Why not?"},
    )

    assert response.status_code == 200, response.text
    assert len(interviewed[0]) == 250


def test_repeated_ids_are_not_counted_against_the_cap(
    authed_client, admin, interviewed
):
    """Duplicates cost nothing, so they must not be refused as if they did.

    `interview_batch` resolves ids with one `IN (…)`, so two thousand copies of
    one id is one agent and one pair of model calls. Counting them would refuse
    a harmless client bug while leaving the expensive case at the same number.
    """
    response = authed_client.post(
        f"/api/simulations/{SIM}/interview/batch",
        json={"agent_ids": _ids(1) * 2_000, "prompt": "Say more."},
    )

    assert response.status_code == 200, response.text
    assert interviewed[0] == _ids(1), "duplicates reached the engine"


def test_an_empty_batch_is_refused_with_a_sentence(
    authed_client, admin, interviewed
):
    """It used to answer `[]` — a founder reading "no one replied" as a result."""
    response = authed_client.post(
        f"/api/simulations/{SIM}/interview/batch",
        json={"agent_ids": [], "prompt": "Anyone?"},
    )

    assert response.status_code == 422, response.text
    assert not interviewed


# ---------------------------------------------------------------------------
# The sibling routes — the same audit, the other axis
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(("path", "body"), [
    ("interview", {"agent_id": _ids(1)[0]}),
    ("interview/batch", {"agent_ids": _ids(3)}),
    ("interview/by-persona", {"persona_type": "early adopter"}),
])
def test_an_unbounded_prompt_is_refused_on_every_interview_route(
    authed_client, admin, path, body
):
    """The prompt rides in every one of the batch's calls, so its length
    multiplies by the fan-out. One route capping it would have been the same
    hole moved next door."""
    response = authed_client.post(
        f"/api/simulations/{SIM}/{path}",
        json={**body, "prompt": "x" * 5_000},
    )

    assert response.status_code == 422, response.text
    assert not admin.calls


@pytest.mark.parametrize("model", [
    sims_api.InterviewBody,
    sims_api.BatchInterviewBody,
    sims_api.PersonaInterviewBody,
])
def test_no_interview_field_is_unbounded(model):
    """The structural version of the finding, so a fourth route inherits it.

    Every string field on an interview body must state a maximum, and every
    list field must be validated. This is what would have failed on the day
    `agent_ids: list[str]` was written.
    """
    for name, field in model.model_fields.items():
        constraints = repr(field)
        if field.annotation is str:
            assert "max_length" in constraints, f"{model.__name__}.{name} is unbounded"
        elif getattr(field.annotation, "__origin__", None) is list:
            assert model.__pydantic_decorators__.field_validators, (
                f"{model.__name__}.{name} is a list with nothing bounding it"
            )
