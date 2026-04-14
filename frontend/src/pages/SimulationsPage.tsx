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
import api from '@/lib/api';

/* ------------------------------------------------------------------ */
/*  Types                                                             */
/* ------------------------------------------------------------------ */

interface Simulation {
  id: string;
  name: string;
  status: string;
  created_at: string;
  platforms?: string[];
  agent_count?: number;
  sentiment_score?: number;
  project_name?: string;
}

type SortField = 'name' | 'status' | 'created_at' | 'agent_count';
type SortDir = 'asc' | 'desc';

const STATUS_FILTERS = ['all', 'running', 'complete', 'queued', 'draft', 'failed'] as const;
type StatusFilter = (typeof STATUS_FILTERS)[number];

const STATUS_COLOR: Record<string, string> = {
  running: '#3B82F6',
  complete: '#22C55E',
  completed: '#22C55E',
  queued: '#F59E0B',
  draft: '#818CF8',
  failed: '#EF4444',
};

const PLATFORM_MAP: Record<string, string> = {
  twitter_x: '\ud835\udd4F',
  reddit: 'R',
  instagram: 'IG',
  tiktok: 'TT',
  youtube: '\u25B6',
  linkedin: 'in',
  news_comments: 'N',
  hacker_news: 'HN',
  discord: 'D',
};

/* ------------------------------------------------------------------ */
/*  Helpers                                                           */
/* ------------------------------------------------------------------ */

function normalizeStatus(s: string): string {
  return s === 'completed' ? 'complete' : s;
}

function formatAgentCount(n: number | undefined): string {
  if (n == null) return '\u2014';
  if (n >= 1000) return `${Math.round(n / 1000)}K`;
  return String(n);
}

function statusDot(status: string, pulse = false): ReactElement {
  const color = STATUS_COLOR[status] ?? '#5A6578';
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
        const data = res.data;
        const items: Simulation[] = Array.isArray(data) ? data : data.items ?? [];
        const t: number = Array.isArray(data) ? items.length : data.total ?? items.length;
        setSims(items);
        setTotal(t);
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
    if (!window.confirm(`Delete ${ids.length} simulation(s)? This cannot be undone.`)) return;
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
          <div className="h-7 w-40 bg-white/[0.05] rounded animate-pulse" />
          <div className="h-9 w-36 bg-white/[0.05] rounded-lg animate-pulse" />
        </div>
        <div className="bg-[#111820] border border-[#1B2433] rounded-2xl overflow-hidden">
          {Array.from({ length: 5 }).map((_, i) => (
            <div
              key={i}
              className="flex items-center gap-4 px-5 py-4 border-b border-[#1B2433] last:border-b-0"
            >
              <div className="h-4 w-4 bg-white/[0.04] rounded animate-pulse" />
              <div className="h-4 w-48 bg-white/[0.04] rounded animate-pulse" />
              <div className="h-4 w-20 bg-white/[0.04] rounded animate-pulse ml-auto" />
              <div className="h-4 w-16 bg-white/[0.04] rounded animate-pulse" />
              <div className="h-4 w-24 bg-white/[0.04] rounded animate-pulse" />
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
          <div className="w-16 h-16 rounded-2xl bg-[#C9A227]/10 flex items-center justify-center mb-5">
            <FlaskConical className="w-8 h-8 text-[#C9A227]" />
          </div>
          <p className="text-[#E8ECF2] font-semibold text-lg mb-1">No simulations yet</p>
          <p className="text-[#5A6578] text-sm mb-8 max-w-xs">
            Create your first simulation to see predicted public reactions
          </p>
          <Link
            to="/app/simulations/new"
            className="inline-flex items-center gap-2 bg-[#C9A227] text-[#070B14] font-semibold px-5 py-2.5 rounded-lg hover:bg-[#D4AF37] transition-colors text-sm"
          >
            <Plus className="w-4 h-4" /> Create Simulation
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
          <h1 className="font-extrabold text-[22px] text-[#E8ECF2]">Simulations</h1>
          <p className="text-xs text-[#5A6578] mt-0.5 font-mono">
            {total} total &middot; {runningCount} running &middot; {completeCount} complete
          </p>
        </div>
        <Link
          to="/app/simulations/new"
          className="inline-flex items-center gap-2 bg-[#C9A227] text-[#070B14] font-semibold px-4 py-2 rounded-lg hover:bg-[#D4AF37] transition-colors text-sm"
        >
          <Plus className="w-4 h-4" /> New Simulation
        </Link>
      </div>

      {/* ---- Toolbar ---- */}
      <div className="flex items-center gap-4 mb-4 flex-wrap">
        {/* Search */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#5A6578]" />
          <input
            type="text"
            placeholder="Search simulations..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="bg-white/[0.03] border border-[#1B2433] rounded-lg pl-9 pr-4 py-2 text-sm text-[#E8ECF2] placeholder:text-[#5A6578] focus:outline-none focus:border-[#5B5FEE]/50 transition-colors w-64"
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
                    ? 'bg-white/[0.08] text-[#E8ECF2]'
                    : 'text-[#5A6578] hover:text-[#8B97A8]'
                }`}
              >
                {f !== 'all' && statusDot(f)}
                {f.charAt(0).toUpperCase() + f.slice(1)}
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
            <div className="bg-[#5B5FEE]/10 border border-[#5B5FEE]/20 rounded-xl px-4 py-2 flex items-center gap-3">
              <span className="text-sm text-[#E8ECF2] font-medium">
                {selected.size} selected
              </span>
              <button
                className="inline-flex items-center gap-1.5 text-xs text-[#8B97A8] hover:text-[#E8ECF2] px-2 py-1 rounded transition-colors"
                onClick={() => {
                  // TODO: Export selected simulations
                }}
              >
                <Download className="w-3.5 h-3.5" /> Export
              </button>
              <button
                className="inline-flex items-center gap-1.5 text-xs text-[#8B97A8] hover:text-[#E8ECF2] px-2 py-1 rounded transition-colors"
                onClick={() => {
                  // TODO: Archive selected simulations
                }}
              >
                <Archive className="w-3.5 h-3.5" /> Archive
              </button>
              <button
                className="inline-flex items-center gap-1.5 text-xs text-[#EF4444] hover:bg-[#EF4444]/10 px-2 py-1 rounded transition-colors"
                onClick={() => handleDelete(Array.from(selected))}
              >
                <Trash2 className="w-3.5 h-3.5" /> Delete
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ---- Data Table ---- */}
      <div className="bg-[#111820] border border-[#1B2433] rounded-2xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[#1B2433]">
              <th className="w-10 px-4 py-3">
                <input
                  type="checkbox"
                  checked={selected.size === filteredSims.length && filteredSims.length > 0}
                  onChange={toggleSelectAll}
                  className="accent-[#5B5FEE] w-3.5 h-3.5 cursor-pointer"
                />
              </th>
              {(
                [
                  ['name', 'Name'],
                  ['status', 'Status'],
                  [null, 'Platforms'],
                  ['agent_count', 'Agents'],
                  [null, 'Sentiment'],
                  ['created_at', 'Created'],
                  [null, ''],
                ] as const
              ).map(([field, label], i) => (
                <th
                  key={i}
                  className={`text-left px-4 py-3 text-[10px] font-medium tracking-widest uppercase text-[#5A6578] ${
                    field ? 'cursor-pointer select-none hover:text-[#8B97A8]' : ''
                  }`}
                  onClick={() => field && toggleSort(field as SortField)}
                >
                  <span className="inline-flex items-center gap-1">
                    {label}
                    {field && sortField === field && (
                      <ArrowUpDown className="w-3 h-3 text-[#5B5FEE]" />
                    )}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filteredSims.length === 0 ? (
              <tr>
                <td colSpan={8} className="text-center py-12 text-[#5A6578] text-sm">
                  No simulations match your filters
                </td>
              </tr>
            ) : (
              filteredSims.map((sim) => {
                const ns = normalizeStatus(sim.status);
                const color = STATUS_COLOR[sim.status] ?? '#5A6578';
                return (
                  <tr
                    key={sim.id}
                    className={`border-b border-[#1B2433] last:border-b-0 hover:bg-white/[0.02] transition-colors cursor-pointer ${
                      selected.has(sim.id) ? 'bg-[#5B5FEE]/5' : ''
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
                        className="accent-[#5B5FEE] w-3.5 h-3.5 cursor-pointer"
                      />
                    </td>

                    {/* Name */}
                    <td className="px-4 py-3">
                      <div className="font-medium text-[#E8ECF2]">{sim.name}</div>
                      <div className="text-[10px] font-mono text-[#5A6578] mt-0.5">
                        SIM-{sim.id.slice(0, 4).toUpperCase()}
                      </div>
                    </td>

                    {/* Status pill */}
                    <td className="px-4 py-3">
                      <span
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium"
                        style={{
                          backgroundColor: `${color}1A`,
                          color,
                        }}
                      >
                        {statusDot(sim.status, ns === 'running')}
                        {ns.charAt(0).toUpperCase() + ns.slice(1)}
                      </span>
                    </td>

                    {/* Platforms */}
                    <td className="px-4 py-3">
                      {sim.platforms && sim.platforms.length > 0 ? (
                        <div className="flex items-center gap-1 flex-wrap">
                          {sim.platforms.map((p) => (
                            <span
                              key={p}
                              className="bg-white/[0.04] rounded px-1.5 py-0.5 text-[10px] font-mono text-[#8B97A8]"
                            >
                              {PLATFORM_MAP[p] ?? p}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <span className="text-[#5A6578]">&mdash;</span>
                      )}
                    </td>

                    {/* Agents */}
                    <td className="px-4 py-3 font-mono text-xs text-[#8B97A8]">
                      {formatAgentCount(sim.agent_count)}
                    </td>

                    {/* Sentiment */}
                    <td className="px-4 py-3 text-xs text-[#8B97A8]">
                      {ns === 'complete' && sim.sentiment_score != null ? (
                        <span
                          style={{
                            color:
                              sim.sentiment_score >= 0.6
                                ? '#22C55E'
                                : sim.sentiment_score >= 0.4
                                  ? '#F59E0B'
                                  : '#EF4444',
                          }}
                        >
                          {sim.sentiment_score.toFixed(2)}
                        </span>
                      ) : (
                        <span className="text-[#5A6578]">&mdash;</span>
                      )}
                      {/* TODO: Fetch sentiment from report endpoint */}
                    </td>

                    {/* Created */}
                    <td className="px-4 py-3 font-mono text-xs text-[#5A6578] whitespace-nowrap">
                      {formatDistanceToNow(new Date(sim.created_at), { addSuffix: true })}
                    </td>

                    {/* Actions */}
                    <td className="px-4 py-3 relative" data-actions ref={openMenu === sim.id ? menuRef : undefined}>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setOpenMenu(openMenu === sim.id ? null : sim.id);
                        }}
                        className="p-1.5 rounded-lg hover:bg-white/[0.06] text-[#5A6578] hover:text-[#E8ECF2] transition-colors"
                      >
                        <MoreHorizontal className="w-4 h-4" />
                      </button>

                      {openMenu === sim.id && (
                        <div
                          className="absolute right-4 top-10 z-50 w-40 bg-[#1B2433] border border-[#2A3545] rounded-xl shadow-xl py-1 text-xs"
                        >
                          <button
                            className="w-full text-left px-3 py-2 text-[#E8ECF2] hover:bg-white/[0.06] transition-colors"
                            onClick={(e) => {
                              e.stopPropagation();
                              navigate(`/app/simulations/${sim.id}`);
                            }}
                          >
                            View
                          </button>
                          <button
                            className="w-full text-left px-3 py-2 text-[#8B97A8] hover:bg-white/[0.06] transition-colors"
                            onClick={(e) => {
                              e.stopPropagation();
                              // TODO: Duplicate simulation
                            }}
                          >
                            Duplicate
                          </button>
                          <button
                            className="w-full text-left px-3 py-2 text-[#8B97A8] hover:bg-white/[0.06] transition-colors"
                            onClick={(e) => {
                              e.stopPropagation();
                              // TODO: Archive simulation
                            }}
                          >
                            Archive
                          </button>
                          <button
                            className="w-full text-left px-3 py-2 text-[#EF4444] hover:bg-[#EF4444]/10 transition-colors"
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
        <p className="text-xs text-[#5A6578] font-mono">
          Showing {pageStart}&ndash;{pageEnd} of {total}
        </p>
        <div className="flex items-center gap-1">
          <button
            disabled={page <= 1}
            onClick={() => goToPage((p) => p - 1)}
            className="px-3 py-1.5 rounded-lg border border-[#1B2433] text-xs text-[#8B97A8] hover:bg-white/[0.04] disabled:opacity-30 transition-colors"
          >
            Previous
          </button>
          {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
            <button
              key={p}
              onClick={() => goToPage(p)}
              className={`px-2.5 py-1.5 rounded-lg text-xs font-mono transition-colors ${
                p === page
                  ? 'bg-white/[0.08] text-[#E8ECF2]'
                  : 'text-[#5A6578] hover:text-[#8B97A8]'
              }`}
            >
              {p}
            </button>
          ))}
          <button
            disabled={page >= totalPages}
            onClick={() => goToPage((p) => p + 1)}
            className="px-3 py-1.5 rounded-lg border border-[#1B2433] text-xs text-[#8B97A8] hover:bg-white/[0.04] disabled:opacity-30 transition-colors"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
