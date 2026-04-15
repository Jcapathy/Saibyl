# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# generate_report(simulation_id, config) -> dict
# generate_ab_comparison_report(simulation_id, config) -> dict
# get_report_progress(report_id) -> ReportProgress
# clean_report_output(text) -> str
# strip_react_artifacts(text) -> str   (alias for clean_report_output)
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
    ab_comparison: bool = False

    def resolved(self) -> ReACTConfig:
        """Apply depth preset overrides."""
        preset = DEPTH_PRESETS.get(self.evidence_depth, {})
        return self.model_copy(update=preset)


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

REPORT_SYSTEM_PROMPT = """\
REPORT QUALITY STANDARD:
This report will be read by C-suite executives, board members, and senior political strategists. \
Write with the authority and precision of a McKinsey or Bloomberg Intelligence analyst.

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
supporting data."""

OUTLINE_PROMPT = """You are a predictive intelligence analyst producing a comprehensive, evidence-rich report.

Prediction goal: {prediction_goal}
Platforms simulated: {platforms}
Agent count: {agent_count}
Rounds completed: {rounds}
Total events: {event_count}

Generate a report outline with {section_count} sections. Each section must have a title and 3-5 research angles (specific questions to investigate with data).

REQUIRED: Every report must include sections covering:
- Sentiment trajectories over time (round-by-round arc, inflection points, polarization)
- Platform-specific dynamics (how each platform shaped discourse differently)
- Agent/persona archetype analysis (cluster agents by behavior patterns, emotional signatures)
- Key trigger events and viral moments (what caused sentiment spikes/shifts)
- Predictive implications and forecast (what the trajectories suggest going forward)

Each research angle should be specific enough to require multiple tool calls. Prefer quantitative angles (sentiment scores, engagement metrics, platform comparisons) over vague qualitative ones.

Return JSON: {{"sections": [{{"title": str, "research_angles": [str]}}]}}"""

REACT_PROMPT = """You are a ReACT (Reasoning-Action-Observation) intelligence analyst writing section "{section_title}" of a comprehensive predictive intelligence report.

Prediction goal: {prediction_goal}
Research angles for this section: {research_angles}

You have access to these tools (call by name):
1. insight_forge(query) — Deep semantic search of knowledge graph for entities, relationships, facts
2. quick_search(query) — Fast keyword search for specific facts and data points
3. simulation_analytics(type) — Analyze simulation data. Types: top_posts, sentiment_over_time, viral_moments, agent_activity, platform_comparison, persona_breakdown
4. agent_interview(prompt) — Interview simulation agents in-character about their experiences and reactions

Evidence gathered so far:
{evidence}

Instructions:
- If you need more evidence, respond with: TOOL: <tool_name>(<args>)
- If you have enough evidence, respond with: ANSWER: <section content in markdown>
- Use MULTIPLE different tools before writing your answer — do not answer after just 1-2 tool calls
- Call simulation_analytics with DIFFERENT types to get varied data dimensions
- Use agent_interview to get qualitative quotes and persona-specific reactions
- Use insight_forge or quick_search for contextual knowledge beyond the simulation data

QUALITY REQUIREMENTS for your ANSWER:
- Lead with the key insight — answer "so what?" in the first sentence before presenting data
- Include specific numbers: sentiment scores, engagement counts, round-by-round metrics
- Build markdown tables for platform comparisons, agent archetype breakdowns, or timeline data
- Precede EVERY markdown table with a **bold one-sentence insight headline** explaining what the \
table reveals (e.g., "**Twitter/X drove the sharpest negative shift, hitting -0.62 by Round 4.**")
- Bold key findings and inflection points throughout
- Identify 3-4 distinct clusters/archetypes when analyzing agent behavior
- Describe trajectory arcs with specific inflection points (e.g., "Round 3 saw a -0.25 drop")
- Include cross-cutting dynamics: contagion effects, narrative fatigue, archetype migration
- End with predictive implications: what do the patterns forecast if trends continue?
- Write 800-1500 words per section — comprehensive analysis, not summaries
- Use direct quotes from agent interviews as supporting evidence

Be analytical and data-driven. Synthesize across multiple data sources. Do NOT produce thin, surface-level summaries."""

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

=== SIMULATION CONTEXT ===
Prediction goal: {prediction_goal}
Platforms: {platforms}
Agent count: {agent_count}
Rounds completed: {rounds}
Total events: {event_count}
Polarization ratio (extreme-to-moderate): {polarization_ratio}
Polarization controversy score (0-1): {controversy_score}

=== REPORT SECTIONS (your evidence base) ===
{sections_text}

=== REMINDER: Begin your output with Part A (Situation Brief), NOT with data. ===

=== MANDATORY OUTPUT STRUCTURE — Follow Parts A through E in EXACT order ===

### Part A: Situation Brief
THE FIRST THING YOU WRITE. 2-3 sentences MAX in plain English.
Summarise what was simulated, for whom, and why it matters.
No jargon. No metrics. No numbers. A CEO who has never seen Saibyl should understand \
the scenario in 10 seconds.
Example: "Saibyl simulated public reaction to a hypothetical LA Times investigative piece \
attacking Spencer Pratt's mayoral candidacy. 40 synthetic agents across 4 platforms debated \
the narrative over 5 rounds, modeling how voters, media, and political operatives would \
respond if this story broke."

### Part B: Key Findings
Write 3-5 numbered bullet points. Each is ONE sentence with ONE supporting number.
These are the "so what" takeaways — the headline insights a decision-maker needs.
Format each as: **Bold headline claim.** Supporting sentence with a specific metric.
Example:
1. **The attack backfires on Bass.** Public sentiment toward Bass declined from -0.05 to \
-0.64 across five rounds with no recovery.
2. **The moderate middle is collapsing.** Conflicted Moderates shrank from 35% to 21%, \
with the majority migrating toward anti-Bass positions.
3. **Twitter/X is the narrative battleground.** Sentiment hit -0.62 on Twitter/X vs. -0.11 \
on LinkedIn — a 0.51 cross-platform divergence gap.

### Part C: Bottom Line
Write 1-2 sentences in **bold markdown**. State the single most important strategic implication.
What should the reader DO with this information? This is a recommendation, not a summary.
Example: **"Spencer Pratt should amplify the attack narrative rather than defend against it. \
The simulation shows every attack on Pratt drives sympathy toward him and permanently erodes \
Bass's position."**

### Part D: Stat Cards
Output exactly this markdown table with values filled from your analysis:

| Metric | Value | Label |
|--------|-------|-------|
| Sentiment | <overall sentiment score, signed decimal e.g. -0.42> | <Strongly Positive/Positive/Mixed/Negative/Strongly Negative> |
| Engagement | <engagement score X.X / 10> | <High virality potential OR Moderate reach> |
| Polarization Ratio | {polarization_ratio} | <Low/Moderate/High — description> |
| Platforms | <count of platforms> | <comma-separated platform names> |
| Sentiment Trajectory | <directional summary e.g. "Topic A: -0.59 ↓ / Topic B: +0.40 ↑"> | <Net shift description> |

IMPORTANT for Polarization Ratio: Use the provided value "{polarization_ratio}". Label it as:
- Low (< 1.5:1): minimal polarization
- Moderate (1.5:1 - 3:1): notable division
- High (> 3:1): significant polarization

IMPORTANT for Sentiment Trajectory: Show the directional arrow and net change for the primary \
subjects/topics in the simulation. Use ↑ for positive movement, ↓ for negative, → for flat.

### Part E: Round-by-Round Evidence
NOW and ONLY now, provide the supporting data tables:
1. A round-by-round sentiment progression table (columns: Round, Overall Sentiment, Key Shift, \
Notable Event)
2. Brief narrative of the polarization dynamics — which archetypes moved, when, and why
3. Any platform-specific divergences worth highlighting

This section is SUPPORTING EVIDENCE for the Key Findings above, not the opening content.
Keep it concise — 1-2 pages maximum. The reader has already gotten the headline from Parts A-C."""

AB_COMPARISON_PROMPT = """Compare the two simulation variants and determine a winner.

Prediction goal: {prediction_goal}

Variant A metrics: {variant_a_data}
Variant B metrics: {variant_b_data}

Provide:
1. Key differences between variants
2. Which variant better achieved the prediction goal
3. Confidence in the determination
4. Specific evidence supporting the conclusion

Return JSON: {{"winner": "a" or "b", "confidence": float 0-1, "reasoning": str, "key_differences": [str]}}"""


class _WinnerResult(BaseModel):
    winner: str
    confidence: float
    reasoning: str
    key_differences: list[str]


CONCLUSION_PROMPT = """You are a senior political/crisis strategist writing the concluding section \
of a predictive intelligence report for a C-suite audience. Be direct. Be specific. Every \
recommendation must cite simulation data. Do not hedge excessively. The client is paying for \
decisive intelligence, not academic caution.

=== SIMULATION CONTEXT ===
Prediction goal: {prediction_goal}
Platforms: {platforms}
Agent count: {agent_count}
Rounds completed: {rounds}
Total events: {event_count}
Polarization ratio (extreme-to-moderate): {polarization_ratio}
Controversy score (0-1): {controversy_score}

=== REPORT SECTIONS (your evidence base) ===
{sections_text}

=== MANDATORY OUTPUT STRUCTURE ===

Write the section titled "Strategic Implications & Recommended Actions" using EXACTLY the \
sub-sections below. Do NOT add preamble, methodology notes, or throat-clearing. Start writing \
the first sub-section immediately.

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

**[Action Verb]: [Specific recommendation naming the platform, audience segment, and timeframe]**
- **Evidence:** [Cite the specific simulation finding — cluster migration, platform sentiment delta, archetype behavior shift]
- **Timeline:** [When to execute — must be within 7-14 days]
- **Expected Impact:** [What the simulation data predicts will happen if this action is taken]

Requirements for each recommendation:
- Be SPECIFIC: name the platform (Twitter/X, Instagram, LinkedIn, etc.), the audience segment \
(e.g., "Conflicted Moderates", "Media Watchdogs"), and the timeframe
- Be GROUNDED: cite the exact metric that supports it (sentiment score, percentage shift, \
archetype migration rate)
- Be ACTIONABLE within 7-14 days — no vague "build a long-term strategy" recommendations
- Prioritise recommendations by expected impact (highest-impact first)

### 5.3 — Risks & Watch Items

Write 2-3 items identifying what could change the trajectory. For each:
- Name the specific risk or scenario
- Cite the simulation evidence that suggests this risk is plausible (e.g., an archetype that \
showed instability, a platform where sentiment oscillated rather than converged)
- State what the reader should monitor and what trigger would indicate the risk is materialising

### 5.4 — Confidence Assessment

State the overall confidence level: **High**, **Medium**, or **Low**.

Then justify it based on these three factors (one sentence each):
1. **Agent count:** {agent_count} agents — state whether this provides adequate statistical \
representation (>30 = adequate, >50 = strong, <20 = limited)
2. **Sentiment convergence:** Did archetypes converge toward similar positions (high confidence) \
or remain split/oscillating (lower confidence)? Cite the evidence.
3. **Pattern consistency:** Did trajectories sustain directionally (high confidence) or oscillate \
unpredictably (lower confidence)? Cite the evidence.

End with ONE sentence on the single biggest uncertainty in the findings."""


# ── Core functions ───────────────────────────────────────

def _get_redis() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


async def _run_react_loop(
    section: SectionPlan,
    simulation_id: str,
    prediction_goal: str,
    graph_id: str | None,
    config: ReACTConfig,
    variant: str = "a",
) -> str:
    """Run the ReACT loop for a single report section."""
    evidence: list[str] = []
    resolved = config.resolved()

    for tool_call_num in range(resolved.max_tool_calls_per_section):
        prompt = REACT_PROMPT.format(
            section_title=section.title,
            prediction_goal=prediction_goal,
            research_angles=", ".join(section.research_angles),
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
    final_prompt = REACT_PROMPT.format(
        section_title=section.title,
        prediction_goal=prediction_goal,
        research_angles=", ".join(section.research_angles),
        evidence="\n".join(evidence),
    ) + "\n\nYou have used all available tool calls. You MUST now provide your ANSWER. Synthesize ALL evidence gathered into a comprehensive, data-rich section (800-1500 words) with specific metrics, tables, archetype analysis, and predictive implications:"

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

    # Create report record
    section_count = config.section_count or min(7, max(4, event_count // 30 + 2))
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
        outline_prompt = OUTLINE_PROMPT.format(
            prediction_goal=sim["prediction_goal"],
            platforms=", ".join(sim.get("platforms") or ["twitter_x"]),
            agent_count=agent_count,
            rounds=sim.get("max_rounds", 10),
            event_count=event_count,
            section_count=section_count,
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
        async def generate_section(idx: int, section: SectionPlan):
            r.publish(f"report:{report_id}:progress", json.dumps({
                "section_index": idx, "status": "generating", "title": section.title,
            }))

            content = await _run_react_loop(
                section, sim_id, sim["prediction_goal"], graph_id, config
            )
            content = clean_report_output(content)  # sanitise before DB write

            admin.table("report_sections").update({
                "content": content,
                "status": "complete",
            }).eq("report_id", report_id).eq("section_index", idx).execute()

            r.publish(f"report:{report_id}:progress", json.dumps({
                "section_index": idx, "status": "complete", "title": section.title,
            }))
            return content

        tasks = [generate_section(i, s) for i, s in enumerate(outline.sections)]
        section_contents = await asyncio.gather(*tasks)

        # Phase 3: Assembly
        sections_text = "\n\n---\n\n".join(
            f"## {s.title}\n\n{c}" for s, c in zip(outline.sections, section_contents)
        )

        # Compute polarization metrics for executive summary prompt
        from app.api.reports import _compute_polarization
        all_events = admin.table("simulation_events").select(
            "metadata, round_number, agent_id"
        ).eq("simulation_id", sim_id).limit(2000).execute().data or []
        pol_metrics = _compute_polarization(all_events)
        polarization_ratio = pol_metrics["polarization_ratio"] or "N/A"
        controversy_score = str(pol_metrics["controversy_score"]) if pol_metrics["controversy_score"] is not None else "N/A"

        platforms = ", ".join(sim.get("platforms") or ["twitter_x"])
        rounds = sim.get("max_rounds", 10)

        # Phase 3b: Generate conclusion — Strategic Implications & Recommended Actions
        conclusion_idx = len(outline.sections)
        conclusion_title = "Strategic Implications & Recommended Actions"

        r.publish(f"report:{report_id}:progress", json.dumps({
            "section_index": conclusion_idx, "status": "generating",
            "title": conclusion_title,
        }))

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
                {"role": "user", "content": CONCLUSION_PROMPT.format(
                prediction_goal=sim["prediction_goal"],
                platforms=platforms,
                agent_count=agent_count,
                rounds=rounds,
                event_count=event_count,
                polarization_ratio=polarization_ratio,
                controversy_score=controversy_score,
                sections_text=sections_text[:20000],
            )}],
        )
        conclusion_content = clean_report_output(conclusion_raw)

        admin.table("report_sections").update({
            "content": conclusion_content,
            "status": "complete",
        }).eq("report_id", report_id).eq("section_index", conclusion_idx).execute()

        r.publish(f"report:{report_id}:progress", json.dumps({
            "section_index": conclusion_idx, "status": "complete",
            "title": conclusion_title,
        }))

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
                {"role": "user", "content": EXECUTIVE_SUMMARY_PROMPT.format(
                prediction_goal=sim["prediction_goal"],
                platforms=platforms,
                agent_count=agent_count,
                rounds=rounds,
                event_count=event_count,
                polarization_ratio=polarization_ratio,
                controversy_score=controversy_score,
                sections_text=sections_text[:20000],
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


async def generate_ab_comparison_report(
    simulation_id: UUID,
    config: ReACTConfig | None = None,
) -> dict:
    """Generate a comparison report for an A/B simulation."""
    if config is None:
        config = ReACTConfig(ab_comparison=True)
    config.ab_comparison = True

    # Generate base report for variant A
    report = await generate_report(simulation_id, config)
    report_id = report["id"]
    admin = get_supabase_admin()
    sim = admin.table("simulations").select("*").eq("id", str(simulation_id)).single().execute().data

    # Get A/B comparison data
    ab_data = await simulation_analytics(simulation_id, "ab_comparison")

    # Determine winner
    winner_result = await llm_structured(
        messages=[{"role": "user", "content": AB_COMPARISON_PROMPT.format(
            prediction_goal=sim["prediction_goal"],
            variant_a_data=json.dumps(ab_data.data.get("variant_a", {})),
            variant_b_data=json.dumps(ab_data.data.get("variant_b", {})),
        )}],
        schema=_WinnerResult,
    )

    # Update simulation with winner
    admin.table("simulations").update({
        "winner_variant": winner_result.winner,
    }).eq("id", str(simulation_id)).execute()

    # Append comparison section to report
    comparison_md = (
        f"\n\n## A/B Comparison Summary\n\n"
        f"**Winner: Variant {winner_result.winner.upper()}** "
        f"(confidence: {winner_result.confidence:.0%})\n\n"
        f"{winner_result.reasoning}\n\n"
        f"### Key Differences\n\n"
        + "\n".join(f"- {d}" for d in winner_result.key_differences)
    )

    current = admin.table("reports").select("markdown_content").eq(
        "id", report_id).single().execute().data
    admin.table("reports").update({
        "markdown_content": (current["markdown_content"] or "") + comparison_md,
        "variant": "comparison",
    }).eq("id", report_id).execute()

    logger.info("ab_report_generated", report_id=report_id, winner=winner_result.winner)
    return admin.table("reports").select("*").eq("id", report_id).single().execute().data


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
