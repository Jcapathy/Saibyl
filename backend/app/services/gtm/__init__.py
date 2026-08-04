# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# schema          — DiscoveryQuery, SearchResult, Candidate, Contact, evidence
# query_compiler  — compile_queries(profile) -> list[DiscoveryQuery]
# search_adapter  — SearchAdapter.search(query) -> list[SearchResult]
# extraction      — extract_candidates(...) / verify_candidates(...)
# scoring         — score_candidates(candidates, archetype)
# discovery       — run_discovery(...) / preview_queries(...)
# privacy         — contact_discovery_gate(org_id), the reasoning behind it
# pricing         — estimate_discovery_cost / check_discovery_budget
# store           — every read and write, including real deletion
# ─────────────────────────────────────────────────────────
"""Go-to-market candidate discovery: the ICP, pointed at the open web.

The Founder lens synthesizes who a founder's buyers are. This turns that into a
list of companies they could actually sell to, with the source each claim came
from. It is also the only surface in the product that is not episodic — a run
finishes and is read once, where a candidate list is an asset that grows across
sessions and gets revisited — which is why it is the retention surface and why
nothing here may present a guess as a finding.

Four stages, each its own module so each is testable on its own:

    query_compiler   ICP archetypes -> searches, deterministically
    search_adapter   searches -> sources, behind a swappable interface
    extraction       sources -> candidates, with every field evidenced or None
    scoring          candidates -> a ranking, with the arithmetic shown

`privacy.py` is not a utility module. Read its docstring before touching the
contact gate — it is the boundary between Saibyl being a tool and Saibyl being
a controller of personal data.
"""
