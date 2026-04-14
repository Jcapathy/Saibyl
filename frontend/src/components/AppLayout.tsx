import { useState, useEffect, useCallback } from 'react';
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard,
  FolderOpen,
  Clock,
  BarChart3,
  Search,
  Settings,
  LogOut,
  ChevronDown,
  Menu,
  X,
} from 'lucide-react';
import { useAuthStore } from '@/store/auth';
import api from '@/lib/api';

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface BillingStatus {
  simulations_used: number;
  simulations_limit: number;
  agents_used?: number;
  agents_limit?: number;
}

/* ------------------------------------------------------------------ */
/*  Nav definitions                                                    */
/* ------------------------------------------------------------------ */

interface NavItem {
  path: string;
  label: string;
  Icon: React.ComponentType<{ className?: string }>;
}

const coreNav: NavItem[] = [
  { path: '/app/dashboard', label: 'Dashboard', Icon: LayoutDashboard },
  { path: '/app/projects', label: 'Projects', Icon: FolderOpen },
  { path: '/app/simulations', label: 'Simulations', Icon: Clock },
];

const intelligenceNav: NavItem[] = [
  { path: '/app/markets', label: 'Markets', Icon: BarChart3 },
  { path: '/app/guide', label: 'Guide', Icon: Search },
];

const workspaceNav: NavItem[] = [
  { path: '/app/settings', label: 'Settings', Icon: Settings },
];

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function formatCount(n: number | undefined | null): string {
  if (n == null) return '—';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n % 1_000_000 === 0 ? 0 : 1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(n % 1_000 === 0 ? 0 : 1)}K`;
  return n.toString();
}

function getInitials(value: string): string {
  const parts = value.trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return value.slice(0, 2).toUpperCase();
}

/* ------------------------------------------------------------------ */
/*  Sub-components                                                     */
/* ------------------------------------------------------------------ */

function GradientAvatar({ text, size }: { text: string; size: number }) {
  return (
    <div
      className="shrink-0 rounded-full flex items-center justify-center font-bold text-white select-none"
      style={{
        width: size,
        height: size,
        fontSize: size * 0.38,
        background: 'linear-gradient(135deg, #5B5FEE, #00D4FF)',
      }}
    >
      {getInitials(text)}
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="block px-3 pt-5 pb-1.5 font-mono text-[9px] font-semibold uppercase tracking-widest text-[#5A6578] select-none">
      {children}
    </span>
  );
}

function NavLink({ item, pathname, onClick }: { item: NavItem; pathname: string; onClick?: () => void }) {
  const isActive = pathname.startsWith(item.path);
  const { Icon } = item;

  return (
    <Link
      to={item.path}
      onClick={onClick}
      className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] font-medium transition-all ${
        isActive
          ? 'bg-[rgba(91,95,238,0.12)] text-[#E8ECF2]'
          : 'text-[#8B97A8] hover:bg-white/[0.04] hover:text-[#E8ECF2]'
      }`}
    >
      <Icon
        className={`w-4 h-4 shrink-0 ${
          isActive ? 'text-[#5B5FEE]' : 'text-[#5A6578]'
        }`}
      />
      {item.label}
    </Link>
  );
}

function UsageBar({
  label,
  used,
  limit,
}: {
  label: string;
  used: number;
  limit: number;
}) {
  const pct = limit > 0 ? Math.min((used / limit) * 100, 100) : 0;

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-[11px]">
        <span className="text-[#5A6578]">{label}</span>
        <span className="text-[#8B97A8] font-mono">
          {formatCount(used)} / {formatCount(limit)}
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-white/[0.06] overflow-hidden">
        <div
          className="h-full rounded-full bg-gradient-to-r from-[#5B5FEE] to-[#00D4FF] transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function UsageSkeleton() {
  return (
    <div className="space-y-3 animate-pulse">
      {[1, 2].map((i) => (
        <div key={i} className="space-y-1">
          <div className="flex justify-between">
            <div className="h-3 w-16 rounded bg-white/[0.06]" />
            <div className="h-3 w-20 rounded bg-white/[0.06]" />
          </div>
          <div className="h-1.5 rounded-full bg-white/[0.06]" />
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main component                                                     */
/* ------------------------------------------------------------------ */

export default function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, org, logout } = useAuthStore();

  const [mobileOpen, setMobileOpen] = useState(false);
  const [billing, setBilling] = useState<BillingStatus | null>(null);
  const [billingLoading, setBillingLoading] = useState(true);

  // Fetch billing status on mount
  useEffect(() => {
    let cancelled = false;
    api
      .get<BillingStatus>('/billing/status')
      .then(({ data }) => {
        if (!cancelled) setBilling(data);
      })
      .catch(() => {
        /* silent — usage bars just won't show */
      })
      .finally(() => {
        if (!cancelled) setBillingLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const closeMobile = useCallback(() => setMobileOpen(false), []);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const userName = user?.email?.split('@')[0] ?? '';

  /* ---- Sidebar content (shared between mobile & desktop) ---- */
  const sidebarContent = (
    <div className="flex flex-col h-full">
      {/* Brand header */}
      <div className="px-5 py-5 flex items-center gap-2.5 border-b border-[#1B2433]">
        <img src="/logo-mark.svg" alt="" className="w-8 h-8" />
        <span className="text-gradient-brand font-extrabold text-base select-none" style={{ letterSpacing: '-0.025em' }}>
          SAIBYL
        </span>
      </div>

      {/* Organization selector */}
      {org && (
        <div className="px-4 pt-4 pb-2">
          {/* TODO: Multi-org selector */}
          <button
            type="button"
            className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-[10px] bg-white/[0.03] border border-white/[0.06] hover:bg-white/[0.06] transition-colors text-left"
          >
            <GradientAvatar text={org.name} size={28} />
            <div className="flex-1 min-w-0">
              <p className="text-[13px] font-medium text-[#E8ECF2] truncate">{org.name}</p>
              <p className="font-mono text-[9px] uppercase tracking-widest text-[#7C6CDE]">{org.plan}</p>
            </div>
            <ChevronDown className="w-3.5 h-3.5 text-[#5A6578] shrink-0" />
          </button>
        </div>
      )}

      {/* Navigation */}
      <nav className="flex-1 px-3 overflow-y-auto">
        <SectionLabel>Core</SectionLabel>
        {coreNav.map((item) => (
          <NavLink key={item.path} item={item} pathname={location.pathname} onClick={closeMobile} />
        ))}

        <SectionLabel>Intelligence</SectionLabel>
        {intelligenceNav.map((item) => (
          <NavLink key={item.path} item={item} pathname={location.pathname} onClick={closeMobile} />
        ))}

        <SectionLabel>Workspace</SectionLabel>
        {workspaceNav.map((item) => (
          <NavLink key={item.path} item={item} pathname={location.pathname} onClick={closeMobile} />
        ))}
      </nav>

      {/* Usage bars */}
      <div className="px-4 py-3 border-t border-[#1B2433] space-y-3">
        {billingLoading ? (
          <UsageSkeleton />
        ) : billing ? (
          <>
            <UsageBar
              label="Simulations"
              used={billing.simulations_used}
              limit={billing.simulations_limit}
            />
            {billing.agents_used != null && billing.agents_limit != null && (
              <UsageBar
                label="Agents"
                used={billing.agents_used}
                limit={billing.agents_limit}
              />
            )}
          </>
        ) : null}
      </div>

      {/* User footer */}
      <div className="px-4 py-3 border-t border-[#1B2433]">
        <div className="flex items-center gap-2.5">
          <GradientAvatar text={user?.email ?? '??'} size={32} />
          <div className="flex-1 min-w-0">
            <p className="text-[13px] font-medium text-[#E8ECF2] truncate">{userName}</p>
            <p className="text-[11px] text-[#5A6578] truncate">{user?.email}</p>
          </div>
        </div>
        <button
          onClick={handleLogout}
          className="mt-2.5 flex items-center gap-2 text-[12px] text-[#5A6578] hover:text-[#E8ECF2] transition-colors px-1 py-1 group"
        >
          <LogOut className="w-3.5 h-3.5 group-hover:text-red-400 transition-colors" />
          Sign out
        </button>
      </div>
    </div>
  );

  return (
    <div className="flex h-screen bg-[#070B14]">
      {/* Mobile toggle button */}
      <button
        className="lg:hidden fixed top-4 left-4 z-50 p-2 rounded-lg bg-[#0D1117] border border-[#1B2433] text-[#8B97A8] hover:text-[#E8ECF2] transition-colors"
        onClick={() => setMobileOpen((o) => !o)}
      >
        {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
      </button>

      {/* Sidebar */}
      <aside
        className={`fixed top-0 left-0 h-screen w-[260px] bg-[#0D1117] border-r border-[#1B2433] z-40 transition-transform ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        } lg:translate-x-0`}
      >
        {sidebarContent}
      </aside>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-30 lg:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Main content */}
      <div className="flex-1 lg:ml-[260px] flex flex-col min-h-screen">
        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
