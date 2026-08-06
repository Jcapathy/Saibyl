# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# generate_report(simulation_id, config) -> dict
# build_lens_context(sim, analysis) -> str
# get_report_progress(report_id) -> ReportProgress
# clean_report_output(text) -> str
# strip_react_artifacts(text) -> str   (alias for clean_report_output)
# compute_polarization(events) -> dict
# ─────────────────────────────────────────────────────────
from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

import redis
import structlog
from pydantic import BaseModel

from app.core.config import settings
from app.core.database import get_supabase_admin
from app.core.llm_client import llm_complete, llm_structured
from app.services.billing.agent_pricing import report_section_count
from app.services.engine.founder_stages import stage_spec
from app.services.intelligence.analysis_builder import get_analysis
from app.services.intelligence.analysis_data import MeasuredEvent, load_run_data
from app.services.intelligence.react_tools import (
    agent_interview_tool,
    insight_forge,
    panorama_search,
    quick_search,
    simulation_analytics,
)

logger = structlog.get_logger()


# ── Post-processing ─────────────────────────────────────

_PREAMBLE_VERBS = (
    r"gather|start|begin|analyze|look|pull|search|investigate|examine"
    r"|collect|retrieve|check|review|query|explore|write|assess|evaluate"
    r"|compile|synthesize|research|identify|determine|provide"
    r"|systematically"
)


def clean_report_output(text: str) -> str:
    """Sanitise raw LLM text before storage **and** before rendering.

    Applied belt-and-suspenders: once when content is written to the DB,
    and again when it is read for display / export.

    Strips:
      1. Chain-of-thought preamble blocks through ANSWER: marker
      2. Preamble sentences without a following ANSWER:
      3. All standalone TOOL: call lines
      4. All ANSWER: markers at start of any line
      5. CoT artifact lines (Thought:, Reasoning:, Action:, Observation:, etc.)
      6. Collapses resulting multi-blank-line runs
    """
    # 1a. Full preamble-through-ANSWER blocks (dotAll for multiline CoT)
    text = re.sub(
        r"I'll\s+(?:gather|systematically|start by).*?ANSWER:\s*",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # 1b. Broader preamble-through-ANSWER (covers "I will", "Let me", etc.)
    text = re.sub(
        r"(?:I'll|I will|Let me)\s+(?:\w+\s+)*?(?:" + _PREAMBLE_VERBS + r").*?ANSWER:\s*",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # 1c. Preamble sentences NOT followed by ANSWER: (stop at sentence period)
    text = re.sub(
        r"(?:I'll|I will|Let me)\s+(?:\w+\s+)*?(?:" + _PREAMBLE_VERBS + r")\b[^.]*\.\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    # 1d. Broader self-referential preambles ("I have extensive evidence..., but ##")
    text = re.sub(
        r"^(?:I have|I've|Based on|From the|Using the|After)"
        r"(?:\s+\w+){0,5}?\s+"
        r"(?:evidence|data|research|analysis|findings|information|results|rounds?)\b"
        r".*?(?=\n##|\n\n)",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE | re.MULTILINE,
    )
    # 2. All standalone TOOL: call lines
    text = re.sub(r"^TOOL:\s*.*$", "", text, flags=re.MULTILINE)
    # 3. All ANSWER: markers at start of any line (strip marker, keep content after it)
    text = re.sub(r"^ANSWER:\s*", "", text, flags=re.MULTILINE)
    # 4. Chain-of-thought artifact lines (Thought:, Reasoning:, Action:, Observation:, etc.)
    text = re.sub(r"^(?:Thought|Reasoning|Action|Observation):\s.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^(?:Using tool|Calling tool|Tool call|Tool output|Tool result)\b.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^(?:>?\s*)?(?:search_web|read_url|get_page)\b.*$", "", text, flags=re.MULTILINE)
    # 5. Strip wrapping code fences (LLMs sometimes wrap output in ```markdown ... ```)
    text = re.sub(r"^```(?:markdown|md|text)?\s*\n", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\n```\s*$", "", text.strip())
    # 6. Collapse triple+ blank lines to a single blank line
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# Backward-compatible alias — existing imports still work
strip_react_artifacts = clean_report_output


# ── Config & Models ──────────────────────────────────────

DEPTH_PRESETS = {
    "shallow": {"max_tool_calls_per_section": 2, "max_reflection_rounds": 1},
    "standard": {"max_tool_calls_per_section": 5, "max_reflection_rounds": 2},
    "deep": {"max_tool_calls_per_section": 10, "max_reflection_rounds": 3},
    "exhaustive": {"max_tool_calls_per_section": 20, "max_reflection_rounds": 5},
}


class ReACTConfig(BaseModel):
    max_tool_calls_per_section: int = 5
    max_reflection_rounds: int = 2
    temperature: float = 0.5
    evidence_depth: Literal["shallow", "standard", "deep", "exhaustive"] = "standard"
    section_count: int | None = None
    include_agent_interviews: bool = True

    def resolved(self) -> ReACTConfig:
        """Apply depth preset overrides."""
        preset = DEPTH_PRESETS.get(self.evidence_depth, {})
        return self.model_copy(update=preset)

    def evidence_depth_preset(self) -> str:
        """Map the four ReACT depths onto the three pricing depths.

        The ReACT depth controls how hard the agent researches each section;
        the pricing depth controls how many sections there are. They are
        different knobs, but a user who asked for exhaustive research and got a
        two-section report would reasonably feel short-changed, so the deeper
        two ReACT settings also buy a section.
        """
        if self.evidence_depth == "shallow":
            return "brief"
        if self.evidence_depth in ("deep", "exhaustive"):
            return "deep"
        return "standard"


def build_lens_context(sim: dict, analysis: dict | None) -> str:
    """Stage questions and the adversarial disclosure, as prompt text.

    Two things the writer cannot infer from the data and must not be left to
    guess at.

    **The stage's questions.** A pre-launch positioning run and a fundraise run
    produce the same events and want different reports. The questions come from
    `founder_stages`, the same registry the stage picker and the Run Configurator
    read, so the report cannot answer a different question from the one the
    founder was shown when they chose the stage.

    **What the run cannot conclude.** A concept-validation run has no product to
    adopt and therefore no adoption intent to measure; a fundraise run models
    how a story reads, not whether the round closes. Stated as prohibitions
    rather than caveats, because a model given a caveat writes the claim and
    then hedges it.

    **The adversarial disclosure.** PRD §4 requires incumbent-aligned agents to
    be labelled synthetic wherever the run is presented. The sentence is composed
    in the artifact and passed through verbatim so the report, the viewer and
    every export say the same thing.

    Returns an empty string for a run with no lens and no cohort, which is every
    run made before Phase 2 — those reports are unchanged.
    """
    blocks: list[str] = []

    spec = stage_spec(sim.get("founder_stage"))
    if spec is not None:
        questions = "\n".join(f"  - {q}" for q in spec.report_questions)
        limits = "\n".join(f"  - {c}" for c in spec.cannot_conclude)
        blocks.append(
            f"""
FOUNDER LENS — stage: {spec.label}
The founder ran this at the "{spec.label}" stage. The report exists to answer:
{questions}

THIS RUN CANNOT CONCLUDE — do not state or imply any of these, in any section:
{limits}
"""
        )

    disclosure = (analysis or {}).get("adversarial") or {}
    if disclosure.get("enabled"):
        named = disclosure.get("named_competitors") or []
        naming_rule = (
            f"""  - {', '.join(named)} appear in this run only because the founder uploaded
    material naming them. You may report what people said about them. You MUST
    NOT state any fact about their product, pricing, roadmap, or customers —
    the uploaded material grounded the name, not the claims."""
            if named
            else """  - No rival was named in this run. Do not name one. If a section
    needs a comparison, describe the category or what buyers use today."""
        )
        blocks.append(
            f"""
PART OF THIS ROOM WAS BUILT TO ARGUE AGAINST THE FOUNDER
{disclosure.get('disclosure', '')}

RULES — these are disclosure obligations, not style preferences:
  - Wherever you report a figure that mixes both sides of the room, say so. The
    breakdown in the measured analysis separates them; use it.
  - Never present an argument from someone built to oppose switching as
    independent market reaction. It is a constructed position, and saying so is
    what makes the finding usable.
  - An objection that started with the people arguing against the founder AND
    spread to buyers is the most important thing in this report. One that never
    left that group is a rival talking to themselves — say which is which.
{naming_rule}
"""
        )

    blocks.append(_scoreboard_block((analysis or {}).get("scoreboard")))
    return "\n".join(b for b in blocks if b)


def _scoreboard_block(scoreboard: dict | None) -> str:
    """The variant comparison, as prompt text.

    Empty for every single-arena run, which is every Founder- and Crisis-lens run
    and everything made before Phase 3.

    The rule this block exists to enforce is the one the scoreboard itself
    encodes: **when the server declined to name a winner, the report must not
    name one either.** A writer handed six ranked rows and no instruction will
    describe the top one as the winner, because that is what a ranked list reads
    like — and the whole point of computing intervals is that an ordering drawn
    from overlapping bands is not a result. This is Phase 1's bug #5 in the shape
    it would take on a Marketing run: not inventing a number, but inventing a
    conclusion the numbers do not carry.
    """
    if not scoreboard:
        return ""

    variants = scoreboard.get("variants") or []
    if not variants:
        return ""

    lines = []
    for v in variants:
        rate = v.get("objective_rate") or {}
        virality = v.get("virality") or {}
        score = virality.get("score")
        flags = []
        if v.get("viral_but_off_message"):
            flags.append("VIRAL BUT OFF-MESSAGE")
        if v.get("converts_but_wont_travel"):
            flags.append("CONVERTS BUT WON'T TRAVEL")
        lines.append(
            f"  - {v.get('label') or v.get('variant_key')}: "
            f"objective {rate.get('mean', 0):.1%} "
            f"(95% CI {rate.get('lower', 0):.1%}–{rate.get('upper', 0):.1%}, "
            f"n={rate.get('n', 0)} agents), "
            f"virality {'not measured' if score is None else f'{score:.0f}/100'}"
            + (f" — {', '.join(flags)}" if flags else "")
        )

    winner = scoreboard.get("winner_variant_key")
    if winner:
        winner_label = next(
            (
                v.get("label")
                for v in variants
                if v.get("variant_key") == winner and v.get("label")
            ),
            winner,
        )
        ruling = (
            f"A winner IS supported: {winner_label}. Its interval clears the "
            f"runner-up's. You may state it as the leading version."
        )
    else:
        ruling = (
            "NO WINNER IS SUPPORTED. The leading versions' confidence intervals "
            "overlap. You MUST NOT name a winner, describe one version as "
            "'best' or 'the strongest performer', or recommend spending behind "
            "one on the basis of this ordering. Report that the test did not "
            "separate them and say what would — more people, or more rounds."
        )

    return f"""
MESSAGE SCOREBOARD — this run tested {len(variants)} messages against one shared audience
Objective: {scoreboard.get('objective') or 'none set; committing intent used'}
{chr(10).join(lines)}

VERDICT FROM THE MEASUREMENT: {scoreboard.get('verdict', '')}

RULES — these are measurement obligations, not style preferences:
  - {ruling}
  - The ordering above is display order. It is not itself a claim.
  - Virality is a SEPARATE axis from the objective metric. Never blend them into
    one judgement. A version that spreads and does not convert, or converts and
    does not spread, is the finding — not a contradiction to reconcile.
  - Where a virality component reads 'not measured', do not describe it as zero
    or as a weakness of the version. It was not measured.
  - The run's overall sentiment figures pool every version. They describe the
    audience, not any one message. Do not attribute them to a version.
"""


class ReportOutline(BaseModel):
    sections: list[SectionPlan]


class SectionPlan(BaseModel):
    title: str
    research_angles: list[str]


class ReportProgress(BaseModel):
    report_id: str
    status: str
    total_sections: int
    completed_sections: int
    current_section: str | None = None


# ── Prompts ──────────────────────────────────────────────

#: The vocabulary rule, stated once and injected into every prompt.
#:
#: The document's own copy is checked mechanically by
#: `tests/test_report_vocabulary.py`; the narrative sections are written by a
#: model and cannot be. This block is the only lever on them, so it is written
#: as a substitution table rather than as advice — a model told to "avoid
#: jargon" keeps its own, and a model handed the replacement word uses it.
#:
#: Held in one constant because four prompts each carrying their own copy of
#: the rule is the two-sources-of-truth class, and the symptom would be three
#: sections in the founder's words and one in the discipline's.
HOUSE_STYLE = """\
VOCABULARY — the reader is a founder, not a market researcher. These are \
substitutions, not preferences. Every screen of this product uses the right-hand \
column and a report that uses the left-hand one reads as a different product.

  simulation, the swarm        -> the run, the room
  agent, respondent            -> person, buyer, someone
  ICP, segment                 -> audience, the people you sell to
  archetype, persona           -> kind of person, kind of buyer
  cohort                       -> group, or name the group: buyers / the people
                                  arguing against you
  adversarial agents           -> people built to argue against you
  variant, arena, A/B, cell    -> version
  valence                      -> sentiment
  canonical objection          -> the objection

Never write: ICP, variant, A/B, adversarial, cohort, arena, lens, archetype, \
canonical, valence, simulation, persona, project. Write about a product, a run, \
a room of people, and the versions of a message they were shown."""

REPORT_SYSTEM_PROMPT = f"""\
REPORT QUALITY STANDARD:
This report is read by the founder who commissioned the run, and by the investors and \
operators they forward it to. Write with the authority and precision of a McKinsey or \
Bloomberg Intelligence analyst — and in the vocabulary below, which is not negotiable.

{HOUSE_STYLE}

Rules:
1. Lead with insights, not methodology. Every section answers "so what?" before presenting \
supporting data.
2. Never include internal tooling references, chain-of-thought reasoning, TOOL: calls, ANSWER: \
markers, or processing notes in the final output.
3. Use specific numbers — not "sentiment declined" but "sentiment declined 0.59 points from \
-0.05 to -0.64."
4. Bold key findings and inflection points.
5. Each chart or table must be preceded by a one-sentence insight headline explaining what it \
reveals.
6. The executive summary must open with a plain-English situation brief, not data tables.
7. The conclusion must include specific, actionable recommendations with timelines and \
supporting data.
8. PLATFORM FIDELITY: Only reference the platforms this run actually used (listed in the run \
context). NEVER mention, analyze, or recommend actions on a platform that was not part of the \
run. If a platform was not in the run, it does not exist for this report."""

OUTLINE_PROMPT = """You are a predictive intelligence analyst producing a comprehensive, evidence-rich report.

Prediction goal: {prediction_goal}
Platforms in this run (ONLY these — no others exist for this report): {platforms}
People in the room: {agent_count}
Rounds completed: {rounds}
Total events: {event_count}

{house_style}

SECTION TITLES follow the same vocabulary rule as the prose. A title is the first \
thing the founder reads and the most likely place for a discipline word to survive.

{lens_context}
Generate a report outline with {section_count} sections. Each section must have a title and 3-5 research angles (specific questions to investigate with data).

CRITICAL: Every research angle MUST reference ONLY the platforms listed above. \
Do NOT mention, hypothesize about, or reference any platform not in that list.

REQUIRED: Every report must include sections covering:
- Sentiment over time (round-by-round arc, turning points, how split the room became)
- Platform-specific dynamics (how each platform in the run shaped the conversation differently)
- Who reacted how (group the people by behaviour and by what they came in believing)
- Key trigger events and moments that spread (what caused sentiment to move)
- What this predicts (what the trajectories suggest going forward)

Each research angle should be specific enough to require multiple tool calls. Prefer quantitative angles (sentiment scores, engagement metrics, platform comparisons) over vague qualitative ones.

Return JSON: {{"sections": [{{"title": str, "research_angles": [str]}}]}}"""

REACT_PROMPT = """You are a ReACT (Reasoning-Action-Observation) intelligence analyst writing section "{section_title}" of a comprehensive predictive intelligence report.

Prediction goal: {prediction_goal}
Platforms in this run (ONLY these): {platforms}
Research angles for this section: {research_angles}

{house_style}

{lens_context}
You have access to these tools (call by name). The tool names are internal — call \
them by these names, and never name one in the text you write:
1. insight_forge(query) — Deep semantic search of knowledge graph for entities, relationships, facts
2. quick_search(query) — Fast keyword search for specific facts and data points
3. simulation_analytics(type) — Analyze the run's data. Types: measured_findings, sentiment_over_time, platform_comparison, persona_breakdown, top_posts, viral_moments, agent_activity
4. agent_interview(prompt) — Interview people from the run in-character about what they made of it

Evidence gathered so far:
{evidence}

Instructions:
- If you need more evidence, respond with: TOOL: <tool_name>(<args>)
- If you have enough evidence, respond with: ANSWER: <section content in markdown>
- Use MULTIPLE different tools before writing your answer — do not answer after just 1-2 tool calls
- Call simulation_analytics with DIFFERENT types to get varied data dimensions
- Use agent_interview to get quotes in people's own words
- Use insight_forge or quick_search for contextual knowledge beyond this run's data

MEASUREMENT RULES — these are not style guidance:
- Every sentiment, stance, intensity, or objection figure you state MUST come
  from simulation_analytics. Do not estimate one from reading post text, and do
  not carry a number over from a previous section from memory.
- Sentiment figures arrive with a confidence interval. Quote it. "-0.42
  (95% CI -0.61 to -0.23, 47 people)" is the format. A bare mean overstates what
  a constructed room can support.
- If two groups' intervals overlap, say the difference is not resolved. Do not
  rank them.
- If a tool reports that no analysis artifact exists, write that the run has no
  measured sentiment. Do not substitute your own reading of the posts.

QUALITY REQUIREMENTS for your ANSWER:
- Lead with the key insight — answer "so what?" in the first sentence before presenting data
- Include specific numbers: sentiment scores, engagement counts, round-by-round metrics
- Build markdown tables for platform comparisons, breakdowns by kind of person, or timeline data
- Precede EVERY markdown table with a **bold one-sentence insight headline** explaining what the \
table reveals (e.g., "**Reddit drove the sharpest negative shift, hitting -0.62 by Round 4.**")
- Bold key findings and turning points throughout
- Identify 3-4 distinct kinds of person when describing how the room behaved, and name each one \
in words a founder would recognise ("the finance buyer", "the engineer who has to migrate")
- Describe trajectory arcs with specific turning points (e.g., "Round 3 saw a -0.25 drop")
- Include cross-cutting dynamics: what spread, what wore out, who changed their mind
- End with what this predicts: what do the patterns forecast if trends continue?
- Write 800-1500 words per section — comprehensive analysis, not summaries
- Use direct quotes from the people in the run as supporting evidence

Be analytical and data-driven. Synthesize across multiple data sources. Do NOT produce thin, surface-level summaries.

IMPORTANT: Only discuss the platforms listed above. Do NOT reference any other platforms."""

EXECUTIVE_SUMMARY_PROMPT = """\
╔══════════════════════════════════════════════════════════════════╗
║  CRITICAL STRUCTURE CONSTRAINT — READ BEFORE WRITING ANYTHING  ║
╠══════════════════════════════════════════════════════════════════╣
║  Your output will be REJECTED and regenerated if it does not   ║
║  begin with Part A (Situation Brief) as the FIRST text.        ║
║                                                                ║
║  FORBIDDEN as opening content:                                 ║
║  ✗ Data tables          ✗ Round-by-round analysis              ║
║  ✗ Methodology notes    ✗ Metric definitions                   ║
║  ✗ Statistical summaries ✗ "This report analyzes..."           ║
║                                                                ║
║  MANDATORY order: A → B → C → D → E. No exceptions.           ║
╚══════════════════════════════════════════════════════════════════╝

Write the Executive Summary for this predictive intelligence report.
The FIRST paragraph the reader sees must be the Situation Brief — plain English, no numbers.
Then Key Findings. Then Bottom Line. Then Stat Cards. Then evidence tables LAST.

{house_style}

=== RUN CONTEXT ===
Prediction goal: {prediction_goal}
Platforms: {platforms}
People in the room: {agent_count}
Rounds completed: {rounds}
Total events: {event_count}
{polarization_context}

=== REPORT SECTIONS (your evidence base) ===
{sections_text}

=== REMINDER: Begin your output with Part A (Situation Brief), NOT with data. ===

=== MANDATORY OUTPUT STRUCTURE — Follow Parts A through E in EXACT order ===

### Part A: Situation Brief
THE FIRST THING YOU WRITE. 2-3 sentences MAX in plain English.
Summarise what was put in front of whom, and why it matters.
No jargon. No metrics. No numbers. Someone who has never seen Saibyl should understand \
the scenario in 10 seconds.
Example: "Saibyl put Tallyhook's launch page in front of 120 freelancers and agency owners \
who chase late invoices, and let them argue about it across Reddit and Hacker News over five \
rounds. The question was whether they would pay for it, and what they would say against it."

### Part B: Key Findings
Write 3-5 numbered bullet points. Each is ONE sentence with ONE supporting number.
These are the "so what" takeaways — the headline insights a decision-maker needs.
Format each as: **Bold headline claim.** Supporting sentence with a specific metric.
Example:
1. **The objection is the client relationship, not the price.** Sentiment fell from -0.05 to \
-0.64 across five rounds, and the drop tracked the "this will damage my client relationships" \
thread rather than any pricing thread.
2. **Buyers split on who sends the message.** The people who would let software chase a client \
shrank from 35% to 21% once the tone of the automated reminder was shown.
3. **Reddit is where the argument happens.** Sentiment hit -0.62 on Reddit against -0.11 on \
Hacker News — a 0.51 gap between the two.

### Part C: Bottom Line
Write 1-2 sentences in **bold markdown**. State the single most important strategic implication.
What should the reader DO with this information? This is a recommendation, not a summary.
Example: **"Lead with the founder sending the reminder, not the software. Every version where \
the tool spoke for the freelancer lost the room on tone, and the two where the freelancer \
stayed the sender did not."**

### Part D: Stat Cards
Output exactly this markdown table with values filled from your analysis:

| Metric | Value | Label |
|--------|-------|-------|
| Sentiment | <overall sentiment score, signed decimal e.g. -0.42> | <Strongly Positive/Positive/Mixed/Negative/Strongly Negative> |
| Engagement | <engagement score X.X / 10> | <High virality potential OR Moderate reach> |
{polarization_row}| Platforms | <count of platforms> | <comma-separated platform names> |
| Sentiment Trajectory | <directional summary e.g. "Topic A: -0.59 ↓ / Topic B: +0.40 ↑"> | <Net shift description> |

{polarization_guidance}

IMPORTANT for Sentiment Trajectory: Show the directional arrow and net change for the main \
subjects in the run. Use ↑ for positive movement, ↓ for negative, → for flat.

### Part E: Round-by-Round Evidence
NOW and ONLY now, provide the supporting data tables:
1. A round-by-round sentiment progression table (columns: Round, Overall Sentiment, Key Shift, \
Notable Event)
2. Brief narrative of how split the room became — which kinds of person moved, when, and why
3. Any platform-specific divergences worth highlighting

This section is SUPPORTING EVIDENCE for the Key Findings above, not the opening content.
Keep it concise — 1-2 pages maximum. The reader has already gotten the headline from Parts A-C."""

# `AB_COMPARISON_PROMPT` and `_WinnerResult` were here. The prompt asked a
# model to name a winner from two blobs of aggregate metrics and return a
# confidence float it had no basis to compute - the schema had no way to say
# "these are indistinguishable". That is the failure the variant scoreboard
# was built to make impossible.


CONCLUSION_PROMPT = """You are a senior go-to-market strategist writing the concluding section \
of a predictive intelligence report for the founder who commissioned it. Be direct. Be specific. \
Every recommendation must cite what this run measured. Do not hedge excessively. The client is \
paying for decisive intelligence, not academic caution.

{house_style}

=== RUN CONTEXT ===
Prediction goal: {prediction_goal}
Platforms (ONLY these were in the run): {platforms}
People in the room: {agent_count}
Rounds completed: {rounds}
Total events: {event_count}
{polarization_context}

=== REPORT SECTIONS (your evidence base) ===
{sections_text}

=== MANDATORY OUTPUT STRUCTURE ===

Write the section titled "Strategic Implications & Recommended Actions" using EXACTLY the \
sub-sections below. Do NOT add preamble, methodology notes, or throat-clearing. Start writing \
the first sub-section immediately.

CRITICAL: All recommendations MUST target ONLY these platforms: {platforms}. \
Do NOT recommend actions on a platform that was not part of the run.

FORMATTING RULES:
- Bold key findings and inflection points throughout.
- Use specific numbers (e.g., "declined 0.59 points from -0.05 to -0.64"), never vague language.
- If you include any table, precede it with a **bold one-sentence insight headline**.

### 5.1 — Situation Assessment

Write 2-3 sentences restating the core finding in strategic terms.
NOT "sentiment declined" — instead: "the narrative environment is structurally \
favorable/unfavorable for [subject] because..."
Frame the situation as an opportunity or threat that demands specific action.

### 5.2 — Recommended Actions

Write 3-5 numbered recommendations. Each MUST follow this exact format:

**[Action Verb]: [Specific recommendation naming a platform from this run, who it is aimed at, and a timeframe]**
- **Evidence:** [Cite the specific finding — who changed their mind, the sentiment gap between two platforms, what one kind of buyer did that the others did not]
- **Timeline:** [When to execute — must be within 7-14 days]
- **Expected Impact:** [What this run predicts will happen if this action is taken]

Requirements for each recommendation:
- Be SPECIFIC: name the platform, name who it is aimed at in words a founder would use \
(e.g., "the freelancers who bill under $5k a month", "the finance buyer"), and the timeframe
- Be GROUNDED: cite the exact metric that supports it (sentiment score, percentage shift, \
how many people carried an objection)
- Be ACTIONABLE within 7-14 days — no vague "build a long-term strategy" recommendations
- Prioritise recommendations by expected impact (highest-impact first)

### 5.3 — Risks & Watch Items

Write 2-3 items identifying what could change the trajectory. For each:
- Name the specific risk or scenario
- Cite the evidence from this run that suggests the risk is plausible (e.g., a kind of buyer \
who kept changing their mind, a platform where sentiment swung rather than settled)
- State what the reader should monitor and what trigger would indicate the risk is materialising

### 5.4 — Confidence Assessment

State the overall confidence level: **High**, **Medium**, or **Low**.

Then justify it based on these three factors (one sentence each):
1. **How many people:** {agent_count} — state whether this is enough to stand behind \
(>30 = adequate, >50 = strong, <20 = limited)
2. **Did the room agree:** Did the different kinds of buyer end up in similar positions \
(high confidence) or stay split and keep swinging (lower confidence)? Cite the evidence.
3. **Pattern consistency:** Did trajectories sustain directionally (high confidence) or oscillate \
unpredictably (lower confidence)? Cite the evidence.

End with ONE sentence on the single biggest uncertainty in the findings."""


#: Every prompt that reaches the writer, so the block below can prove each one
#: carries the vocabulary rule. A new prompt added outside this tuple is a
#: prompt `test_report_vocabulary` cannot see.
WRITER_PROMPTS = (
    ("OUTLINE_PROMPT", OUTLINE_PROMPT),
    ("REACT_PROMPT", REACT_PROMPT),
    ("EXECUTIVE_SUMMARY_PROMPT", EXECUTIVE_SUMMARY_PROMPT),
    ("CONCLUSION_PROMPT", CONCLUSION_PROMPT),
)


def _prompt(template: str, **fields: object) -> str:
    """Fill a prompt, always with the house style in it.

    Every user message in this file goes through here rather than calling
    `.format()` directly, so the vocabulary block cannot be forgotten at one of
    five call sites.

    The placeholder is checked rather than merely supplied. `str.format` accepts
    keyword arguments a template never uses, so passing `house_style=` to a
    prompt with no slot for it succeeds silently and produces a prompt with no
    rule in it — which is the same shape as the defect this whole change exists
    to fix: a guarantee that looks enforced and is not.
    """
    if "{house_style}" not in template:
        raise KeyError(
            "house_style: this prompt reaches the report writer and must carry "
            "the vocabulary rule. Add {house_style} to the template."
        )
    return template.format(house_style=HOUSE_STYLE, **fields)


# ── Polarization ─────────────────────────────────────────

_POLARIZATION_ABSENT: dict[str, float | str | None] = {
    "controversy_score": None,
    "polarization_ratio": None,
    "valence_switching_pct": None,
}


def compute_polarization(events: list[MeasuredEvent]) -> dict:
    """Polarization metrics from measured event valence.

    Reads `valence` rather than the metadata "sentiment" key this used to
    average. That key was written by the drift formula removed in Phase 1 —
    `sentiment_baseline * (1 + round/max_rounds * 1.5)` — so on a measured run
    it is absent and on an older one it is the archetype preset, meaning the
    ratio described the persona pack rather than the conversation.

    Reactions carry no text and are stored with a null valence; off-topic events
    hold no view of the subject. Both are excluded rather than counted as 0.0,
    because a like is not a moderate opinion and would inflate the moderate
    denominator on every run.

    Every metric is None when nothing was measured, so a caller cannot render an
    unmeasured run as an unpolarized one.
    """
    scored = [e for e in events if e.scored]
    if not scored:
        return dict(_POLARIZATION_ABSENT)

    max_round = max(e.round_number for e in scored)

    # Per-agent mean valence at the final round. Averaged rather than
    # last-event-wins: an agent that posted twice in the last round holds one
    # position, and taking whichever row happened to sort last made the ratio
    # depend on read order.
    final_round: dict[str, list[float]] = {}
    for event in scored:
        if event.round_number == max_round:
            key = event.agent_id or event.agent_username
            final_round.setdefault(key, []).append(float(event.valence))

    agent_means = [sum(vals) / len(vals) for vals in final_round.values()]
    if not agent_means:
        return dict(_POLARIZATION_ABSENT)

    # Extreme-to-moderate ratio: |valence| > 0.5 vs |valence| <= 0.5
    extreme = sum(1 for v in agent_means if abs(v) > 0.5)
    moderate = max(sum(1 for v in agent_means if abs(v) <= 0.5), 1)
    ratio = round(extreme / moderate, 1)

    # Valence switching: how often an agent's position crosses the zero line
    # between consecutive rounds. Computed within an agent, because the previous
    # version compared consecutive rows of an arbitrarily ordered event list —
    # counting one agent's opinion against a different agent's as a "switch",
    # and returning a different number depending on how the rows came back.
    by_agent_round: dict[str, dict[int, list[float]]] = {}
    for event in scored:
        key = event.agent_id or event.agent_username
        by_agent_round.setdefault(key, {}).setdefault(
            event.round_number, []
        ).append(float(event.valence))

    pairs = 0
    switches = 0
    for rounds in by_agent_round.values():
        arc = [
            sum(vals) / len(vals)
            for _round, vals in sorted(rounds.items())
        ]
        for i in range(1, len(arc)):
            pairs += 1
            if (arc[i] > 0) != (arc[i - 1] > 0):
                switches += 1

    # An agent that spoke in only one round has no transition to switch across.
    # That is an absent measurement, not zero switching.
    switching_pct = round(switches / pairs * 100) if pairs else None

    return {
        # Normalized to 0-1; a ratio of 5:1 or above saturates at 1.0.
        "controversy_score": round(min(1.0, ratio / 5.0), 2),
        "polarization_ratio": f"{ratio}:1",
        "valence_switching_pct": switching_pct,
    }


def _polarization_prompt_fields(metrics: dict) -> dict[str, str]:
    """Render polarization metrics as prompt fragments, omitting the unmeasured.

    An unmeasured metric is left out of the prompt rather than passed through as
    "N/A". Part D of the executive summary mandates a filled stat card, so a
    writer handed "N/A" for a row it is required to complete supplies the
    missing figure itself — a fabricated number in published copy, which is
    exactly what the measurement layer exists to prevent.
    """
    ratio = metrics.get("polarization_ratio")
    controversy = metrics.get("controversy_score")

    if ratio is None:
        return {
            "polarization_row": "",
            "polarization_guidance": (
                "IMPORTANT for Polarization Ratio: this run has NO measured "
                "polarization ratio, which is why the table above has no such "
                "row. Do not add one, do not estimate a ratio, and do not "
                "characterise the audience as polarized or unified anywhere in "
                "Part D."
            ),
            "polarization_context": (
                "Polarization: not measured for this run — state no "
                "polarization ratio and no controversy score, and do not "
                "describe the room as divided or united on the strength of a "
                "figure you were not given."
            ),
        }

    return {
        "polarization_row": (
            f"| Polarization Ratio | {ratio} | <Low/Moderate/High — description> |\n"
        ),
        "polarization_guidance": (
            f'IMPORTANT for Polarization Ratio: Use the provided value "{ratio}". '
            "Label it as:\n"
            "- Low (< 1.5:1): minimal polarization\n"
            "- Moderate (1.5:1 - 3:1): notable division\n"
            "- High (> 3:1): significant polarization"
        ),
        "polarization_context": (
            f"Polarization ratio (extreme-to-moderate): {ratio}\n"
            + (
                f"Controversy score (0-1): {controversy}"
                if controversy is not None
                else "Controversy score: not measured — do not state one."
            )
        ),
    }


# ── Core functions ───────────────────────────────────────

def _get_redis() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


def _publish_progress(r: redis.Redis, report_id: str, payload: dict) -> None:
    """Emit a live progress event, and never fail the report if it can't.

    Progress publishing is a side channel for the UI. It was previously an
    unguarded `r.publish(...)` inside the section generator, so an unreachable
    Redis raised ConnectionError out of `asyncio.gather` and killed report
    generation outright — every section left `pending`, the report marked
    `failed`, and an Opus-priced run's whole narrative lost to a notification
    that nobody was listening to. The report is the product; the progress bar
    is not.
    """
    try:
        r.publish(f"report:{report_id}:progress", json.dumps(payload))
    except Exception:
        logger.warning("report_progress_publish_failed", report_id=report_id)


async def _run_react_loop(
    section: SectionPlan,
    simulation_id: str,
    prediction_goal: str,
    graph_id: str | None,
    config: ReACTConfig,
    variant: str = "a",
    platforms: str = "",
    lens_context: str = "",
) -> str:
    """Run the ReACT loop for a single report section.

    The measured findings are seeded into evidence before the loop starts, so
    every section begins from the analysis artifact whether or not the model
    chooses to ask for it.

    Without this the loop can emit `ANSWER:` on its first turn against
    `evidence = "None yet."` and write the whole section from the prediction
    goal — an LLM opinion wearing a report's formatting, which is the exact
    thing this phase exists to remove. "Use MULTIPLE different tools" in the
    prompt is advice; a model under a token budget will decline it.

    Seeding is also strictly cheaper than letting the model ask: it costs one
    read of a row we already built, instead of an Opus turn spent deciding to
    request it.
    """
    resolved = config.resolved()

    seed = await simulation_analytics(UUID(simulation_id), "measured_findings", variant=variant)
    evidence: list[str] = [
        f"[Measured analysis — the only source of numbers for this report]\n"
        f"{seed.summary}\n{json.dumps(seed.data, default=str)[:6000]}"
    ]

    for tool_call_num in range(resolved.max_tool_calls_per_section):
        prompt = _prompt(
            REACT_PROMPT,
            section_title=section.title,
            prediction_goal=prediction_goal,
            platforms=platforms,
            research_angles=", ".join(section.research_angles),
            lens_context=lens_context,
            evidence="\n".join(evidence) if evidence else "None yet.",
        )

        response = await llm_complete(
            messages=[
                {"role": "system", "content": REPORT_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=config.temperature,
        )

        if response.strip().startswith("ANSWER:"):
            return strip_react_artifacts(response.split("ANSWER:", 1)[1].strip())

        if response.strip().startswith("TOOL:"):
            tool_line = response.split("TOOL:", 1)[1].strip()
            observation = await _execute_tool(
                tool_line, simulation_id, graph_id, variant, config
            )
            evidence.append(f"[Tool: {tool_line}]\n{observation}")
        else:
            # LLM didn't follow format — treat as final answer
            return strip_react_artifacts(response.strip())

    # Max tool calls reached — force answer
    final_prompt = _prompt(
        REACT_PROMPT,
        section_title=section.title,
        prediction_goal=prediction_goal,
        platforms=platforms,
        research_angles=", ".join(section.research_angles),
        lens_context=lens_context,
        evidence="\n".join(evidence),
    ) + "\n\nYou have used all available tool calls. You MUST now provide your ANSWER. Synthesize ALL evidence gathered into a comprehensive, data-rich section (800-1500 words) with specific metrics, tables, a breakdown of who reacted how, and what it predicts:"

    result = await llm_complete(
        messages=[
            {"role": "system", "content": REPORT_SYSTEM_PROMPT},
            {"role": "user", "content": final_prompt},
        ],
        temperature=config.temperature,
    )
    if "ANSWER:" in result:
        return strip_react_artifacts(result.split("ANSWER:", 1)[1].strip())
    return strip_react_artifacts(result.strip())


async def _execute_tool(
    tool_line: str,
    simulation_id: str,
    graph_id: str | None,
    variant: str,
    config: ReACTConfig,
) -> str:
    """Parse and execute a tool call, return observation string."""
    tool_line = tool_line.strip()

    try:
        if tool_line.startswith("insight_forge"):
            query = _extract_arg(tool_line)
            if graph_id:
                result = await insight_forge(graph_id, query)
                return f"Found {result.total_results} entities. Facts: {'; '.join(result.facts[:10])}"
            return "No knowledge graph available."

        elif tool_line.startswith("quick_search"):
            query = _extract_arg(tool_line)
            if graph_id:
                results = await quick_search(graph_id, query)
                return "\n".join(f"- {r.name}: {r.summary}" for r in results[:5])
            return "No knowledge graph available."

        elif tool_line.startswith("simulation_analytics"):
            atype = _extract_arg(tool_line)
            result = await simulation_analytics(
                UUID(simulation_id), atype, variant=variant
            )
            return f"{result.summary}\nData: {json.dumps(result.data, default=str)[:5000]}"

        elif tool_line.startswith("agent_interview"):
            prompt = _extract_arg(tool_line)
            if config.include_agent_interviews:
                responses = await agent_interview_tool(
                    UUID(simulation_id), prompt, sample_size=5, variant=variant
                )
                return "\n".join(
                    f"- {r.agent_username} ({r.persona_type}, sentiment: {r.sentiment_score:.2f}): {r.response[:500]}"
                    for r in responses
                )
            return "Agent interviews disabled in config."

        elif tool_line.startswith("panorama_search"):
            if graph_id:
                result = await panorama_search(graph_id)
                return f"Graph overview: {result.node_count} nodes, {result.edge_count} edges"
            return "No knowledge graph available."

        else:
            return f"Unknown tool: {tool_line}"

    except Exception as e:
        logger.warning("tool_execution_error", tool=tool_line, error=str(e))
        return f"Tool error: {e}"


def _extract_arg(tool_call: str) -> str:
    """Extract the argument from a tool call like tool_name(arg)."""
    if "(" in tool_call and ")" in tool_call:
        return tool_call.split("(", 1)[1].rsplit(")", 1)[0].strip().strip("\"'")
    return tool_call.split(None, 1)[1] if " " in tool_call else ""


async def generate_report(
    simulation_id: UUID,
    config: ReACTConfig | None = None,
) -> dict:
    """Generate a full intelligence report from simulation results."""
    if config is None:
        config = ReACTConfig()

    admin = get_supabase_admin()
    r = _get_redis()
    sim_id = str(simulation_id)

    # Load simulation
    sim = admin.table("simulations").select("*").eq("id", sim_id).single().execute().data
    org_id = sim["organization_id"]

    # Get event count
    events = admin.table("simulation_events").select(
        "id", count="exact"
    ).eq("simulation_id", sim_id).execute()
    event_count = events.count or 0

    # Get agent count
    agents = admin.table("simulation_agents").select(
        "id", count="exact"
    ).eq("simulation_id", sim_id).execute()
    agent_count = agents.count or 0

    # Get knowledge graph ID
    kg = admin.table("knowledge_graphs").select("id").eq(
        "project_id", sim["project_id"]
    ).eq("build_status", "complete").limit(1).execute().data
    graph_id = kg[0]["id"] if kg else None

    # Report depth scales with run size in both directions. The old formula,
    # min(7, max(4, event_count // 30 + 2)), had a floor of 4 — so a 25-agent
    # free-trial run generated 6 Opus-written sections, $1.07 of that run's
    # $1.27 total cost, on a run whose entire purpose is to be nearly free.
    section_count = config.section_count or report_section_count(
        event_count, config.evidence_depth_preset()
    )
    report = admin.table("reports").insert({
        "simulation_id": sim_id,
        "organization_id": org_id,
        "title": f"Intelligence Report: {sim['name']}",
        "status": "generating",
        "variant": "a",
        "react_config": config.model_dump(),
        "section_count": section_count,
    }).execute().data[0]
    report_id = report["id"]

    try:
        # Phase 1: Planning
        #
        # The lens context is built once and reused for the outline and every
        # section. Rebuilding it per section would be one artifact read per
        # section for a string that cannot change mid-report.
        stored = get_analysis(sim_id) or {}
        lens_context = build_lens_context(sim, stored.get("artifact"))

        outline_prompt = _prompt(
            OUTLINE_PROMPT,
            prediction_goal=sim["prediction_goal"],
            platforms=", ".join(sim.get("platforms") or ["twitter_x"]),
            agent_count=agent_count,
            rounds=sim.get("max_rounds", 10),
            event_count=event_count,
            section_count=section_count,
            lens_context=lens_context,
        )
        outline = await llm_structured(
            messages=[{"role": "user", "content": outline_prompt}],
            schema=ReportOutline,
        )

        # Create section skeletons
        for i, section in enumerate(outline.sections):
            admin.table("report_sections").insert({
                "report_id": report_id,
                "organization_id": org_id,
                "section_index": i,
                "title": section.title,
                "status": "pending",
            }).execute()

        # Phase 2: Generate sections in parallel
        platforms = ", ".join(sim.get("platforms") or ["twitter_x"])

        async def generate_section(idx: int, section: SectionPlan):
            _publish_progress(r, report_id, {
                "section_index": idx, "status": "generating", "title": section.title,
            })

            content = await _run_react_loop(
                section, sim_id, sim["prediction_goal"], graph_id, config,
                platforms=platforms, lens_context=lens_context,
            )
            content = clean_report_output(content)  # sanitise before DB write

            admin.table("report_sections").update({
                "content": content,
                "status": "complete",
            }).eq("report_id", report_id).eq("section_index", idx).execute()

            _publish_progress(r, report_id, {
                "section_index": idx, "status": "complete", "title": section.title,
            })
            return content

        tasks = [generate_section(i, s) for i, s in enumerate(outline.sections)]
        section_contents = await asyncio.gather(*tasks)

        # Phase 3: Assembly
        sections_text = "\n\n---\n\n".join(
            f"## {s.title}\n\n{c}" for s, c in zip(outline.sections, section_contents)
        )

        # Polarization for the conclusion and executive-summary prompts, from
        # measured valence. `load_run_data` pages past PostgREST's 1,000-row
        # cap; the previous `.limit(2000)` silently truncated any run larger
        # than that and reported the ratio of its first thousand events.
        pol_metrics = compute_polarization(load_run_data(sim_id).events)
        if pol_metrics["polarization_ratio"] is None:
            logger.warning("report_polarization_unmeasured", simulation_id=sim_id)
        polarization_fields = _polarization_prompt_fields(pol_metrics)

        rounds = sim.get("max_rounds", 10)

        # Phase 3b: Generate conclusion — Strategic Implications & Recommended Actions
        conclusion_idx = len(outline.sections)
        conclusion_title = "Strategic Implications & Recommended Actions"

        _publish_progress(r, report_id, {
            "section_index": conclusion_idx, "status": "generating",
            "title": conclusion_title,
        })

        admin.table("report_sections").insert({
            "report_id": report_id,
            "organization_id": org_id,
            "section_index": conclusion_idx,
            "title": conclusion_title,
            "status": "pending",
        }).execute()

        conclusion_raw = await llm_complete(
            messages=[
                {"role": "system", "content": REPORT_SYSTEM_PROMPT},
                {"role": "user", "content": _prompt(
                CONCLUSION_PROMPT,
                prediction_goal=sim["prediction_goal"],
                platforms=platforms,
                agent_count=agent_count,
                rounds=rounds,
                event_count=event_count,
                sections_text=sections_text[:20000],
                **polarization_fields,
            )}],
        )
        conclusion_content = clean_report_output(conclusion_raw)

        admin.table("report_sections").update({
            "content": conclusion_content,
            "status": "complete",
        }).eq("report_id", report_id).eq("section_index", conclusion_idx).execute()

        _publish_progress(r, report_id, {
            "section_index": conclusion_idx, "status": "complete",
            "title": conclusion_title,
        })

        # Append conclusion to sections text so exec summary can reference it
        sections_text += f"\n\n---\n\n## {conclusion_title}\n\n{conclusion_content}"

        # Update section_count to include conclusion
        admin.table("reports").update({
            "section_count": conclusion_idx + 1,
        }).eq("id", report_id).execute()

        # Phase 4: Executive Summary (generated last — sees all sections + conclusion)
        exec_summary_raw = await llm_complete(
            messages=[
                {"role": "system", "content": REPORT_SYSTEM_PROMPT},
                {"role": "user", "content": _prompt(
                EXECUTIVE_SUMMARY_PROMPT,
                prediction_goal=sim["prediction_goal"],
                platforms=platforms,
                agent_count=agent_count,
                rounds=rounds,
                event_count=event_count,
                sections_text=sections_text[:20000],
                **polarization_fields,
            )}],
        )
        exec_summary = clean_report_output(exec_summary_raw)

        # Store exec summary as a section so the frontend can find it
        admin.table("report_sections").insert({
            "report_id": report_id,
            "organization_id": org_id,
            "section_index": -1,  # sorts before all ReACT sections
            "title": "Executive Summary",
            "content": exec_summary,
            "status": "complete",
        }).execute()

        full_markdown = f"# {sim['name']} — Intelligence Report\n\n## Executive Summary\n\n{exec_summary}\n\n{sections_text}"
        full_markdown = clean_report_output(full_markdown)  # sanitise before DB write

        admin.table("reports").update({
            "status": "complete",
            "markdown_content": full_markdown,
            "completed_at": datetime.now(UTC).isoformat(),
        }).eq("id", report_id).execute()

        logger.info("report_generated", report_id=report_id, sections=len(outline.sections))
        return admin.table("reports").select("*").eq("id", report_id).single().execute().data

    except Exception as e:
        admin.table("reports").update({
            "status": "failed",
        }).eq("id", report_id).execute()
        logger.error("report_generation_failed", report_id=report_id, error=str(e))
        raise


# `generate_ab_comparison_report` was here. It asked a model to pick a winner
# between two variants from raw aggregates, with no confidence interval and no
# way to answer "neither" - on an engine that only ever ran variant A. The
# N-way scoreboard replaces it, and what it adds is the refusal: a winner is
# named only when the intervals separate.


def get_report_progress(report_id: UUID) -> ReportProgress:
    """Get live report generation progress."""
    admin = get_supabase_admin()
    report = admin.table("reports").select(
        "status, section_count"
    ).eq("id", str(report_id)).single().execute().data

    sections = admin.table("report_sections").select(
        "status, title"
    ).eq("report_id", str(report_id)).order("section_index").execute().data

    completed = sum(1 for s in sections if s["status"] == "complete")
    current = next((s["title"] for s in sections if s["status"] != "complete"), None)

    return ReportProgress(
        report_id=str(report_id),
        status=report["status"],
        total_sections=report.get("section_count", 0),
        completed_sections=completed,
        current_section=current,
    )
