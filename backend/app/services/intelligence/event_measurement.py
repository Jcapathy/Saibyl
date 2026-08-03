# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# measure_simulation_events(simulation_id, organization_id) -> MeasurementResult
# BATCH_SIZE
# ─────────────────────────────────────────────────────────
"""Scores every simulation event from what the agent actually said.

This replaces the V1 formula

    drift_factor = 1.0 + (round_num / max_rounds) * 1.5
    sentiment = clamp(agent.profile.sentiment_baseline * drift_factor, -1, 1)

which was a function of the archetype preset and the round index and never read
the event's content at all. Two agents of the same archetype posting "this is
exactly what we've needed for years" and "this will get someone fired" received
identical sentiment. Everything downstream — the timeline, the platform
breakdown, the flashpoints — inherited that.

Three design points worth keeping:

**Reactions are engagement, not sentiment.** A like or a repost carries no text,
so there is nothing to measure. Rather than assign one an invented valence, they
are marked measured with a null valence and excluded from every sentiment
aggregate. They still count as engagement. Inventing "like = +0.3" would be the
same class of mistake this module exists to remove, just smaller.

**A failed batch leaves events unmeasured.** It does not fall back to a guess.
Coverage is reported in the artifact's quality block, so a partial measurement
is visible rather than silently averaged over.

**Batched ~25 events per call.** Per-event calls would make measurement cost
comparable to the agent actions themselves; at 25 per call the stage is roughly
4% of a standard run's cost.
"""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import structlog
from pydantic import BaseModel

from app.core.config import settings
from app.core.database import fetch_all, get_supabase_admin
from app.core.llm_client import _extract_json, llm_fast
from app.services.billing.usage_ledger import usage_context

logger = structlog.get_logger()

# Events per classifier call. Raising this lowers cost per event but widens the
# blast radius of one malformed response, since a batch is retried or dropped
# whole.
BATCH_SIZE = 25

# Concurrent classifier calls. Matches the agent-generation semaphore; the
# constraint is the provider's rate limit, not local CPU.
_MEASURE_SEMAPHORE = asyncio.Semaphore(8)

# Event types that carry no text. Measured — so coverage accounting is honest —
# but with a null valence, and excluded from sentiment aggregates.
_CONTENTLESS_EVENT_TYPES = {"react", "reaction", "like", "repost", "vote"}

_VALID_STANCES = {"support", "oppose", "undecided", "off_topic"}

_SYSTEM = (
    "You are a discourse analyst. You score social media posts for how their "
    "author actually feels about a specific subject. You return only JSON. You "
    "never infer a score from an author's persona label — only from the text."
)

_PROMPT = """Subject under discussion: {goal}

Score each numbered post below. Judge only what the text says about the subject.

For each post return:
- "i": the post number, exactly as given
- "valence": -1.0 to 1.0 — how negative or positive the author is about the
  subject. 0.0 means genuinely neutral, not "unsure".
- "stance": one of "support", "oppose", "undecided", "off_topic". Use
  "off_topic" when the post is not about the subject at all.
- "intensity": 0.0 to 1.0 — how strongly the view is held. A mild preference is
  0.2; "I will cancel my account over this" is 0.9. Intensity is independent of
  valence: strong praise is also high intensity.
- "objections": array of short noun phrases naming each distinct concern the
  post raises about the subject, in the author's own framing (e.g. "price too
  high for a small team", "no SOC 2"). Empty array if it raises none. Do not
  invent objections that are not in the text.
- "intent": one of "purchase", "trial", "click", "visit", "inquire", "share",
  "abandon", "none" — the action the post implies the author would take.
- "is_novel_claim": true only if the post introduces an assertion about the
  subject that no earlier post in this batch made. Restating an existing point
  is false.

Posts:
{posts}

Return JSON exactly: {{"results": [{{"i": 0, "valence": 0.0, "stance": "...", \
"intensity": 0.0, "objections": [], "intent": "none", "is_novel_claim": false}}]}}
Return one entry per post, in order. No commentary."""


class MeasurementResult(BaseModel):
    simulation_id: str
    events_total: int
    events_measured: int
    events_scored: int          # content-bearing events that got a valence
    events_contentless: int     # reactions — measured, no valence
    events_failed: int
    batches_failed: int
    model: str


def _clamp(value: Any, low: float, high: float) -> float | None:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if num != num:  # NaN
        return None
    return max(low, min(high, num))


def _normalize_objections(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        text = " ".join(item.split()).strip().lower()
        # Long "objections" are the model summarising the post rather than
        # naming a concern; they cluster badly and are dropped.
        if 3 <= len(text) <= 120:
            out.append(text)
    return out[:5]


def _build_batch_prompt(goal: str, batch: list[dict[str, Any]]) -> str:
    lines = []
    for idx, event in enumerate(batch):
        content = (event.get("content") or "").replace("\n", " ").strip()
        lines.append(f"[{idx}] ({event.get('platform', '?')}) {content[:600]}")
    return _PROMPT.format(goal=goal or "(not specified)", posts="\n".join(lines))


async def _measure_batch(
    goal: str, batch: list[dict[str, Any]], model: str
) -> list[dict[str, Any]] | None:
    """Score one batch. Returns None if the batch could not be scored.

    Returning None rather than a default score is deliberate: an unmeasured
    event is visible in the coverage figure, whereas a defaulted one silently
    drags every aggregate toward zero.
    """
    async with _MEASURE_SEMAPHORE:
        try:
            raw = await llm_fast(
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": _build_batch_prompt(goal, batch)},
                ],
                temperature=0.0,
                max_tokens=200 * len(batch) + 200,
            )
            parsed = json.loads(_extract_json(raw))
        except Exception as exc:
            logger.warning("measure_batch_failed", size=len(batch), error=str(exc))
            return None

    results = parsed.get("results")
    if not isinstance(results, list):
        logger.warning("measure_batch_malformed", size=len(batch))
        return None

    by_index: dict[int, dict[str, Any]] = {}
    for entry in results:
        if not isinstance(entry, dict):
            continue
        try:
            idx = int(entry.get("i"))
        except (TypeError, ValueError):
            continue
        if 0 <= idx < len(batch):
            by_index[idx] = entry

    updates: list[dict[str, Any]] = []
    now = datetime.now(UTC).isoformat()
    for idx, event in enumerate(batch):
        entry = by_index.get(idx)
        if entry is None:
            # One missing entry does not invalidate the batch; that event stays
            # unmeasured and is retried on the next build.
            continue

        valence = _clamp(entry.get("valence"), -1.0, 1.0)
        intensity = _clamp(entry.get("intensity"), 0.0, 1.0)
        stance = entry.get("stance")
        if stance not in _VALID_STANCES:
            stance = None

        # A scored event needs a valence. Without one there is nothing to
        # aggregate, so it is left unmeasured rather than half-written.
        if valence is None:
            continue

        intent = entry.get("intent")
        updates.append({
            "id": event["id"],
            "valence": round(valence, 4),
            "stance": stance,
            "intensity": round(intensity, 4) if intensity is not None else None,
            "intent": intent if isinstance(intent, str) and intent else None,
            "is_novel_claim": bool(entry.get("is_novel_claim")),
            "objections": _normalize_objections(entry.get("objections")),
            "measured_at": now,
            "measure_model": model,
        })

    return updates


def _write_updates(updates: list[dict[str, Any]]) -> None:
    admin = get_supabase_admin()
    for row in updates:
        event_id = row.pop("id")
        admin.table("simulation_events").update(row).eq("id", event_id).execute()


def _mark_contentless(event_ids: list[str], now: str) -> None:
    """Reactions are measured but carry no valence — see the module docstring."""
    if not event_ids:
        return
    admin = get_supabase_admin()
    for i in range(0, len(event_ids), 50):
        admin.table("simulation_events").update({
            "measured_at": now,
            "measure_model": "n/a:no_content",
            "valence": None,
            "stance": None,
            "intensity": None,
            "objections": [],
            "is_novel_claim": False,
        }).in_("id", event_ids[i : i + 50]).execute()


async def measure_simulation_events(
    simulation_id: str, organization_id: str
) -> MeasurementResult:
    """Score every unmeasured event in a simulation from its content."""
    admin = get_supabase_admin()
    model = settings.llm_fast_model

    sim = (
        admin.table("simulations")
        .select("prediction_goal")
        .eq("id", simulation_id)
        .single()
        .execute()
    ).data or {}
    goal = sim.get("prediction_goal", "")

    # Paged: a 250-agent, 10-round run exceeds PostgREST's 1,000-row cap, and a
    # truncated read would silently leave most of the run unmeasured.
    events = fetch_all(
        admin.table("simulation_events")
        .select("id, event_type, platform, content, round_number")
        .eq("simulation_id", simulation_id)
        .is_("measured_at", "null")
        .order("id")
    )

    contentless: list[str] = []
    scorable: list[dict[str, Any]] = []
    for event in events:
        content = (event.get("content") or "").strip()
        if event.get("event_type") in _CONTENTLESS_EVENT_TYPES or not content:
            contentless.append(event["id"])
        else:
            scorable.append(event)

    now = datetime.now(UTC).isoformat()
    await asyncio.to_thread(_mark_contentless, contentless, now)

    batches = [
        scorable[i : i + BATCH_SIZE] for i in range(0, len(scorable), BATCH_SIZE)
    ]
    logger.info(
        "measurement_start",
        simulation_id=simulation_id,
        scorable=len(scorable),
        contentless=len(contentless),
        batches=len(batches),
        model=model,
    )

    scored = 0
    batches_failed = 0

    with usage_context(
        "event_measurement",
        simulation_id=simulation_id,
        organization_id=organization_id,
    ):
        results = await asyncio.gather(
            *[_measure_batch(goal, batch, model) for batch in batches],
            return_exceptions=True,
        )

    for batch, result in zip(batches, results, strict=True):
        if isinstance(result, BaseException) or result is None:
            batches_failed += 1
            logger.warning(
                "measure_batch_dropped",
                simulation_id=simulation_id,
                size=len(batch),
                error=str(result) if isinstance(result, BaseException) else "no_result",
            )
            continue
        if result:
            await asyncio.to_thread(_write_updates, result)
            scored += len(result)

    result = MeasurementResult(
        simulation_id=simulation_id,
        events_total=len(events),
        events_measured=scored + len(contentless),
        events_scored=scored,
        events_contentless=len(contentless),
        events_failed=len(scorable) - scored,
        batches_failed=batches_failed,
        model=model,
    )
    logger.info("measurement_complete", **result.model_dump())
    return result
