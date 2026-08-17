import { AlertTriangle, Radio, Scale, Trophy } from 'lucide-react';
import type { VariantScore, VariantScoreboard } from '@/lib/analysis';

const GOLD = '#286cf0'; // legacy accent name — the Signal Blue accent
const BLUE = '#1e5ad9'; // the darker blue — safe as text on the light ground
const VIOLET = '#6a4fe0'; // Insight Violet, text-safe variant

const OBJECTIVE_LABELS: Record<string, string> = {
  clicks: 'Would click',
  foot_traffic: 'Would visit',
  product_sale: 'Would buy',
  service_sale: 'Would get in touch',
  signup: 'Would sign up',
  awareness: 'Would share it',
};

const pct = (n: number) => `${(n * 100).toFixed(1)}%`;

/**
 * Which of several messages won, when the same people saw all of them.
 *
 * Two rules this component exists to honour, both easy to break by making the
 * UI look more decisive:
 *
 * **The verdict outranks the ordering.** The list is sorted by whichever
 * outcome the run was aiming at, but that ordering is display order, not a
 * claim. When the server declines to name a winner — because the ranges around
 * the top two overlap — no row is marked as winning. Highlighting row one
 * anyway would put a number the product explicitly refused to stand behind in
 * front of a spend decision.
 *
 * **null is not zero.** Anything about spread that could not be measured
 * renders as "not measured", never as 0%. Showing a dash where a gap exists is
 * the difference between "this one did not travel" and "we did not look at
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
    ? (OBJECTIVE_LABELS[scoreboard.objective] ?? 'Would act on it')
    : 'Would act on it';

  return (
    <div className="mb-8">
      <div className="flex items-baseline justify-between mb-3 gap-4 flex-wrap">
        <h2 className="text-sm font-semibold text-saibyl-ink">
          Which message won
        </h2>
        <span className="text-[11px] text-saibyl-muted">
          Ordered by how many {metricLabel.toLowerCase()} · {scoreboard.variants.length}{' '}
          versions · the same people saw every one
        </span>
      </div>

      {/* The verdict, always, and before the table. A reader who stops here must
          not come away with a winner the measurement did not support. */}
      <div
        className="rounded-2xl border p-4 mb-4 flex items-start gap-3"
        style={
          scoreboard.winner_variant_key
            ? { borderColor: `${GOLD}33`, backgroundColor: `${GOLD}0D` }
            : { borderColor: '#264f8b24', backgroundColor: '#f3f7fd' }
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
        How the call was reached. Shown because from schema version 4 the
        winner is decided by comparing the top two *person by person* — the
        same people saw every message, so someone who acted on both tells you
        nothing about which is better, and only the ones who split carry
        information.

        `discordant_agents` is therefore the honest sample size of the
        comparison, and it is usually much smaller than the room. Showing it
        is the difference between "we tested this on 250 people" and "31 of
        them went one way on one and the other way on the other, and that is
        what the call rests on".

        Absent on v3 artifacts, which predate the paired comparison. Nothing is
        rendered in that case rather than a zeroed block that would read as
        "nobody split".
      */}
      {scoreboard.paired && (
        <div className="rounded-xl border border-saibyl-border bg-saibyl-elevated px-4 py-3 mb-4">
          <p className="text-[11px] font-mono uppercase tracking-widest text-saibyl-muted mb-1.5">
            How we decided
          </p>
          <p className="text-[12px] leading-relaxed text-saibyl-muted">
            The same{' '}
            <span className="text-saibyl-silver">
              {scoreboard.paired.shared_agents}
            </span>{' '}
            people saw both of the top two.{' '}
            <span className="text-saibyl-silver">
              {scoreboard.paired.discordant_agents}
            </span>{' '}
            of them went one way on one and the other way on the other. The call
            above rests on those people, not on the headline percentages.
          </p>
          {/* The older rule, for one release, so a changed answer reads as a
              documented change rather than the product changing its mind. */}
          {scoreboard.unpaired_verdict &&
            scoreboard.unpaired_winner_variant_key !==
              scoreboard.winner_variant_key && (
              <p className="text-[11px] leading-relaxed text-saibyl-muted mt-2 pt-2 border-t border-saibyl-border">
                The way we used to work this out treated each message as though a
                different set of people had seen it. That way, this run would have
                read: <span className="italic">{scoreboard.unpaired_verdict}</span>
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
          : { borderColor: '#264f8b24', backgroundColor: '#ffffff' }
      }
    >
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[11px] text-saibyl-muted">#{rank}</span>
            <span className="text-[13px] font-semibold text-saibyl-ink">
              {variant.label || `Version ${variant.variant_key.toUpperCase()}`}
            </span>
            {isWinner && (
              <span
                className="px-2 py-0.5 rounded text-[10px] font-semibold"
                style={{ backgroundColor: `${GOLD}1A`, color: BLUE }}
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
          <div className="text-xl font-semibold text-saibyl-ink tabular-nums">
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

      {/* A message nobody engaged with is a finding, not an absence. It stays
          on the board, and it says why the row is empty. */}
      {silent ? (
        <p className="text-[11px] text-saibyl-muted mt-3">
          Nobody reacted to this one at all, so there is nothing to score. That
          is itself the answer, not a gap in the data.
        </p>
      ) : (
        <>
          <div className="flex flex-wrap gap-x-6 gap-y-2 mt-4 text-[11px]">
            <Stat label="People" value={String(variant.agent_count)} />
            <Stat label="Posts and replies" value={String(variant.event_count)} />
            <Stat
              label="How they felt"
              value={variant.valence.mean.toFixed(3)}
              hint="Worth knowing, but not what picks the winner"
            />
            <Stat
              label="How far it spread"
              value={
                variant.virality.score === null
                  ? 'not measured'
                  : variant.virality.score.toFixed(0)
              }
              hint={`${variant.virality.components_used} of the ${variant.virality.components_total} things we look at could be measured`}
              accent={VIOLET}
            />
            <Stat
              label="Repeated it right"
              value={
                variant.takeaway_accuracy === null
                  ? 'not measured'
                  : pct(variant.takeaway_accuracy)
              }
              hint="Rough — we compare their words against yours"
            />
          </div>

          <ViralityBreakdown variant={variant} />
          <Flags variant={variant} offMessageThreshold={offMessageThreshold} />

          {variant.by_archetype.length > 0 && (
            <div className="mt-4 pt-3 border-t border-saibyl-border">
              <p className="text-[10px] text-saibyl-muted mb-2">
                Who it wins and who it loses
              </p>
              <div className="flex flex-wrap gap-1.5">
                {variant.by_archetype.map((slice) => (
                  <span
                    key={slice.archetype}
                    className="px-2 py-0.5 rounded text-[10px]"
                    style={{ backgroundColor: `${BLUE}14`, color: BLUE }}
                    title={`${slice.agent_count} people, ${slice.event_count} posts and replies`}
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
              Read what people said about this one
            </button>
          )}
        </>
      )}
    </div>
  );
}

/**
 * The six things "how far it spread" is made of.
 *
 * Anything the run could not measure shows "not measured" rather than a zero,
 * and replies are counted per post rather than by how deep a thread went — the
 * platforms modelled here have no reply-to-a-reply, so a depth number would be
 * 2 for every message that got a single reply.
 */
function ViralityBreakdown({ variant }: { variant: VariantScore }) {
  const v = variant.virality;
  const parts: Array<[string, string]> = [
    [
      'Reached different kinds of buyer',
      `${v.archetypes_reached} of ${v.archetypes_total} (${pct(v.cross_archetype_reach)})`,
    ],
    ['Said they would share it', pct(v.share_intent_rate.mean)],
    [
      'Carried to another platform',
      v.cross_platform_jump === null ? 'not measured' : pct(v.cross_platform_jump),
    ],
    [
      'Repeated in their own words',
      v.restatement_rate === null ? 'not measured' : pct(v.restatement_rate),
    ],
    [
      'Replies it drew',
      v.cascade_branching === null
        ? 'not measured'
        : `${v.cascade_branching.toFixed(1)} per post`,
    ],
    [
      'Busiest round',
      v.velocity_rounds_to_peak === null
        ? 'not measured'
        : `round ${v.velocity_rounds_to_peak}`,
    ],
  ];

  return (
    <details className="mt-3 group">
      <summary className="text-[11px] text-saibyl-muted cursor-pointer select-none hover:text-saibyl-silver">
        What &ldquo;how far it spread&rdquo; is made of
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
        Reaching different kinds of buyer counts for the most. Something that only
        travels inside the group it started in is an echo chamber, not reach.
        Replies are counted per post rather than by how deep a thread went,
        because replies to replies are not modelled here.
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
          kind="warning"
          color="#b45309"
          title="It spreads, but not as you wrote it"
          body={`People pass it on and change what it says on the way — fewer than ${pct(offMessageThreshold)} of them repeat it accurately. It will travel as a message you did not write.`}
        />
      )}
      {variant.converts_but_wont_travel && (
        <Flag
          kind="reach"
          color={BLUE}
          title="It works, but it will not spread"
          body="It gets people to act and nobody passes it on. Good copy that you will have to pay to put in front of people."
        />
      )}
    </div>
  );
}

/**
 * `kind` picks the icon, rather than sniffing the first word of `title`.
 *
 * It used to be `title.startsWith('Viral')`, so rewording the heading silently
 * changed the icon — copy and behaviour coupled through a string prefix, which
 * is exactly the kind of link nobody remembers when they edit a label.
 */
function Flag({
  kind,
  color,
  title,
  body,
}: {
  kind: 'warning' | 'reach';
  color: string;
  title: string;
  body: string;
}) {
  return (
    <div
      className="rounded-xl border px-3 py-2 flex items-start gap-2"
      style={{ borderColor: `${color}33`, backgroundColor: `${color}0D` }}
    >
      {kind === 'warning' ? (
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
        style={unmeasured ? undefined : { color: accent ?? '#14294a' }}
      >
        {value}
      </div>
    </div>
  );
}
