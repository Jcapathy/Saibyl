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

function Slider({
  label,
  value,
  min,
  max,
  cap,
  onChange,
  planLabel,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  cap: number;
  onChange: (value: number) => void;
  planLabel: string;
}) {
  const atCap = value >= cap;
  return (
    <div>
      <div className="flex items-baseline justify-between mb-2">
        <label className="text-[12px] font-medium text-saibyl-muted uppercase tracking-wide">
          {label}: <span className="text-saibyl-gold font-bold">{value}</span>
        </label>
        {atCap && (
          <span className="flex items-center gap-1 text-[11px] text-saibyl-warning">
            <Lock className="w-3 h-3" />
            {planLabel} caps this at {cap}
          </span>
        )}
      </div>
      <input
        type="range"
        min={min}
        // Clamped to the tier cap rather than left open and rejected at start.
        // A slider that moves past what the plan allows quotes a run the user
        // cannot launch.
        max={Math.min(max, cap)}
        value={Math.min(value, cap)}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-saibyl-gold"
      />
      <div className="flex justify-between text-[10px] text-saibyl-muted/60 mt-1">
        <span>{min}</span>
        <span>{Math.min(max, cap)}</span>
      </div>
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
  onChange: (shape: RunShape) => void;
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
          <Slider
            label="Agents"
            value={shape.agent_count}
            min={5}
            max={250}
            cap={caps.max_agents}
            planLabel={planLabel}
            onChange={(agent_count) => onChange({ ...shape, agent_count })}
          />
          <Slider
            label="Rounds"
            value={shape.rounds}
            min={1}
            max={20}
            cap={caps.max_rounds}
            planLabel={planLabel}
            onChange={(rounds) => onChange({ ...shape, rounds })}
          />
          {/* A slider that cannot move is worse than an explanation. The
              engine runs one variant arena; the cap comes from the server, so
              this reappears on its own when N-way matched swarms ship. */}
          {caps.max_variants > 1 ? (
            <Slider
              label="Variants"
              value={shape.variants}
              min={1}
              max={8}
              cap={caps.max_variants}
              planLabel={planLabel}
              onChange={(variants) => onChange({ ...shape, variants })}
            />
          ) : (
            <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-4 py-3">
              <p className="text-[12px] text-saibyl-silver">
                <span className="text-saibyl-muted uppercase tracking-wide text-[11px]">
                  Variants
                </span>
                <br />
                One message per run for now. Testing several messages against the
                same audience — same agents, same seed — arrives with the
                Marketing lens.
              </p>
            </div>
          )}

          <div>
            <label className="block text-[12px] font-medium text-saibyl-muted uppercase tracking-wide mb-2">
              Report depth
            </label>
            <div className="grid grid-cols-3 gap-2">
              {(['brief', 'standard', 'deep'] as const).map((depth) => (
                <button
                  key={depth}
                  type="button"
                  onClick={() => onChange({ ...shape, depth })}
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
                onChange({
                  ...shape,
                  agent_count: data.largest_affordable!.agent_count,
                  rounds: data.largest_affordable!.rounds,
                  variants: data.largest_affordable!.variants,
                })
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
