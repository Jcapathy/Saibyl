import { useEffect, useState, useMemo, useCallback, useRef, type ReactElement } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Search,
  Plus,
  MoreHorizontal,
  Trash2,
  ArrowUpDown,
} from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import api, { unwrapList } from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { ACTIVE_STATUSES, SIMULATION_STATUSES } from '@/lib/constants';
import { isFinished } from '@/lib/status';
import { EmptyState } from '@/components/stages/StagePrimitives';
import {
  Action,
  Card,
  Chapter,
  Ground,
  Hero,
  Longform,
  Notice,
  Reveal,
} from '@/components/design';
import type { Simulation } from '@/types';

/**
 * Every run this workspace has ever started.
 *
 * **The frame is the landing page's.** Founder's decision on 2026-08-23: every
 * page behind the login opens the way the public site opens — a hero, large
 * type, then scroll, with the work arriving as the reader reaches it. His words
 * for what was here instead were "very sterile, mechanical, and looks
 * AI-generated". `GuidePage` is the approved example and this page copies its
 * shape: `Longform` owns the measure and runs the reveal observer, `Hero` opens,
 * and each `Chapter` is one section.
 *
 * **What is inside a chapter did not change.** A long list is a *dense* surface
 * and the canvas is explicit about what that means: "soft blue shadows on cards
 * that carry meaning — hairlines stay on dense lists." So the table still sits
 * in one `carries="density"` card, every row keeps its hairline, and the search
 * box, the chips and the pager are exactly as tight as they were. The frame grew;
 * the work did not.
 *
 * **One `Reveal`, and it is static on purpose.** The list body swaps between a
 * skeleton, an empty state and the table, so the wrapper is rendered once and
 * the *children* are what change — one arrival for the section, rather than a
 * second fade every time the fetch resolves. It also means this page does not
 * lean on `useReveal` tracking nodes that appear after mount: the element the
 * observer finds on load is the element that is still there afterwards.
 */

/* ------------------------------------------------------------------ */
/*  Types                                                             */
/* ------------------------------------------------------------------ */

type SortField = 'name' | 'status' | 'created_at' | 'agent_count';
type SortDir = 'asc' | 'desc';

/**
 * Filter chips, driven off the backend's status list so a new status cannot
 * become unfilterable. The previous hand-written list offered `queued`, which
 * the backend never writes, and omitted `preparing`, `ready`, `analyzing` and
 * `stopped` — four states a run can sit in with no way to select them.
 */
const STATUS_FILTERS = ['all', ...SIMULATION_STATUSES] as const;
type StatusFilter = (typeof STATUS_FILTERS)[number];

const STATUS_COLOR: Record<string, string> = {
  draft:     '#6a4fe0',
  preparing: '#b45309',
  ready:     '#286cf0',
  running:   '#286cf0',
  analyzing: '#b45309',
  complete:  '#0e7d55',
  completed: '#0e7d55',
  stopped:   '#60718e',
  failed:    '#d92d3c',
};

const PLATFORM_MAP: Record<string, string> = {
  twitter_x: '𝕏',
  reddit: 'R',
  instagram: 'IG',
  tiktok: 'TT',
  youtube: '▶',
  facebook: 'FB',
  threads: 'TH',
  linkedin: 'in',
  news_comments: 'N',
  hacker_news: 'HN',
  discord: 'D',
};

/* ------------------------------------------------------------------ */
/*  Helpers                                                           */
/* ------------------------------------------------------------------ */

/**
 * One spelling per state, so a filter and a pill cannot disagree.
 *
 * The database holds both `complete` and `completed` — see `lib/status.ts` —
 * and this used to be a hand-written `=== 'completed'` test. Reading through
 * `isFinished` means there is one place that knows which spellings mean
 * finished, and this file is not a second one.
 */
function normalizeStatus(s: string): string {
  return isFinished(s) ? 'complete' : s;
}

/** What a run's state is called on screen. Never the raw column value. */
const STATE_WORD: Record<string, string> = {
  draft: 'Not started',
  preparing: 'Building the room',
  ready: 'Ready to start',
  running: 'Running',
  analyzing: 'Working it out',
  complete: 'Finished',
  stopped: 'Stopped',
  failed: 'Failed',
};

function stateWord(status: string): string {
  return STATE_WORD[normalizeStatus(status)] ?? status;
}

function formatAgentCount(n: number | null | undefined): string {
  if (n == null) return '—';
  if (n >= 1000) return `${Math.round(n / 1000)}K`;
  return String(n);
}

function statusDot(status: string, pulse = false): ReactElement {
  const color = STATUS_COLOR[status] ?? '#60718e';
  return (
    <span
      className={`inline-block w-1.5 h-1.5 rounded-full mr-1.5 ${pulse ? 'animate-pulse' : ''}`}
      style={{ backgroundColor: color }}
    />
  );
}

/* ------------------------------------------------------------------ */
/*  Component                                                         */
/* ------------------------------------------------------------------ */

export default function SimulationsPage() {
  const navigate = useNavigate();
  const PER_PAGE = 20;

  /* --- data state ------------------------------------------------- */
  const [sims, setSims] = useState<Simulation[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);

  /* --- UI state --------------------------------------------------- */
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [sortField, setSortField] = useState<SortField>('created_at');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  // What the server said when a delete was refused. Rendered above the table,
  // because a delete that quietly does nothing reads as a broken button.
  const [deleteError, setDeleteError] = useState('');
  const menuRef = useRef<HTMLTableCellElement>(null);

  /* --- fetch ------------------------------------------------------ */
  const [fetchKey, setFetchKey] = useState(0);

  /* The search box, settled.

     Typing re-runs the query, so every keystroke would otherwise be a request.
     250ms is the same debounce the discovery estimate uses. */
  const [debouncedSearch, setDebouncedSearch] = useState('');
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search.trim()), 250);
    return () => clearTimeout(t);
  }, [search]);

  /* Changing a filter goes back to page 1.
     Without it, filtering while on page 3 asks the server for rows 40–59 of a
     set that may hold four, and the founder gets an empty table for a filter
     that matches plenty.

     Done in the handlers rather than in an effect on purpose: a `setPage(1)`
     in an effect body is the cascading render this codebase's lint rule
     forbids, and it would also fight the pager — clicking "next" would set the
     page and an effect would immediately set it back. */
  const changeSearch = useCallback((value: string) => {
    setSearch(value);
    setPage(1);
  }, []);

  const changeStatus = useCallback((value: StatusFilter) => {
    setStatusFilter(value);
    setPage(1);
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .get('/simulations', {
        /* **Filtering happens on the server, with the counting.**
           These two were applied in the browser, to whichever twenty rows this
           page happened to hold, while the pager reported the server's count of
           everything. Searching for a run that sat on page 2 therefore answered
           "Nothing matches what you have filtered to" — a confident false
           statement about the account. Filter and count have to be done by the
           same query or they describe different sets. */
        params: {
          offset: (page - 1) * PER_PAGE,
          limit: PER_PAGE,
          ...(debouncedSearch ? { search: debouncedSearch } : {}),
          ...(statusFilter !== 'all' ? { status: statusFilter } : {}),
        },
      })
      .then((res) => {
        if (cancelled) return;
        const { items, total } = unwrapList<Simulation>(res.data);
        setSims(items);
        // A null total means the server could not count. Fall back to what we
        // can see rather than claiming a page count we do not have.
        setTotal(total ?? items.length);
      })
      .catch(() => {
        if (cancelled) return;
        setSims([]);
        setTotal(0);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [page, fetchKey, debouncedSearch, statusFilter]);

  const refetchSims = useCallback(() => {
    setLoading(true);
    setFetchKey((k) => k + 1);
  }, []);

  const goToPage = useCallback((p: number | ((prev: number) => number)) => {
    setLoading(true);
    setPage(p);
  }, []);

  /* close action menu on outside click */
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpenMenu(null);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  /* --- derived ---------------------------------------------------- */
  /* Sorting only, now. The search and the status filter moved into the request
     above; re-applying them here would filter the filtered set, which is
     harmless but would quietly hide a mismatch between the two rules instead of
     letting it show.

     **Sort is deliberately still page-local, and the chapter lead says so.**
     Ordering twenty rows the server chose by recency is a different operation
     from ordering the whole account, and a control that silently does the first
     while looking like the second is the defect this page has just been fixed
     for. Server-side ordering is a small backend change and belongs with the
     decision to make it. */
  const filteredSims = useMemo(() => {
    const list = [...sims].sort((a, b) => {
      let cmp = 0;
      if (sortField === 'name') cmp = a.name.localeCompare(b.name);
      else if (sortField === 'status') cmp = a.status.localeCompare(b.status);
      else if (sortField === 'agent_count') cmp = (a.agent_count ?? 0) - (b.agent_count ?? 0);
      else cmp = new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
      return sortDir === 'asc' ? cmp : -cmp;
    });

    return list;
  }, [sims, sortField, sortDir]);

  /* Counts for the filter chips, over the rows this page holds. */
  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = { all: sims.length };
    for (const s of sims) {
      const ns = normalizeStatus(s.status);
      counts[ns] = (counts[ns] ?? 0) + 1;
    }
    return counts;
  }, [sims]);

  const runningCount = statusCounts['running'] ?? 0;
  const completeCount = statusCounts['complete'] ?? 0;

  const totalPages = Math.max(1, Math.ceil(total / PER_PAGE));
  const pageStart = (page - 1) * PER_PAGE + 1;
  const pageEnd = Math.min(page * PER_PAGE, total);

  /* --- handlers --------------------------------------------------- */
  function toggleSort(field: SortField) {
    if (sortField === field) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortDir('asc');
    }
  }

  function toggleSelect(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAll() {
    if (selected.size === filteredSims.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(filteredSims.map((s) => s.id)));
    }
  }

  async function handleDelete(ids: string[]) {
    if (
      !window.confirm(
        ids.length === 1
          ? 'Delete this run? You cannot undo this.'
          : `Delete these ${ids.length} runs? You cannot undo this.`,
      )
    )
      return;
    setDeleteError('');
    // `allSettled`, and the refusals are read.
    //
    // `DELETE /simulations/{id}` now answers 409 when the run is the "before"
    // for a re-simulation — deleting it would cascade away a before/after the
    // founder paid for and cannot rebuild. With `Promise.all` and no catch that
    // rejection was unhandled: the delete silently did nothing, the selection
    // was never cleared, and the list was never refetched, so the run appeared
    // to survive for no stated reason. A guard on one side of a two-call
    // contract is not a guard.
    const outcomes = await Promise.allSettled(
      ids.map((id) => api.delete(`/simulations/${id}`)),
    );
    const refused = outcomes
      .filter((o): o is PromiseRejectedResult => o.status === 'rejected')
      .map((o) => getErrorMessage(o.reason, 'We could not delete that run.'));
    if (refused.length) {
      setDeleteError(Array.from(new Set(refused)).join(' '));
    }
    setSelected(new Set());
    setOpenMenu(null);
    refetchSims();
  }

  /* --- render ----------------------------------------------------- */

  /*
    One shell, three bodies.

    The header used to be re-typed inside each of the loading, empty and listed
    branches — three early returns, three different top-of-page treatments, and
    the empty branch had no header at all. A founder with no runs landed on a
    screen with no title, no eyebrow and no way to tell which surface they were
    on. The hero is rendered once now and the body is what changes.
  */
  return (
    <Ground className="min-h-full pb-24">
      <Longform>
        {/* Never wrapped in `Reveal`: it is the first screen, and a page whose
            opening fades in looks broken for 700ms. */}
        <Hero
          eyebrow="Your workspace"
          title="Every room you have"
          serif="ever built."
          actions={
            <>
              {/* The one gradient on this screen. Everything else here opens
                  something that already exists. */}
              <Action as={Link} to="/app/simulations/new">
                <Plus className="w-4 h-4" /> New run
              </Action>
              <Action as={Link} to="/app/guide" kind="quiet">
                How this works
              </Action>
            </>
          }
        >
          <p>
            A run is one message put in front of one room of buyers. Open any of
            them to see what was said, what people pushed back on, and what it
            would take to change their minds &mdash; and start a new one whenever
            the wording, the price or the audience changes.{' '}
            <b className="text-saibyl-ink font-semibold">
              Every room you have paid for, and what came out of it.
            </b>
          </p>
        </Hero>

        {/* ── The list ── */}
        <Chapter
          kicker="The list"
          title={
            <>
              Every run, <em>newest first</em>
            </>
          }
          lead="Search and the status chips are answered by the server, so what you filter to is the whole workspace and not just the rows in front of you. Sorting reorders this page only."
        >
          {/* One wrapper, rendered on mount, holding whichever body applies —
              skeleton, empty state or table. See the note at the top of this
              file: the section arrives once, and the fetch resolving is not a
              second arrival. */}
          <Reveal>
            {/* ---- A delete the server refused, in its own words ---- */}
            {deleteError && (
              <Notice
                tone="blocked"
                title="That delete was refused"
                className="mb-4"
              >
                {deleteError}
              </Notice>
            )}

            {loading ? (
              /* Skeleton, on the same hairline card the real table lands on, so
                 the page does not change shape underneath the reader. */
              <Card carries="density" className="overflow-hidden">
                {Array.from({ length: 5 }).map((_, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-4 px-5 py-4 border-b border-saibyl-border last:border-b-0"
                  >
                    <div className="h-4 w-4 bg-[#14294a]/[0.04] rounded animate-pulse" />
                    <div className="h-4 w-48 bg-[#14294a]/[0.04] rounded animate-pulse" />
                    <div className="h-4 w-20 bg-[#14294a]/[0.04] rounded animate-pulse ml-auto" />
                    <div className="h-4 w-16 bg-[#14294a]/[0.04] rounded animate-pulse" />
                    <div className="h-4 w-24 bg-[#14294a]/[0.04] rounded animate-pulse" />
                  </div>
                ))}
              </Card>
            ) : total === 0 ? (
              <EmptyState
                headline="No runs here"
                body="Start one and you'll see what people say about your product before you spend anything putting it in front of them."
                action={{ label: 'Start your first run', href: '/app/simulations/new' }}
              />
            ) : (
              <>
                {/* ---- Toolbar ----
                    Exactly as dense as it was. The chapter around it grew; the
                    controls inside it did not. */}
                <div className="flex items-center gap-4 mb-4 flex-wrap">
                  {/* Search */}
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-saibyl-muted" />
                    <input
                      type="text"
                      placeholder="Search your runs…"
                      value={search}
                      onChange={(e) => changeSearch(e.target.value)}
                      className="bg-white border border-saibyl-border-light rounded-xl pl-9 pr-4 py-2 text-sm text-saibyl-ink placeholder:text-saibyl-muted/70 focus:outline-none focus:border-saibyl-blue focus:ring-2 focus:ring-saibyl-blue/20 transition-colors w-64"
                    />
                  </div>

                  {/* Filter chips */}
                  <div className="flex items-center gap-1">
                    {STATUS_FILTERS.map((f) => {
                      const active = statusFilter === f;
                      const count = f === 'all' ? sims.length : (statusCounts[f] ?? 0);
                      return (
                        <button
                          key={f}
                          onClick={() => changeStatus(f)}
                          className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                            active
                              ? 'bg-saibyl-blue/[0.10] text-saibyl-ink'
                              : 'text-saibyl-muted hover:text-saibyl-silver'
                          }`}
                        >
                          {f !== 'all' && statusDot(f)}
                          {f === 'all' ? 'All' : stateWord(f)}
                          <span className="ml-0.5 text-[10px] opacity-60">{count}</span>
                        </button>
                      );
                    })}
                  </div>

                  {/* The summary that used to sit beside the page title. It has
                      nowhere to live in a hero — `Hero` takes no `mark` — and
                      dropping it would lose the only place the workspace total
                      is stated above the pager. */}
                  <p className="ml-auto font-mono tabular-nums text-[11px] text-saibyl-muted">
                    {total} in total · {runningCount} going now · {completeCount} finished
                  </p>
                </div>

                {/* ---- Bulk Actions Bar ---- */}
                {selected.size > 0 && (
                  <div className="mb-4">
                    <div className="rounded-xl border border-saibyl-violet/25 bg-saibyl-violet/10 px-4 py-2 flex items-center gap-3">
                      <span className="text-sm text-saibyl-ink font-medium">
                        {selected.size} selected
                      </span>
                      {/* Export and Archive stood here and did nothing.
                          Both were `onClick={() => { /* TODO * / }}` — controls
                          that render, take a click and swallow it, which is the
                          failure the no-grey-button rule exists to prevent wearing
                          its opposite face: the button looks live, so the founder
                          concludes the archive silently failed rather than that it
                          was never built. There is no archive endpoint and
                          `/exports` is per-report, reachable from Your reports.
                          Deleting them removes no capability, because there was
                          none. */}
                      <button
                        className="inline-flex items-center gap-1.5 text-xs text-saibyl-negative hover:bg-saibyl-negative/10 px-2 py-1 rounded transition-colors"
                        onClick={() => handleDelete(Array.from(selected))}
                      >
                        <Trash2 className="w-3.5 h-3.5" /> Delete
                      </button>
                    </div>
                  </div>
                )}

                {/* ---- Data Table ----
                    A dense surface: hairline rows, no shadow per row, the same
                    row rhythm and type sizes it had before the frame changed.
                    The rows are not dealt or revealed one by one — twenty
                    staggered rows stop being an arrival and become a loading bar
                    made of content. */}
                <Card carries="density" className="overflow-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-saibyl-border">
                        <th className="w-10 px-4 py-3">
                          <input
                            type="checkbox"
                            checked={selected.size === filteredSims.length && filteredSims.length > 0}
                            onChange={toggleSelectAll}
                            className="accent-[#8b73ee] w-3.5 h-3.5 cursor-pointer"
                          />
                        </th>
                        {(
                          [
                            ['name', 'Name'],
                            ['status', 'Where it got to'],
                            [null, 'Platforms'],
                            ['agent_count', 'People'],
                            ['created_at', 'Started'],
                            [null, ''],
                          ] as const
                        ).map(([field, label], i) => (
                          <th
                            key={i}
                            className={`text-left px-4 py-3 text-[10px] font-medium tracking-widest uppercase text-saibyl-muted ${
                              field ? 'cursor-pointer select-none hover:text-saibyl-silver' : ''
                            }`}
                            onClick={() => field && toggleSort(field as SortField)}
                          >
                            <span className="inline-flex items-center gap-1">
                              {label}
                              {field && sortField === field && (
                                <ArrowUpDown className="w-3 h-3 text-saibyl-violet" />
                              )}
                            </span>
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {filteredSims.length === 0 ? (
                        <tr>
                          <td colSpan={7} className="text-center py-12 text-saibyl-muted text-sm">
                            Nothing matches what you have filtered to.
                          </td>
                        </tr>
                      ) : (
                        filteredSims.map((sim) => {
                          const ns = normalizeStatus(sim.status);
                          const color = STATUS_COLOR[sim.status] ?? '#60718e';
                          return (
                            <tr
                              key={sim.id}
                              className={`border-b border-saibyl-border last:border-b-0 hover:bg-[#14294a]/[0.02] transition-colors cursor-pointer ${
                                selected.has(sim.id) ? 'bg-saibyl-violet/5' : ''
                              }`}
                              onClick={(e) => {
                                /* don't navigate when clicking checkbox or actions */
                                const target = e.target as HTMLElement;
                                if (
                                  target.closest('input[type="checkbox"]') ||
                                  target.closest('[data-actions]')
                                )
                                  return;
                                navigate(`/app/simulations/${sim.id}`);
                              }}
                            >
                              {/* Checkbox */}
                              <td className="w-10 px-4 py-3">
                                <input
                                  type="checkbox"
                                  checked={selected.has(sim.id)}
                                  onChange={() => toggleSelect(sim.id)}
                                  className="accent-[#8b73ee] w-3.5 h-3.5 cursor-pointer"
                                />
                              </td>

                              {/* Name.

                                  There used to be a second line here reading
                                  `SIM-{first four characters of the id}`. It looked
                                  like a reference number and was not one: four
                                  characters off the front of a UUID identify
                                  nothing, collide between rows, and a founder
                                  reported three different runs all showing the same
                                  "SIM-1111". A run is identified by its name and
                                  when it started — both of which are already on this
                                  row and are both real. */}
                              <td className="px-4 py-3">
                                <div className="font-medium text-saibyl-ink">{sim.name}</div>
                                {sim.prediction_goal && (
                                  <div className="text-[11px] text-saibyl-muted mt-0.5 line-clamp-1 max-w-md">
                                    {sim.prediction_goal}
                                  </div>
                                )}
                              </td>

                              {/* Status pill */}
                              <td className="px-4 py-3">
                                <span
                                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium whitespace-nowrap"
                                  style={{
                                    backgroundColor: `${color}1A`,
                                    color,
                                  }}
                                >
                                  {statusDot(sim.status, ACTIVE_STATUSES.includes(ns))}
                                  {stateWord(sim.status)}
                                </span>
                              </td>

                              {/* Platforms */}
                              <td className="px-4 py-3">
                                {sim.platforms && sim.platforms.length > 0 ? (
                                  <div className="flex items-center gap-1 flex-wrap">
                                    {sim.platforms.map((p) => (
                                      <span
                                        key={p}
                                        className="bg-[#14294a]/[0.04] rounded px-1.5 py-0.5 text-[10px] font-mono text-saibyl-silver"
                                      >
                                        {PLATFORM_MAP[p] ?? p}
                                      </span>
                                    ))}
                                  </div>
                                ) : (
                                  <span className="text-saibyl-muted">&mdash;</span>
                                )}
                              </td>

                              {/* Agents */}
                              <td className="px-4 py-3 font-mono text-xs text-saibyl-silver">
                                {formatAgentCount(sim.agent_count)}
                              </td>

                              {/* No "how they felt" column. A run's row carries no
                                  such field, and the measured reading is only
                                  addressable one id at a time via
                                  /simulations/{id}/analysis — a column here would be
                                  one request per row, most of them 404. */}

                              {/* Created */}
                              <td className="px-4 py-3 font-mono text-xs text-saibyl-muted whitespace-nowrap">
                                {formatDistanceToNow(new Date(sim.created_at), { addSuffix: true })}
                              </td>

                              {/* Actions */}
                              <td className="px-4 py-3 relative" data-actions ref={openMenu === sim.id ? menuRef : undefined}>
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setOpenMenu(openMenu === sim.id ? null : sim.id);
                                  }}
                                  className="p-1.5 rounded-lg hover:bg-[#14294a]/[0.04] text-saibyl-muted hover:text-saibyl-ink transition-colors"
                                >
                                  <MoreHorizontal className="w-4 h-4" />
                                </button>

                                {openMenu === sim.id && (
                                  <div
                                    className="absolute right-4 top-10 z-50 w-40 bg-white border border-saibyl-border-light rounded-xl shadow-[0_22px_60px_rgba(52,96,164,0.18)] py-1 text-xs"
                                  >
                                    <button
                                      className="w-full text-left px-3 py-2 text-saibyl-ink hover:bg-[#14294a]/[0.04] transition-colors"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        navigate(`/app/simulations/${sim.id}`);
                                      }}
                                    >
                                      Open it
                                    </button>
                                    {/* Duplicate and Archive were here and did
                                        nothing — see the bulk bar above. Neither
                                        has a backend, and a menu item that
                                        swallows a click teaches a founder that
                                        the app is unreliable rather than that the
                                        feature is unbuilt. */}
                                    <button
                                      className="w-full text-left px-3 py-2 text-saibyl-negative hover:bg-saibyl-negative/10 transition-colors"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        handleDelete([sim.id]);
                                      }}
                                    >
                                      Delete
                                    </button>
                                  </div>
                                )}
                              </td>
                            </tr>
                          );
                        })
                      )}
                    </tbody>
                  </table>
                </Card>

                {/* ---- Pagination ----
                    Previous and Next are rendered only when they lead somewhere.
                    They used to be `disabled` at the ends of the list, which is the
                    grey rectangle the founder's standing rule forbids: a control
                    either does something or it is not a control. */}
                <div className="flex items-center justify-between mt-4">
                  <p className="text-xs text-saibyl-muted font-mono">
                    Showing {pageStart}&ndash;{pageEnd} of {total}
                  </p>
                  <div className="flex items-center gap-1">
                    {page > 1 && (
                      <button
                        onClick={() => goToPage((p) => p - 1)}
                        className="px-3 py-1.5 rounded-lg border border-saibyl-border text-xs text-saibyl-silver hover:bg-[#14294a]/[0.04] transition-colors"
                      >
                        Previous
                      </button>
                    )}
                    {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
                      <button
                        key={p}
                        onClick={() => goToPage(p)}
                        className={`px-2.5 py-1.5 rounded-lg text-xs font-mono transition-colors ${
                          p === page
                            ? 'bg-saibyl-blue/[0.10] text-saibyl-ink'
                            : 'text-saibyl-muted hover:text-saibyl-silver'
                        }`}
                      >
                        {p}
                      </button>
                    ))}
                    {page < totalPages && (
                      <button
                        onClick={() => goToPage((p) => p + 1)}
                        className="px-3 py-1.5 rounded-lg border border-saibyl-border text-xs text-saibyl-silver hover:bg-[#14294a]/[0.04] transition-colors"
                      >
                        Next
                      </button>
                    )}
                  </div>
                </div>
              </>
            )}
          </Reveal>
        </Chapter>

        {/* ── The way out ──
            The landing page closes by asking for the next step, and so does
            this. Rendered unconditionally and worded so it reads the same
            whether the list above holds forty runs or none — a closing section
            that blinked in and out with the fetch would move the whole page
            under the reader every time a filter changed. */}
        <Chapter
          kicker="Starting another"
          title={
            <>
              The room is <em>always open</em>
            </>
          }
          lead="Nothing here changes until you run something. When the wording, the price or the audience moves, put it in front of a room again — and send it back to the room that objected the first time if you want a measured difference rather than a second opinion."
        >
          <Reveal>
            <Action as={Link} to="/app/simulations/new" kind="quiet">
              <Plus className="w-4 h-4" /> Start a run
            </Action>
          </Reveal>
        </Chapter>
      </Longform>
    </Ground>
  );
}
