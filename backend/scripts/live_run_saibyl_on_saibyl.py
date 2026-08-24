#!/usr/bin/env python
"""Saibyl, put through Saibyl.

    cd backend && python scripts/live_run_saibyl_on_saibyl.py --dry-run   # price only
    cd backend && python scripts/live_run_saibyl_on_saibyl.py             # spends money

The product's own pitch, in front of the buyers it claims to be able to build:
founders shipping software with AI tools, a week before launch. It runs the
Founder lens at `pre_launch_positioning`, which is exactly where Saibyl itself
is standing.

**Why this is worth spending money on the day before a launch.** Every other
live run so far has been a fixture — Tallyhook, Chartwell, Fernway — products
invented to exercise the pipeline. None of them could tell us whether the
*pitch* survives contact with the people it is aimed at, because nobody on the
team believes in Tallyhook. This one we do believe in, which makes the objections
readable as feedback rather than as output.

The material is the real material, not a description of it:

  · the idea brief is Saibyl's five answers, written the way the guided form
    (`POST /documents/idea-brief`) composes them;
  · the website document is the live landing page's own copy, lifted from
    `frontend/src/pages/LandingPage.tsx` — the words a stranger actually reads
    at https://saibyl-frontend.onrender.com.

Both go through `store_upload`, the same ingestion path a founder's file takes,
so extraction, the subject brief and audience synthesis all consume them exactly
as they would for a customer. Nothing here is a shortcut around the product.

**The incumbent cohort is switched on, at 25%.** Saibyl's real competition is
not another tool — it is "just post it on Reddit and see", "ask ten founders",
and "launch it and find out". A room with none of those voices in it would
return a flattering answer, and a flattering answer is the one thing this run
cannot be allowed to produce. PRD §4 permits that cohort only when it is
grounded in uploaded material; the brief names those alternatives, which is what
grounds it.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from io import BytesIO
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Quote signing falls back to an empty key in development (HANDOFF §8 item 11).
# Set before anything imports settings.
os.environ.setdefault("SECRET_KEY", "saibyl-on-saibyl-" + "x" * 32)

from fastapi import UploadFile  # noqa: E402

from app.core.database import get_supabase_admin  # noqa: E402
from app.services.billing.agent_pricing import estimate_simulation_cost  # noqa: E402

# The sample org the recent Founder-lens runs used. Its credits are test
# credits; no customer org is touched by this script.
ORG_ID = "26d46806-eba9-409b-be7c-465320014c29"      # "Saibyl Samples"
CREATED_BY = "5c0ac604-425d-4595-ac3e-21c0577d6777"

# Matches the six Founder-lens runs of 21–23 August, so this one is readable
# beside them rather than being a different experiment as well as a different
# subject.
AGENTS = 25
ROUNDS = 3
PLATFORMS = ["reddit", "twitter_x"]
FOUNDER_STAGE = "pre_launch_positioning"
ADVERSARIAL_SHARE = 0.25

PREDICTION_GOAL = (
    "Will founders who build with AI pay $99 a month to test their product on a "
    "room of synthetic buyers before they launch?"
)

# ── Run two ────────────────────────────────────────────────────────────────
# Same room, same shape, two things changed — so the difference between the
# runs is attributable rather than merely observed.
#
# **The material.** Run one described Saibyl as one thing: a room of synthetic
# buyers. Run one's answer was that the room is not the hard part — four real
# buyers said they had already built one with Claude and a spreadsheet, and the
# thing that broke was everything *after* the room. So run two is given the
# pitch deck written against exactly that objection, uploaded as a PDF through
# the same path a founder's deck takes.
#
# **The question.** Reframed from a single-purpose tool to the suite: the five
# stages, named. A founder is not being asked to pay $99 for a room; they are
# being asked to pay it for validation, positioning, go-to-market, growth and
# capital — which is what the product actually is, and what run one's pitch
# never said out loud.
RUN_TWO_GOAL = (
    "Will founders who build with AI pay $99 per month for a full suite of "
    "tools that gives them synthetic feedback on their idea and product "
    "validation, their product positioning, their go-to-market, how to grow "
    "their product sales, and who they can go to for capital?"
)

DECK_PATH = Path(
    r"C:\Users\jcapa\OneDrive\Personal\Saido Labs LLC\Saibyl"
    r"\sample-run-review\Saibyl\02-pitch-deck.pdf"
)


# ── Run three ──────────────────────────────────────────────────────────────
# The v2 deck, and two more places to be read in.
#
# **The deck.** Run two's report recommended leading with the two claims that
# were believed *and* discussed on both platforms — synthetic feedback and
# positioning — and demoting the other three. `04-pitch-deck-v2.pdf` does that:
# the two claims are slides 4–6, capital is slide 10.
#
# **The platforms.** LinkedIn and Hacker News join Reddit and Twitter/X. Run
# two's single most useful finding was platform divergence — Reddit at 46.2%
# support against Twitter/X's 86.1%, with intervals that did not overlap — so
# more places is the highest-value axis to widen.
#
# **And the room grows with them.** 25 buyers over four platforms is ~6 each,
# which cannot support a per-platform interval worth reading: the thing this run
# exists to measure would come back as four shrugs. 48 keeps ~12 per platform,
# the same per-platform density run two had at 25 over two. Costing more is the
# point of the change, not a side effect of it.
RUN_THREE_PLATFORMS = ["reddit", "twitter_x", "linkedin", "hacker_news"]
RUN_THREE_AGENTS = 48

DECK_V2_PATH = Path(
    r"C:\Users\jcapa\OneDrive\Personal\Saido Labs LLC\Saibyl"
    r"\sample-run-review\Saibyl\04-pitch-deck-v2.pdf"
)


class RunSpec(NamedTuple):
    """One run: what it is about, what it reads, and what it is asked."""

    key: str
    product: str
    blurb: str
    goal: str
    audience_name: str

    @property
    def platforms(self) -> list[str]:
        return RUN_THREE_PLATFORMS if self.key == "three" else PLATFORMS

    @property
    def agents(self) -> int:
        return RUN_THREE_AGENTS if self.key == "three" else AGENTS

    def materials(self) -> list[tuple[str, str | bytes, str, str | None]]:
        """`(filename, body, material_kind, source_url)` for each upload."""
        if self.key == "one":
            return [
                ("idea-brief.md", IDEA_BRIEF, "idea_brief", None),
                ("website.md", WEBSITE_COPY, "own",
                 "https://saibyl-frontend.onrender.com"),
            ]
        # Runs two and three read a deck itself — a PDF, through the same
        # extraction path a founder's uploaded deck takes. Feeding the markdown
        # source instead would test a document nobody will ever send us.
        deck = DECK_V2_PATH if self.key == "three" else DECK_PATH
        if not deck.exists():
            raise SystemExit(f"Pitch deck not found at {deck}")
        return [(deck.name, deck.read_bytes(), "own", None)]


RUNS = {
    "one": RunSpec(
        key="one",
        product="Saibyl",
        blurb="Test your startup on a synthetic market.",
        goal=PREDICTION_GOAL,
        audience_name="Founders who build with AI",
    ),
    "two": RunSpec(
        key="two",
        product="Saibyl — the suite",
        blurb="Five stages: validate, position, launch, grow, raise.",
        goal=RUN_TWO_GOAL,
        audience_name="Founders who build with AI (suite framing)",
    ),
    "three": RunSpec(
        key="three",
        product="Saibyl — two claims",
        blurb="Synthetic feedback, and proof your positioning fix worked.",
        goal=RUN_TWO_GOAL,
        audience_name="Founders who build with AI (four places)",
    ),
}

# ── The material ───────────────────────────────────────────────────────────
# Saibyl's five answers, in the order and shape `_compose_idea_brief` writes
# them. Written to be true rather than to be flattering: the honest version is
# the only one whose objections are worth reading.

IDEA_BRIEF = """# Saibyl — test your startup on a synthetic market

## The problem
Founders building with AI can ship a product in a weekend and still have no
idea whether anyone wants it. Finding out is slow, expensive and biased: the
people who reply are the people who already like you, cold outreach gets
ignored, and by the time silence has told you the truth you have spent the
runway. The feedback that would have changed the product arrives after the
product is built.

## Who has it
Founders building software with AI tools — mostly solo or two-person teams,
pre-launch or a few weeks past it. They have a working product, a landing page
and a pitch they have rewritten five times, and no customers yet. They are
technical enough to ship daily and have never run a customer interview.

## The solution
Saibyl builds a room of synthetic buyers out of your own material — your deck,
your landing page, or five answers — and puts your pitch in front of them. They
argue about it in written threads, with each other, and you get back what they
pushed back on, ranked by how much of the room carried each objection, with the
sentences behind every number. Then Saibyl drafts a reply to the objections
worth answering, runs the same room again, and shows you whether the reply moved
anything or not. Five stages: validate the idea, position it, launch the
message, grow on evidence, raise with answers.

## What they use today
Posting on X or Reddit and reading the replies. Cold DMs to people who look like
customers. Asking other founders in a Slack group. Paying for a focus group,
which costs thousands and takes weeks. Or launching and interpreting the
silence.

## Rough price
One full run free, no card required — 25 buyers over the first two stages.
After that, plans from $99 a month, which buy a bigger room, more rounds, more
places at once, and more versions of the message head to head. A standard run is
100 buyers over 5 rounds, and every run shows its exact price before it starts.
"""

# The live landing page's own words. Lifted from `LandingPage.tsx` rather than
# paraphrased — if the room objects to a sentence, it is a sentence a stranger
# really reads.
WEBSITE_COPY = """# Saibyl — saibyl-frontend.onrender.com

Test your startup on a synthetic market.

One full run free · No card · Your files never train models

## How far the room scales
Every number Saibyl reports opens into the sentences it came from. The room
argues in written threads — nothing is ever posted anywhere real.
1,000 AI buyers in the largest rooms. 25 in your first free run.

## The platform that grows with you
Validate — IDEA STAGE. Does the pain exist, who feels it most, and what would
they pay? Five answers are enough to build your first room.

Position — PRE-LAUNCH. Which objections kill the pitch — and which answers
actually move them. Test the fix on the same room, and watch the delta.

Launch — GO-TO-MARKET. Up to eight versions of the message, head to head, in
front of the same room — the winner earns your budget.

Grow — TRACTION. Pricing moves, feature drops, expansion pitches — rehearsed
before the market grades them.

Raise — FUNDRAISE. How the story reads to investors — and the questions you'll
be asked, before you're in the room that matters.

## A full run you can inspect
We built a sample product — Tallyhook, invoice chasing for freelancers — and put
it through a full run, so you can inspect real output before you upload a word.
The room returned 26 objections. Only one was about price.

## What each run answers
The free run answers the first two questions. Each one after that turns the last
answer into the next advantage.

In your free run — Audience: who reacts to this? Built from your material, not
picked from a list. You approve it before anything runs.

In your free run — Reactions: what do they object to? The room argues with your
pitch — and with each other. The pushback arrives ranked, with receipts.

Unlocks with any plan, from $99/mo — Answers: did my reply work? Saibyl drafts a
reply to each objection worth answering, runs the same room again, and shows
whether it moved.

Unlocks with any plan, from $99/mo — Buyers: which real companies match? The
audience you approved becomes a list of real companies that fit it — each with
the source shown.

## Pricing
Start free. Scale on evidence. A plan buys a bigger room, more rounds, more
places, and more versions head to head. A standard run is 100 buyers over 5
rounds — and every run shows its exact price before it starts.
"""


def price(spec: RunSpec) -> None:
    """What this costs to serve, before anything is created."""
    est = estimate_simulation_cost(
        agent_count=spec.agents,
        rounds=ROUNDS,
        platforms=len(spec.platforms),
        variants=1,
        depth="standard",
    )
    print("\n── What this run costs ─────────────────────────────")
    print(f"  shape       {spec.agents} buyers / {ROUNDS} rounds / "
          f"{len(spec.platforms)} places — {', '.join(spec.platforms)}")
    print(f"  stage       {FOUNDER_STAGE} · {int(ADVERSARIAL_SHARE * 100)}% incumbent-aligned")
    print(f"  COGS        ${est.actual_cost_usd:.2f}")
    print(f"  credits     {est.credits:,}")
    for stage, cost in est.breakdown.items():
        print(f"    {stage:<28} ${cost:.3f}")
    admin = get_supabase_admin()
    org = (
        admin.table("organizations")
        .select("name, credits_balance")
        .eq("id", ORG_ID)
        .execute()
    ).data[0]
    print(f"\n  org         {org['name']} · {org['credits_balance']:,} credits before")
    print()


async def _wait_for_extraction(project_id: str, timeout_s: int = 120) -> None:
    """Block until every upload has been read, or say which one did not.

    `store_upload` **queues** extraction — it returns a row with
    `processing_status='pending'` and an `asyncio` task does the work. Calling
    `synthesize_icp` straight afterwards raced that task and hit "No processed
    documents in this project", which is the API's own error and correct: the
    guard fired before the synthesis model was paid for, which is the right
    direction to fail in.

    The UI polls the same column for the same reason. A script that does not is
    a script that only worked because extraction happened to be fast.
    """
    admin = get_supabase_admin()
    for _ in range(timeout_s):
        rows = (
            admin.table("documents")
            .select("filename, processing_status, extracted_char_count")
            .eq("project_id", project_id)
            .execute()
        ).data or []
        pending = [r for r in rows if r["processing_status"] in ("pending", "processing")]
        if not pending:
            for r in rows:
                print(f"  read        {r['filename']} · "
                      f"{r['processing_status']} · {r['extracted_char_count']} chars")
            failed = [r for r in rows if r["processing_status"] != "complete"]
            if failed:
                raise SystemExit(
                    "Extraction failed for: "
                    + ", ".join(r["filename"] for r in failed)
                )
            return
        await asyncio.sleep(1)
    raise SystemExit("Extraction did not finish within two minutes.")


async def build(spec: RunSpec) -> tuple[str, dict]:
    """Create the product and ingest its material. Returns (project_id, icp)."""
    # `store_upload` lives on the documents router rather than in a service —
    # it is the one intake path both upload routes share, and calling it here
    # is what makes this ingestion and not a row insert that resembles it.
    from app.api.documents import store_upload

    admin = get_supabase_admin()

    # Reuse a product of this name that already has its material.
    #
    # Run one raced extraction and died after the uploads had landed, leaving a
    # product with two documents in it. Creating a second would re-upload the
    # same bytes, bill the org's storage twice, and leave two identically-named
    # products in a founder-facing list.
    existing = (
        admin.table("projects")
        .select("id")
        .eq("organization_id", ORG_ID)
        .eq("name", spec.product)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    ).data
    if existing:
        pid = existing[0]["id"]
        print(f"  product     {pid} (reusing)")
        await _wait_for_extraction(pid)
        return pid, await _audience(pid, spec)

    project = (
        admin.table("projects")
        .insert({
            "name": spec.product,
            "description": spec.blurb,
            "organization_id": ORG_ID,
            "created_by": CREATED_BY,
        })
        .execute()
    ).data[0]
    pid = project["id"]
    print(f"  product     {pid}")

    for filename, body, kind, source in spec.materials():
        raw = body if isinstance(body, bytes) else body.encode("utf-8")
        upload = UploadFile(file=BytesIO(raw), size=len(raw), filename=filename)
        stored = await store_upload(
            project_id=pid,
            org_id=ORG_ID,
            file=upload,
            material_kind=kind,
            source_url=source,
        )
        print(f"  material    {filename} · {len(raw):,} bytes · "
              f"{stored.get('processing_status')}")

    await _wait_for_extraction(pid)
    return pid, await _audience(pid, spec)


async def _audience(pid: str, spec: RunSpec) -> dict:
    """Work out who buys this, from the material just ingested."""
    from app.services.engine.personas.icp_synthesizer import synthesize_icp

    print("\n── Working out who buys this ───────────────────────")
    icp = await synthesize_icp(
        pid,
        ORG_ID,
        adversarial=True,
        platforms=spec.platforms,
        adversarial_share=ADVERSARIAL_SHARE,
        created_by=CREATED_BY,
        name=spec.audience_name,
    )
    profile = icp.get("profile") or {}
    buyers = [a.get("name") for a in profile.get("archetypes", [])]
    against = [a.get("name") for a in profile.get("adversarial", [])]
    print(f"  audience    {icp['id']}")
    print(f"  buyers      {', '.join(b for b in buyers if b)}")
    if against:
        print(f"  sceptics    {', '.join(a for a in against if a)}")
    return icp


def create(pid: str, icp: dict, spec: RunSpec) -> str:
    """Create the run itself. Returns the simulation id."""
    admin = get_supabase_admin()
    sim = (
        admin.table("simulations")
        .insert({
            "name": spec.product,
            "prediction_goal": spec.goal,
            "project_id": pid,
            "organization_id": ORG_ID,
            "platforms": spec.platforms,
            "max_rounds": ROUNDS,
            "agent_count": spec.agents,
            "persona_pack_ids": [icp["pack_id"]],
            "icp_profile_id": icp["id"],
            "adversarial_share": ADVERSARIAL_SHARE,
            "variants": 1,
            "depth": "standard",
            "lens": "founder",
            "founder_stage": FOUNDER_STAGE,
            "status": "draft",
            "created_by": CREATED_BY,
        })
        .execute()
    ).data[0]
    print(f"\n  run         {sim['id']}")
    return sim["id"]


async def execute(sim_id: str) -> None:
    from app.workers.simulation_tasks import run_prepare_agents, run_simulation

    print("\n── Building the room ───────────────────────────────")
    await run_prepare_agents(sim_id)

    print("\n── Putting the pitch in front of it ────────────────")
    result = await run_simulation(sim_id)
    print(f"  status {result.get('status')} · events {result.get('total_events')}")


def read_back(sim_id: str) -> int:
    """What the room actually said. Returns an exit code."""
    admin = get_supabase_admin()
    art = (
        admin.table("simulation_analysis")
        .select("artifact")
        .eq("simulation_id", sim_id)
        .execute()
    ).data
    if not art:
        print("\n  No analysis artifact. The run finished without one.")
        return 1

    a = art[0]["artifact"] or {}
    headline = a.get("headline") or {}
    stance = headline.get("stance") or {}
    quality = a.get("quality") or {}

    print("\n── What they said ──────────────────────────────────")
    print(f"  room        {quality.get('agents_total')} buyers · "
          f"{quality.get('rounds')} rounds · {quality.get('events_total')} things said")
    for caveat in quality.get("caveats") or []:
        print(f"  caveat      {caveat}")
    val = headline.get("valence") or {}
    if val.get("n"):
        print(f"  felt        {val.get('mean'):+.2f} "
              f"(between {val.get('lower'):+.2f} and {val.get('upper'):+.2f}, "
              f"n={val.get('n')})")
    if stance:
        print(f"  for/against {stance.get('support_pct', 0):.0f}% for · "
              f"{stance.get('oppose_pct', 0):.0f}% against · "
              f"{stance.get('undecided_pct', 0):.0f}% undecided")

    # Ranked by `load_bearing_score`, which is the artifact's own ordering —
    # how much of the room carried the objection, weighted by how hard. The
    # first version of this reader invented `reach_pct` and
    # `representative_quote`, neither of which the artifact has, so it printed a
    # dash for every number and no quote at all. Reading a field that does not
    # exist is the same defect the frontend had on `analysis.scoreboard`.
    objections = sorted(
        a.get("objections") or [],
        key=lambda o: o.get("load_bearing_score") or 0,
        reverse=True,
    )
    print("\n  What they pushed back on, hardest first:")
    for obj in objections[:10]:
        buyers = obj.get("buyer_agent_count") or 0
        sceptics = obj.get("adversarial_agent_count") or 0
        who = f"{buyers} buyer{'s' if buyers != 1 else ''}"
        if sceptics:
            who += f" + {sceptics} built to argue"
        print(f"    · {obj.get('label')}  ({who})")
        quotes = obj.get("quotes") or []
        text = (quotes[0].get("text") if quotes else "") or ""
        if text.strip():
            print(f'        "{text.strip()[:200]}"')
    return 0


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="price it and stop")
    p.add_argument("--read", metavar="SIM_ID", help="re-read a finished run")
    p.add_argument("--run", choices=("one", "two", "three"), default="one",
                   help="one = the original pitch; two = the deck and the suite question")
    args = p.parse_args()

    if args.read:
        raise SystemExit(read_back(args.read))

    spec = RUNS[args.run]
    print(f"\n  run         {spec.key} — {spec.product}")
    print(f"  asking      {spec.goal}")
    price(spec)
    if args.dry_run:
        print("  --dry-run: nothing created, nothing spent.\n")
        return

    print("── Creating the product ────────────────────────────")
    pid, icp = asyncio.run(build(spec))
    sim_id = create(pid, icp, spec)
    asyncio.run(execute(sim_id))
    raise SystemExit(read_back(sim_id))


if __name__ == "__main__":
    main()
