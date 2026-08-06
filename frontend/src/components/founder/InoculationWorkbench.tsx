import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FlaskConical, Loader2, PenLine } from 'lucide-react';
import api from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import {
  ASSET_TYPE_LABELS,
  formatReach,
  VERDICT_COPY,
  VERDICT_TONE,
  type InoculationAsset,
  type InoculationResult,
  type ObjectionDelta,
} from '@/lib/founder';
import { formatSigned, type ObjectionSummary } from '@/lib/analysis';
import Panel, { NoData } from '@/components/analysis/Panel';

const TONE_COLOR: Record<'good' | 'bad' | 'neutral', string> = {
  good: '#22C55E',
  bad: '#EF4444',
  neutral: '#94A3B8',
};

/* ------------------------------------------------------------------ */
/*  Result                                                             */
/* ------------------------------------------------------------------ */

function DeltaRow({ delta }: { delta: ObjectionDelta }) {
  const tone = VERDICT_TONE[delta.verdict];
  const color = TONE_COLOR[tone];

  return (
    <div className="py-3 border-b border-white/[0.04] last:border-0">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[13px] text-saibyl-platinum font-medium">{delta.label}</p>
          {delta.asset_titles.length > 0 && (
            <p className="text-[11px] text-saibyl-muted mt-0.5">
              Answered by: {delta.asset_titles.join(', ')}
            </p>
          )}
        </div>
        <span
          className="text-[10px] px-2 py-0.5 rounded whitespace-nowrap"
          style={{ backgroundColor: `${color}1A`, color }}
        >
          {delta.verdict}
        </span>
      </div>

      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 mt-1.5 text-[11px] text-saibyl-muted">
        <span>Before: {formatReach(delta.before)}</span>
        <span>After: {formatReach(delta.after)}</span>
        <span style={{ color }}>{formatSigned(delta.reach_delta_pct, 1)} pts</span>
      </div>

      <p className="text-[11px] text-saibyl-muted mt-1 leading-relaxed">
        {VERDICT_COPY[delta.verdict]}
        {/* The distinction the whole loop turns on. A move inside the bands is
            not a small result — it is not a result. Saying so here is what
            stops "34% to 31%" being read as progress. */}
        {!delta.significant && delta.verdict !== 'unchanged' && (
          <span className="text-saibyl-gold/80">
            {' '}
            The two rooms overlap too much to call this a real change.
          </span>
        )}
      </p>

      {delta.converted_agent_usernames.length > 0 && (
        <p className="text-[11px] text-saibyl-muted mt-1">
          Stopped raising it: {delta.converted_agent_usernames.slice(0, 6).join(', ')}
          {delta.converted_agent_usernames.length > 6 &&
            ` +${delta.converted_agent_usernames.length - 6} more`}
        </p>
      )}
    </div>
  );
}

function ResultPanel({ result }: { result: InoculationResult }) {
  const targeted = result.deltas.filter((d) => d.asset_ids.length > 0);
  const untargeted = result.deltas.filter((d) => d.asset_ids.length === 0);

  return (
    <Panel
      title="Before and after"
      note={
        result.assets_effective === 0
          ? `${
              result.assets_tested === 1
                ? 'The one thing you tested did not move'
                : `None of the ${result.assets_tested} things you tested moved`
            } its objection by more than this run can tell apart from noise. That is a real answer, not a failed run — it means this material does not change how people react.`
          : `${result.assets_effective} of the ${result.assets_tested} things you tested measurably moved the objection ${result.assets_effective === 1 ? 'it was' : 'they were'} written against.`
      }
    >
      <div className="mb-4 pb-3 border-b border-white/[0.06] text-[12px] text-saibyl-muted">
        How the room felt overall: {formatSigned(result.headline_before.mean)} →{' '}
        {formatSigned(result.headline_after.mean)}
        {result.headline_before.lower <= result.headline_after.upper &&
          result.headline_after.lower <= result.headline_before.upper && (
            <span className="text-saibyl-gold/80">
              {' '}
              — too small a move to call. Something you wrote can kill one objection without
              shifting the overall mood, and that is still worth having.
            </span>
          )}
      </div>

      {targeted.length > 0 ? (
        targeted.map((delta) => <DeltaRow key={delta.objection_key} delta={delta} />)
      ) : (
        <NoData>Nothing here was written against a particular objection.</NoData>
      )}

      {untargeted.length > 0 && (
        <div className="mt-5 pt-4 border-t border-white/[0.06]">
          <p className="text-[11px] text-saibyl-muted uppercase tracking-wide mb-2">
            Objections nothing was written against
          </p>
          {untargeted.slice(0, 8).map((delta) => (
            <DeltaRow key={delta.objection_key} delta={delta} />
          ))}
        </div>
      )}
    </Panel>
  );
}

/* ------------------------------------------------------------------ */
/*  Workbench                                                          */
/* ------------------------------------------------------------------ */

/**
 * Detect → draft → re-simulate → prove, as one screen.
 *
 * The objections are already on this page; this adds the three steps after
 * them. The design decision worth keeping: **nothing here reports an
 * improvement that the intervals do not support.** The loop's value is that it
 * can come back and say the asset did not work, and a UI that renders every
 * downward move as green would destroy exactly that.
 */
export default function InoculationWorkbench({
  simulationId,
  parentSimulationId,
  objections,
}: {
  simulationId: string;
  parentSimulationId?: string | null;
  objections: ObjectionSummary[];
}) {
  const navigate = useNavigate();
  const [assets, setAssets] = useState<InoculationAsset[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [drafting, setDrafting] = useState(false);
  const [launching, setLaunching] = useState(false);
  const [result, setResult] = useState<InoculationResult | null>(null);
  const [cost, setCost] = useState<{ credits_required: number } | null>(null);
  const [error, setError] = useState('');

  const loadResult = useCallback(() => {
    if (!parentSimulationId) return;
    api
      .get(`/inoculation/${simulationId}/result`)
      .then((r) => setResult(r.data))
      .catch(() => setResult(null));
  }, [simulationId, parentSimulationId]);

  useEffect(() => {
    api
      .get(`/inoculation/${simulationId}/assets`)
      .then((r) => setAssets(r.data))
      .catch(() => {});
    api
      .get('/inoculation/draft-estimate')
      .then((r) => setCost(r.data))
      .catch(() => {});
    loadResult();
  }, [simulationId, loadResult]);

  const draft = async () => {
    setDrafting(true);
    setError('');
    try {
      const { data } = await api.post(`/inoculation/${simulationId}/assets`, {
        objection_keys: [],
      });
      setAssets((prev) => [...prev, ...data]);
    } catch (err) {
      setError(getErrorMessage(err, 'We could not write anything against these.'));
    } finally {
      setDrafting(false);
    }
  };

  const resimulate = async () => {
    setLaunching(true);
    setError('');
    try {
      const { data: child } = await api.post(`/inoculation/${simulationId}/resimulate`, {
        asset_ids: selected,
      });
      // The child arrives ready — its agents are copies, so there is nothing to
      // prepare. It still goes through the normal start endpoint, which quotes
      // and charges it like any other run.
      navigate(`/app/simulations/${child.id}`);
    } catch (err) {
      setError(getErrorMessage(err, 'We could not set up the second run.'));
      setLaunching(false);
    }
  };

  if (result) {
    return <ResultPanel result={result} />;
  }

  if (parentSimulationId) {
    return (
      <Panel title="Before and after">
        <NoData>
          You put new material in front of the same room. The before-and-after appears once this
          run finishes.
        </NoData>
      </Panel>
    );
  }

  const byObjection = new Map<string, InoculationAsset[]>();
  for (const asset of assets) {
    const list = byObjection.get(asset.objection_key) ?? [];
    list.push(asset);
    byObjection.set(asset.objection_key, list);
  }

  return (
    <div className="space-y-6">
      {error && (
        <div className="px-4 py-3 rounded-xl bg-saibyl-negative/10 border border-saibyl-negative/20 text-saibyl-negative text-[13px]">
          {error}
        </div>
      )}

      <Panel
        title="Get ahead of these objections"
        note="We write against the objections that reached the most people, hit them hardest and spread widest between groups — not the ones said most often. The loudest objection and the one that loses you the sale are usually not the same objection."
      >
        {objections.length === 0 ? (
          <NoData>Nobody in this run raised an objection clearly enough to write against.</NoData>
        ) : (
          <>
            <div className="space-y-1 mb-4">
              {objections.slice(0, 6).map((objection) => (
                <div key={objection.key} className="flex items-baseline gap-3 text-[12px]">
                  <span className="text-saibyl-platinum flex-1 truncate">{objection.label}</span>
                  <span className="text-saibyl-muted text-[11px] whitespace-nowrap">
                    {objection.agent_count} {objection.agent_count === 1 ? 'person' : 'people'}
                    {objection.originated_adversarial &&
                      ' · first raised by someone arguing against you'}
                  </span>
                </div>
              ))}
            </div>

            <button
              type="button"
              onClick={draft}
              disabled={drafting}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-dashed border-saibyl-gold/30 bg-saibyl-gold/5 hover:border-saibyl-gold/50 hover:bg-saibyl-gold/10 disabled:opacity-40 transition-all text-[13px] text-saibyl-gold"
            >
              {drafting ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <PenLine className="w-4 h-4" />
              )}
              {drafting ? 'Writing…' : 'Write answers to these'}
            </button>
            {cost && (
              <p className="text-[11px] text-saibyl-muted mt-2">
                {cost.credits_required.toLocaleString()} credits each time you do this.
              </p>
            )}
          </>
        )}
      </Panel>

      {assets.length > 0 && (
        <Panel
          title="Choose what to test"
          note="Each one says up front what it expects to change, and that is written down before the second run happens. We hold it to that — including when the answer is that it changed nothing."
        >
          <div className="space-y-3">
            {[...byObjection.entries()].map(([key, group]) => (
              <div key={key}>
                <p className="text-[11px] text-saibyl-muted uppercase tracking-wide mb-1.5">
                  {group[0].objection_label}
                </p>
                <div className="space-y-2">
                  {group.map((asset) => {
                    const isSelected = selected.includes(asset.id);
                    return (
                      <button
                        key={asset.id}
                        type="button"
                        onClick={() =>
                          setSelected((prev) =>
                            isSelected ? prev.filter((x) => x !== asset.id) : [...prev, asset.id],
                          )
                        }
                        className={`w-full text-left p-4 rounded-xl border transition-all ${
                          isSelected
                            ? 'border-saibyl-gold/50 bg-saibyl-gold/10'
                            : 'border-white/[0.06] bg-white/[0.02] hover:border-white/[0.12]'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-[13px] font-medium text-saibyl-platinum truncate">
                            {asset.title}
                          </span>
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.04] text-saibyl-muted whitespace-nowrap">
                            {ASSET_TYPE_LABELS[asset.asset_type] ?? asset.asset_type}
                          </span>
                        </div>
                        <p className="text-[12px] text-saibyl-silver mt-1.5 leading-relaxed whitespace-pre-wrap">
                          {asset.body}
                        </p>
                        {asset.hypothesis && (
                          <p className="text-[11px] text-saibyl-muted mt-2 italic">
                            Expects to: {asset.hypothesis}
                          </p>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>

          <div className="mt-5 pt-4 border-t border-white/[0.06]">
            <button
              type="button"
              onClick={resimulate}
              disabled={selected.length === 0 || launching}
              className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-saibyl-gold text-saibyl-void font-semibold text-[13px] disabled:opacity-40 transition-all hover:bg-saibyl-gold-hover"
            >
              {launching ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <FlaskConical className="w-4 h-4" />
              )}
              {selected.length === 1
                ? 'Run it again with this one'
                : `Run it again with these ${selected.length}`}
            </button>
            <p className="text-[11px] text-saibyl-muted mt-2 leading-relaxed">
              The same people react again — the exact ones from this run, not a fresh set — only
              this time they have seen what you wrote. Nothing else changes, so any difference is
              down to your material. You are not charged again for building the room.
            </p>
          </div>
        </Panel>
      )}
    </div>
  );
}
