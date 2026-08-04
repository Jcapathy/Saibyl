# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# Arena(variant_key, label, content)
# load_arenas(simulation_id, prediction_goal) -> list[Arena]
# DEFAULT_VARIANT_KEY
# ─────────────────────────────────────────────────────────
"""The arenas a run is executed in, one per variant under test.

**DECISIONS_V2 §5.** 2–8 variants judged by the *same* generated audience —
identical agents, identical seeds — each in an isolated arena. The sharing is not
an optimisation, it is the claim: if each variant faced a differently-drawn
swarm, the differences between them would be confounded by audience draw and the
scoreboard would be noise dressed as signal.

Isolation is structural rather than enforced. `get_adapter()` returns a fresh
instance per call, and an adapter instance owns its feed, its posts and its
`_agent_history` — so one adapter per arena gives each variant its own world with
no changes to any of the twelve adapters. **If adapters ever become singletons or
acquire shared class-level state, matched-swarm testing breaks silently**: every
arena would read one feed and the variants would be scored on a conversation they
were all in together.

An ordinary run — every Founder- and Crisis-lens run, and every Marketing run
before variants are configured — has exactly one arena carrying the simulation's
own `prediction_goal`. That is the pre-Phase-3 behaviour expressed in the new
shape, not a special case beside it.
"""
from __future__ import annotations

import structlog
from pydantic import BaseModel

from app.core.database import get_supabase_admin

logger = structlog.get_logger()

# The arena an ordinary single-variant run executes in. Every event ever written
# before Phase 3 carries this in `simulation_events.variant`, so a run with no
# configured variants stays comparable with the entire history.
DEFAULT_VARIANT_KEY = "a"


class Arena(BaseModel):
    """One variant's isolated world.

    `content` is what the arena's agents are told the conversation is about. It
    replaces `prediction_goal` for this arena and nowhere else — which is
    simultaneously what makes the arenas different and what makes them
    comparable, because everything else about them is identical.
    """

    variant_key: str
    label: str
    content: str

    @property
    def is_default(self) -> bool:
        return self.variant_key == DEFAULT_VARIANT_KEY


def load_arenas(simulation_id: str, prediction_goal: str) -> list[Arena]:
    """The arenas this run executes in, in display order.

    Returns a single default arena when no variants are configured. Never
    returns an empty list: a run with no arena would complete with zero events
    and no error, which is Phase 1's bug #2 in a new place.
    """
    try:
        rows = (
            get_supabase_admin()
            .table("simulation_variants")
            .select("variant_key, label, content, position")
            .eq("simulation_id", simulation_id)
            .order("position")
            .execute()
        ).data or []
    except Exception:
        # A run is worth more than a scoreboard. Falling back to the single
        # default arena produces a valid, measurable, reportable simulation of
        # the subject — losing the comparison but not the run.
        logger.exception("variant_lookup_failed", simulation_id=simulation_id)
        rows = []

    if not rows:
        return [
            Arena(
                variant_key=DEFAULT_VARIANT_KEY,
                label="",
                content=prediction_goal or "",
            )
        ]

    arenas = [
        Arena(
            variant_key=str(r["variant_key"]),
            label=str(r.get("label") or ""),
            # An empty variant body would run an arena about nothing and score
            # it against the others as though it were a real alternative.
            content=str(r.get("content") or "").strip() or prediction_goal or "",
        )
        for r in rows
    ]

    logger.info(
        "arenas_loaded",
        simulation_id=simulation_id,
        arenas=len(arenas),
        keys=[a.variant_key for a in arenas],
    )
    return arenas
