"""One bad brace must not destroy a paid artifact.

Found by running three sample products end to end through production. A
Chartwell outbound sequence — 2,500 credits, already charged — died on this,
written verbatim into a column the founder reads:

    1 validation error for _Generated
      Invalid JSON: expected `,` or `}` at line 16 column 375

Two independent defects, and the second is why the first was visible at all.

1. **`llm_structured` made exactly one attempt.** A truncated string ended the
   artifact. The failure is random rather than systematic, so a retry that
   shows the model its own output and the parse error recovers almost all of
   them — and a schema the model genuinely cannot satisfy still fails, which
   it should.

2. **`pydantic.ValidationError` subclasses `ValueError`.** All three GTM
   workers catch `ValueError` to pass through *deliberate* refusals, which
   carry a founder-readable sentence. So a malformed model response took the
   refusal branch and its pydantic error was shown to the customer as though
   it were an explanation.
"""
from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from app.core import llm_client


class _Shape(BaseModel):
    steps: list[str]


class _Usage:
    completion_tokens = 10
    prompt_tokens = 10
    total_tokens = 20


def _response(content: str):
    return type(
        "R", (),
        {
            "choices": [type("C", (), {"message": type("M", (), {"content": content})()})()],
            "usage": _Usage(),
        },
    )()


@pytest.fixture
def calls(monkeypatch):
    """Record every completion request and serve scripted replies."""
    recorded: list[list[dict]] = []
    replies: list[str] = []

    async def _acompletion(*, model, messages, **_kwargs):
        recorded.append(list(messages))
        return _response(replies.pop(0))

    monkeypatch.setattr(llm_client, "acompletion", _acompletion)
    monkeypatch.setattr(llm_client, "_record", lambda *_a, **_k: None)
    monkeypatch.setattr(llm_client, "_api_key", lambda: "test")
    return recorded, replies


# ---------------------------------------------------------------------------
# The retry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_truncated_response_is_retried_rather_than_lost(calls):
    """The exact production failure: JSON that stops mid-string."""
    recorded, replies = calls
    replies.extend([
        '{"steps": ["open with the audit trail, because that is what a compl',
        '{"steps": ["open with the audit trail"]}',
    ])

    result = await llm_client.llm_structured([{"role": "user", "content": "go"}], _Shape)

    assert result.steps == ["open with the audit trail"]
    assert len(recorded) == 2, "the malformed response was not retried"


@pytest.mark.asyncio
async def test_the_retry_shows_the_model_what_was_wrong(calls):
    """Asking again identically is a coin flip. The corrective turn carries
    the parser's own error, so the model is told what to fix."""
    recorded, replies = calls
    replies.extend(['{"steps": [', '{"steps": ["ok"]}'])

    await llm_client.llm_structured([{"role": "user", "content": "go"}], _Shape)

    second = recorded[1]
    assert second[-2]["role"] == "assistant", "the bad output was not shown back"
    assert second[-2]["content"] == '{"steps": ['
    correction = second[-1]["content"]
    assert second[-1]["role"] == "user"
    assert "did not parse" in correction
    assert "_Shape" in correction or "steps" in correction


@pytest.mark.asyncio
async def test_a_schema_the_model_cannot_satisfy_still_fails(calls):
    """The retry must not turn a real disagreement into an infinite loop or a
    silent empty result. It fails, loudly, after a bounded number of tries."""
    _recorded, replies = calls
    replies.extend(['{"wrong": 1}'] * (llm_client.STRUCTURED_RETRIES + 1))

    with pytest.raises(ValidationError):
        await llm_client.llm_structured([{"role": "user", "content": "go"}], _Shape)


@pytest.mark.asyncio
async def test_a_good_first_response_costs_exactly_one_call(calls):
    recorded, replies = calls
    replies.append('{"steps": ["fine"]}')

    await llm_client.llm_structured([{"role": "user", "content": "go"}], _Shape)

    assert len(recorded) == 1, "a valid response was retried anyway"


@pytest.mark.asyncio
async def test_every_attempt_lands_in_the_cost_ledger(monkeypatch):
    """A retry is real spend. A ledger that counted only the successful turn
    would understate COGS exactly when the model behaves worst — and the
    margin on every artifact is computed from it."""
    replies = ['{"steps": [', '{"steps": ["ok"]}']
    recorded_usage: list[object] = []

    async def _acompletion(**_kwargs):
        return _response(replies.pop(0))

    monkeypatch.setattr(llm_client, "acompletion", _acompletion)
    monkeypatch.setattr(llm_client, "_api_key", lambda: "test")
    monkeypatch.setattr(
        llm_client, "_record", lambda _m, usage: recorded_usage.append(usage)
    )

    await llm_client.llm_structured([{"role": "user", "content": "go"}], _Shape)

    assert len(recorded_usage) == 2, "the retry's tokens were never recorded"


# ---------------------------------------------------------------------------
# The exception ordering, in all three workers
# ---------------------------------------------------------------------------

WORKERS = [
    ("app.workers.outbound_tasks", "outbound_sequences"),
    ("app.workers.messaging_doc_tasks", "messaging_docs"),
    ("app.workers.answer_pack_tasks", "answer_packs"),
]


@pytest.mark.parametrize(("module_path", "table"), WORKERS)
def test_validation_error_is_caught_before_value_error(module_path, table):
    """`except` clauses are tried in order, and `ValidationError` is a
    `ValueError`. Caught second, it can never be reached — so the ordering is
    the fix, and a later edit that reorders them silently restores the bug.
    """
    import importlib
    import inspect

    module = importlib.import_module(module_path)
    source = inspect.getsource(module)

    v_error = source.find("except ValidationError")
    value_error = source.find("except ValueError")

    assert v_error != -1, f"{module_path} does not handle ValidationError at all"
    assert value_error != -1, f"{module_path} no longer handles ValueError"
    assert v_error < value_error, (
        f"{module_path} catches ValueError before ValidationError, so a "
        f"malformed model response is treated as a deliberate refusal and its "
        f"pydantic error is written into a column the founder reads"
    )


@pytest.mark.parametrize(("module_path", "table"), WORKERS)
def test_the_unparseable_branch_shows_the_founder_a_sentence(module_path, table):
    import importlib
    import inspect

    module = importlib.import_module(module_path)
    source = inspect.getsource(module)
    branch = source[source.find("except ValidationError"):source.find("except ValueError")]

    assert "GENERIC_FAILURE_MESSAGE" in branch, (
        "the unparseable branch must hand the founder the written sentence, "
        "not str(exc)"
    )
    assert "_fail(str(exc))" not in branch
