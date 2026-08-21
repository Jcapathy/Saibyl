"""Fill the family-office bank. An editorial pass, run by us, never by a founder.

    python scripts/curate_family_offices.py --sectors healthcare fintech
    python scripts/curate_family_offices.py --dry-run

`family_offices` grants write to nobody, so this runs under the service role:
what enters the bank is a recommendation carrying Saido Labs' name, which makes
admitting a record an editorial act rather than a customer one.

Re-running is safe and is the intended way to grow the bank. Firms already
stored are passed to the verifier as `known_domains`, so a second pass adds
what it found and skips what it already has rather than doubling every row —
a bank that lists a firm twice tells a founder to approach it twice.

Nothing here is charged to anybody. The model spend still lands in the cost
ledger through `record_llm_call`, because curation that is invisible to the
ledger makes the margin on every other artifact fiction.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

# Runnable as `python scripts/curate_family_offices.py` from `backend/`,
# without the caller having to set PYTHONPATH first.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sectors", nargs="*", default=None,
        help="Sectors to search for. Defaults to the module's standing list.",
    )
    parser.add_argument(
        "--limit-queries", type=int, default=None,
        help="Run only the first N queries. Useful for a cheap smoke pass.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Search, propose and verify, but write nothing.",
    )
    parser.add_argument(
        "--env-file", default=None,
        help=(
            "Path to the .env holding the Anthropic and Supabase keys. "
            "Defaults to the nearest one at or above the working directory."
        ),
    )
    return parser.parse_args()


def _load_env(explicit: str | None) -> Path | None:
    """Put the keys in the process environment before settings is imported.

    `config.Settings` looks for `../.env` and `.env` relative to the working
    directory, which finds the repo root from `backend/` in a normal checkout
    and finds nothing from a git worktree. Walking up covers both without
    anybody having to remember which tree they are standing in. Values already
    present in the environment win, so a container's real config is never
    overwritten by a file that happens to be on disk.
    """
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise SystemExit(f"no .env at {path}")
    else:
        path = None
        for parent in [Path.cwd(), *Path.cwd().parents]:
            if (parent / ".env").is_file():
                path = parent / ".env"
                break
        if path is None:
            return None

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
    return path


async def main() -> int:
    args = _parse_args()
    loaded = _load_env(args.env_file)
    print(f"config: {loaded or 'process environment only'}")

    from app.core.database import get_supabase_admin
    from app.services.capital.discovery import (
        CurationUnavailableError,
        curation_queries,
        run_curation,
    )
    from app.services.gtm.search_adapter import AnthropicWebSearchAdapter

    admin = get_supabase_admin()

    # What the bank already holds, so a re-run grows it instead of doubling it.
    existing = (
        admin.table("family_offices").select("domain, source_url, firm_name").execute()
    ).data or []
    known: set[str] = set()
    for row in existing:
        domain = (row.get("domain") or "").strip().lower()
        if domain:
            known.add(domain.removeprefix("www."))
    print(f"bank holds {len(existing)} firm(s); {len(known)} known domain(s)")

    queries = curation_queries(args.sectors)
    if args.limit_queries:
        queries = queries[: args.limit_queries]
    print(f"running {len(queries)} quer{'y' if len(queries) == 1 else 'ies'}")

    now = datetime.now(UTC)
    try:
        outcome = await run_curation(
            adapter=AnthropicWebSearchAdapter(),
            queries=queries,
            now=now,
            known_domains=known,
        )
    except CurationUnavailableError as exc:
        # Deliberately not "found nothing" — a dead provider must not read as
        # an exhausted web on the next pass.
        print(f"FAILED: {exc}", file=sys.stderr)
        return 2

    print(
        f"\nqueries run {outcome.queries_run} · failed {outcome.queries_failed} "
        f"· sources {outcome.sources_seen}"
    )
    print(
        f"names found: {outcome.names_found} → firms verified: "
        f"{len(outcome.firms)}"
    )
    if outcome.names_found and not outcome.firms:
        print(
            "  (every named firm failed the firm's-own-site rule. Many family "
            "offices publish no thesis anywhere — those are firms we decline "
            "to recommend, not firms we failed to find.)"
        )
    if outcome.rejections:
        print("rejections (each one is a gate doing its job):")
        for reason, count in sorted(outcome.rejections.items()):
            print(f"  {reason}: {count}")

    for firm in outcome.firms:
        route = firm.inbound_path.kind
        print(
            f"  · {firm.firm_name} ({firm.firm_type}) — {route} — "
            f"{', '.join(firm.sectors) or 'no stated sector'} — {firm.source_url}"
        )

    if args.dry_run:
        print("\ndry run: nothing written")
        return 0

    if not outcome.firms:
        print("\nnothing new to write")
        return 0

    payload = []
    for firm in outcome.firms:
        row = firm.model_dump(mode="json")
        row.pop("is_stale", None)  # computed, not a column
        payload.append(row)

    written = (admin.table("family_offices").insert(payload).execute()).data or []
    print(f"\nwrote {len(written)} firm(s) to the bank")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
