import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Loader2 } from 'lucide-react';

import api, { unwrapList } from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { isFinished } from '@/lib/status';
import type { Simulation } from '@/types';
import StageHeader from '@/components/stages/StageHeader';
import { EmptyState, Guarded, StageError } from '@/components/stages/StagePrimitives';
import { useProduct, useStage } from '@/components/stages/useProduct';

/**
 * Step 5 — which version of this should I spend money on?
 *
 * Several versions of the same pitch, argued about by **one shared room**, so
 * the comparison is like-for-like. The scoreboard names a winner only when the
 * evidence separates them, and when it does not it says how many more people it
 * would take.
 *
 * The refusal is the feature. A ranking drawn from overlapping bands launders
 * sampling noise into a decision somebody then spends a budget on, so this page
 * shows "too close to call" as a result rather than quietly ordering the rows
 * and letting the reader assume the top one won.
 */

interface Scoreboard {
  winner_variant_key: string | null;
  verdict: string;
  variants: { variant_key: string; label?: string | null }[];
}

export default function MessagesStagePage() {
  const { product } = useProduct();
  const stage = useStage('messages');

  const [runs, setRuns] = useState<Simulation[]>([]);
  const [board, setBoard] = useState<Scoreboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    api
      .get('/simulations', { params: { project_id: product.id, limit: 20 } })
      .then((r) => {
        const items = unwrapList<Simulation>(r.data).items;
        setRuns(items);
        const compared = items.find(
          (s) => isFinished(s.status) && (s.variants ?? 1) > 1,
        );
        if (!compared) {
          setBoard(null);
          return null;
        }
        return api
          .get(`/simulations/${compared.id}/analysis`)
          .then((a) => setBoard(a.data?.scoreboard ?? null))
          // No scoreboard is the normal answer for a run that has not been
          // analysed yet. Kept distinct from a request that failed.
          .catch(() => setBoard(null));
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

  const compared = runs.find(
    (s) => isFinished(s.status) && (s.variants ?? 1) > 1,
  );
  const setupHref = `/app/marketing?project=${product.id}`;

  return (
    <div className="space-y-6">
      <StageHeader stage={stage} />

      {error && <StageError message={error} retry={retry} />}

      {loading && !compared ? (
        <p className="flex items-center gap-2 text-[12.5px] text-saibyl-muted">
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          Loading…
        </p>
      ) : !compared ? (
        <EmptyState
          headline="No versions tested yet"
          body="Write two or more versions of the same pitch. The same room reads all of them, so the difference you see is the wording rather than who happened to be in the room."
          action={{ label: 'Write the versions', href: setupHref }}
        />
      ) : (
        <section className="glass rounded-2xl p-6 space-y-4">
          <h2 className="text-[15px] font-medium text-saibyl-platinum">
            {compared.variants} versions, one room
          </h2>

          {board === null ? (
            <p className="text-[12.5px] text-saibyl-muted leading-relaxed">
              That run finished and the comparison has not been worked out yet.
              Open the run and everything it recorded is there.
            </p>
          ) : board.winner_variant_key ? (
            <>
              <p className="text-[13px] text-saibyl-positive">One version came out ahead.</p>
              <p className="text-[12.5px] text-saibyl-muted leading-relaxed">
                {board.verdict}
              </p>
            </>
          ) : (
            <>
              <p className="text-[13px] text-saibyl-gold">Too close to call.</p>
              <p className="text-[12.5px] text-saibyl-muted leading-relaxed">
                {board.verdict ||
                  'The versions did not separate. Picking the top row would be picking noise.'}
              </p>
            </>
          )}

          <div className="flex flex-wrap items-center gap-3">
            <Guarded
              label="See the comparison"
              to={`/app/simulations/${compared.id}/compare`}
            />
            <Link to={setupHref} className="text-[12.5px] text-saibyl-gold hover:underline">
              Test another set of versions
            </Link>
          </div>
        </section>
      )}
    </div>
  );
}
