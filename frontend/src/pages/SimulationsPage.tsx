import { useEffect, useState, useMemo, useCallback, useRef, type ReactElement } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search,
  Plus,
  MoreHorizontal,
  Trash2,
  Archive,
  Download,
  FlaskConical,
  ArrowUpDown,
} from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import api, { unwrapList } from '@/lib/api';
import { ACTIVE_STATUSES, SIMULATION_STATUSES } from '@/lib/constants';
import { isFinished } from '@/lib/status';
import type { Simulation } from '@/types';

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
  twitter_x: '\ud835\udd4F',
  reddit: 'R',
  instagram: 'IG',
  tiktok: 'TT',
  youtube: '\u25B6',
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
 * The database holds both `complete` and `completed` \u2014 see `lib/status.ts` \u2014
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
  if (n == null) return '\u2014';
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
  const menuRef = useRef<HTMLTableCellElement>(null);

  /* --- fetch ------------------------------------------------------ */
  const [fetchKey, setFetchKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    api
      .get('/simulations', {
        params: { offset: (page - 1) * PER_PAGE, limit: PER_PAGE },
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
  }, [page, fetchKey]);

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
  const filteredSims = useMemo(() => {
    let list = sims;

    // search
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter((s) => s.name.toLowerCase().includes(q));
    }

    // status filter
    if (statusFilter !== 'all') {
      list = list.filter((s) => normalizeStatus(s.status) === statusFilter);
    }

    // sort
    list = [...list].sort((a, b) => {
      let cmp = 0;
      if (sortField === 'name') cmp = a.name.localeCompare(b.name);
      else if (sortField === 'status') cmp = a.status.localeCompare(b.status);
      else if (sortField === 'agent_count') cmp = (a.agent_count ?? 0) - (b.agent_count ?? 0);
      else cmp = new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
      return sortDir === 'asc' ? cmp : -cmp;
    });

    return list;
  }, [sims, search, statusFilter, sortField, sortDir]);

  /* status counts (computed from ALL fetched data, not filtered) */
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
    await Promise.all(ids.map((id) => api.delete(`/simulations/${id}`)));
    setSelected(new Set());
    setOpenMenu(null);
    refetchSims();
  }

  /* --- render ----------------------------------------------------- */

  /* Loading skeleton */
  if (loading) {
    return (
      <div className="p-6 max-w-6xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div className="h-7 w-40 bg-[#14294a]/[0.06] rounded animate-pulse" />
          <div className="h-9 w-36 bg-[#14294a]/[0.06] rounded-lg animate-pulse" />
        </div>
        <div className="bg-white border border-saibyl-border rounded-2xl overflow-hidden">
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
        </div>
      </div>
    );
  }

  /* Empty state */
  if (total === 0 && !loading) {
    return (
      <div className="p-6 max-w-6xl mx-auto">
        <div className="flex flex-col items-center justify-center py-28 text-center">
          <div className="w-16 h-16 rounded-2xl bg-saibyl-blue/10 flex items-center justify-center mb-5">
            <FlaskConical className="w-8 h-8 text-saibyl-blue" />
          </div>
          <p className="text-saibyl-ink font-semibold text-lg mb-1">No runs yet</p>
          <p className="text-saibyl-muted text-sm mb-8 max-w-sm">
            Start one and you&rsquo;ll see what people say about your product before
            you spend anything putting it in front of them.
          </p>
          <Link
            to="/app/simulations/new"
            className="inline-flex items-center gap-2 bg-saibyl-blue text-white font-semibold px-5 py-2.5 rounded-lg hover:bg-saibyl-gold-hover transition-colors text-sm"
          >
            <Plus className="w-4 h-4" /> Start your first run
          </Link>
        </div>
      </div>
    );
  }

  const pageStart = (page - 1) * PER_PAGE + 1;
  const pageEnd = Math.min(page * PER_PAGE, total);

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* ---- Page Header ---- */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="font-extrabold text-[22px] text-saibyl-ink">Your runs</h1>
          <p className="text-xs text-saibyl-muted mt-0.5 font-mono">
            {total} in total &middot; {runningCount} going now &middot; {completeCount} finished
          </p>
        </div>
        <Link
          to="/app/simulations/new"
          className="inline-flex items-center gap-2 bg-saibyl-blue text-white font-semibold px-4 py-2 rounded-lg hover:bg-saibyl-gold-hover transition-colors text-sm"
        >
          <Plus className="w-4 h-4" /> New run
        </Link>
      </div>

      {/* ---- Toolbar ---- */}
      <div className="flex items-center gap-4 mb-4 flex-wrap">
        {/* Search */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-saibyl-muted" />
          <input
            type="text"
            placeholder="Search your runs…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
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
                onClick={() => setStatusFilter(f)}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  active
                    ? 'bg-[#14294a]/[0.06] text-saibyl-ink'
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
      </div>

      {/* ---- Bulk Actions Bar ---- */}
      <AnimatePresence>
        {selected.size > 0 && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden mb-4"
          >
            <div className="bg-[#8b73ee]/10 border border-[#8b73ee]/25 rounded-xl px-4 py-2 flex items-center gap-3">
              <span className="text-sm text-saibyl-ink font-medium">
                {selected.size} selected
              </span>
              <button
                className="inline-flex items-center gap-1.5 text-xs text-saibyl-silver hover:text-saibyl-ink px-2 py-1 rounded transition-colors"
                onClick={() => {
                  // TODO: Export selected simulations
                }}
              >
                <Download className="w-3.5 h-3.5" /> Export
              </button>
              <button
                className="inline-flex items-center gap-1.5 text-xs text-saibyl-silver hover:text-saibyl-ink px-2 py-1 rounded transition-colors"
                onClick={() => {
                  // TODO: Archive selected simulations
                }}
              >
                <Archive className="w-3.5 h-3.5" /> Archive
              </button>
              <button
                className="inline-flex items-center gap-1.5 text-xs text-saibyl-negative hover:bg-saibyl-negative/10 px-2 py-1 rounded transition-colors"
                onClick={() => handleDelete(Array.from(selected))}
              >
                <Trash2 className="w-3.5 h-3.5" /> Delete
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ---- Data Table ---- */}
      <div className="bg-white border border-saibyl-border rounded-2xl overflow-hidden">
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
                      <ArrowUpDown className="w-3 h-3 text-[#6a4fe0]" />
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
                      selected.has(sim.id) ? 'bg-[#8b73ee]/5' : ''
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
                        `SIM-{first four characters of the id}`. It looked like
                        a reference number and was not one: four characters off
                        the front of a UUID identify nothing, collide between
                        rows, and a founder reported three different runs all
                        showing the same "SIM-1111". A run is identified by its
                        name and when it started — both of which are already on
                        this row and are both real. */}
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

                    {/* No "how they felt" column. A run's row carries no such
                        field, and the measured reading is only addressable one
                        id at a time via /simulations/{id}/analysis — a column
                        here would be one request per row, most of them 404. */}

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
                          className="absolute right-4 top-10 z-50 w-40 bg-white border border-saibyl-border-light rounded-xl shadow-xl py-1 text-xs"
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
                          <button
                            className="w-full text-left px-3 py-2 text-saibyl-silver hover:bg-[#14294a]/[0.04] transition-colors"
                            onClick={(e) => {
                              e.stopPropagation();
                              // TODO: Duplicate simulation
                            }}
                          >
                            Duplicate
                          </button>
                          <button
                            className="w-full text-left px-3 py-2 text-saibyl-silver hover:bg-[#14294a]/[0.04] transition-colors"
                            onClick={(e) => {
                              e.stopPropagation();
                              // TODO: Archive simulation
                            }}
                          >
                            Archive
                          </button>
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
      </div>

      {/* ---- Pagination ---- */}
      <div className="flex items-center justify-between mt-4">
        <p className="text-xs text-saibyl-muted font-mono">
          Showing {pageStart}&ndash;{pageEnd} of {total}
        </p>
        <div className="flex items-center gap-1">
          <button
            disabled={page <= 1}
            onClick={() => goToPage((p) => p - 1)}
            className="px-3 py-1.5 rounded-lg border border-saibyl-border text-xs text-saibyl-silver hover:bg-[#14294a]/[0.04] disabled:opacity-30 transition-colors"
          >
            Previous
          </button>
          {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
            <button
              key={p}
              onClick={() => goToPage(p)}
              className={`px-2.5 py-1.5 rounded-lg text-xs font-mono transition-colors ${
                p === page
                  ? 'bg-[#14294a]/[0.06] text-saibyl-ink'
                  : 'text-saibyl-muted hover:text-saibyl-silver'
              }`}
            >
              {p}
            </button>
          ))}
          <button
            disabled={page >= totalPages}
            onClick={() => goToPage((p) => p + 1)}
            className="px-3 py-1.5 rounded-lg border border-saibyl-border text-xs text-saibyl-silver hover:bg-[#14294a]/[0.04] disabled:opacity-30 transition-colors"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
