import { useCallback, useEffect, useRef, useState } from 'react';
import { Loader2, X } from 'lucide-react';

import api, { unwrapList } from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { cn } from '@/lib/utils';
import { Card, Eyebrow, cardSurface } from '@/components/design';
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
 * "Is this even mine to build?" — the USPTO check, folded into the idea stage.
 *
 * The founder's call, and it is a correction rather than a move: the clearance
 * check was a top-level module only because it had nowhere else to live. It is
 * an idea-stage question. A founder who finds a live trademark in week one
 * renames a product; the same founder finds it in month nine and renames a
 * company.
 *
 * ── What this reuses, and what it deliberately does not restate ─────────────
 *
 * Every rendered surface here belongs to `components/clearance/`:
 * `ClearanceRunForm` is the only thing that starts a run, `ClearanceReport` is
 * the only thing that renders one, and `RiskChip` / `StatusChip` / `TIER_SHORT`
 * / `NOT_LEGAL_ADVICE` / `IP_CHECK_NAME` are the shared vocabulary. Nothing
 * about the report is re-implemented, because a second renderer is a second
 * answer to "what did the USPTO actually say".
 *
 * What this file does carry is the orchestration `IpCheckPage` also carries —
 * list, open, poll — because that lives in a page component and a page cannot
 * be embedded in a card. It is kept deliberately thin, and one thing is
 * **left out on purpose**: the per-tier "usually takes N minutes" sentences are
 * private to `IpCheckPage`, and copying them here would create exactly the
 * two-sources-of-truth defect this codebase keeps producing. The wait sentence
 * below is tier-independent instead, and the tier itself is named by the chip
 * beside it.
 *
 * Rendered outside the product picker on purpose. The check needs no product to
 * run — "is the name taken" is the one question a founder asks before there is
 * anything to run a room against.
 */

function isWorking(run: ClearanceRun | null): boolean {
  return run !== null && (run.status === 'queued' || run.status === 'running');
}

interface ProductOption {
  id: string;
  name: string;
}

export default function ClearanceCard({ products }: { products: ProductOption[] }) {
  const [runs, setRuns] = useState<ClearanceListRow[]>([]);
  const [runsLoading, setRunsLoading] = useState(true);
  const [runsError, setRunsError] = useState('');
  const [selected, setSelected] = useState<ClearanceRun | null>(null);
  const [openError, setOpenError] = useState('');
  const [opening, setOpening] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [prefill, setPrefill] = useState<{ item: string; tier: ClearanceTier } | null>(
    null,
  );
  const [formKey, setFormKey] = useState(0);
  const panelRef = useRef<HTMLDivElement>(null);

  /* ── Every check this account has run ── */
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

  /* Retrying is a click, so it says so. `loadRuns` itself never sets this: an
     effect that sets state synchronously on mount is a cascading render, and
     `runsLoading` already starts true. */
  const retryRuns = useCallback(() => {
    setRunsLoading(true);
    loadRuns();
  }, [loadRuns]);

  /* ── Poll the open run while the backend is still searching, so "Searching"
        does not sit there after the worker has finished. ── */
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

  /* Scroll the opened report into view — the click that opened it happened in
     the list above, and the report is longer than the card that names it. */
  const selectedId = selected?.id;
  useEffect(() => {
    if (selectedId) {
      panelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [selectedId]);

  function started(run: ClearanceRun) {
    setPrefill(null);
    setShowForm(false);
    setSelected(run);
    loadRuns();
  }

  /* A failed run's way forward: the same search, set up again for review rather
     than silently re-charged. Remounting the form applies the prefill. */
  function setUpAgain(run: ClearanceRun) {
    setPrefill({ item: run.item, tier: run.tier });
    setFormKey((k) => k + 1);
    setSelected(null);
    setShowForm(true);
  }

  function openForm() {
    setPrefill(null);
    setShowForm(true);
  }

  return (
    <section className="space-y-4">
      <Card carries="meaning" className="p-6">
        <Eyebrow>{IP_CHECK_NAME}</Eyebrow>
        <h2 className="text-[15px] font-medium text-saibyl-ink mt-2">
          Is this even mine to build?
        </h2>
        <p className="text-[12.5px] text-saibyl-muted mt-1.5 leading-relaxed max-w-2xl">
          Search the USPTO before you build &mdash; the name against live
          trademarks, the mechanism against granted patents, and the filings that
          are still pending and cannot be seen any other way. Find a conflict now
          and you rename a product. Find it after launch and you rename a company.
        </p>
        <p className="text-[11.5px] text-saibyl-muted mt-2">{NOT_LEGAL_ADVICE}</p>

        {runsError && (
          <div className="mt-4">
            <StageError message={runsError} retry={retryRuns} />
          </div>
        )}

        <div className="mt-5">
          {runsLoading && runs.length === 0 ? (
            <p
              className="flex items-center gap-2 text-[12.5px] text-saibyl-muted"
              aria-live="polite"
            >
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              Loading&hellip;
            </p>
          ) : runs.length === 0 && !runsError ? (
            <p className="text-[12.5px] text-saibyl-muted leading-relaxed">
              Nothing checked yet &mdash; the snapshot costs nothing and takes
              about a minute.{' '}
              <button
                type="button"
                onClick={openForm}
                className="text-saibyl-blue hover:underline"
              >
                Check a name or an idea
              </button>
            </p>
          ) : (
            <>
              <p className="text-[12px] text-saibyl-silver">
                Checks this account has run. Open one to reread its report.
              </p>
              <ul className="mt-2.5 space-y-1.5">
                {runs.map((row) => (
                  <li key={row.id}>
                    <button
                      type="button"
                      onClick={() => openRun(row.id)}
                      className={cn(
                        cardSurface('density'),
                        'w-full rounded-xl p-3.5 text-left transition-colors flex flex-wrap items-center gap-x-3 gap-y-1.5',
                        selected?.id === row.id
                          ? 'border-saibyl-blue/45 bg-saibyl-blue/[0.05]'
                          : 'hover:border-saibyl-border-light',
                      )}
                    >
                      <span className="text-[13px] text-saibyl-ink truncate flex-1 min-w-[10rem]">
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

              {!showForm && (
                <button
                  type="button"
                  onClick={openForm}
                  className="mt-3 text-[12.5px] text-saibyl-blue hover:underline"
                >
                  Check something else
                </button>
              )}
            </>
          )}
        </div>
      </Card>

      {/* ── The open run: progress, failure, or the report ── */}
      {opening && !selected && (
        <p
          className="flex items-center gap-2 text-[12.5px] text-saibyl-muted"
          aria-live="polite"
        >
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          Opening that report&hellip;
        </p>
      )}
      {openError && <StageError message={openError} />}

      {selected && (
        <div ref={panelRef} className="scroll-mt-6 space-y-4">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <h3 className="text-[15px] font-medium text-saibyl-ink min-w-0">
              {selected.item}
            </h3>
            <span className="text-[11px] text-saibyl-muted">
              {TIER_SHORT[selected.tier]}
            </span>
            <StatusChip status={selected.status} />
            {selected.risk && <RiskChip risk={selected.risk} />}
            <button
              type="button"
              onClick={() => setSelected(null)}
              className="ml-auto inline-flex items-center gap-1 text-[12px] text-saibyl-muted hover:text-saibyl-ink transition-colors"
            >
              <X className="w-3.5 h-3.5" />
              Put this away
            </button>
          </div>

          {isWorking(selected) ? (
            <Card carries="meaning" className="p-6">
              <p className="flex items-center gap-2.5 text-[14px] text-saibyl-ink">
                <Loader2 className="w-4 h-4 animate-spin text-saibyl-blue" />
                {selected.status === 'queued'
                  ? 'In the queue — the search starts in a moment.'
                  : 'Searching the USPTO…'}
              </p>
              <p className="text-[12.5px] text-saibyl-muted mt-2 leading-relaxed">
                A deeper search takes longer. You can leave this page &mdash; the
                run keeps going and the report will be waiting here.
              </p>
            </Card>
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
            <Card carries="meaning" className="p-6">
              <p className="text-[11.5px] text-saibyl-muted mb-4">{NOT_LEGAL_ADVICE}</p>
              <pre className="whitespace-pre-wrap font-sans text-[12.5px] text-saibyl-ink leading-relaxed">
                {selected.report_markdown}
              </pre>
            </Card>
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

      {/* ── The form, asked for rather than always open ──
          The card above is a standing offer; this is the surface that spends
          credits, and a founder who came here to read last week's report should
          not have to scroll past it. */}
      {showForm && (
        <div id="clearance-form" className="scroll-mt-6">
          <ClearanceRunForm
            key={formKey}
            products={products}
            initialItem={prefill?.item}
            initialTier={prefill?.tier}
            onStarted={started}
          />
        </div>
      )}
    </section>
  );
}
