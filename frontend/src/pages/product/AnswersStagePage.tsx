import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Loader2 } from 'lucide-react';

import api, { unwrapList } from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { isFinished } from '@/lib/status';
import {
  ASSET_TYPE_LABELS,
  isEffective,
  VERDICT_COPY,
  VERDICT_TONE,
  type InoculationAsset,
  type InoculationResult,
} from '@/lib/founder';
import type { Simulation } from '@/types';
import StageHeader from '@/components/stages/StageHeader';
import { EmptyState, Guarded, StageError } from '@/components/stages/StagePrimitives';
import { useProduct, useStage } from '@/components/stages/useProduct';

/**
 * Step 3 — what do I say to the people who said no?
 *
 * For each objection, draft the counter-material, publish it, and run the *same*
 * room again to find out whether the objection actually died. An answer that
 * moves nothing is reported as moving nothing.
 *
 * This is the one stage that is genuinely blocked rather than merely weaker
 * without its input: you cannot draft an answer to an objection nobody raised.
 * `StageHeader` renders that state, with the button that unblocks it — the
 * server decides, this page does not second-guess it.
 */

const TONE_CLASS: Record<'good' | 'bad' | 'neutral', string> = {
  good: 'text-saibyl-positive',
  bad: 'text-saibyl-negative',
  neutral: 'text-saibyl-muted',
};

export default function AnswersStagePage() {
  const { product } = useProduct();
  const stage = useStage('answers');

  const [source, setSource] = useState<Simulation | null>(null);
  const [assets, setAssets] = useState<InoculationAsset[]>([]);
  const [result, setResult] = useState<InoculationResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    api
      .get('/simulations', { params: { project_id: product.id, limit: 20 } })
      .then((r) => {
        const finished = unwrapList<Simulation>(r.data).items.find(
          (s) => isFinished(s.status) && !s.parent_simulation_id,
        );
        setSource(finished ?? null);
        if (!finished) return null;
        return Promise.all([
          api
            .get(`/inoculation/${finished.id}/assets`)
            .then((a) => setAssets(unwrapList<InoculationAsset>(a.data).items)),
          api
            .get<InoculationResult>(`/inoculation/${finished.id}/result`)
            .then((res) => setResult(res.data))
            // A 404 here is the ordinary state before the second run, not a
            // failure. Distinguished from a real error so the two do not
            // render the same.
            .catch(() => setResult(null)),
        ]);
      })
      .then(() => setError(''))
      .catch((err) => setError(getErrorMessage(err, 'We could not read this step.')))
      .finally(() => setLoading(false));
  }, [product.id]);

  useEffect(() => {
    load();
  }, [load]);

  /* Retrying is a click, so it says so. `load` itself never sets this: an
     effect that sets state synchronously on mount is a cascading render, and
     `loading` already starts true. */
  const retry = useCallback(() => {
    setLoading(true);
    load();
  }, [load]);


  if (stage.runnable === 'blocked') {
    // The header already carries the reason and the button. Repeating it below
    // would be the same sentence twice.
    return (
      <div className="space-y-6">
        <StageHeader stage={stage} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <StageHeader stage={stage} />

      {error && <StageError message={error} retry={retry} />}

      {loading && assets.length === 0 ? (
        <p className="flex items-center gap-2 text-[12.5px] text-saibyl-muted">
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          Loading…
        </p>
      ) : assets.length === 0 ? (
        <EmptyState
          headline="Nothing drafted yet"
          body="Pick the objections worth answering, and Saibyl drafts the material that answers them — a pricing rationale, a security page, a migration guide. Then the same room reads it and we measure whether the objection actually died."
          action={{
            label: 'Draft the answers',
            href: source ? `/app/simulations/${source.id}` : `/app/products/${product.id}/reactions`,
          }}
        />
      ) : (
        <>
          <section className="space-y-3">
            <h2 className="text-[15px] font-medium text-saibyl-platinum">
              What you would say back
            </h2>
            <ul className="space-y-2">
              {assets.map((asset) => (
                <li
                  key={asset.id}
                  className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-4 py-3.5"
                >
                  <div className="flex items-baseline justify-between gap-3">
                    <p className="text-[13.5px] text-saibyl-platinum">{asset.title}</p>
                    <span className="text-[11px] text-saibyl-muted shrink-0">
                      {ASSET_TYPE_LABELS[asset.asset_type] ?? asset.asset_type}
                    </span>
                  </div>
                  <p className="text-[12px] text-saibyl-muted mt-1 leading-relaxed">
                    Answers: {asset.objection_label}
                  </p>
                </li>
              ))}
            </ul>
          </section>

          <section className="space-y-3">
            <h2 className="text-[15px] font-medium text-saibyl-platinum">
              Did it work?
            </h2>
            {result === null ? (
              <div className="glass rounded-2xl p-6">
                <p className="text-[12.5px] text-saibyl-muted leading-relaxed">
                  Nothing has been tested yet. Publishing these and running the
                  same room again is what turns them from a plausible answer into
                  a measured one — and some of them will not work, which is the
                  point of measuring.
                </p>
                <div className="mt-4">
                  <Guarded
                    label="Test these answers"
                    to={source ? `/app/simulations/${source.id}` : `/app/products/${product.id}/reactions`}
                  />
                </div>
              </div>
            ) : (
              <>
                <p className="text-[13px] text-saibyl-silver">
                  {result.assets_effective} of {result.assets_tested} actually moved
                  the objection they were written for.
                </p>
                <ul className="space-y-2">
                  {result.deltas.map((delta) => (
                    <li
                      key={delta.objection_key}
                      className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-4 py-3.5"
                    >
                      <div className="flex items-baseline justify-between gap-3">
                        <p className="text-[13.5px] text-saibyl-platinum">
                          {delta.label}
                        </p>
                        <span
                          className={`text-[11.5px] shrink-0 ${
                            TONE_CLASS[VERDICT_TONE[delta.verdict] ?? 'neutral']
                          }`}
                        >
                          {VERDICT_COPY[delta.verdict] ?? delta.verdict}
                        </span>
                      </div>
                      {!isEffective(delta) && (
                        <p className="text-[11.5px] text-saibyl-muted mt-1 leading-relaxed">
                          This one did not shift. Worth rewriting rather than
                          shipping.
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
                {source && (
                  <Link
                    to={`/app/simulations/${source.id}`}
                    className="inline-block text-[12.5px] text-saibyl-gold hover:underline"
                  >
                    See the full before-and-after
                  </Link>
                )}
              </>
            )}
          </section>
        </>
      )}
    </div>
  );
}
