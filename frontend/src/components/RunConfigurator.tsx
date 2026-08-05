import { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, Clock, Lock, Wallet } from 'lucide-react';
import api from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';

/**
 * The Run Configurator.
 *
 * Replaces an "estimator" that computed `agents * rounds * platforms / 200` on
 * the client and displayed no cost at all — a user could configure a run with
 * no idea what it would consume until after it had run.
 *
 * Two rules from PRICING_GUIDE.md Part 1 are load-bearing here, not cosmetic:
 *
 * 1. **The client never computes a price.** Every figure shown comes from
 *    `POST /billing/estimate-cost`, and the run is started against a signed
 *    quote from `POST /billing/quote`. Credits ration usage instead of hard
 *    caps, and that trade is only fair if the disclosure actually happens.
 *
 * 2. **A run count is never shown without the standard-run definition.** The
 *    "worth N standard runs" line is the honesty line: a user who bought
 *    "18 runs" and configures a 4-variant 150-agent run must see immediately
 *    that it consumes ten of them.
 */

export interface RunShape {
  agent_count: number;
  rounds: number;
  platforms: number;
  variants: number;
  depth: 'brief' | 'standard' | 'deep';
}

interface CostEstimate {
  agent_count: number;
  rounds: number;
  platforms: number;
  variants: number;
  depth: string;
  agent_rounds: number;
  llm_calls: number;
  report_sections: number;
  actual_cost_usd: number;
  retail_cost_usd: number;
  credits: number;
  margin_pct: number;
  standard_run_equivalents: number;
}

interface BudgetCheck {
  allowed: boolean;
  credits_required: number;
  credits_remaining: number;
  credits_after: number;
  balance_share_pct: number;
  message: string;
}

interface RunCaps {
  max_agents: number;
  max_rounds: number;
  max_platforms: number;
  max_variants: number;
}

interface EstimateResponse {
  estimate: CostEstimate;
  budget: BudgetCheck;
  caps: RunCaps;
  plan: string;
  largest_affordable: {
    agent_count: number;
    rounds: number;
    platforms: number;
    variants: number;
  } | null;
}

/** Debounce so dragging a slider does not fire a request per pixel. */
const QUOTE_DEBOUNCE_MS = 350;

/** Above this share of the remaining balance, the run gets a warning. */
const HIGH_SPEND_PCT = 30;

/** Below this share of the monthly grant, the balance itself gets a warning. */
const LOW_BALANCE_PCT = 15;

/* A standard run is roughly a minute per hundred agent-rounds on the current
   concurrency limits. Shown as a range, because it is a real estimate and
   presenting it as a single number invites it to be wrong. */
function estimateMinutes(estimate: CostEstimate): [number, number] {
  const units = estimate.agent_rounds * estimate.platforms * estimate.variants;
  const low = Math.max(1, Math.round(units / 900));
  return [low, Math.max(low + 1, Math.round(units / 450))];
}

/** Force `n` into `[low, high]`, rejecting NaN. */
function clamp(n: number, low: number, high: number): number {
  if (!Number.isFinite(n)) return low;
  return Math.min(Math.max(Math.round(n), low), high);
}

/**
 * One number, set two ways.
 *
 * **The displayed number and the submitted number are the same value.** The
 * previous version showed the raw `value` in the label while the range input
 * showed `Math.min(value, cap)` — a thumb sitting at one number under a label
 * reading another, with the label's number being the one that got quoted,
 * charged and built. Here `shown` is derived once and drives the label, the
 * thumb and every `onChange`, so there is no expression the two can disagree
 * through.
 *
 * The typed field exists because a slider is a bad instrument for "27". Across
 * a full-width track a single pixel is roughly two agents, and a wheel notch or
 * a stray click on the track moves it further than that — a founder who wants a
 * specific number should be able to say the number.
 */
function Slider({
  label,
  value,
  min,
  max,
  cap,
  onChange,
  planLabel,
  hint,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  /** The tier ceiling. Never exceeded by anything this emits. */
  cap: number;
  onChange: (value: number) => void;
  planLabel: string;
  hint?: string;
}) {
  const ceiling = Math.max(min, Math.min(max, cap));
  const shown = clamp(value, min, ceiling);
  const atCap = shown >= ceiling;

  /* The typed field keeps its own draft so the user can clear it and retype
     without the value snapping back to `min` on the first empty keystroke. It
     is committed on blur and on Enter, clamped; the slider is the live control
     and stays authoritative for everything else. */
  const [draft, setDraft] = useState<string | null>(null);

  const commit = (raw: string) => {
    setDraft(null);
    const parsed = Number(raw);
    if (raw.trim() === '' || !Number.isFinite(parsed)) return;
    const next = clamp(parsed, min, ceiling);
    if (next !== shown) onChange(next);
  };

  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 mb-2">
        <label className="text-[12px] font-medium text-saibyl-muted uppercase tracking-wide">
          {label}
        </label>
        <div className="flex items-center gap-2">
          {atCap && (
            <span className="flex items-center gap-1 text-[11px] text-saibyl-warning">
              <Lock className="w-3 h-3" />
              {planLabel} caps this at {ceiling}
            </span>
          )}
          <input
            type="number"
            inputMode="numeric"
            min={min}
            max={ceiling}
            aria-label={label}
            value={draft ?? String(shown)}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={(e) => commit(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                commit((e.target as HTMLInputElement).value);
              }
            }}
            className="w-20 rounded-lg bg-[#0B1120] border border-white/[0.08] px-2 py-1 text-right text-[13px] font-bold text-saibyl-gold focus:outline-none focus:ring-1 focus:ring-saibyl-gold/50"
          />
        </div>
      </div>
      <input
        type="range"
        min={min}
        // Clamped to the tier cap rather than left open and rejected at start.
        // A slider that moves past what the plan allows quotes a run the user
        // cannot launch.
        max={ceiling}
        value={shown}
        onChange={(e) => onChange(clamp(Number(e.target.value), min, ceiling))}
        className="w-full accent-saibyl-gold"
      />
      <div className="flex justify-between text-[10px] text-saibyl-muted/60 mt-1">
        <span>{min}</span>
        <span>{ceiling}</span>
      </div>
      {hint && <p className="text-[11px] text-saibyl-muted/70 mt-1.5">{hint}</p>}
    </div>
  );
}

export default function RunConfigurator({
  shape,
  platformCount,
  onChange,
  onQuote,
  readOnly = false,
}: {
  shape: RunShape;
  /** Platforms are chosen in their own step; the configurator only prices them. */
  platformCount: number;
  /**
   * Takes an updater as well as a value, and every caller here passes an
   * updater.
   *
   * `onChange({ ...shape, agent_count })` closes over the `shape` of the render
   * that created the handler. React treats `input` on a range as a continuous
   * event, so several can be batched into one commit — and the second handler
   * in that batch spreads a `shape` that predates the first, silently reverting
   * whatever the first one set. Passing a function makes every write a
   * read-modify-write against current state instead.
   */
  onChange: (update: RunShape | ((prev: RunShape) => RunShape)) => void;
  /** Fires whenever the priced shape changes, so the parent can clear a stale quote. */
  onQuote?: (estimate: CostEstimate | null) => void;
  /**
   * Hide the controls and show only the readout and warnings. Used on the
   * review step, which re-prices live rather than echoing a figure the user saw
   * several minutes earlier — "never start a run without showing its credit
   * cost first" means the cost shown must be the cost charged.
   */
  readOnly?: boolean;
}) {
  const [data, setData] = useState<EstimateResponse | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const priced: RunShape = { ...shape, platforms: Math.max(platformCount, 1) };

  const fetchEstimate = useCallback(
    async (body: RunShape) => {
      setLoading(true);
      try {
        const res = await api.post('/billing/estimate-cost', body);
        setData(res.data as EstimateResponse);
        setError('');
        onQuote?.((res.data as EstimateResponse).estimate);
      } catch (err) {
        setError(getErrorMessage(err, 'Could not price this run.'));
        setData(null);
        onQuote?.(null);
      } finally {
        setLoading(false);
      }
    },
    [onQuote],
  );

  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    const body = { ...priced };
    timer.current = setTimeout(() => void fetchEstimate(body), QUOTE_DEBOUNCE_MS);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    priced.agent_count,
    priced.rounds,
    priced.platforms,
    priced.variants,
    priced.depth,
    fetchEstimate,
  ]);

  const caps = data?.caps ?? {
    max_agents: 100,
    max_rounds: 8,
    max_platforms: 3,
    max_variants: 3,
  };
  const planLabel = (data?.plan ?? 'your plan').replace(/^\w/, (c) => c.toUpperCase());

  /* ── Caps arrive after the first render, and they clamp the *state* ──
     Until this existed the cap clamped only the thumb: a shape above the tier
     ceiling left the slider pinned at the cap while the number underneath —
     the one sent to `/billing/quote`, stored on the run and built by the
     engine — stayed wherever it was. The two could disagree indefinitely and
     nothing on screen said which one was real.

     Clamping down only. Raising a user's choice because their plan allows more
     would be the same defect pointing the other way. */
  /** Only the capped dimensions. `depth` has no cap and is not a number. */
  type CappedShape = Pick<RunShape, 'agent_count' | 'rounds' | 'variants'>;
  const [reduced, setReduced] = useState<Partial<CappedShape> | null>(null);

  useEffect(() => {
    // Never on the read-only readout. There is nothing to submit there, so
    // there is nothing to correct — and its `onChange` is a fresh no-op every
    // render, which would make this effect re-fire on its own output forever.
    if (readOnly || !data) return;
    const limits = data.caps;
    const next: Partial<CappedShape> = {};
    if (shape.agent_count > limits.max_agents) next.agent_count = limits.max_agents;
    if (shape.rounds > limits.max_rounds) next.rounds = limits.max_rounds;
    if (shape.variants > limits.max_variants) next.variants = limits.max_variants;
    if (Object.keys(next).length === 0) return;

    setReduced(next);
    onChange((prev) => ({ ...prev, ...next }));
    // `shape` is intentionally absent: this reacts to caps arriving, and the
    // clamp is idempotent — after it runs the condition above is false.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, onChange, readOnly]);
  const estimate = data?.estimate;
  const budget = data?.budget;
  const [minLow, minHigh] = estimate ? estimateMinutes(estimate) : [0, 0];

  const balancePct =
    budget && budget.credits_remaining > 0
      ? (budget.credits_after / budget.credits_remaining) * 100
      : 100;

  return (
    <div className="space-y-6">
      {!readOnly && (
        <>
          {reduced && (
            <div className="rounded-xl border border-saibyl-warning/25 bg-saibyl-warning/[0.06] px-4 py-3">
              <p className="text-[12px] text-saibyl-silver leading-relaxed">
                {planLabel} tops out at{' '}
                {[
                  reduced.agent_count != null && `${caps.max_agents} people`,
                  reduced.rounds != null && `${caps.max_rounds} rounds`,
                  reduced.variants != null && `${caps.max_variants} messages`,
                ]
                  .filter(Boolean)
                  .join(', ')}
                , so this run has been set to that. Everything below is what will
                actually run.
              </p>
            </div>
          )}

          <Slider
            label="People in the room"
            value={shape.agent_count}
            min={5}
            max={250}
            cap={caps.max_agents}
            planLabel={planLabel}
            hint="More people narrows the range on every finding. This is the exact number that will be built."
            onChange={(agent_count) => onChange((prev) => ({ ...prev, agent_count }))}
          />
          <Slider
            label="Rounds"
            value={shape.rounds}
            min={1}
            max={20}
            cap={caps.max_rounds}
            planLabel={planLabel}
            hint="How many times they get to see each other's reactions and change their mind."
            onChange={(rounds) => onChange((prev) => ({ ...prev, rounds }))}
          />

          {/* ── Testing more than one message ──
              **No count control here, deliberately.** A variant count is a price
              multiplier: the swarm reacts to each message in its own arena, and
              the quote charges for every one. The copy for those messages is set
              on the run's own page, after the run exists — so a number chosen
              here produced a run priced for N arenas with zero messages written,
              which `POST /simulations/{id}/start` refuses outright. That is
              exactly the guard that exists because a 4-variant run with no copy
              was once billed 4x and executed one arena, and a control that can
              only ever produce a run the server declines to start is a control
              that does nothing.

              Setting the count from the messages actually written is what makes
              the two unable to disagree. The previous copy here — "one message
              per run for now… arrives with the Marketing lens" — was written
              before that lens shipped and was still on screen a release later. */}
          <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-4 py-3">
            <p className="text-[11px] text-saibyl-muted uppercase tracking-wide mb-1">
              Testing more than one message
            </p>
            <p className="text-[12px] text-saibyl-silver leading-relaxed">
              You can put up to {caps.max_variants} different messages in front of
              the same room — same people, same order, so the difference is down
              to the words and not to who happened to be listening. Write them on
              the run&rsquo;s page once you&rsquo;ve created it; the price updates
              when you do, because each message is a full run of its own.
            </p>
          </div>

          <div>
            <label className="block text-[12px] font-medium text-saibyl-muted uppercase tracking-wide mb-2">
              Report depth
            </label>
            <div className="grid grid-cols-3 gap-2">
              {(['brief', 'standard', 'deep'] as const).map((depth) => (
                <button
                  key={depth}
                  type="button"
                  onClick={() => onChange((prev) => ({ ...prev, depth }))}
                  className={`px-3 py-2 rounded-xl text-[13px] capitalize border transition-colors ${
                    shape.depth === depth
                      ? 'border-saibyl-gold/50 bg-saibyl-gold/10 text-saibyl-platinum'
                      : 'border-white/[0.06] bg-white/[0.02] text-saibyl-muted hover:border-white/[0.12]'
                  }`}
                >
                  {depth}
                </button>
              ))}
            </div>
            <p className="text-[11px] text-saibyl-muted/70 mt-1.5">
              Depth sets how many sections the written report has. Report writing
              runs on the expensive model, so this is the one setting that changes
              cost without changing the simulation.
            </p>
          </div>
        </>
      )}

      {/* ── Live readout ── */}
      <div className="rounded-2xl border border-saibyl-border bg-saibyl-surface p-5">
        {error && <p className="text-[12px] text-saibyl-negative">{error}</p>}

        {!error && !estimate && (
          <p className="text-[12px] text-saibyl-muted">Pricing this run…</p>
        )}

        {estimate && budget && (
          <div className={loading ? 'opacity-60 transition-opacity' : 'transition-opacity'}>
            <p className="text-[12px] text-saibyl-muted mb-3">
              {estimate.agent_count} agents · {estimate.rounds} rounds ·{' '}
              {estimate.platforms} platform{estimate.platforms === 1 ? '' : 's'} ·{' '}
              {estimate.variants} variant{estimate.variants === 1 ? '' : 's'}
            </p>

            <dl className="space-y-2 text-[13px]">
              <div className="flex justify-between gap-4">
                <dt className="text-saibyl-muted">This run will use</dt>
                <dd className="text-saibyl-platinum font-semibold">
                  {estimate.credits.toLocaleString()} credits
                </dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-saibyl-muted">Your balance</dt>
                <dd className="text-saibyl-silver">
                  {budget.credits_remaining.toLocaleString()} →{' '}
                  <span
                    className={
                      budget.allowed ? 'text-saibyl-platinum' : 'text-saibyl-negative'
                    }
                  >
                    {budget.credits_after.toLocaleString()} after
                  </span>
                </dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-saibyl-muted flex items-center gap-1.5">
                  <Clock className="w-3.5 h-3.5" /> Estimated runtime
                </dt>
                <dd className="text-saibyl-silver">
                  ~{minLow}–{minHigh} minutes
                </dd>
              </div>
            </dl>

            {/* The honesty line. */}
            <p className="text-[12px] text-saibyl-gold mt-3 pt-3 border-t border-saibyl-border">
              ≈ {estimate.standard_run_equivalents.toFixed(1)} standard runs&rsquo; worth of
              capacity
            </p>
            <p className="text-[11px] text-saibyl-muted/70 mt-1">
              A <strong className="text-saibyl-muted">standard run</strong> is 100 agents,
              5 rounds, 2 platforms, 1 variant. Larger runs use more of your monthly
              credits — you always see the exact cost before starting.
            </p>
          </div>
        )}
      </div>

      {/* ── Warning states (PRICING_GUIDE §1.4) ── */}
      {budget && !budget.allowed && (
        <div className="rounded-2xl border border-saibyl-negative/30 bg-saibyl-negative/[0.08] p-4">
          <p className="flex items-center gap-2 text-[13px] font-semibold text-saibyl-negative">
            <Wallet className="w-4 h-4" /> Not enough credits
          </p>
          <p className="text-[12px] text-saibyl-silver mt-1">{budget.message}</p>
          {data?.largest_affordable && !readOnly && (
            <button
              type="button"
              onClick={() =>
                onChange((prev) => ({
                  ...prev,
                  agent_count: data.largest_affordable!.agent_count,
                  rounds: data.largest_affordable!.rounds,
                  variants: data.largest_affordable!.variants,
                }))
              }
              className="mt-3 px-3 py-1.5 rounded-lg text-[12px] font-medium bg-saibyl-gold text-saibyl-void hover:bg-saibyl-gold-hover transition-colors"
            >
              Reduce to fit my balance ({data.largest_affordable.agent_count} agents,{' '}
              {data.largest_affordable.rounds} rounds,{' '}
              {data.largest_affordable.variants} variant
              {data.largest_affordable.variants === 1 ? '' : 's'})
            </button>
          )}
        </div>
      )}

      {budget?.allowed && budget.balance_share_pct > HIGH_SPEND_PCT && (
        <div className="rounded-2xl border border-saibyl-warning/30 bg-saibyl-warning/[0.08] p-4">
          <p className="flex items-center gap-2 text-[13px] font-semibold text-saibyl-warning">
            <AlertTriangle className="w-4 h-4" />
            This run uses {budget.balance_share_pct.toFixed(0)}% of your remaining
            credits
          </p>
          <p className="text-[12px] text-saibyl-silver mt-1">
            You&rsquo;ll have {budget.credits_after.toLocaleString()} left this cycle —
            about{' '}
            {estimate
              ? (budget.credits_after / (estimate.credits / estimate.standard_run_equivalents)).toFixed(
                  1,
                )
              : '—'}{' '}
            standard runs.
          </p>
        </div>
      )}

      {budget?.allowed &&
        budget.balance_share_pct <= HIGH_SPEND_PCT &&
        balancePct < LOW_BALANCE_PCT && (
          <p className="text-[12px] text-saibyl-muted">
            Heads up — after this run you&rsquo;ll have used most of this cycle&rsquo;s
            credits.
          </p>
        )}
    </div>
  );
}
