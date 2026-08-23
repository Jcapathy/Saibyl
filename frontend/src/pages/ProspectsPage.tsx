import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { formatDistanceToNow } from 'date-fns';
import { ChevronLeft, ChevronRight, Search, Settings2, Users } from 'lucide-react';
import api, { unwrapList } from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { ANGLE_COPY, present, presentList, sourceHost } from '@/lib/gtm';
import { RunCard } from '@/components/gtm/RunCard';
import { EmptyState, StageError } from '@/components/stages/StagePrimitives';
import {
  Action,
  Card,
  Deal,
  Eyebrow,
  Ground,
  Notice,
  PageHeader,
  Rise,
  dealDelayMs,
} from '@/components/design';
import type { CandidateListItem, DiscoveryRun } from '@/types';

/**
 * Every company discovery has found, newest search first.
 *
 * This is the surface a founder comes back to, so the things it must not do are
 * as load-bearing as the things it does.
 *
 * **It does not render `match_score` as a number.** The list arrives ordered by
 * it — `store.list_candidates` sorts `match_score DESC, company_name` — and the
 * only thing shown is that position. `0.73` is a rank ordering against one buyer
 * type and `scoring.py` says outright that it is not a probability and not a
 * calibrated fit score; "73% match" would be a number the product invented. The
 * position is honest because it claims nothing beyond "we put this one first".
 *
 * **It does not fill in blanks.** A company whose headcount no source stated has
 * no headcount line — not a dash, not "Unknown". `present()` and `presentList()`
 * are the only way those fields reach the markup.
 *
 * **It shows the searches, not just their output.** A `failed` run and a run
 * that searched properly and found nobody produce the same empty grid, and they
 * mean opposite things. The run strip above the list is what keeps them apart,
 * and it is why this page fetches `/gtm/runs` even when it has candidates to
 * show.
 *
 * The `min_score` filter the API offers is deliberately not exposed. Any
 * threshold put in front of a founder ("show me everything above 0.5") asserts
 * that 0.5 means something, and it does not. Ordering already does that job.
 *
 * ---
 *
 * **On the design, and on how loud this screen is allowed to be.**
 *
 * Companies was taken out of the primary navigation on 2026-08-23: it ranks a
 * company by how much it resembles a described buyer, which is not intent to
 * buy, and on a live run it handed back the competitors building the same
 * product. The module stays, and it is still reached from inside a product, so
 * this page is live code and gets the approved system properly — washed ground,
 * one accent phrase, depth where a card carries a claim, hairlines on the list.
 * What it does not get is volume: one gradient action, one amber notice saying
 * what the ordering actually means, and a list of rows that stay hairlines.
 * Shadow every row and the page turns to soup; shout on a demoted surface and
 * the app has told the founder the wrong thing about what matters.
 *
 * Before that pass this page painted `saibyl-gold` fills — a legacy dark-theme
 * alias that still resolves to the blue accent, which is exactly why nobody
 * noticed the page had never been converted — and disabled its pagination
 * controls, which is the one rendering the founder's standing rule refuses.
 */

const PER_PAGE = 25;

export default function ProspectsPage() {
  const [params, setParams] = useSearchParams();

  const runFilter = params.get('discovery_run_id') ?? '';
  const archetypeFilter = params.get('archetype_id') ?? '';
  const searchParam = params.get('search') ?? '';
  const page = Math.max(1, Number(params.get('page') ?? '1') || 1);

  const [runs, setRuns] = useState<DiscoveryRun[]>([]);
  const [runsLoaded, setRunsLoaded] = useState(false);

  const [candidates, setCandidates] = useState<CandidateListItem[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [searchDraft, setSearchDraft] = useState(searchParam);

  /**
   * Change a filter or the page.
   *
   * Every refetch goes through here, which is why this — and not the effect
   * below — is where the list is put back into its loading state. Flipping it
   * inside the effect would be a setState in an effect body, and the skeleton
   * belongs to the interaction that asked for new rows rather than to the
   * render that happens to observe the new params.
   */
  const patchParams = useCallback(
    (patch: Record<string, string>, resetPage = true) => {
      setLoading(true);
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          for (const [key, value] of Object.entries(patch)) {
            if (value) next.set(key, value);
            else next.delete(key);
          }
          if (resetPage) next.delete('page');
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  /* Lifted out of the "Clear" button so the empty result can offer the same
     way out. A filtered list with nothing in it and no control to unfilter it
     is a dead end, and a dead end is a defect. */
  const clearFilters = useCallback(() => {
    setSearchDraft('');
    patchParams({ discovery_run_id: '', archetype_id: '', search: '' });
  }, [patchParams]);

  /* --- runs, for the status strip and the filter options -------------- */
  useEffect(() => {
    let cancelled = false;
    api
      .get('/gtm/runs', { params: { limit: 20 } })
      .then((res) => {
        if (cancelled) return;
        setRuns(unwrapList<DiscoveryRun>(res.data).items);
      })
      .catch(() => {
        if (!cancelled) setRuns([]);
      })
      .finally(() => {
        if (!cancelled) setRunsLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  /* --- the list ------------------------------------------------------- */
  useEffect(() => {
    let cancelled = false;
    api
      .get('/gtm/candidates', {
        params: {
          limit: PER_PAGE,
          offset: (page - 1) * PER_PAGE,
          ...(runFilter ? { discovery_run_id: runFilter } : {}),
          ...(archetypeFilter ? { archetype_id: archetypeFilter } : {}),
          ...(searchParam ? { search: searchParam } : {}),
        },
      })
      .then((res) => {
        if (cancelled) return;
        const paged = unwrapList<CandidateListItem>(res.data);
        setCandidates(paged.items);
        setTotal(paged.total);
        setError('');
      })
      .catch((err) => {
        if (cancelled) return;
        setCandidates([]);
        setTotal(null);
        setError(getErrorMessage(err, 'We could not load your companies.'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [page, runFilter, archetypeFilter, searchParam]);

  /* Submitting the search box is what queries the server — the filter is
     `ilike` over every candidate the org holds, not a slice of the current
     page, so keystroke-by-keystroke would be a request per character. */
  function submitSearch(e: React.FormEvent) {
    e.preventDefault();
    patchParams({ search: searchDraft.trim() });
  }

  /**
   * The buyer types available to filter on.
   *
   * Built from the runs' stored queries rather than from the candidates on
   * screen: a page of 25 rows may contain only one buyer type, and a filter
   * offering only what is already visible cannot be used to find anything.
   */
  const buyerTypes = useMemo(() => {
    const byId = new Map<string, string>();
    for (const run of runs) {
      for (const query of run.queries ?? []) {
        if (query.archetype_id && !byId.has(query.archetype_id)) {
          byId.set(query.archetype_id, query.archetype_label || query.archetype_id);
        }
      }
    }
    return [...byId.entries()].map(([id, label]) => ({ id, label }));
  }, [runs]);

  const selectedRun = runs.find((r) => r.id === runFilter) ?? null;
  const latestRun = runs[0] ?? null;
  const shownRun = selectedRun ?? latestRun;

  const filtered = Boolean(runFilter || archetypeFilter || searchParam);
  const knownTotal = total ?? candidates.length;
  const totalPages = Math.max(1, Math.ceil(knownTotal / PER_PAGE));

  const everSearched = runsLoaded && runs.length > 0;

  /* The one header this page has, in both of its branches. Declared once so the
     empty screen and the full one cannot drift apart. */
  const header = (
    <PageHeader
      eyebrow="From your searches"
      title="Companies"
      phrase="Ordered so you know which one to open first — never scored."
    >
      <p>
        Real companies that look like the buyers you described, in the order we
        put them in. Every one has a page behind it carrying the sentences we
        found and the page they came from, and nothing on it was filled in by
        us.
      </p>
    </PageHeader>
  );

  /* --- nothing has ever run -------------------------------------------
     Guarded on `!error`. A request that failed also leaves this page with no
     runs and no candidates, and "no companies found yet" is a confident,
     wrong answer to give somebody whose account is fine and whose backend is
     not. An error gets the error banner in the main layout instead. */
  if (
    runsLoaded &&
    runs.length === 0 &&
    candidates.length === 0 &&
    !loading &&
    !filtered &&
    !error
  ) {
    return (
      <Ground className="min-h-full p-6 lg:p-8">
        <div className="max-w-5xl mx-auto space-y-5">
          <Rise>{header}</Rise>
          <Rise delayMs={dealDelayMs(1)}>
            {/* `EmptyState`, which will not compile without a way forward.
                The hand-rolled version this replaces was a centred icon in a
                `saibyl-gold` tint — the legacy dark-theme alias — with the
                offer written as a bare link. */}
            <EmptyState
              headline="No companies found yet"
              body="You have described who your buyers are. The next step is to go and find real companies that look like them: we search the web and bring back only what we can point at a source for."
              action={{ label: 'Find companies', href: '/app/prospects/discover' }}
            />
          </Rise>
        </div>
      </Ground>
    );
  }

  return (
    <Ground className="min-h-full p-6 lg:p-8">
      <div className="max-w-5xl mx-auto space-y-5">
        {/* ---- Header ---- */}
        <Rise className="flex items-start justify-between gap-4 flex-wrap">
          {header}
          <div className="flex items-center gap-2 shrink-0">
            <Action as={Link} to="/app/prospects/settings" kind="quiet">
              <Settings2 className="w-3.5 h-3.5" /> Data settings
            </Action>
            {/* The one gradient on this screen. Everything else here opens
                something that already exists. */}
            <Action as={Link} to="/app/prospects/discover">
              <Search className="w-4 h-4" /> Find companies
            </Action>
          </div>
        </Rise>

        <Rise delayMs={dealDelayMs(1)} className="space-y-5">
          {/* ---- What this ordering is, and what it is not ----
              Said in colour rather than in grey small print, because it is the
              reason this module was taken out of the sidebar and a founder
              reading the list deserves it before they act on a row. */}
          <Notice tone="thin" title="Resemblance, not intent">
            These companies are ranked by how much they look like the buyers you
            described. That is not the same as wanting to buy: on one real
            search this came back with companies building the same product as
            yours. Read it as a starting list rather than a shortlist &mdash;
            which is why it is reached from inside a product now, and not from
            your sidebar.
          </Notice>

          {/* ---- What the last search actually did ----
              Shown whether or not there are candidates. A run that failed and a
              run that found nobody both leave the list below empty; only this
              tells the founder which happened. */}
          {shownRun && (
            <div>
              <Eyebrow className="mb-2">
                {runFilter ? 'The search you picked' : 'Your most recent search'}
              </Eyebrow>
              <RunCard
                run={shownRun}
                action={
                  runs.length > 1 && !runFilter ? (
                    <p className="text-[11px] text-saibyl-muted">
                      One of {runs.length}. Pick another below to see just what
                      it found.
                    </p>
                  ) : undefined
                }
              />
            </div>
          )}
        </Rise>

        {/* ---- Filters ---- */}
        {everSearched && (
          <div className="flex items-end gap-3 flex-wrap">
            <form onSubmit={submitSearch} className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-saibyl-muted" />
              <input
                type="text"
                value={searchDraft}
                onChange={(e) => setSearchDraft(e.target.value)}
                placeholder="Search by company name…"
                className="w-64 rounded-lg border border-saibyl-border-light bg-white py-2 pl-9 pr-4 text-sm text-saibyl-ink placeholder:text-saibyl-muted/70 focus:outline-none focus:border-saibyl-blue focus:ring-2 focus:ring-saibyl-blue/20 transition-colors"
              />
            </form>

            {runs.length > 1 && (
              <label className="block">
                {/* Not an `Eyebrow`: rule 3's dot marks where a block begins,
                    and dotting each field label in a filter row turns it into a
                    constellation. Same size, same weight as before — density
                    does not change. */}
                <span className="block text-[10px] uppercase tracking-widest text-saibyl-muted mb-1">
                  From which search
                </span>
                <select
                  value={runFilter}
                  onChange={(e) => patchParams({ discovery_run_id: e.target.value })}
                  className="rounded-lg border border-saibyl-border-light bg-white px-3 py-2 text-[13px] text-saibyl-ink focus:outline-none focus:border-saibyl-blue focus:ring-2 focus:ring-saibyl-blue/20"
                  style={{ colorScheme: 'light' }}
                >
                  <option value="">Every search</option>
                  {runs.map((run) => (
                    <option key={run.id} value={run.id}>
                      {formatDistanceToNow(new Date(run.created_at), { addSuffix: true })} &middot;{' '}
                      {run.candidates_found} found
                    </option>
                  ))}
                </select>
              </label>
            )}

            {buyerTypes.length > 1 && (
              <label className="block">
                <span className="block text-[10px] uppercase tracking-widest text-saibyl-muted mb-1">
                  Which kind of buyer
                </span>
                <select
                  value={archetypeFilter}
                  onChange={(e) => patchParams({ archetype_id: e.target.value })}
                  className="rounded-lg border border-saibyl-border-light bg-white px-3 py-2 text-[13px] text-saibyl-ink focus:outline-none focus:border-saibyl-blue focus:ring-2 focus:ring-saibyl-blue/20"
                  style={{ colorScheme: 'light' }}
                >
                  <option value="">Every kind</option>
                  {buyerTypes.map((type) => (
                    <option key={type.id} value={type.id}>
                      {type.label}
                    </option>
                  ))}
                </select>
              </label>
            )}

            {filtered && (
              <button
                type="button"
                onClick={clearFilters}
                className="pb-2 text-[12px] text-saibyl-silver hover:text-saibyl-ink transition-colors"
              >
                Clear
              </button>
            )}
          </div>
        )}

        {error && <StageError message={error} />}

        {/* ---- The list ---- */}
        {loading ? (
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-28 rounded-2xl bg-[#14294a]/[0.04] animate-pulse" />
            ))}
          </div>
        ) : candidates.length === 0 ? (
          /* Both of these used to be centred grey text with the way out
             written as a sentence. A state gets a colour and a control. */
          filtered ? (
            <Notice
              tone="thin"
              title="No companies match what you asked for"
              action={
                <Action kind="quiet" onClick={clearFilters}>
                  Clear the filters
                </Action>
              }
            >
              Nothing saved matches every filter at once. Clear them to see the
              whole list, or run a wider search.
            </Notice>
          ) : (
            <Notice
              tone="thin"
              title="There are no companies saved"
              action={
                <Action as={Link} to="/app/prospects/discover" kind="quiet">
                  Run a search
                </Action>
              }
            >
              The searches above say what happened. If one of them found
              companies and this is still empty, they may have been deleted from
              your data settings.
            </Notice>
          )
        ) : (
          <>
            <p className="text-[11px] text-saibyl-muted">
              {knownTotal} {knownTotal === 1 ? 'company' : 'companies'}
              {filtered ? ' matching your filters' : ''} &middot; strongest match first
            </p>

            <ul className="space-y-2">
              {candidates.map((candidate, i) => (
                /* Dealt at the artboard's 70ms, capped inside `dealDelayMs` so
                   a page of 25 does not make anybody wait for its tail. */
                <Deal as="li" key={candidate.id} index={i}>
                  <CandidateRow
                    candidate={candidate}
                    position={(page - 1) * PER_PAGE + i + 1}
                  />
                </Deal>
              ))}
            </ul>
          </>
        )}

        {/* ---- Pagination ----
            Rendered only where it leads somewhere. Both of these carried
            `disabled` with a 30% opacity, which is the grey button the founder's
            standing rule refuses: a control either runs, or it is blocked with
            the reason beside it. On page one there is no previous page and there
            is nothing to explain, so there is nothing to render. */}
        {totalPages > 1 && !loading && (
          <div className="flex items-center justify-between">
            <p className="font-mono text-xs text-saibyl-muted">
              Page {page} of {totalPages}
              {total === null && ' (count unavailable)'}
            </p>
            <div className="flex items-center gap-2">
              {page > 1 && (
                <button
                  type="button"
                  onClick={() => patchParams({ page: String(page - 1) }, false)}
                  className="inline-flex items-center gap-1 rounded-lg border border-saibyl-border bg-white px-3 py-1.5 text-xs text-saibyl-silver hover:text-saibyl-ink hover:border-saibyl-blue/30 transition-colors"
                >
                  <ChevronLeft className="w-3.5 h-3.5" /> Previous
                </button>
              )}
              {page < totalPages && (
                <button
                  type="button"
                  onClick={() => patchParams({ page: String(page + 1) }, false)}
                  className="inline-flex items-center gap-1 rounded-lg border border-saibyl-border bg-white px-3 py-1.5 text-xs text-saibyl-silver hover:text-saibyl-ink hover:border-saibyl-blue/30 transition-colors"
                >
                  Next <ChevronRight className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </Ground>
  );
}

/**
 * One company in the list.
 *
 * `position` is where this row sits in the ordering the server returned, and it
 * is the *only* expression of `match_score` on this screen. It is a place in a
 * queue, which is exactly what the underlying number supports — no percentage,
 * no bar, no "strong match" badge inferred from a threshold nobody calibrated.
 *
 * The list endpoint carries no `evidence`, no `match_reasons` and no contacts by
 * design, so this row shows the source page it came from and links onward for
 * the quotes.
 *
 * `carries="density"`: a hairline, no shadow, whatever the row is worth. The
 * canvas is explicit that depth belongs to cards carrying a claim and that dense
 * lists keep their hairlines, and twenty-five soft-shadowed rows is the soup it
 * is warning about. It does not `lift` either — a list that bounces under the
 * cursor for a quarter of a screen is motion for its own sake, and the hover
 * tint is the artboard's own way of saying "this row is the one under your
 * hand".
 */
function CandidateRow({
  candidate,
  position,
}: {
  candidate: CandidateListItem;
  position: number;
}) {
  const oneLiner = present(candidate.one_liner);
  const domain = present(candidate.domain);
  const tooling = presentList(candidate.incumbent_tooling);
  // Only the facts a source actually stated. An absent one contributes nothing
  // rather than an empty slot.
  const facts = [
    present(candidate.industry),
    present(candidate.employee_count_range),
    present(candidate.hq_location),
  ].filter((f): f is string => f !== null);
  const angle = ANGLE_COPY[candidate.angle];
  const retrieved = new Date(candidate.retrieved_at);

  return (
    <Link to={`/app/prospects/${candidate.id}`} className="block">
      <Card
        carries="density"
        className="p-4 hover:border-saibyl-blue/30 hover:bg-saibyl-blue/[0.03] transition-colors"
      >
        <div className="flex items-start gap-3">
          <span
            className="mt-0.5 shrink-0 font-mono text-[11px] text-saibyl-muted w-7"
            title="Where this sits in the order we put them in. It is a position in a list, not a score."
          >
            {position}.
          </span>

          <div className="min-w-0 flex-1">
            <div className="flex items-baseline gap-2 flex-wrap">
              <h3 className="text-[14px] font-medium text-saibyl-ink">
                {candidate.company_name}
              </h3>
              {domain && (
                <span className="font-mono text-[11px] text-saibyl-muted">{domain}</span>
              )}
            </div>

            {oneLiner && (
              <p className="text-[12px] text-saibyl-silver mt-1 leading-relaxed">{oneLiner}</p>
            )}

            {facts.length > 0 && (
              <p className="text-[11px] text-saibyl-muted mt-1.5">{facts.join(' · ')}</p>
            )}

            {tooling && (
              <div className="flex flex-wrap gap-1.5 mt-2">
                {tooling.map((tool) => (
                  <span
                    key={tool}
                    className="rounded-md bg-saibyl-violet/10 px-2 py-0.5 text-[10px] text-[#6a4fe0]"
                  >
                    uses {tool}
                  </span>
                ))}
              </div>
            )}

            <div className="flex items-center gap-3 mt-2.5 flex-wrap text-[10px] text-saibyl-muted">
              {present(candidate.archetype_label) && (
                <span className="rounded-md bg-[#14294a]/[0.04] px-2 py-0.5">
                  {candidate.archetype_label}
                </span>
              )}
              {angle && <span>found by: {angle.label.toLowerCase()}</span>}
              {sourceHost(candidate.source_url) && (
                <span>from {sourceHost(candidate.source_url)}</span>
              )}
              {Number.isFinite(retrieved.getTime()) && (
                <span title={retrieved.toLocaleString()}>
                  checked {formatDistanceToNow(retrieved, { addSuffix: true })}
                </span>
              )}
              {candidate.contact_count > 0 && (
                <span className="inline-flex items-center gap-1 text-saibyl-silver">
                  <Users className="w-3 h-3" />
                  {candidate.contact_count}{' '}
                  {candidate.contact_count === 1 ? 'person' : 'people'}
                </span>
              )}
            </div>
          </div>
        </div>
      </Card>
    </Link>
  );
}
