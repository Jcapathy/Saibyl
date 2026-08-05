import { AlertTriangle, Radio, Scale, Trophy } from 'lucide-react';
import type { VariantScore, VariantScoreboard } from '@/lib/analysis';

const GOLD = '#C9A227'; // Sovereign Gold
const BLUE = '#2563EB'; // Signal Blue
const VIOLET = '#8B5CF6'; // Insight Violet

const OBJECTIVE_LABELS: Record<string, string> = {
  clicks: 'Click intent',
  foot_traffic: 'Visit intent',
  product_sale: 'Purchase intent',
  service_sale: 'Inquiry intent',
  signup: 'Trial intent',
  awareness: 'Share intent',
};

const pct = (n: number) => `${(n * 100).toFixed(1)}%`;

/**
 * The N-way matched-swarm scoreboard.
 *
 * Two rules this component exists to honour, both easy to break by making the
 * UI look more decisive:
 *
 * **The verdict outranks the ordering.** The list is sorted by the objective
 * metric, but that ordering is display order, not a claim. When the server
 * declines to name a winner — because the top two intervals overlap — no row is
 * marked as winning. Highlighting row one anyway would put a number the product
 * explicitly refused to stand behind in front of a spend decision.
 *
 * **null is not zero.** A virality component that could not be measured renders
 * as "not measured", never as 0%. Showing a dash where a gap exists is the
 * difference between "this variant did not travel" and "we did not measure
 * whether it travelled".
 */
export default function VariantScoreboardPanel({
  scoreboard,
  onDrillDown,
}: {
  scoreboard: VariantScoreboard | null | undefined;
  onDrillDown?: (eventIds: string[]) => void;
}) {
  if (!scoreboard || scoreboard.variants.length === 0) return null;

  const metricLabel = scoreboard.objective
    ? (OBJECTIVE_LABELS[scoreboard.objective] ?? 'Objective intent')
    : 'Committing intent';

  return (
    <div className="mb-8">
      <div className="flex items-baseline justify-between mb-3 gap-4 flex-wrap">
        <h2 className="text-sm font-semibold text-saibyl-pearl">
          Variant scoreboard
        </h2>
        <span className="text-[11px] text-saibyl-muted">
          Ranked by {metricLabel.toLowerCase()} · {scoreboard.variants.length} variants ·
          one shared audience
        </span>
      </div>

      {/* The verdict, always, and before the table. A reader who stops here must
          not come away with a winner the measurement did not support. */}
      <div
        className="rounded-2xl border p-4 mb-4 flex items-start gap-3"
        style={
          scoreboard.winner_variant_key
            ? { borderColor: `${GOLD}33`, backgroundColor: `${GOLD}0D` }
            : { borderColor: '#ffffff1a', backgroundColor: '#ffffff08' }
        }
      >
        {scoreboard.winner_variant_key ? (
          <Trophy className="w-4 h-4 mt-0.5 shrink-0" style={{ color: GOLD }} />
        ) : (
          <Scale className="w-4 h-4 mt-0.5 shrink-0 text-saibyl-muted" />
        )}
        <p className="text-[12px] leading-relaxed text-saibyl-silver">
          {scoreboard.verdict}
        </p>
      </div>

      {/*
        How the verdict was reached. Shown because from schema version 4 the
        winner is decided by comparing the top two arenas *agent by agent* —
        the same people saw every variant, so an agent who converted on both
        tells you nothing about which is better, and only the ones who
        disagreed carry information.

        `discordant_agents` is therefore the honest sample size of the
        comparison, and it is usually much smaller than the swarm. Showing it
        is the difference between "we tested this on 250 people" and "31 of
        them behaved differently between these two, and that is what the call
        rests on".

        Absent on v3 artifacts, which predate the paired comparison. Nothing is
        rendered in that case rather than a zeroed block that would read as
        "no agents disagreed".
      */}
      {scoreboard.paired && (
        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-4 py-3 mb-4">
          <p className="text-[11px] font-mono uppercase tracking-widest text-saibyl-muted mb-1.5">
            How this was decided
          </p>
          <p className="text-[12px] leading-relaxed text-saibyl-muted">
            The same{' '}
            <span className="text-saibyl-silver">
              {scoreboard.paired.shared_agents}
            </span>{' '}
            agents saw both of the top two.{' '}
            <span className="text-saibyl-silver">
              {scoreboard.paired.discordant_agents}
            </span>{' '}
            of them behaved differently between the two — that difference, and
            not the headline rates, is what the call above rests on.
          </p>
          {/* The unpaired rule, for one release, so a changed answer reads as a
              documented change rather than the product changing its mind. */}
          {scoreboard.unpaired_verdict &&
            scoreboard.unpaired_winner_variant_key !==
              scoreboard.winner_variant_key && (
              <p className="text-[11px] leading-relaxed text-saibyl-muted mt-2 pt-2 border-t border-white/[0.06]">
                Under the previous method, which compared the arenas as if
                different people had seen each one, this run would have read:{' '}
                <span className="italic">{scoreboard.unpaired_verdict}</span>
              </p>
            )}
        </div>
      )}

      <div className="space-y-3">
        {scoreboard.variants.map((variant, index) => (
          <VariantRow
            key={variant.variant_key}
            variant={variant}
            rank={index + 1}
            metricLabel={metricLabel}
            isWinner={variant.variant_key === scoreboard.winner_variant_key}
            offMessageThreshold={scoreboard.off_message_threshold}
            onDrillDown={onDrillDown}
          />
        ))}
      </div>
    </div>
  );
}

function VariantRow({
  variant,
  rank,
  metricLabel,
  isWinner,
  offMessageThreshold,
  onDrillDown,
}: {
  variant: VariantScore;
  rank: number;
  metricLabel: string;
  isWinner: boolean;
  offMessageThreshold: number;
  onDrillDown?: (eventIds: string[]) => void;
}) {
  const rate = variant.objective_rate;
  const silent = variant.event_count === 0;

  return (
    <div
      className="rounded-2xl border p-5"
      style={
        isWinner
          ? { borderColor: `${GOLD}4D`, backgroundColor: `${GOLD}0A` }
          : { borderColor: '#ffffff14', backgroundColor: '#ffffff05' }
      }
    >
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[11px] text-saibyl-muted">#{rank}</span>
            <span className="text-[13px] font-semibold text-saibyl-pearl">
              {variant.label || `Variant ${variant.variant_key.toUpperCase()}`}
            </span>
            {isWinner && (
              <span
                className="px-2 py-0.5 rounded text-[10px] font-semibold"
                style={{ backgroundColor: `${GOLD}1A`, color: GOLD }}
              >
                Leads
              </span>
            )}
          </div>
          {variant.content && (
            <p className="text-[12px] text-saibyl-silver mt-1.5 leading-relaxed line-clamp-2">
              “{variant.content}”
            </p>
          )}
        </div>

        <div className="text-right shrink-0">
          <div className="text-xl font-semibold text-saibyl-pearl tabular-nums">
            {silent ? '—' : pct(rate.mean)}
          </div>
          <div className="text-[10px] text-saibyl-muted">
            {metricLabel}
            {!silent && (
              <>
                {' · '}
                {pct(rate.lower)}–{pct(rate.upper)}
              </>
            )}
          </div>
        </div>
      </div>

      {/* An arena nobody engaged with is a finding, not an absence. It stays on
          the board, and it says why the row is empty. */}
      {silent ? (
        <p className="text-[11px] text-saibyl-muted mt-3">
          No agent produced a measured event in this arena. Nothing to score —
          this is a result, not a gap.
        </p>
      ) : (
        <>
          <div className="flex flex-wrap gap-x-6 gap-y-2 mt-4 text-[11px]">
            <Stat label="Agents" value={String(variant.agent_count)} />
            <Stat label="Events" value={String(variant.event_count)} />
            <Stat
              label="Sentiment"
              value={variant.valence.mean.toFixed(3)}
              hint="Supporting metric, not the score"
            />
            <Stat
              label="Virality"
              value={
                variant.virality.score === null
                  ? 'not measured'
                  : variant.virality.score.toFixed(0)
              }
              hint={`${variant.virality.components_used} of ${variant.virality.components_total} components measured`}
              accent={VIOLET}
            />
            <Stat
              label="Takeaway accuracy"
              value={
                variant.takeaway_accuracy === null
                  ? 'not measured'
                  : pct(variant.takeaway_accuracy)
              }
              hint="Approximate — lexical overlap with the copy"
            />
          </div>

          <ViralityBreakdown variant={variant} />
          <Flags variant={variant} offMessageThreshold={offMessageThreshold} />

          {variant.by_archetype.length > 0 && (
            <div className="mt-4 pt-3 border-t border-white/5">
              <p className="text-[10px] text-saibyl-muted mb-2">
                Who it wins and who it loses
              </p>
              <div className="flex flex-wrap gap-1.5">
                {variant.by_archetype.map((slice) => (
                  <span
                    key={slice.archetype}
                    className="px-2 py-0.5 rounded text-[10px]"
                    style={{ backgroundColor: `${BLUE}14`, color: '#9CB4E8' }}
                    title={`${slice.agent_count} agents, ${slice.event_count} events`}
                  >
                    {slice.archetype} · {pct(slice.objective_rate.mean)}
                  </span>
                ))}
              </div>
            </div>
          )}

          {onDrillDown && variant.event_ids.length > 0 && (
            <button
              type="button"
              onClick={() => onDrillDown(variant.event_ids)}
              className="mt-3 text-[11px] underline underline-offset-2"
              style={{ color: BLUE }}
            >
              Read what this arena actually said
            </button>
          )}
        </>
      )}
    </div>
  );
}

/**
 * The six components.
 *
 * A component the run could not measure shows "not measured" rather than a
 * zero, and the cascade figure is labelled branching — the adapters have no
 * reply-to-reply, so a depth number would be 2 for every variant that got a
 * single reply.
 */
function ViralityBreakdown({ variant }: { variant: VariantScore }) {
  const v = variant.virality;
  const parts: Array<[string, string]> = [
    [
      'Cross-archetype reach',
      `${v.archetypes_reached}/${v.archetypes_total} (${pct(v.cross_archetype_reach)})`,
    ],
    ['Share intent', pct(v.share_intent_rate.mean)],
    [
      'Cross-platform jump',
      v.cross_platform_jump === null ? 'not measured' : pct(v.cross_platform_jump),
    ],
    [
      'Restatement',
      v.restatement_rate === null ? 'not measured' : pct(v.restatement_rate),
    ],
    [
      'Cascade branching',
      v.cascade_branching === null
        ? 'not measured'
        : `${v.cascade_branching.toFixed(1)} replies/post`,
    ],
    [
      'Peak round',
      v.velocity_rounds_to_peak === null ? 'not measured' : `R${v.velocity_rounds_to_peak}`,
    ],
  ];

  return (
    <details className="mt-3 group">
      <summary className="text-[11px] text-saibyl-muted cursor-pointer select-none hover:text-saibyl-silver">
        Virality components
      </summary>
      <div className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1.5">
        {parts.map(([label, value]) => (
          <div key={label} className="flex justify-between gap-3 text-[11px]">
            <span className="text-saibyl-muted">{label}</span>
            <span
              className={
                value === 'not measured'
                  ? 'text-saibyl-muted italic'
                  : 'text-saibyl-silver tabular-nums'
              }
            >
              {value}
            </span>
          </div>
        ))}
      </div>
      <p className="text-[10px] text-saibyl-muted mt-2 leading-relaxed">
        Cross-archetype reach carries the heaviest weight: content that spreads
        only inside the cohort it started in is an echo chamber, not virality.
        Cascade is measured as branching rather than depth — the platform
        adapters support replies to posts, not replies to replies.
      </p>
    </details>
  );
}

/** The two cases DECISIONS §6 exists to keep visible. */
function Flags({
  variant,
  offMessageThreshold,
}: {
  variant: VariantScore;
  offMessageThreshold: number;
}) {
  if (!variant.viral_but_off_message && !variant.converts_but_wont_travel) return null;

  return (
    <div className="mt-3 space-y-2">
      {variant.viral_but_off_message && (
        <Flag
          color={GOLD}
          title="Viral but off-message"
          body={`It spreads, and agents restate it as something other than what it says (takeaway accuracy below ${pct(offMessageThreshold)}). It will travel as a message you did not write.`}
        />
      )}
      {variant.converts_but_wont_travel && (
        <Flag
          color={BLUE}
          title="Converts but won't travel"
          body="It performs on the objective and does not spread. Good copy that needs paid distribution rather than organic reach."
        />
      )}
    </div>
  );
}

function Flag({ color, title, body }: { color: string; title: string; body: string }) {
  return (
    <div
      className="rounded-xl border px-3 py-2 flex items-start gap-2"
      style={{ borderColor: `${color}33`, backgroundColor: `${color}0D` }}
    >
      {title.startsWith('Viral') ? (
        <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" style={{ color }} />
      ) : (
        <Radio className="w-3.5 h-3.5 mt-0.5 shrink-0" style={{ color }} />
      )}
      <div>
        <p className="text-[11px] font-semibold" style={{ color }}>
          {title}
        </p>
        <p className="text-[11px] text-saibyl-silver mt-0.5 leading-relaxed">{body}</p>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  hint,
  accent,
}: {
  label: string;
  value: string;
  hint?: string;
  accent?: string;
}) {
  const unmeasured = value === 'not measured';
  return (
    <div title={hint}>
      <div className="text-saibyl-muted text-[10px]">{label}</div>
      <div
        className={
          unmeasured
            ? 'text-saibyl-muted italic text-[12px]'
            : 'text-[12px] tabular-nums'
        }
        style={unmeasured ? undefined : { color: accent ?? '#E8EAF0' }}
      >
        {value}
      </div>
    </div>
  );
}
