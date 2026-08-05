import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Loader2 } from 'lucide-react';

import api, { unwrapList } from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { isFinished, isUnderway } from '@/lib/status';
import type { Simulation } from '@/types';
import MomentPicker from '@/components/stages/MomentPicker';
import StageHeader from '@/components/stages/StageHeader';
import { EmptyState, Guarded, StageError } from '@/components/stages/StagePrimitives';
import { useProduct, useStage } from '@/components/stages/useProduct';

/**
 * Step 2 — will anyone want this, and what will they say against it?
 *
 * The audience argues about your material. Out comes a headline with its
 * confidence band and the objections ranked by how much of the room carries
 * them.
 *
 * This is where the free run ends, and it ends on the most interesting screen in
 * the product. The moment picker above the button is Axis B — asked per run,
 * defaulted from whatever the last run used, because the same product at
 * pre-launch and at growth wants a different mix of people in the room.
 */

interface ObjectionRow {
  objection_key: string;
  label: string;
  summary: string | null;
  agent_count: number | null;
  load_bearing_score: number | null;
}

export default function ReactionsStagePage() {
  const { product } = useProduct();
  const stage = useStage('reactions');

  const [runs, setRuns] = useState<Simulation[]>([]);
  const [objections, setObjections] = useState<ObjectionRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [moment, setMoment] = useState(product.moment.id);

  const load = useCallback(() => {
    api
      .get('/simulations', { params: { project_id: product.id, limit: 20 } })
      .then((r) => {
        const items = unwrapList<Simulation>(r.data).items;
        setRuns(items);
        const finished = items.find((s) => isFinished(s.status));
        if (!finished) {
          setObjections([]);
          return null;
        }
        return api
          .get(`/simulations/${finished.id}/objections`)
          .then((o) => setObjections(unwrapList<ObjectionRow>(o.data).items));
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

  const finished = runs.find((s) => isFinished(s.status));
  const inFlight = runs.find((s) => isUnderway(s.status));

  // Axis B rides along as a query parameter so the run configurator opens on the
  // moment the founder just picked rather than making them pick it twice.
  const startHref =
    `/app/simulations/new?project=${product.id}&founder_stage=${moment}`;

  return (
    <div className="space-y-6">
      <StageHeader stage={stage} />

      {error && <StageError message={error} retry={retry} />}

      <section className="glass rounded-2xl p-6">
        <h2 className="text-[15px] font-medium text-saibyl-platinum">
          Put this in front of the room
        </h2>
        <p className="text-[12.5px] text-saibyl-muted mt-1.5 leading-relaxed">
          Your buyers read your material and argue about it across a few places
          online. You get back what they said, and the objections ranked by how
          much of the room actually carries them.
        </p>

        <div className="mt-5">
          <MomentPicker value={moment} onChange={setMoment} source={product.moment.source} />
        </div>

        <div className="mt-5">
          {inFlight ? (
            <Link
              to={`/app/simulations/${inFlight.id}/run`}
              className="inline-flex items-center gap-2 text-[13px] text-saibyl-gold hover:underline"
            >
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              A run is going now — watch it
            </Link>
          ) : (
            <Guarded label="Start a run" to={startHref} />
          )}
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-[15px] font-medium text-saibyl-platinum">
          What they objected to
        </h2>

        {loading && objections.length === 0 ? (
          <p className="flex items-center gap-2 text-[12.5px] text-saibyl-muted">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            Loading…
          </p>
        ) : objections.length === 0 ? (
          <EmptyState
            headline={
              finished
                ? 'That run finished, but nothing has been grouped out of it yet'
                : 'Nothing has run yet'
            }
            body={
              finished
                ? 'The run completed and we are still grouping what people said into the things they objected to. If this does not change, open the run and the raw reactions are all there.'
                : 'Once a run finishes, the things people pushed back on show up here — ranked by how much of the room carried each one, not by how often the words appeared.'
            }
            action={
              finished
                ? { label: 'Open the run', href: `/app/simulations/${finished.id}` }
                : { label: 'Start a run', href: startHref }
            }
          />
        ) : (
          <>
            <ul className="space-y-2">
              {objections.map((row) => (
                <li
                  key={row.objection_key}
                  className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-4 py-3.5"
                >
                  <div className="flex items-baseline justify-between gap-3">
                    <p className="text-[13.5px] text-saibyl-platinum">{row.label}</p>
                    {/* Rendered only when the count is a real number. A dash
                        here would read as "nobody", which is a finding. */}
                    {typeof row.agent_count === 'number' && (
                      <span className="text-[11px] text-saibyl-muted shrink-0">
                        {row.agent_count} {row.agent_count === 1 ? 'person' : 'people'}
                      </span>
                    )}
                  </div>
                  {row.summary && (
                    <p className="text-[12px] text-saibyl-muted mt-1 leading-relaxed">
                      {row.summary}
                    </p>
                  )}
                </li>
              ))}
            </ul>

            <div className="flex flex-wrap items-center gap-3 pt-1">
              <Guarded
                label="Answer these"
                to={`/app/products/${product.id}/answers`}
              />
              {finished && (
                <Link
                  to={`/app/simulations/${finished.id}`}
                  className="text-[12.5px] text-saibyl-gold hover:underline"
                >
                  See everything from that run
                </Link>
              )}
            </div>
          </>
        )}
      </section>
    </div>
  );
}
