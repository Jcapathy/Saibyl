"""`run_prepare_agents`, end to end against stubs.

Two claims, both of which were false and neither of which raised anything.

**The swarm is the size the customer paid for.** Credits are charged at start
from the selected agent count (HANDOFF §4.3). The old apportionment allocated 45
agents for a 48-agent run at some shapes and 4 for a 2-agent run at others, and
`prepare_agents_complete` reported the number it built rather than the number it
owed. `test_agent_apportionment.py` covers the arithmetic; this covers the two
apportionments composed inside the real function.

**Agents are grounded in extracted text, not in the file's bytes.** The prompt's
"Document context" block came from `storage_path` decoded as UTF-8 — for a PDF,
mojibake, silently, because `errors="replace"` never raises. Extracted text has
lived at `processed_text_path` since the ingestion unification.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
import structlog

from app.services.engine.personas import pack_loader
from app.services.engine.personas.icp_schema import (
    AdversarialArchetype,
    ICPArchetype,
    ICPProfile,
)
from app.services.engine.personas.icp_synthesizer import compile_pack
from app.workers import simulation_tasks

SIM = "55555555-5555-5555-5555-555555555555"
PROJECT = "66666666-6666-6666-6666-666666666666"
ORG = "77777777-7777-7777-7777-777777777777"
PACK_ID = "icp_testpack"

# A real PDF's first bytes. Decoded as UTF-8 with `errors="replace"` this is
# what every agent in a PDF-backed project used to be told the material said.
PDF_BYTES = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<</Type/Catalog>>\n\xff\xfe\x00binary"
EXTRACTED = "Our pricing starts at $99 a month and onboarding imports a deck."


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

class _Query:
    def __init__(self, admin, table: str):
        self._admin = admin
        self._table = table
        self._payload: dict | None = None
        self._single = False

    def select(self, *_a, **_k):
        return self

    def update(self, payload):
        self._payload = payload
        return self

    def insert(self, rows):
        self._admin.inserted.extend(rows)
        return self

    def eq(self, *_a):
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a):
        return self

    def single(self):
        self._single = True
        return self

    def execute(self):
        if self._payload is not None:
            self._admin.updates.append((self._table, self._payload))
            return SimpleNamespace(data=[{}])
        rows = self._admin.rows.get(self._table, [])
        return SimpleNamespace(data=(rows[0] if self._single else rows))


class _Bucket:
    def __init__(self, objects: dict[str, bytes]):
        self._objects = objects

    def download(self, path: str) -> bytes:
        if path not in self._objects:
            raise FileNotFoundError(path)
        return self._objects[path]


class _Admin:
    def __init__(self, rows: dict, objects: dict[str, bytes]):
        self.rows = rows
        self.storage = SimpleNamespace(from_=lambda _bucket: _Bucket(objects))
        self.inserted: list[dict] = []
        self.updates: list[tuple[str, dict]] = []

    def table(self, name: str):
        return _Query(self, name)


def _sim_row(agent_count: int, platforms: list[str], share: float = 0.3) -> dict:
    return {
        "id": SIM,
        "project_id": PROJECT,
        "organization_id": ORG,
        "platforms": platforms,
        "persona_pack_ids": [PACK_ID],
        "agent_count": agent_count,
        "adversarial_share": share,
        "prediction_goal": "Will teams adopt this?",
    }


def _pack(buyers: int = 3, cohort: int = 4, share: float = 0.3):
    profile = ICPProfile(
        name="Test ICP",
        archetypes=[
            ICPArchetype(id=f"buyer-{i}", label=f"Buyer {i}", weight=1.0, role="buyer")
            for i in range(buyers)
        ],
        adversarial=[
            AdversarialArchetype(
                id=f"adv-{i}", label=f"Adversary {i}", weight=1.0, role="category_skeptic"
            )
            for i in range(cohort)
        ],
    )
    return compile_pack(profile, PACK_ID, ["hacker_news"], share)


def _capturable_logger(monkeypatch, module) -> None:
    """Make `capture_logs` able to see this module's logger, in any test order.

    `setup_logging()` calls `structlog.configure(processors=[...])` with a
    **new** list, and `create_app()` calls it every time. `capture_logs` mutates
    whichever list is current *in place*, deliberately, so that loggers already
    bound keep working. Put those two together with
    `cache_logger_on_first_use=True` and a module logger first used before the
    last `create_app()` is frozen against the previous list: it still logs, and
    `capture_logs` still returns `[]`.

    That is order-dependent and it fails in the direction that matters — a log
    assertion that passes because nothing was captured is the vacuous assertion
    HANDOFF's verification note warns about. Rebinding a fresh proxy per test
    removes the dependency: it binds inside the capture block, against the list
    the capture block is holding.
    """
    monkeypatch.setattr(module, "logger", structlog.get_logger(module.__name__))


def _install(monkeypatch, *, sim: dict, docs: list[dict], objects: dict[str, bytes]):
    admin = _Admin(
        {"simulations": [sim], "documents": docs, "ontologies": []},
        objects,
    )
    monkeypatch.setattr(simulation_tasks, "get_supabase_admin", lambda: admin)
    monkeypatch.setattr(pack_loader, "get_pack", lambda _pack_id, _org: _pack())

    prompts: list[str] = []

    async def _llm(messages, **_kwargs):
        prompts.append(messages[0]["content"])
        return json.dumps({
            "display_name": "Test Person",
            "username": f"user{len(prompts)}",
            "bio": "bio",
            "age": 33,
            "profession": "engineer",
            "sentiment_baseline": 0.0,
            "backstory": "backstory",
        })

    monkeypatch.setattr(simulation_tasks, "llm_fast", _llm)
    return admin, prompts


# ---------------------------------------------------------------------------
# The swarm is the size that was charged for
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("agent_count,platforms", [
    (48, ["hacker_news"]),
    (30, ["hacker_news"]),
    (96, ["hacker_news", "reddit"]),
    (30, ["hacker_news", "reddit", "twitter_x", "linkedin"]),
    (25, ["hacker_news", "reddit"]),
    (7, ["hacker_news", "reddit", "twitter_x"]),
])
async def test_the_run_builds_exactly_the_agents_that_were_charged_for(
    monkeypatch, agent_count, platforms
):
    admin, _prompts = _install(
        monkeypatch, sim=_sim_row(agent_count, platforms), docs=[], objects={}
    )

    result = await simulation_tasks.run_prepare_agents(SIM)

    assert result["agents"] == agent_count
    assert len(admin.inserted) == agent_count


@pytest.mark.asyncio
async def test_the_reported_48_agent_run_is_not_45(monkeypatch):
    """The reported case, through the real function rather than the arithmetic."""
    admin, _prompts = _install(
        monkeypatch, sim=_sim_row(48, ["hacker_news"]), docs=[], objects={}
    )

    result = await simulation_tasks.run_prepare_agents(SIM)

    assert (result["agents"], len(admin.inserted)) == (48, 48)


@pytest.mark.asyncio
async def test_every_archetype_is_represented_and_the_cohort_share_holds(monkeypatch):
    admin, _prompts = _install(
        monkeypatch, sim=_sim_row(96, ["hacker_news"]), docs=[], objects={}
    )

    await simulation_tasks.run_prepare_agents(SIM)

    archetypes = {row["profile"]["archetype"] for row in admin.inserted}
    assert len(archetypes) == 7, archetypes

    adversarial = [row for row in admin.inserted if row["is_adversarial"]]
    assert abs(len(adversarial) / 96 - 0.3) <= 0.034, len(adversarial)


@pytest.mark.asyncio
async def test_the_swarm_is_split_across_platforms_not_replicated(monkeypatch):
    """Adding a platform spreads the same swarm thinner — HANDOFF §7."""
    admin, _prompts = _install(
        monkeypatch, sim=_sim_row(96, ["hacker_news", "reddit"]), docs=[], objects={}
    )

    await simulation_tasks.run_prepare_agents(SIM)

    per_platform: dict[str, int] = {}
    for row in admin.inserted:
        per_platform[row["platform"]] = per_platform.get(row["platform"], 0) + 1
    assert per_platform == {"hacker_news": 48, "reddit": 48}


# ---------------------------------------------------------------------------
# Grounding comes from extracted text
# ---------------------------------------------------------------------------

def _doc(doc_id: str = "doc-1", *, processed: bool = True) -> dict:
    return {
        "id": doc_id,
        "filename": "deck.pdf",
        "file_type": "pdf",
        "storage_path": f"org/{doc_id}.pdf",
        "processed_text_path": f"org/{doc_id}.txt" if processed else None,
    }


@pytest.mark.asyncio
async def test_the_prompt_carries_extracted_text_and_never_the_raw_pdf(monkeypatch):
    """The mojibake fix, asserted on both sides.

    The raw object is present in storage and readable — the point is that the
    prompt does not contain it.
    """
    doc = _doc()
    _admin, prompts = _install(
        monkeypatch,
        sim=_sim_row(6, ["hacker_news"]),
        docs=[doc],
        objects={
            doc["storage_path"]: PDF_BYTES,
            doc["processed_text_path"]: EXTRACTED.encode("utf-8"),
        },
    )

    await simulation_tasks.run_prepare_agents(SIM)

    assert prompts
    for prompt in prompts:
        assert EXTRACTED in prompt
        assert "%PDF" not in prompt
        assert "�" not in prompt, "the raw object reached the prompt as mojibake"


@pytest.mark.asyncio
async def test_a_document_that_cannot_be_read_is_reported_not_swallowed(monkeypatch):
    """The old `except Exception: return ""` made a lost source invisible."""
    doc = _doc()
    _admin, prompts = _install(
        monkeypatch,
        sim=_sim_row(6, ["hacker_news"]),
        docs=[doc],
        objects={},  # neither object exists
    )
    _capturable_logger(monkeypatch, simulation_tasks)

    with structlog.testing.capture_logs() as logs:
        await simulation_tasks.run_prepare_agents(SIM)

    events = {entry["event"] for entry in logs}
    assert "agent_doc_context_read_failed" in events
    assert prompts, "the run must continue with less grounding, not fail"


@pytest.mark.asyncio
async def test_a_legacy_row_without_extracted_text_still_reaches_the_prompt(monkeypatch):
    """`source_text` re-extracts rows that predate `processed_text_path`."""
    doc = _doc(processed=False)
    _admin, prompts = _install(
        monkeypatch,
        sim=_sim_row(6, ["hacker_news"]),
        docs=[doc],
        objects={doc["storage_path"]: PDF_BYTES},
    )
    monkeypatch.setattr(
        "app.services.engine.document_processor._extract_text",
        lambda file_bytes, file_type: (EXTRACTED, "utf-8", 1),
    )

    await simulation_tasks.run_prepare_agents(SIM)

    assert all(EXTRACTED in prompt for prompt in prompts)
