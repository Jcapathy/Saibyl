import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Clock, Users, FileText, Activity, Zap, ArrowRight } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import api from '@/lib/api';

interface Simulation {
  id: string;
  name: string;
  status: string;
  created_at: string;
  platforms?: string[];
  agent_count?: number;
  sentiment_score?: number;
}

interface BillingStatus {
  plan: string;
  simulations_used: number;
  simulations_limit: number;
  agents_used?: number;
  agents_limit?: number;
}

function formatCount(n: number | undefined | null): string {
  if (n == null) return '—';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n % 1_000_000 === 0 ? 0 : 1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(n % 1_000 === 0 ? 0 : 1)}K`;
  return n.toString();
}

const STATUS_COLORS: Record<string, string> = {
  running: '#3B82F6',
  completed: '#22C55E',
  complete: '#22C55E',
  queued: '#F59E0B',
  failed: '#EF4444',
  draft: '#818CF8',
};

function StatusDot({ status }: { status: string }) {
  const color = STATUS_COLORS[status] ?? '#5A6578';
  const isRunning = status === 'running';
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
  return <div className={`animate-pulse bg-[#111820] rounded-2xl ${className}`} />;
}

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
  value: React.ReactNode;
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
      className="bg-[#111820] border border-[#1B2433] rounded-2xl p-5 relative overflow-hidden"
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
      <p className="text-2xl font-bold text-[#E8ECF2]">{value}</p>
      <p className="text-xs text-[#5A6578] mt-1">{meta}</p>
    </motion.div>
  );
}

export default function DashboardPage() {
  const [recentSims, setRecentSims] = useState<Simulation[]>([]);
  const [allSims, setAllSims] = useState<Simulation[]>([]);
  const [billing, setBilling] = useState<BillingStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchData() {
      try {
        const [recentRes, allRes, billRes] = await Promise.all([
          api.get('/simulations', { params: { limit: 5 } }),
          api.get('/simulations', { params: { limit: 100 } }),
          api.get('/billing/status'),
        ]);
        setRecentSims(recentRes.data.items || recentRes.data);
        setAllSims(allRes.data.items || allRes.data);
        setBilling(billRes.data);
      } catch {
        // Dashboard renders with fallback values
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  // Derived stats
  const completedSims = allSims.filter(
    (s) => s.status === 'completed' || s.status === 'complete',
  );

  const avgSentiment = (() => {
    const withScore = completedSims.filter(
      (s) => s.sentiment_score != null,
    );
    if (withScore.length === 0) return null;
    const sum = withScore.reduce((acc, s) => acc + (s.sentiment_score ?? 0), 0);
    return (sum / withScore.length).toFixed(2);
  })();

  // Activity feed derived from recent sims
  const activityEntries = recentSims.slice(0, 5).map((sim) => {
    let action: string;
    let dotColor: string;
    if (sim.status === 'completed' || sim.status === 'complete') {
      action = 'completed';
      dotColor = '#22C55E';
    } else if (sim.status === 'running') {
      action = 'started running';
      dotColor = '#3B82F6';
    } else if (sim.status === 'failed') {
      action = 'failed';
      dotColor = '#EF4444';
    } else if (sim.status === 'queued') {
      action = 'queued';
      dotColor = '#F59E0B';
    } else {
      action = 'created';
      dotColor = '#818CF8';
    }
    return {
      id: sim.id,
      text: `Simulation "${sim.name}" ${action}`,
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
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Skeleton className="h-32" />
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
        <h1 className="font-extrabold text-[22px] text-[#E8ECF2]">Dashboard</h1>
        <Link
          to="/app/projects"
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#C9A227] text-[#070B14] font-semibold text-sm hover:bg-[#D4AF37] transition-all hover:-translate-y-0.5"
        >
          Start a New Project
        </Link>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={<Clock className="w-5 h-5" />}
          label="Simulations"
          value={
            <>
              {billing?.simulations_used ?? '—'}
              <span className="text-sm font-normal text-[#5A6578] ml-1">
                / {billing?.simulations_limit ?? '—'}
              </span>
            </>
          }
          meta="this billing period"
          gradientFrom="#5B5FEE"
          gradientTo="#00D4FF"
          iconBg="rgba(91,95,238,0.1)"
          iconColor="#5B5FEE"
        />
        <StatCard
          icon={<Users className="w-5 h-5" />}
          label="Agents Deployed"
          value={
            <>
              {billing?.agents_used != null ? formatCount(billing.agents_used) : '—'}
              {billing?.agents_limit != null && (
                <span className="text-sm font-normal text-[#5A6578] ml-1">
                  / {formatCount(billing.agents_limit)}
                </span>
              )}
            </>
          }
          meta={billing?.plan ?? '—'}
          gradientFrom="#00D4FF"
          gradientTo="#5B5FEE"
          iconBg="rgba(0,212,255,0.1)"
          iconColor="#00D4FF"
        />
        <StatCard
          icon={<FileText className="w-5 h-5" />}
          label="Reports"
          value={completedSims.length}
          meta="completed simulations"
          gradientFrom="#22C55E"
          gradientTo="#00D4FF"
          iconBg="rgba(34,197,94,0.1)"
          iconColor="#22C55E"
        />
        <StatCard
          icon={<Activity className="w-5 h-5" />}
          label="Avg Sentiment"
          value={avgSentiment ?? '—'}
          meta="across completed sims"
          gradientFrom="#C9A227"
          gradientTo="#5B5FEE"
          iconBg="rgba(201,162,39,0.1)"
          iconColor="#C9A227"
        />
      </div>

      {/* Two-Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Left: Recent Simulations */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, delay: 0.1 }}
          className="lg:col-span-3 bg-[#111820] border border-[#1B2433] rounded-2xl overflow-hidden"
        >
          <div className="px-5 py-4 border-b border-[#1B2433] flex items-center justify-between">
            <h2 className="font-semibold text-[#E8ECF2] text-sm">Recent Simulations</h2>
            <Link
              to="/app/simulations"
              className="text-xs text-[#C9A227] hover:text-[#D4AF37] transition-colors flex items-center gap-1"
            >
              View All <ArrowRight className="w-3 h-3" />
            </Link>
          </div>

          {recentSims.length === 0 ? (
            <div className="py-12 text-center">
              <p className="text-[#5A6578] text-sm mb-4">No simulations yet</p>
              <Link
                to="/app/simulations/new"
                className="text-sm text-[#C9A227] hover:text-[#D4AF37] transition-colors"
              >
                Create your first simulation
              </Link>
            </div>
          ) : (
            <div>
              {recentSims.map((sim, i) => (
                <Link
                  key={sim.id}
                  to={`/app/simulations/${sim.id}`}
                  className={`flex items-center justify-between px-5 py-3.5 hover:bg-white/[0.02] transition-colors ${
                    i < recentSims.length - 1 ? 'border-b border-[#1B2433]/50' : ''
                  }`}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <StatusDot status={sim.status} />
                    <span className="text-sm font-medium text-[#E8ECF2] truncate">
                      {sim.name}
                    </span>
                  </div>
                  <div className="flex items-center gap-4 shrink-0 ml-4">
                    {sim.agent_count != null && (
                      <span className="text-xs text-[#5A6578] font-mono">
                        {formatCount(sim.agent_count)} agents
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
            className="bg-gradient-to-r from-[#5B5FEE] to-[#00D4FF] p-px rounded-2xl"
          >
            <div className="bg-[#111820] rounded-2xl p-6">
              <div className="flex items-center gap-3 mb-3">
                <div className="w-10 h-10 rounded-xl bg-[#5B5FEE]/10 flex items-center justify-center">
                  <Zap className="w-5 h-5 text-[#5B5FEE]" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-[#E8ECF2]">Start a New Project</h3>
                  <p className="text-xs text-[#5A6578]">Set up your scenario and run your first simulation</p>
                </div>
              </div>
              <Link
                to="/app/projects"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-[#C9A227] text-[#070B14] font-semibold text-sm hover:bg-[#D4AF37] transition-all hover:-translate-y-0.5 mt-2"
              >
                Start a Project <ArrowRight className="w-4 h-4" />
              </Link>
            </div>
          </motion.div>

          {/* Activity Feed */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, delay: 0.2 }}
            className="bg-[#111820] border border-[#1B2433] rounded-2xl overflow-hidden"
          >
            <div className="px-5 py-4 border-b border-[#1B2433]">
              <h2 className="font-semibold text-[#E8ECF2] text-sm">Recent Activity</h2>
            </div>
            {activityEntries.length === 0 ? (
              <div className="py-8 text-center">
                <p className="text-[#5A6578] text-sm">No recent activity</p>
              </div>
            ) : (
              <div className="divide-y divide-[#1B2433]/50">
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
