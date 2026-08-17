import { useCallback, useEffect, useState } from 'react';
import { Link, Outlet, useLocation, useParams } from 'react-router-dom';
import { ArrowLeft, Loader2 } from 'lucide-react';

import api from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { STAGES, stageHref, type ProductState, type StageState } from '@/lib/stages';
import { StageError } from '@/components/stages/StagePrimitives';
import type { ProductContext } from '@/components/stages/useProduct';

/**
 * Everything inside one product: the rail down the side, the stage on the right.
 *
 * The product's whole state is fetched **once, here**, and handed down. Each
 * stage page therefore renders what it inherited without going and asking — and
 * more importantly, without each page inventing its own idea of what "the
 * audience is confirmed" means. That reasoning lives on the server, in
 * `services/stages/`, and this layout is the only thing that reads it.
 */

/* ------------------------------------------------------------------ */
/*  The rail                                                           */
/* ------------------------------------------------------------------ */

function RailItem({
  productId,
  stage,
  active,
}: {
  productId: string;
  stage: StageState;
  active: boolean;
}) {
  return (
    <Link
      /*
        Built from the client's own route table rather than the `href` the
        server sent. The server's href is right, and it is what the inherited
        lines and the unblocking buttons use — but the rail is *navigation*, and
        a navigation whose targets arrive over the wire is a second source of
        truth for the route table. The two agreeing today is not a guarantee
        they agree after the next route change.
      */
      to={stageHref(productId, stage.id)}
      className={`block rounded-xl border px-3.5 py-3 transition-colors ${
        active
          ? 'border-saibyl-gold/40 bg-saibyl-gold/[0.07]'
          : 'border-saibyl-border bg-white hover:border-saibyl-border-light'
      }`}
    >
      <div className="flex items-baseline gap-2.5">
        <span
          className={`font-mono text-[13px] tabular-nums ${
            active ? 'text-saibyl-gold' : 'text-saibyl-muted'
          }`}
        >
          {stage.number}
        </span>
        <span
          className={`text-[13px] font-medium ${
            active ? 'text-saibyl-white' : 'text-saibyl-platinum'
          }`}
        >
          {stage.label}
        </span>
      </div>
      <p className="text-[11px] text-saibyl-muted mt-0.5 leading-snug pl-[1.4rem]">
        {stage.blurb}
      </p>
      {/*
        What this step has produced, on the rail itself. Rendered only when the
        server had something to say — a stage with nothing yet shows nothing,
        rather than a dash or a zero that reads as a measurement of nothing.
      */}
      {stage.produced && (
        <p className="text-[11px] text-saibyl-silver mt-1.5 leading-snug pl-[1.4rem]">
          {stage.produced}
        </p>
      )}
      {stage.runnable !== 'ready' && (
        <p
          className={`text-[10.5px] mt-1.5 leading-snug pl-[1.4rem] ${
            stage.runnable === 'blocked' ? 'text-[#6a4fe0]' : 'text-saibyl-warning'
          }`}
        >
          {stage.runnable === 'blocked'
            ? 'Needs something first'
            : 'Will run, but thinner'}
        </p>
      )}
    </Link>
  );
}

/* ------------------------------------------------------------------ */
/*  Layout                                                             */
/* ------------------------------------------------------------------ */

export default function ProductLayout() {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const [product, setProduct] = useState<ProductState | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    if (!id) return;
    api
      .get<ProductState>(`/products/${id}`)
      .then(({ data }) => {
        setProduct(data);
        setError('');
      })
      .catch((err) => setError(getErrorMessage(err, 'We could not open this product.')))
      .finally(() => setLoading(false));
  }, [id]);

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

  const active = STAGES.find((s) => location.pathname.endsWith(`/${s.segment}`));

  if (loading && !product) {
    return (
      <div className="p-8 flex items-center gap-2.5 text-saibyl-muted text-[13px]">
        <Loader2 className="w-4 h-4 animate-spin" />
        Opening…
      </div>
    );
  }

  if (!product) {
    return (
      <div className="p-8 max-w-2xl">
        <StageError
          message={error || 'We could not open this product.'}
          retry={retry}
        />
        <Link
          to="/app/home"
          className="inline-flex items-center gap-1.5 mt-4 text-[13px] text-saibyl-gold hover:underline"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Back to your products
        </Link>
      </div>
    );
  }

  return (
    <div className="p-6 lg:p-8 bg-saibyl-void min-h-full">
      <div className="max-w-6xl mx-auto">
        <Link
          to="/app/home"
          className="inline-flex items-center gap-1.5 text-[12px] text-saibyl-muted hover:text-saibyl-platinum transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Your products
        </Link>

        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 mt-3 mb-6">
          <h1 className="text-h1 text-saibyl-white">{product.name}</h1>
          <span className="text-[12px] text-saibyl-muted">
            {product.stages_ready} of {product.stages.length} steps have what they
            need
          </span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[15rem_1fr] gap-6 lg:gap-8">
          <nav className="space-y-2" aria-label="Steps">
            {product.stages.map((stage) => (
              <RailItem
                key={stage.id}
                productId={product.id}
                stage={stage}
                active={active?.id === stage.id}
              />
            ))}
          </nav>

          <div className="min-w-0">
            <Outlet context={{ product, refresh: load } satisfies ProductContext} />
          </div>
        </div>
      </div>
    </div>
  );
}
