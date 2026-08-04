# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# SearchAdapter                    — the interface every provider implements
# AnthropicWebSearchAdapter        — the one implementation today
# SearchUnavailableError                — provider refused or is misconfigured
# WEB_SEARCH_TOOL_TYPE, MAX_SEARCHES_PER_QUERY, MAX_SOURCES_PER_QUERY
# ─────────────────────────────────────────────────────────
"""Web search, behind an interface narrow enough to swap the provider.

There was no search capability in this codebase before this module, which makes
the interface the decision worth getting right — `report_agent.py:103` has been
stripping hallucinated `search_web` / `read_url` lines out of model output for
long enough to prove the writer wants one. The precedent is
`BasePlatformAdapter`: twelve platforms behind one abstract method, and the
reason twelve adapters were survivable is that nothing above them knows which
one is running.

    async def search(self, query: str, *, max_results: int) -> list[SearchResult]

That is the whole contract. Everything provider-specific — how a search is
billed, whether results arrive as text or as encrypted blocks, how many
round-trips it takes — stops here.

**Why the Anthropic implementation is a model turn rather than an HTTP call.**
The server-side web search tool is not a search API; it runs inside a Messages
request, and its `web_search_result` blocks carry `encrypted_content` that only
the model in that turn can read. There is no way to get the page text out of it
directly. So this adapter spends one turn whose only job is to run the query and
have the model write a factual digest per URL through a strict `record_source`
tool, and that digest becomes `SearchResult.snippet`.

That has a consequence the next stage depends on: **the snippet is model-written,
so it cannot be trusted on its own.** It is trusted only as a *bound*.
`extraction.verify_candidates` requires every evidence quote to appear verbatim
in one of these snippets and every URL to be one the provider actually returned,
which turns "the model said so" into "the model said so about a page that
exists, in words it also wrote down against that page". A provider that returns
real text extracts (Brave, Serper, Exa) drops into the same interface and makes
that check stronger, not different.

**Search runs on the fast model.** DECISIONS §14: Haiku for volume, the main
model for judgment. Issuing a query and transcribing what a page says is the
volume half — and it is where the tokens are, because the retrieved page content
is billed as input to *this* turn. Running it on the main model would multiply
the dominant cost line of the whole feature by five and buy nothing: the
judgment (does this company match the archetype, is that headcount actually
stated) happens in `extraction`, on the main model, over text a fifth the size.

**Tool version.** `web_search_20250305` — the basic variant — is deliberate.
The `_20260209` and later variants add dynamic filtering, which runs the search
from inside code execution and requires a Claude 4.6-or-later model; the fast
model this adapter runs on is Haiku. Dynamic filtering would cut input tokens
materially, so this is a real trade and not an oversight: it becomes available
the moment the search turn moves to a 4.6+ model, and the measurement to take
first is `input_tokens` per search turn from `llm_usage` at `stage='gtm_discovery'`.
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any, ClassVar

import structlog
from anthropic import APIStatusError, AsyncAnthropic

from app.core.config import settings
from app.services.billing.agent_pricing import search_fee_usd
from app.services.billing.usage_ledger import record_llm_call
from app.services.gtm.schema import SearchResult

log = structlog.get_logger()

# See the module docstring. One constant so the upgrade is one edit.
WEB_SEARCH_TOOL_TYPE = "web_search_20250305"

# Searches the provider may run for one compiled query. The compiler already
# produced a specific query, so this is a refinement budget, not a research
# budget — and it is the multiplier on the per-search charge, which the token
# ledger cannot see. See `pricing.py`.
MAX_SEARCHES_PER_QUERY = 2

# Sources digested per query. Caps the output of the search turn and the input
# of the extraction turn in one number.
MAX_SOURCES_PER_QUERY = 8

# Round-trips allowed in the tool loop: one search turn, one turn to emit
# sources, one to finish, plus headroom for `pause_turn`. A loop without a
# ceiling is a loop that can bill without a ceiling.
_MAX_TURNS = 6

# Enough for MAX_SOURCES_PER_QUERY digests. Also the reason no `thinking`
# parameter is set anywhere in this module: on models where thinking is on by
# default it shares this budget, and a budget sized only for the answer
# truncates the answer instead (HANDOFF §8 item 9). Sized for both.
_SEARCH_MAX_TOKENS = 3_000

_SOURCE_TOOL = {
    "name": "record_source",
    "description": (
        "Record one page you retrieved through web_search. Call this once per "
        "page that is relevant to the query. The summary must contain only "
        "statements the page itself makes."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The exact URL as it appeared in the search results.",
            },
            "title": {"type": "string", "description": "The page title."},
            "summary": {
                "type": "string",
                "description": (
                    "What this page states about companies, their size, their "
                    "industry, their location, and the tools they use. Copy the "
                    "page's own wording for anything factual. Do not add "
                    "anything you know from elsewhere. If the page states none "
                    "of these things, say so plainly."
                ),
            },
        },
        "required": ["url", "title", "summary"],
        "additionalProperties": False,
    },
}

_SYSTEM = (
    "You retrieve pages and transcribe what they say. You do not analyse, "
    "rank, or recommend.\n\n"
    "Run the search you are given, then call record_source once for each "
    "retrieved page that is relevant, with a summary drawn only from that "
    "page's own content. Never write a fact into a summary that the page does "
    "not state — a summary that says less than you know is correct; a summary "
    "that says more than the page does is a defect. If a search returns "
    "nothing relevant, record nothing and say so."
)


class SearchUnavailableError(RuntimeError):
    """The provider could not run the search at all.

    Distinct from "the search returned nothing", which is an empty list. The
    two must not share a value: a misconfigured API key and a genuinely empty
    result would otherwise both read as "no candidates found", and only one of
    them is a fact about the market.
    """


class SearchAdapter(ABC):
    """One web search provider.

    Implementations accumulate `searches_performed` across their lifetime. That
    counter is not decoration: the Anthropic provider charges per search on top
    of tokens, and no token count expresses it. The fee is carried onto the
    ledger row via `record_llm_call(surcharge_usd=…)`; this counter is the
    independent second path to the same number, which is what makes the two
    checkable against each other. One adapter instance per discovery.
    """

    provider: ClassVar[str] = "abstract"

    def __init__(self) -> None:
        self.searches_performed: int = 0

    @abstractmethod
    async def search(
        self,
        query: str,
        *,
        max_results: int = MAX_SOURCES_PER_QUERY,
        blocked_domains: list[str] | None = None,
    ) -> list[SearchResult]:
        """Retrieve sources for one query.

        Returns an empty list when the query matched nothing. Raises
        `SearchUnavailableError` when the provider could not answer.
        """


class AnthropicWebSearchAdapter(SearchAdapter):
    """The Anthropic Messages API's server-side web search tool."""

    provider: ClassVar[str] = "anthropic_web_search"

    def __init__(
        self,
        client: AsyncAnthropic | None = None,
        model: str | None = None,
        max_searches_per_query: int = MAX_SEARCHES_PER_QUERY,
    ) -> None:
        super().__init__()
        self._client = client or AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = model or settings.llm_fast_model
        self._max_searches = max_searches_per_query

    def _tools(self, blocked_domains: list[str] | None) -> list[dict[str, Any]]:
        web_search: dict[str, Any] = {
            "type": WEB_SEARCH_TOOL_TYPE,
            "name": "web_search",
            "max_uses": self._max_searches,
        }
        if blocked_domains:
            web_search["blocked_domains"] = list(blocked_domains)
        return [web_search, _SOURCE_TOOL]

    async def search(
        self,
        query: str,
        *,
        max_results: int = MAX_SOURCES_PER_QUERY,
        blocked_domains: list[str] | None = None,
    ) -> list[SearchResult]:
        retrieved_at = datetime.now(UTC)
        messages: list[dict[str, Any]] = [{
            "role": "user",
            "content": (
                f"Search the web for: {query}\n\n"
                f"Record at most {max_results} relevant pages."
            ),
        }]

        # URLs the provider actually returned. This set is the trust boundary
        # for everything downstream — a source the model reports that is not in
        # here did not come from a search.
        returned: dict[str, dict[str, Any]] = {}
        recorded: list[dict[str, str]] = []
        tools = self._tools(blocked_domains)

        for turn in range(_MAX_TURNS):
            try:
                response = await self._client.messages.create(
                    model=self._model,
                    max_tokens=_SEARCH_MAX_TOKENS,
                    system=_SYSTEM,
                    messages=messages,
                    tools=tools,
                )
            except APIStatusError as exc:
                # A 400 here is nearly always "this model does not support this
                # tool version" or "web search is disabled for this
                # organization". Both are configuration, both are fixable, and
                # both must surface as a failed discovery rather than as an
                # empty prospect list.
                log.error(
                    "gtm_search_provider_error",
                    provider=self.provider,
                    model=self._model,
                    tool_type=WEB_SEARCH_TOOL_TYPE,
                    status=exc.status_code,
                    detail=str(exc),
                )
                raise SearchUnavailableError(
                    f"web search unavailable on {self._model} "
                    f"({WEB_SEARCH_TOOL_TYPE}): {exc}"
                ) from exc

            self._record_usage(response)
            self._harvest_results(response, returned, query)
            tool_calls = self._harvest_sources(response, recorded)

            stop = response.stop_reason
            if stop == "pause_turn":
                # A long search turn the API paused. Resend the assistant turn
                # unchanged — including every encrypted_content block — and it
                # continues where it left off.
                messages.append({"role": "assistant", "content": response.content})
                continue
            if stop == "tool_use" and tool_calls:
                messages.append({"role": "assistant", "content": response.content})
                messages.append({
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": call_id, "content": "recorded"}
                        for call_id in tool_calls
                    ],
                })
                continue
            if stop == "refusal":
                log.warning(
                    "gtm_search_refused",
                    provider=self.provider,
                    query=query,
                    category=getattr(response.stop_details, "category", None),
                )
            break
        else:
            log.warning(
                "gtm_search_turn_cap_reached",
                provider=self.provider,
                query=query,
                turns=_MAX_TURNS,
                note="results from completed turns are kept; the search was cut short",
            )

        return self._assemble(query, retrieved_at, returned, recorded, max_results)

    # -- response handling --------------------------------------------------

    def _record_usage(self, response: Any) -> None:
        """Token spend *and* the per-search fee to the ledger.

        The searches billed on this response are charged on the same row as the
        tokens they produced, via `record_llm_call(surcharge_usd=…)`. Both are
        read off the same `usage` object, so the fee cannot drift from the call
        that incurred it.

        This matters because `reconcile_run_cost` sums `llm_usage.cost_usd` and
        compares it against the quote. A fee that never reaches the ledger makes
        the stage reconcile as cheaper than it is, and `margin_floor_breached`
        — the one signal that reopens the closed cost model — cannot fire for
        the part that is missing. On a 12-query discovery the fee is ~19% of
        serving cost, which is far too large to leave to a log line.

        Note for anyone re-deriving stage profiles from the ledger: this row's
        `cost_usd` deliberately exceeds what its token counts imply. The
        re-derivation query in HANDOFF §7 reads token medians, not cost, so it
        is unaffected — but a cost-based derivation would over-state this stage.
        """
        usage = getattr(response, "usage", None)
        if usage is None:
            return

        server_tool_use = getattr(usage, "server_tool_use", None)
        performed = getattr(server_tool_use, "web_search_requests", 0) or 0

        try:
            record_llm_call(
                model=self._model,
                input_tokens=getattr(usage, "input_tokens", 0) or 0,
                output_tokens=getattr(usage, "output_tokens", 0) or 0,
                cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
                cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
                surcharge_usd=search_fee_usd(performed),
            )
        except Exception:
            log.exception("gtm_search_usage_hook_failed", model=self._model)

        self.searches_performed += performed

    def _harvest_results(
        self,
        response: Any,
        returned: dict[str, dict[str, Any]],
        query: str,
    ) -> None:
        """Collect the URLs the provider returned, and surface search errors."""
        for block in getattr(response, "content", []) or []:
            if getattr(block, "type", None) != "web_search_tool_result":
                continue
            content = getattr(block, "content", None)

            # On an error the API returns 200 with `content` as a single error
            # object rather than a list. Reading it as a list of results yields
            # zero results and no error — the exact shape of defect this
            # codebase's §2a sweep exists to catch.
            error_code = getattr(content, "error_code", None)
            if error_code is not None:
                log.error(
                    "gtm_search_tool_error",
                    provider=self.provider,
                    query=query,
                    error_code=error_code,
                    note="this query returned no sources because the search failed",
                )
                continue

            for result in content or []:
                url = getattr(result, "url", None)
                if not url:
                    continue
                returned.setdefault(url, {
                    "url": url,
                    "title": getattr(result, "title", "") or "",
                    "page_age": getattr(result, "page_age", None),
                })

    def _harvest_sources(self, response: Any, recorded: list[dict[str, str]]) -> list[str]:
        """Collect `record_source` calls; return their tool_use ids."""
        call_ids: list[str] = []
        for block in getattr(response, "content", []) or []:
            if getattr(block, "type", None) != "tool_use":
                continue
            if getattr(block, "name", None) != "record_source":
                continue
            call_ids.append(block.id)
            payload = block.input or {}
            recorded.append({
                "url": str(payload.get("url", "")),
                "title": str(payload.get("title", "")),
                "summary": str(payload.get("summary", "")),
            })
        return call_ids

    def _assemble(
        self,
        query: str,
        retrieved_at: datetime,
        returned: dict[str, dict[str, Any]],
        recorded: list[dict[str, str]],
        max_results: int,
    ) -> list[SearchResult]:
        """Join digests to the URLs the provider returned, dropping the rest."""
        results: list[SearchResult] = []
        invented: list[str] = []
        seen: set[str] = set()

        for entry in recorded:
            url = entry["url"]
            provider_result = returned.get(url)
            if provider_result is None:
                # The model reported a page the search did not return. That is
                # recall from training data wearing a URL, and it is exactly
                # what this adapter exists to keep out of the candidate list.
                invented.append(url)
                continue
            if url in seen:
                continue
            seen.add(url)
            results.append(SearchResult(
                provider=self.provider,
                query=query,
                url=url,
                title=entry["title"] or provider_result["title"],
                snippet=entry["summary"],
                page_age=provider_result["page_age"],
                retrieved_at=retrieved_at,
            ))
            if len(results) >= max_results:
                break

        if invented:
            log.warning(
                "gtm_search_unreturned_urls_dropped",
                provider=self.provider,
                query=query,
                dropped=len(invented),
                urls=invented[:5],
            )
        log.info(
            "gtm_search_completed",
            provider=self.provider,
            query=query,
            provider_urls=len(returned),
            sources=len(results),
            searches_performed=self.searches_performed,
        )
        return results


async def search_all(
    adapter: SearchAdapter,
    queries: list[str],
    *,
    concurrency: int = 4,
    blocked_domains: list[str] | None = None,
) -> list[list[SearchResult]]:
    """Run several queries with bounded parallelism, preserving order.

    A query that raises comes back as an empty list *after* its exception has
    been logged with the query attached — the caller sees which queries produced
    nothing and why, rather than a short list with no explanation.
    """
    limit = asyncio.Semaphore(max(1, concurrency))

    async def _one(query: str) -> list[SearchResult]:
        async with limit:
            try:
                return await adapter.search(query, blocked_domains=blocked_domains)
            except SearchUnavailableError:
                raise
            except Exception:
                log.exception("gtm_search_query_failed", query=query)
                return []

    return list(await asyncio.gather(*(_one(q) for q in queries)))
