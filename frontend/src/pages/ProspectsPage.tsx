import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { formatDistanceToNow } from 'date-fns';
import { Building2, ChevronLeft, ChevronRight, Search, Settings2, Users } from 'lucide-react';
import api, { unwrapList } from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { ANGLE_COPY, present, presentList, sourceHost } from '@/lib/gtm';
import { RunCard } from '@/components/gtm/RunCard';
import type { CandidateListItem, DiscoveryRun } from '@/types';

/**
 * Every company discovery has found, newest search first.
 *
 * This is the surface a founder comes back to, so the things it must not do are
 * as load-bearing as the things it does.
 *
 * **It does not render `match_score` as a number.** The list arrives ordered by
 * it — `store.list_candidates` sorts `match_score DESC, company_name` — and the
 * only thing shown is that position. `0.73` is a rank ordering against one
 * archetype and `scoring.py` says outright that it is not a probability and not
 * a calibrated fit score; "73% match" would be a number the product invented.
 * The position is honest because it claims nothing beyond "we put this one
 * first".
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
      <div className="p-6 max-w-5xl mx-auto">
        <div className="flex flex-col items-center justify-center py-28 text-center">
          <div className="w-16 h-16 rounded-2xl bg-[#C9A227]/10 flex items-center justify-center mb-5">
            <Building2 className="w-8 h-8 text-[#C9A227]" />
          </div>
          <p className="text-[#E8ECF2] font-semibold text-lg mb-1.5">
            No companies found yet
          </p>
          <p className="text-[#8B97A8] text-[13px] mb-8 max-w-md leading-relaxed">
            You have described who your buyers are. The next step is to go and find real
            companies that look like them &mdash; we search the web and bring back what we
            can point at a source for.
          </p>
          <Link
            to="/app/prospects/discover"
            className="inline-flex items-center gap-2 rounded-lg bg-[#C9A227] px-5 py-2.5 text-sm font-semibold text-[#0A0F1C] hover:bg-[#D4AF37] transition-colors"
          >
            <Search className="w-4 h-4" /> Find companies
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-5">
      {/* ---- Header ---- */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="font-extrabold text-[22px] text-[#E8ECF2]">Companies</h1>
          <p className="text-xs text-[#5A6578] mt-0.5">
            Real companies that look like the buyers you described. Every one of them has a
            page behind it you can open.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            to="/app/prospects/settings"
            className="inline-flex items-center gap-1.5 rounded-lg border border-[#1E293B] px-3 py-2 text-[12px] text-[#8B97A8] hover:text-[#E8ECF2] hover:bg-white/[0.04] transition-colors"
          >
            <Settings2 className="w-3.5 h-3.5" /> Data settings
          </Link>
          <Link
            to="/app/prospects/discover"
            className="inline-flex items-center gap-2 rounded-lg bg-[#C9A227] px-4 py-2 text-sm font-semibold text-[#0A0F1C] hover:bg-[#D4AF37] transition-colors"
          >
            <Search className="w-4 h-4" /> Find companies
          </Link>
        </div>
      </div>

      {/* ---- What the last search actually did ----
          Shown whether or not there are candidates. A run that failed and a run
          that found nobody both leave the list below empty; only this tells the
          founder which happened. */}
      {shownRun && (
        <RunCard
          run={shownRun}
          action={
            runs.length > 1 && !runFilter ? (
              <p className="text-[11px] text-[#5A6578]">
                Your most recent search, of {runs.length}. Pick another below to see just
                what it found.
              </p>
            ) : undefined
          }
        />
      )}

      {/* ---- Filters ---- */}
      {everSearched && (
        <div className="flex items-end gap-3 flex-wrap">
          <form onSubmit={submitSearch} className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#5A6578]" />
            <input
              type="text"
              value={searchDraft}
              onChange={(e) => setSearchDraft(e.target.value)}
              placeholder="Search by company name…"
              className="w-64 rounded-lg border border-[#1E293B] bg-white/[0.03] py-2 pl-9 pr-4 text-sm text-[#E8ECF2] placeholder:text-[#5A6578] focus:border-[#8B5CF6]/50 focus:outline-none transition-colors"
            />
          </form>

          {runs.length > 1 && (
            <label className="block">
              <span className="block text-[10px] uppercase tracking-widest text-[#5A6578] mb-1">
                From which search
              </span>
              <select
                value={runFilter}
                onChange={(e) => patchParams({ discovery_run_id: e.target.value })}
                className="rounded-lg border border-[#1E293B] bg-[#0B1120] px-3 py-2 text-[13px] text-[#E8ECF2] focus:outline-none focus:ring-1 focus:ring-[#8B5CF6]/50"
                style={{ colorScheme: 'dark' }}
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
              <span className="block text-[10px] uppercase tracking-widest text-[#5A6578] mb-1">
                Which kind of buyer
              </span>
              <select
                value={archetypeFilter}
                onChange={(e) => patchParams({ archetype_id: e.target.value })}
                className="rounded-lg border border-[#1E293B] bg-[#0B1120] px-3 py-2 text-[13px] text-[#E8ECF2] focus:outline-none focus:ring-1 focus:ring-[#8B5CF6]/50"
                style={{ colorScheme: 'dark' }}
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
              onClick={() => {
                setSearchDraft('');
                patchParams({ discovery_run_id: '', archetype_id: '', search: '' });
              }}
              className="pb-2 text-[12px] text-[#8B97A8] hover:text-[#E8ECF2] transition-colors"
            >
              Clear
            </button>
          )}
        </div>
      )}

      {error && (
        <div className="rounded-xl border border-[#EF4444]/25 bg-[#EF4444]/[0.07] p-4">
          <p className="text-[12px] text-[#EF4444] leading-relaxed whitespace-pre-wrap">
            {error}
          </p>
        </div>
      )}

      {/* ---- The list ---- */}
      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-28 rounded-2xl bg-white/[0.03] animate-pulse" />
          ))}
        </div>
      ) : candidates.length === 0 ? (
        <div className="rounded-2xl border border-[#1E293B] bg-[#111827] p-8 text-center">
          <p className="text-[13px] text-[#E8ECF2]">
            {filtered
              ? 'No companies match what you asked for'
              : 'There are no companies saved'}
          </p>
          <p className="text-[12px] text-[#5A6578] mt-1.5 leading-relaxed max-w-md mx-auto">
            {filtered
              ? 'Try clearing the filters, or run a wider search.'
              : 'The searches above say what happened. If one of them found companies and this is still empty, they may have been deleted from your data settings.'}
          </p>
        </div>
      ) : (
        <>
          <p className="text-[11px] text-[#5A6578]">
            {knownTotal} {knownTotal === 1 ? 'company' : 'companies'}
            {filtered ? ' matching your filters' : ''} &middot; strongest match first
          </p>

          <ul className="space-y-2">
            {candidates.map((candidate, i) => (
              <li key={candidate.id}>
                <CandidateRow candidate={candidate} position={(page - 1) * PER_PAGE + i + 1} />
              </li>
            ))}
          </ul>
        </>
      )}

      {/* ---- Pagination ---- */}
      {totalPages > 1 && !loading && (
        <div className="flex items-center justify-between">
          <p className="font-mono text-xs text-[#5A6578]">
            Page {page} of {totalPages}
            {total === null && ' (count unavailable)'}
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => patchParams({ page: String(page - 1) }, false)}
              className="inline-flex items-center gap-1 rounded-lg border border-[#1E293B] px-3 py-1.5 text-xs text-[#8B97A8] hover:bg-white/[0.04] disabled:opacity-30 transition-colors"
            >
              <ChevronLeft className="w-3.5 h-3.5" /> Previous
            </button>
            <button
              type="button"
              disabled={page >= totalPages}
              onClick={() => patchParams({ page: String(page + 1) }, false)}
              className="inline-flex items-center gap-1 rounded-lg border border-[#1E293B] px-3 py-1.5 text-xs text-[#8B97A8] hover:bg-white/[0.04] disabled:opacity-30 transition-colors"
            >
              Next <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}
    </div>
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
    <Link
      to={`/app/prospects/${candidate.id}`}
      className="block rounded-2xl border border-[#1E293B] bg-[#111827] p-4 hover:border-[#8B5CF6]/40 hover:bg-white/[0.02] transition-colors"
    >
      <div className="flex items-start gap-3">
        <span
          className="mt-0.5 shrink-0 font-mono text-[11px] text-[#5A6578] w-7"
          title="Where this sits in the order we put them in. It is a position in a list, not a score."
        >
          {position}.
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2 flex-wrap">
            <h3 className="text-[14px] font-medium text-[#E8ECF2]">{candidate.company_name}</h3>
            {domain && <span className="font-mono text-[11px] text-[#5A6578]">{domain}</span>}
          </div>

          {oneLiner && (
            <p className="text-[12px] text-[#8B97A8] mt-1 leading-relaxed">{oneLiner}</p>
          )}

          {facts.length > 0 && (
            <p className="text-[11px] text-[#5A6578] mt-1.5">{facts.join(' · ')}</p>
          )}

          {tooling && (
            <div className="flex flex-wrap gap-1.5 mt-2">
              {tooling.map((tool) => (
                <span
                  key={tool}
                  className="rounded-md bg-[#8B5CF6]/10 px-2 py-0.5 text-[10px] text-[#A78BFA]"
                >
                  uses {tool}
                </span>
              ))}
            </div>
          )}

          <div className="flex items-center gap-3 mt-2.5 flex-wrap text-[10px] text-[#5A6578]">
            {present(candidate.archetype_label) && (
              <span className="rounded-md bg-white/[0.04] px-2 py-0.5">
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
              <span className="inline-flex items-center gap-1 text-[#8B97A8]">
                <Users className="w-3 h-3" />
                {candidate.contact_count}{' '}
                {candidate.contact_count === 1 ? 'person' : 'people'}
              </span>
            )}
          </div>
        </div>
      </div>
    </Link>
  );
}
