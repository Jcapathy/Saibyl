import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Download,
  FileText,
  Loader2,
  MessageSquare,
  Users,
} from 'lucide-react';

import api, { unwrapList } from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { EmptyState, StageError } from '@/components/stages/StagePrimitives';
import { Card, Deal, Ground, PageHeader, Rise } from '@/components/design';

/**
 * One place to take your work out of the product, and shortcuts to the rest.
 *
 * **This is not the dashboard it replaces.** That one was an account summary —
 * a run count, an agent count and a list of recent runs — all of which already
 * exist on `/app/home` and in the sidebar. It was a second front door, nothing
 * linked to it, and it duplicated the surface that actually walks a founder
 * through the product.
 *
 * What was missing instead: **reports could only be reached one at a time,
 * through the run that produced them.** And `/api/exports` — which turns a
 * report into a PDF, a deck or raw JSON — had **no caller anywhere in the
 * frontend**. The PDF renderer was repaired on 2026-08-05 (the base image ships
 * no fonts; the upload had no `upsert`) and stayed unreachable, so the fix
 * shipped to nobody.
 *
 * So this page is the export surface: every report you have, and three ways to
 * get each one out. A founder who has done a quarter of work here can take it
 * to a board meeting, which is the thing they could not do at all before.
 *
 * ---
 *
 * **Restyled onto the design system on 2026-08-23**, having been built after
 * the canvas was approved and without opening it. What was wrong here is the
 * same list `ProductHomePage` carried:
 *
 * 1. `bg-saibyl-void` on the page root — a flat `#f8fbff` panel laid *over*
 *    the radial wash `<body>` carries, which is canvas rule 1 switched off.
 * 2. `saibyl-white`, `saibyl-platinum` and `saibyl-gold` throughout — legacy
 *    dark-theme aliases that still resolve to light values, which is exactly
 *    why nobody noticed the page had never been converted.
 * 3. No eyebrow, no accent phrase, no depth and no arrival motion.
 *
 * On the two shapes below: the report list is a **dense** surface — hairline
 * rows, no shadow, and its format controls stay chip-sized, because three
 * gradient buttons per row on a list of thirty reports is thirty claims that
 * this is the thing to press. The shortcuts underneath are `meaning` cards and
 * they lift, because each one goes somewhere.
 */

interface ReportRow {
  id: string;
  status: string | null;
  created_at: string | null;
  simulation_id: string | null;
  /** Null when the run was deleted. Rendered as absent, never as "Untitled". */
  run_name: string | null;
  product_name: string | null;
}

type Format = 'pdf' | 'pptx' | 'json';

const FORMATS: { id: Format; label: string; hint: string }[] = [
  { id: 'pdf', label: 'PDF', hint: 'The written report, typeset to read or print' },
  { id: 'pptx', label: 'Slides', hint: 'PowerPoint, for putting in front of people' },
  { id: 'json', label: 'Data', hint: 'Everything behind it, machine readable' },
];

/* A chip, not an action. `Action` is the artboard's gradient shape and it owns
   its own padding at `9px 15px`; used here it would grow every row in a dense
   list by six pixels three times over, and the canvas's density constraint —
   "same row rhythm" — is the one rule a shared component library breaks
   fastest. Radius 11px is the artboard's own chip scale. */
const CHIP_CLASS =
  'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-[11px] border border-saibyl-border bg-white text-[12px] text-saibyl-ink hover:border-saibyl-blue/40 hover:text-saibyl-blue transition-colors';

const SHORTCUTS = [
  {
    to: '/app/home',
    label: 'Your products',
    blurb: 'Start here — every product and what each step still needs',
    Icon: FileText,
  },
  {
    to: '/app/audiences',
    label: 'Audiences you can reuse',
    blurb: 'Buyers you already worked out, ready for anything else you sell',
    Icon: Users,
  },
  /* Companies used to be the third entry here. It is gone by decision: GTM
     discovery ranks candidates against a buyer profile rather than against
     any intent to buy, and on a live security run it returned the competitors
     building the same product. The module and its routes remain, so the call
     is reversible; this was the last surface still recommending it. */
  {
    to: '/app/launch',
    label: 'Message tests',
    blurb: 'Several versions of a pitch, in front of one shared room',
    Icon: MessageSquare,
  },
];

function whenReadable(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? null
    : d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
}

export default function DashboardPage() {
  const [reports, setReports] = useState<ReportRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  /** Keyed `${reportId}:${format}` so two downloads can run at once. */
  const [working, setWorking] = useState<Record<string, boolean>>({});
  const [failures, setFailures] = useState<Record<string, string>>({});

  const load = useCallback(() => {
    api
      .get('/reports')
      .then((r) => {
        setReports(unwrapList<ReportRow>(r.data).items);
        setError('');
      })
      .catch((err) =>
        setError(getErrorMessage(err, 'We could not load your reports.')),
      )
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const retry = useCallback(() => {
    setLoading(true);
    load();
  }, [load]);

  async function download(report: ReportRow, format: Format) {
    const key = `${report.id}:${format}`;
    setWorking((w) => ({ ...w, [key]: true }));
    setFailures((f) => {
      const next = { ...f };
      delete next[key];
      return next;
    });
    try {
      const { data } = await api.post<{ download_url: string }>(
        `/reports/${report.id}/export`,
        { format },
      );
      // The server signs a URL rather than streaming bytes, so the browser
      // fetches it directly. Opened rather than navigated to, so a failed
      // download does not lose the page the founder was on.
      window.open(data.download_url, '_blank', 'noopener');
    } catch (err) {
      // Surfaced against the exact button that failed. The export endpoint
      // states its own failures ("Export produced a file but no download URL
      // could be signed"), and those sentences are more useful than a generic
      // one — so they are shown rather than replaced.
      setFailures((f) => ({
        ...f,
        [key]: getErrorMessage(err, 'That file could not be made.'),
      }));
    } finally {
      setWorking((w) => {
        const next = { ...w };
        delete next[key];
        return next;
      });
    }
  }

  return (
    /* `Ground`, not `bg-saibyl-void`. The old root painted a flat `#f8fbff`
       panel over the radial wash `<body>` already carries, so the one screen
       whose whole job is to hand work to somebody else was also the one screen
       with canvas rule 1 switched off. */
    <Ground className="p-6 lg:p-8 min-h-full">
      <div className="max-w-5xl mx-auto">
        <Rise>
          <PageHeader
            eyebrow="Your workspace"
            title="Your reports"
            phrase="Work you can hand to somebody who was not in the room."
          >
            <p>
              Every run that finished wrote one of these. Take it out as a
              typeset PDF to read, as slides to present, or as the raw data
              behind it &mdash; the same report, in whichever shape the next
              conversation needs.
            </p>
          </PageHeader>
        </Rise>

        {error && (
          <div className="mt-6">
            <StageError message={error} retry={retry} />
          </div>
        )}

        <section className="mt-7">
          {loading && reports.length === 0 ? (
            <p className="flex items-center gap-2 text-[12.5px] text-saibyl-muted">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              Loading…
            </p>
          ) : reports.length === 0 && !error ? (
            <EmptyState
              headline="No reports yet"
              body="A report is written whenever a run finishes. Put a product in front of a room of buyers and one appears here, ready to download."
              action={{ label: 'Go to your products', href: '/app/home' }}
            />
          ) : (
            <ul className="space-y-3">
              {/* Dealt at the artboard's 70ms, capped inside `dealDelayMs` so a
                  founder with a quarter of reports does not wait for the tail. */}
              {reports.map((report, i) => {
                const when = whenReadable(report.created_at);
                return (
                  <Deal as="li" key={report.id} index={i}>
                    {/* `density`: a row in a list, hairline only. Shadow every
                        row and the page turns to soup. */}
                    <Card carries="density" className="p-4">
                      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                        <div className="min-w-0">
                          {/* Only what the server actually sent. A run whose name
                              is gone shows no name rather than "Untitled", which
                              would read as a name somebody chose. */}
                          {report.run_name && (
                            <p className="text-[14px] text-saibyl-ink truncate">
                              {report.run_name}
                            </p>
                          )}
                          {report.product_name && (
                            <p className="text-[12px] text-saibyl-muted mt-0.5">
                              {report.product_name}
                            </p>
                          )}
                        </div>
                        {when && (
                          <span className="text-[11.5px] text-saibyl-muted shrink-0">
                            {when}
                          </span>
                        )}
                      </div>

                      <div className="flex flex-wrap items-center gap-2 mt-3">
                        {FORMATS.map((f) => {
                          const key = `${report.id}:${f.id}`;
                          return (
                            <button
                              key={f.id}
                              type="button"
                              onClick={() => download(report, f.id)}
                              title={f.hint}
                              className={CHIP_CLASS}
                            >
                              {working[key] ? (
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              ) : (
                                <Download className="w-3.5 h-3.5" />
                              )}
                              {working[key] ? 'Making it…' : f.label}
                            </button>
                          );
                        })}
                        {report.simulation_id && (
                          <Link
                            to={`/app/simulations/${report.simulation_id}/report`}
                            className="text-[12px] text-saibyl-blue hover:underline ml-1"
                          >
                            Read it here
                          </Link>
                        )}
                      </div>

                      {FORMATS.map((f) => {
                        const message = failures[`${report.id}:${f.id}`];
                        return message ? (
                          <p
                            key={f.id}
                            className="text-[12px] text-saibyl-negative mt-2 leading-relaxed"
                          >
                            {message}
                          </p>
                        ) : null;
                      })}
                    </Card>
                  </Deal>
                );
              })}
            </ul>
          )}
        </section>

        <section className="mt-10">
          <h2 className="text-[15px] font-medium text-saibyl-ink">
            Everywhere else
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
            {SHORTCUTS.map(({ to, label, blurb, Icon }) => (
              /* `meaning`, and it lifts: each one is a claim about where to go
                 next, and each one goes there — the only condition under which
                 the artboard's hover rise is an honest promise. The Link wraps
                 the Card rather than becoming it, because `Card` takes no
                 router props of its own. */
              <Link key={to} to={to} className="block h-full">
                <Card carries="meaning" lift className="p-4 h-full">
                  <span className="flex items-center gap-2 text-[13.5px] text-saibyl-ink">
                    <Icon className="w-4 h-4 text-saibyl-blue shrink-0" />
                    {label}
                  </span>
                  <span className="block text-[12px] text-saibyl-muted mt-1 leading-relaxed">
                    {blurb}
                  </span>
                </Card>
              </Link>
            ))}
          </div>
        </section>
      </div>
    </Ground>
  );
}
