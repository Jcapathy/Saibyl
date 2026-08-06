import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Clock, Users, FileText, Zap, ArrowRight } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import api, { unwrapList } from '@/lib/api';
import { ACTIVE_STATUSES } from '@/lib/constants';
import { getErrorMessage } from '@/lib/errors';
import type { BillingStatus, Simulation } from '@/types';

/**
 * How many runs the list request asks for.
 *
 * Named because the count of finished runs is derived from that list, and a
 * derived count off a truncated page is a floor being rendered as a total. The
 * card is withheld when the page comes back full.
 */
const RUN_PAGE_SIZE = 100;

/** Statuses that exist before any agent row has been written. */
const BEFORE_AGENTS = new Set(['draft', 'preparing']);

function formatCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n % 1_000_000 === 0 ? 0 : 1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(n % 1_000 === 0 ? 0 : 1)}K`;
  return n.toString();
}

/** One entry per value in `SIMULATION_STATUSES`, plus the legacy `completed`. */
const STATUS_COLORS: Record<string, string> = {
  draft:     '#8B5CF6',
  preparing: '#F59E0B',
  ready:     '#2563EB',
  running:   '#2563EB',
  analyzing: '#F59E0B',
  complete:  '#22C55E',
  completed: '#22C55E',
  stopped:   '#5A6578',
  failed:    '#EF4444',
};

function StatusDot({ status }: { status: string }) {
  const color = STATUS_COLORS[status] ?? '#5A6578';
  const isRunning = ACTIVE_STATUSES.includes(status);
  return (
    <span className="relative flex h-2.5 w-2.5 shrink-0">
      {isRunning && (
        <span
          className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-75"
          style={{ backgroundColor: color }}
        />
      )}
      <span
        className="relative inline-flex h-2.5 w-2.5 rounded-full"
        style={{ backgroundColor: color }}
      />
    </span>
  );
}

function Skeleton({ className }: { className: string }) {
  return <div className={`animate-pulse bg-[#111827] rounded-2xl ${className}`} />;
}

/**
 * One figure.
 *
 * `value` is a `number`, not a node, and there is no "unknown" rendering. A card
 * whose figure is not known is not built at all — the callers below decide that.
 * This used to take a node so it could be handed `'—'`, and a dash sitting in a
 * 2xl bold slot reads as a value rather than as an absence.
 */
function StatCard({
  icon,
  label,
  value,
  meta,
  gradientFrom,
  gradientTo,
  iconBg,
  iconColor,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  meta: string;
  gradientFrom: string;
  gradientTo: string;
  iconBg: string;
  iconColor: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      className="bg-[#111827] border border-[#1E293B] rounded-2xl p-5 relative overflow-hidden"
    >
      <div
        className="absolute top-0 left-0 right-0 h-[2px]"
        style={{
          background: `linear-gradient(to right, ${gradientFrom}, ${gradientTo})`,
        }}
      />
      <div className="flex items-center justify-between mb-3">
        <p className="text-[11px] font-mono tracking-widest uppercase text-[#5A6578]">
          {label}
        </p>
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center"
          style={{ backgroundColor: iconBg }}
        >
          <span style={{ color: iconColor }}>{icon}</span>
        </div>
      </div>
      <p className="text-2xl font-bold text-[#E8ECF2]">{formatCount(value)}</p>
      <p className="text-xs text-[#5A6578] mt-1">{meta}</p>
    </motion.div>
  );
}

export default function DashboardPage() {
  const [recentSims, setRecentSims] = useState<Simulation[]>([]);
  const [allSims, setAllSims] = useState<Simulation[]>([]);
  const [billing, setBilling] = useState<BillingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  /**
   * Empty until the fetch has actually come back.
   *
   * The three requests go out as one `Promise.all`, so this is one flag for all
   * three: either everything below was read or none of it was. It exists so a
   * failed load renders as a failed load. The catch here used to be `catch {}`
   * with a comment saying the page "renders with fallback values" — and the
   * fallback value for every count on it was zero, so a dashboard that could
   * not reach the server was indistinguishable from an account that had never
   * done anything.
   */
  const [loadError, setLoadError] = useState('');

  const fetchData = useCallback(async () => {
    setLoadError('');
    try {
      const [recentRes, allRes, billRes] = await Promise.all([
        api.get('/simulations', { params: { limit: 5 } }),
        api.get('/simulations', { params: { limit: RUN_PAGE_SIZE } }),
        api.get('/billing/status'),
      ]);
      setRecentSims(unwrapList<Simulation>(recentRes.data).items);
      setAllSims(unwrapList<Simulation>(allRes.data).items);
      setBilling(billRes.data);
    } catch (err) {
      setLoadError(getErrorMessage(err, 'We could not read your account just now.'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  // Derived stats
  const completedSims = allSims.filter(
    (s) => s.status === 'completed' || s.status === 'complete',
  );

  /*
    Whether the finished-run figure is a total or a floor.

    `completedSims` is counted out of a page of `RUN_PAGE_SIZE`. A full page
    means there are more runs than were fetched, so the count is a lower bound —
    and a lower bound rendered in the same slot as a total is a wrong number.
    Withheld rather than approximated.
  */
  const finishedCountIsKnown = loadError === '' && allSims.length < RUN_PAGE_SIZE;

  /* A retry that fails leaves the previous response in state. These figures are
     described as "this month", so showing last attempt's numbers under a
     "we could not read your account" notice would be presenting a stale figure
     as a current one. */
  const figuresKnown = loadError === '' && billing != null;

  // There is deliberately no average-sentiment tile here. A simulation row
  // carries no valence field of any name, and the only per-run reading —
  // `GET /simulations/{id}/analysis` — is addressable one id at a time.
  // Averaging across a list would mean N requests, most of which 404.

  /** Past-tense phrasing for each status the backend can write. */
  const STATUS_ACTIVITY: Record<string, { action: string; dotColor: string }> = {
    draft:     { action: 'was set up',           dotColor: '#8B5CF6' },
    preparing: { action: 'started getting ready', dotColor: '#F59E0B' },
    ready:     { action: 'is ready to start',    dotColor: '#2563EB' },
    running:   { action: 'started',              dotColor: '#2563EB' },
    analyzing: { action: 'is being read',        dotColor: '#F59E0B' },
    complete:  { action: 'finished',             dotColor: '#22C55E' },
    completed: { action: 'finished',             dotColor: '#22C55E' },
    stopped:   { action: 'was stopped',          dotColor: '#5A6578' },
    failed:    { action: 'failed',               dotColor: '#EF4444' },
  };

  // Activity feed derived from recent sims
  const activityEntries = recentSims.slice(0, 5).map((sim) => {
    const { action, dotColor } = STATUS_ACTIVITY[sim.status] ?? {
      action: sim.status,
      dotColor: '#5A6578',
    };
    return {
      id: sim.id,
      text: `Run "${sim.name}" ${action}`,
      dotColor,
      time: formatDistanceToNow(new Date(sim.created_at), { addSuffix: true }),
    };
  });

  if (loading) {
    return (
      <div className="p-6 max-w-6xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <Skeleton className="h-8 w-40" />
          <Skeleton className="h-10 w-40" />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          <Skeleton className="lg:col-span-3 h-72" />
          <div className="lg:col-span-2 space-y-6">
            <Skeleton className="h-44" />
            <Skeleton className="h-52" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <h1 className="font-extrabold text-[22px] text-[#E8ECF2]">Your account</h1>
        <Link
          to="/app/projects"
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#C9A227] text-[#0A0F1C] font-semibold text-sm hover:bg-[#D4AF37] transition-all hover:-translate-y-0.5"
        >
          Start a new product
        </Link>
      </div>

      {loadError && (
        <div className="bg-[#111827] border border-[#EF4444]/25 rounded-2xl p-5">
          <p className="text-sm font-medium text-[#E8ECF2]">
            We could not load your figures
          </p>
          <p className="text-xs text-[#8B97A8] mt-1.5 leading-relaxed max-w-xl">
            {loadError} Nothing is being shown below rather than zeros — none of these
            numbers were read, and a zero would say you had done nothing.
          </p>
          <button
            type="button"
            onClick={() => void fetchData()}
            className="mt-3 px-4 py-2 rounded-lg bg-[#C9A227] text-[#0A0F1C] text-[13px] font-medium hover:bg-[#D4AF37] transition-colors"
          >
            Try again
          </button>
        </div>
      )}

      {/*
        Stat cards.

        Each one is built only when its figure was actually read. There is no
        placeholder rendering and no zero: an account that could not be reached
        shows fewer cards, which is the honest shape of not knowing.

        The denominators that used to sit beside the first two — "/ 15",
        "/ 50K" — are gone, and deliberately. `GET /billing/status` derives
        both from lookups keyed on the org's plan string, and both fall through
        to a default when the plan is not one of `starter` / `pro` /
        `enterprise`. Every account created by signup is on `free`
        (`api/auth.py:DEFAULT_SIGNUP_PLAN`), which is in neither table — so the
        50,000 a founder read next to "0" is a constant in
        `stripe_service.py`, not their allowance. A limit nobody set is not a
        limit to render.
      */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {figuresKnown && (
          <StatCard
            icon={<Clock className="w-5 h-5" />}
            label="Runs"
            value={billing.simulations_used}
            meta="started since the 1st of this month"
            gradientFrom="#8B5CF6"
            gradientTo="#2563EB"
            iconBg="rgba(139,92,246,0.1)"
            iconColor="#8B5CF6"
          />
        )}
        {/*
          "Agents deployed" read 0 while every run listed underneath said 100
          agents, and both numbers were right — they answer different questions.
          This one counts the people Saibyl actually built, in `simulation_agents`,
          created since the 1st of the current calendar month. A run started in
          July has its people, and none of them were made this month. The meta
          line now says which question is being answered.
        */}
        {figuresKnown && (
          <StatCard
            icon={<Users className="w-5 h-5" />}
            label="People built for you"
            value={billing.agents_used}
            meta="created since the 1st of this month"
            gradientFrom="#2563EB"
            gradientTo="#8B5CF6"
            iconBg="rgba(0,212,255,0.1)"
            iconColor="#2563EB"
          />
        )}
        {finishedCountIsKnown && (
          <StatCard
            icon={<FileText className="w-5 h-5" />}
            label="Finished"
            value={completedSims.length}
            meta="runs with a report you can read"
            gradientFrom="#22C55E"
            gradientTo="#2563EB"
            iconBg="rgba(34,197,94,0.1)"
            iconColor="#22C55E"
          />
        )}
      </div>

      {/* Two-Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Left: Recent Simulations */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, delay: 0.1 }}
          className="lg:col-span-3 bg-[#111827] border border-[#1E293B] rounded-2xl overflow-hidden"
        >
          <div className="px-5 py-4 border-b border-[#1E293B] flex items-center justify-between">
            <h2 className="font-semibold text-[#E8ECF2] text-sm">Your latest runs</h2>
            <Link
              to="/app/simulations"
              className="text-xs text-[#C9A227] hover:text-[#D4AF37] transition-colors flex items-center gap-1"
            >
              See all of them <ArrowRight className="w-3 h-3" />
            </Link>
          </div>

          {/* An empty list and an unread list are different things, so the
              "you have not done this yet" copy is shown only when the request
              came back. */}
          {loadError ? (
            <div className="py-12 text-center">
              <p className="text-[#5A6578] text-sm">
                Your runs could not be read, so none are listed.
              </p>
            </div>
          ) : recentSims.length === 0 ? (
            <div className="py-12 text-center">
              <p className="text-[#5A6578] text-sm mb-4">No runs yet</p>
              <Link
                to="/app/simulations/new"
                className="text-sm text-[#C9A227] hover:text-[#D4AF37] transition-colors"
              >
                Start your first run
              </Link>
            </div>
          ) : (
            <div>
              {recentSims.map((sim, i) => (
                <Link
                  key={sim.id}
                  to={`/app/simulations/${sim.id}`}
                  className={`flex items-center justify-between px-5 py-3.5 hover:bg-white/[0.02] transition-colors ${
                    i < recentSims.length - 1 ? 'border-b border-[#1E293B]/50' : ''
                  }`}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <StatusDot status={sim.status} />
                    <span className="text-sm font-medium text-[#E8ECF2] truncate">
                      {sim.name}
                    </span>
                  </div>
                  <div className="flex items-center gap-4 shrink-0 ml-4">
                    {/* `simulations.agent_count` is written from the request
                        body when a run is created and overwritten with the real
                        figure once the people are built. Before that it is what
                        was asked for, not what exists — so it is shown only
                        from the point where those two are the same thing. */}
                    {sim.agent_count != null && !BEFORE_AGENTS.has(sim.status) && (
                      <span className="text-xs text-[#5A6578] font-mono">
                        {formatCount(sim.agent_count)} people
                      </span>
                    )}
                    {sim.platforms && sim.platforms.length > 0 && (
                      <span className="text-xs text-[#5A6578] font-mono">
                        {sim.platforms.length} platform{sim.platforms.length !== 1 ? 's' : ''}
                      </span>
                    )}
                    <span className="text-xs text-[#5A6578]">
                      {formatDistanceToNow(new Date(sim.created_at), { addSuffix: true })}
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </motion.div>

        {/* Right Column */}
        <div className="lg:col-span-2 space-y-6">
          {/* Quick Launch Card */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, delay: 0.15 }}
            className="bg-gradient-to-r from-[#8B5CF6] to-[#2563EB] p-px rounded-2xl"
          >
            <div className="bg-[#111827] rounded-2xl p-6">
              <div className="flex items-center gap-3 mb-3">
                <div className="w-10 h-10 rounded-xl bg-[#8B5CF6]/10 flex items-center justify-center">
                  <Zap className="w-5 h-5 text-[#8B5CF6]" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-[#E8ECF2]">Add something you sell</h3>
                  <p className="text-xs text-[#5A6578]">
                    Upload what you have written and find out what people will argue with
                  </p>
                </div>
              </div>
              <Link
                to="/app/projects"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-[#C9A227] text-[#0A0F1C] font-semibold text-sm hover:bg-[#D4AF37] transition-all hover:-translate-y-0.5 mt-2"
              >
                New product <ArrowRight className="w-4 h-4" />
              </Link>
            </div>
          </motion.div>

          {/* Activity Feed */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, delay: 0.2 }}
            className="bg-[#111827] border border-[#1E293B] rounded-2xl overflow-hidden"
          >
            <div className="px-5 py-4 border-b border-[#1E293B]">
              <h2 className="font-semibold text-[#E8ECF2] text-sm">What happened recently</h2>
            </div>
            {loadError ? (
              <div className="py-8 text-center">
                <p className="text-[#5A6578] text-sm">Nothing could be read.</p>
              </div>
            ) : activityEntries.length === 0 ? (
              <div className="py-8 text-center">
                <p className="text-[#5A6578] text-sm">Nothing has happened yet</p>
              </div>
            ) : (
              <div className="divide-y divide-[#1E293B]/50">
                {activityEntries.map((entry) => (
                  <div key={entry.id} className="px-5 py-3 flex items-start gap-3">
                    <span
                      className="mt-1.5 h-2 w-2 rounded-full shrink-0"
                      style={{ backgroundColor: entry.dotColor }}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="text-xs text-[#E8ECF2] leading-relaxed truncate">
                        {entry.text}
                      </p>
                      <p className="text-[11px] text-[#5A6578] mt-0.5">{entry.time}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </motion.div>
        </div>
      </div>
    </div>
  );
}
