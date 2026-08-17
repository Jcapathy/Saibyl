import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Loader2, X } from 'lucide-react';

import api, { unwrapList } from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { StageError } from '@/components/stages/StagePrimitives';
import ClearanceReport from '@/components/clearance/ClearanceReport';
import ClearanceRunForm from '@/components/clearance/ClearanceRunForm';
import { RiskChip, StatusChip } from '@/components/clearance/RiskChip';
import {
  IP_CHECK_NAME,
  NOT_LEGAL_ADVICE,
  TIER_SHORT,
  type ClearanceListRow,
  type ClearanceRun,
  type ClearanceTier,
} from '@/components/clearance/types';

/**
 * IP Check — "is this even mine to build?"
 *
 * A founder submits a name, an idea, or both; the backend runs the USPTO
 * search and this page polls until the report lands. The report renders from
 * the run's JSON artifact only — no number, title or owner appears here that
 * the backend did not read from live USPTO data, and empty never renders as
 * cleared (PRD §11).
 */

interface ProductOption {
  id: string;
  name: string;
}

const TIER_RUNTIME: Record<ClearanceTier, string> = {
  QUICK: 'A snapshot usually takes a minute or two.',
  STANDARD: 'A full search usually takes five to ten minutes.',
  COMPREHENSIVE: 'A deep search usually takes fifteen to twenty-five minutes.',
};

function isWorking(run: ClearanceRun | null): boolean {
  return run !== null && (run.status === 'queued' || run.status === 'running');
}

export default function IpCheckPage() {
  const [products, setProducts] = useState<ProductOption[]>([]);
  const [runs, setRuns] = useState<ClearanceListRow[]>([]);
  const [runsLoading, setRunsLoading] = useState(true);
  const [runsError, setRunsError] = useState('');
  const [selected, setSelected] = useState<ClearanceRun | null>(null);
  const [openError, setOpenError] = useState('');
  const [opening, setOpening] = useState(false);
  const [prefill, setPrefill] = useState<{ item: string; tier: ClearanceTier } | null>(
    null,
  );
  const [formKey, setFormKey] = useState(0);
  const panelRef = useRef<HTMLDivElement>(null);

  /* ── The org's past runs ── */
  const loadRuns = useCallback(() => {
    api
      .get('/clearance')
      .then((r) => {
        const rows = unwrapList<ClearanceListRow>(r.data).items;
        rows.sort(
          (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
        );
        setRuns(rows);
        setRunsError('');
      })
      .catch((err) =>
        setRunsError(getErrorMessage(err, 'We could not load your past checks.')),
      )
      .finally(() => setRunsLoading(false));
  }, []);

  useEffect(() => {
    loadRuns();
  }, [loadRuns]);

  const retryRuns = useCallback(() => {
    setRunsLoading(true);
    loadRuns();
  }, [loadRuns]);

  /* ── Products for the optional picker. A quiet failure here just hides the
        picker — the check itself needs no product to run. ── */
  useEffect(() => {
    let cancelled = false;
    api
      .get('/products')
      .then((r) => {
        if (cancelled) return;
        setProducts(
          unwrapList<ProductOption>(r.data).items.map((p) => ({
            id: p.id,
            name: p.name,
          })),
        );
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  /* ── Poll the open run every 3s while the backend is still searching, so
        "Searching" does not sit there after the worker has finished. ── */
  useEffect(() => {
    if (!selected || !isWorking(selected)) return;
    const id = selected.id;
    const timer = setInterval(() => {
      api
        .get<ClearanceRun>(`/clearance/${id}`)
        .then(({ data }) => {
          setSelected(data);
          if (data.status === 'complete' || data.status === 'failed') loadRuns();
        })
        .catch(() => {
          /* One missed poll is not a failed run — the next tick tries again. */
        });
    }, 3000);
    return () => clearInterval(timer);
  }, [selected, loadRuns]);

  const openRun = useCallback((id: string) => {
    setOpenError('');
    setOpening(true);
    api
      .get<ClearanceRun>(`/clearance/${id}`)
      .then(({ data }) => setSelected(data))
      .catch((err) =>
        setOpenError(getErrorMessage(err, 'We could not open that report.')),
      )
      .finally(() => setOpening(false));
  }, []);

  /* Scroll the opened report into view — it renders above the fold, but the
     click that opened it happened further down the page. */
  const selectedId = selected?.id;
  useEffect(() => {
    if (selectedId) panelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [selectedId]);

  function started(run: ClearanceRun) {
    setPrefill(null);
    setSelected(run);
    loadRuns();
  }

  /* A failed run's way forward: the same search, set up again for review
     rather than silently re-charged. Remounting the form applies the prefill. */
  function setUpAgain(run: ClearanceRun) {
    setPrefill({ item: run.item, tier: run.tier });
    setFormKey((k) => k + 1);
    setSelected(null);
  }

  return (
    <div className="p-6 lg:p-8 bg-saibyl-void min-h-full">
      <div className="max-w-4xl mx-auto space-y-6">
        {/* ── Header ── */}
        <div>
          <h1 className="text-h1 text-saibyl-white">{IP_CHECK_NAME}</h1>
          <p className="text-[13px] text-saibyl-muted mt-1">
            Search the USPTO before you build &mdash; trademarks, prior art, and
            what&rsquo;s still pending.
          </p>
        </div>

        {/* ── The open run: progress, failure, or the report ── */}
        {opening && !selected && (
          <p className="flex items-center gap-2 text-[12.5px] text-saibyl-muted">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            Opening that report&hellip;
          </p>
        )}
        {openError && <StageError message={openError} />}

        {selected && (
          <div ref={panelRef} className="scroll-mt-6 space-y-4">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
              <h2 className="text-[15px] font-medium text-saibyl-platinum min-w-0">
                {selected.item}
              </h2>
              <span className="text-[11px] text-saibyl-muted">
                {TIER_SHORT[selected.tier]}
              </span>
              <StatusChip status={selected.status} />
              <button
                type="button"
                onClick={() => setSelected(null)}
                className="ml-auto inline-flex items-center gap-1 text-[12px] text-saibyl-muted hover:text-saibyl-platinum transition-colors"
              >
                <X className="w-3.5 h-3.5" />
                Put this away
              </button>
            </div>

            {isWorking(selected) ? (
              <div className="glass rounded-2xl p-6">
                <p className="flex items-center gap-2.5 text-[14px] text-saibyl-platinum">
                  <Loader2 className="w-4 h-4 animate-spin text-saibyl-gold" />
                  {selected.status === 'queued'
                    ? 'In the queue — the search starts in a moment.'
                    : 'Searching the USPTO…'}
                </p>
                <p className="text-[12.5px] text-saibyl-muted mt-2 leading-relaxed">
                  {TIER_RUNTIME[selected.tier]} You can leave this page — the run
                  keeps going and the report will be waiting here.
                </p>
              </div>
            ) : selected.status === 'failed' ? (
              <div className="rounded-2xl border border-saibyl-negative/25 bg-saibyl-negative/[0.07] p-6">
                <p className="text-[13.5px] text-saibyl-negative leading-relaxed">
                  {selected.error_message || 'This search did not finish.'}
                </p>
                <button
                  type="button"
                  onClick={() => setUpAgain(selected)}
                  className="inline-flex items-center gap-1.5 mt-4 px-4 py-2 rounded-xl bg-saibyl-gold text-saibyl-void text-[13px] font-semibold hover:bg-saibyl-gold-hover transition-colors"
                >
                  Set this search up again
                </button>
              </div>
            ) : selected.artifact ? (
              <ClearanceReport artifact={selected.artifact} />
            ) : selected.report_markdown ? (
              /* The artifact did not survive the trip; the written report did.
                 Render what is real rather than a reconstruction of it. */
              <div className="glass rounded-2xl p-6">
                <p className="text-[11.5px] text-saibyl-muted mb-4">{NOT_LEGAL_ADVICE}</p>
                <pre className="whitespace-pre-wrap font-sans text-[12.5px] text-saibyl-platinum leading-relaxed">
                  {selected.report_markdown}
                </pre>
              </div>
            ) : (
              <div className="rounded-2xl border border-saibyl-negative/25 bg-saibyl-negative/[0.07] p-6">
                <p className="text-[13.5px] text-saibyl-negative leading-relaxed">
                  This search finished but its report could not be read.
                </p>
                <button
                  type="button"
                  onClick={() => setUpAgain(selected)}
                  className="inline-flex items-center gap-1.5 mt-4 px-4 py-2 rounded-xl bg-saibyl-gold text-saibyl-void text-[13px] font-semibold hover:bg-saibyl-gold-hover transition-colors"
                >
                  Set this search up again
                </button>
              </div>
            )}
          </div>
        )}

        {/* ── The form ── */}
        <div id="clearance-form" className="scroll-mt-6">
          <ClearanceRunForm
            key={formKey}
            products={products}
            initialItem={prefill?.item}
            initialTier={prefill?.tier}
            onStarted={started}
          />
        </div>

        {/* ── Past checks ── */}
        <section className="glass rounded-2xl p-6">
          <h2 className="text-[15px] font-medium text-saibyl-platinum">Past checks</h2>
          <p className="text-[12px] text-saibyl-muted mt-1">
            Every check this account has run. Open one to reread its report.
          </p>

          {runsError && (
            <div className="mt-4">
              <StageError message={runsError} retry={retryRuns} />
            </div>
          )}

          {runsLoading && runs.length === 0 ? (
            <p className="flex items-center gap-2 text-[12.5px] text-saibyl-muted mt-4">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              Loading&hellip;
            </p>
          ) : runs.length === 0 && !runsError ? (
            <p className="text-[12.5px] text-saibyl-muted mt-4 leading-relaxed">
              Nothing here yet.{' '}
              <Link to="#clearance-form" className="text-saibyl-gold hover:underline">
                The form above
              </Link>{' '}
              is where the first one starts &mdash; the snapshot costs nothing.
            </p>
          ) : (
            <ul className="mt-4 space-y-2">
              {runs.map((row) => (
                <li key={row.id}>
                  <button
                    type="button"
                    onClick={() => openRun(row.id)}
                    className={`w-full text-left rounded-xl border p-3.5 transition-all flex flex-wrap items-center gap-x-3 gap-y-1.5 ${
                      selected?.id === row.id
                        ? 'border-saibyl-gold/50 bg-saibyl-gold/[0.06]'
                        : 'border-saibyl-border bg-white hover:border-saibyl-border-light'
                    }`}
                  >
                    <span className="text-[13px] text-saibyl-platinum truncate flex-1 min-w-[10rem]">
                      {row.item}
                    </span>
                    <span className="text-[11px] text-saibyl-muted">
                      {TIER_SHORT[row.tier]}
                    </span>
                    <StatusChip status={row.status} />
                    {row.risk && <RiskChip risk={row.risk} />}
                    <span className="text-[11px] text-saibyl-muted font-mono tabular-nums">
                      {new Date(row.created_at).toLocaleDateString(undefined, {
                        month: 'short',
                        day: 'numeric',
                      })}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
