"""Smoke-test the one assumption the GTM build could not verify offline.

`AnthropicWebSearchAdapter` runs the server-side web search tool on
`settings.llm_fast_model` — Haiku. DECISIONS §14 puts volume work on the fast
model, and the retrieved page content is billed as input to the search turn, so
running it on the main model would multiply the dominant cost line of the whole
feature by five. But the tool-reference documentation defers per-model support
to each tool's own page, which does not enumerate it — so "Haiku supports web
search" was an assumption written into the design, not a fact.

An assumption that is load-bearing and unverified is exactly the class this
codebase keeps getting bitten by, so this script costs about a cent to settle
it: one real search through the real adapter.

It is deliberately NOT a discovery run. It creates no rows, charges no credits,
and touches no ICP. If this fails, the failure is about model support and
nothing else — which is the only reason to run it before spending on a real
discovery.

Usage:  python scripts/smoke_gtm_search.py [--model MODEL]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.config import settings  # noqa: E402
from app.services.gtm.search_adapter import (  # noqa: E402
    MAX_SOURCES_PER_QUERY,
    WEB_SEARCH_TOOL_TYPE,
    AnthropicWebSearchAdapter,
    SearchUnavailableError,
)

QUERY = "B2B SaaS companies using Datadog for observability"


async def run(model: str) -> int:
    adapter = AnthropicWebSearchAdapter(model=model)

    print(f"  model      {model}")
    print(f"  tool       {WEB_SEARCH_TOOL_TYPE}")
    print(f"  query      {QUERY!r}")
    print("  calling …")

    try:
        results = await adapter.search(QUERY, max_results=MAX_SOURCES_PER_QUERY)
    except SearchUnavailableError as exc:
        # The designed failure: loud, naming the model and tool version, rather
        # than an empty list that would read as "the market has nobody in it".
        print(f"\n  REFUSED  {exc}")
        print(
            "\n  This is the failure mode the adapter was built to make legible.\n"
            "  If the cause is model support, point the adapter at the main model\n"
            "  (AnthropicWebSearchAdapter(model=settings.llm_model)) and re-run —\n"
            "  it costs roughly 5x per search turn, so measure before adopting it."
        )
        return 2
    except Exception as exc:  # noqa: BLE001 — a smoke test reports, it does not swallow
        print(f"\n  UNEXPECTED  {type(exc).__name__}: {exc}")
        return 3

    print(f"\n  searches billed   {adapter.searches_performed}")
    print(f"  results returned  {len(results)}")

    if not results:
        # Distinct from a refusal, and worth saying so: the tool ran and the
        # web had nothing, which is a fact about the query rather than the model.
        print(
            "\n  The tool ran and returned nothing. That is a real answer about the\n"
            "  query, not a failure — but it means this run did not exercise the\n"
            "  result-parsing path. Try a broader query before concluding."
        )
        return 1

    for i, r in enumerate(results[:4], 1):
        snippet = (r.snippet or "").replace("\n", " ")
        print(f"\n  [{i}] {r.title[:70]}")
        print(f"      {r.url[:100]}")
        print(f"      {snippet[:160]}{'…' if len(snippet) > 160 else ''}")

    # The snippet is model-written, so it is trusted only as a bound: every
    # evidence quote must later appear verbatim inside one of these. A snippet
    # that is empty would silently make every downstream field unevidenced.
    empty = [r.url for r in results if not (r.snippet or "").strip()]
    if empty:
        print(f"\n  WARNING  {len(empty)} result(s) carry an empty snippet.")
        print("  Extraction requires a verbatim quote inside a snippet, so those")
        print("  sources can never evidence a field — every candidate from them")
        print("  would come back with nothing populated.")

    print("\n  OK — the fast model supports the web search tool and results parsed.")
    return 0


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default=settings.llm_fast_model)
    args = p.parse_args()

    print("\n── GTM web search smoke test ────────────────────────────")
    code = asyncio.run(run(args.model))
    print(
        "\n  Cost: one search (~$0.01) plus the tokens of a single turn.\n"
        "  No rows created, no credits charged."
    )
    sys.exit(code)


if __name__ == "__main__":
    main()
