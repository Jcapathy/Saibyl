import { useState, useEffect, useCallback } from 'react';
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom';
import {
  FileText,
  LayoutDashboard,
  FolderOpen,
  Clock,
  Search,
  Users,
  Settings,
  LogOut,
  ChevronDown,
  Menu,
  X,
} from 'lucide-react';
import { useAuthStore } from '@/store/auth';
import api from '@/lib/api';

interface CreditBalance {
  balance: number;
  grant: number;
  /** Runs the balance still affords, or null when the run price is unknown. */
  runs_left: number | null;
}

/* ------------------------------------------------------------------ */
/*  Nav definitions                                                    */
/* ------------------------------------------------------------------ */

/**
 * A nav row carries a lucide icon **or** a journey mark, never both and never
 * neither — the union is what keeps a stage from quietly falling back to a
 * generic glyph, which is how the nav drifted from the landing page the first
 * time.
 */
type NavItem = { path: string; label: string } & (
  | { Icon: React.ComponentType<{ className?: string }>; Mark?: never }
  | { Mark: string; Icon?: never }
);

/**
 * The five stages the landing page sells, in the order it sells them.
 *
 * **This nav used to be a list of nouns that mapped to none of them.** A
 * founder read "Validate · Position · Launch · Grow · Raise" on the way in,
 * signed up, and arrived at Home · Your reports · IP check · Who would fund
 * this · Settings — a different product wearing the same name. The website
 * check and the three sales artifacts were reachable only as steps inside a
 * product, three clicks behind "Everything you uploaded", which is why the
 * founder could not find his own flagship on his first read of the live site.
 *
 * The marks are the landing page's own (`LandingPage.tsx`, the journey
 * section), and the copy on each page is that section's copy verbatim. Two
 * surfaces telling one story, in the same words and the same symbols — so the
 * promise and the product cannot drift apart without somebody noticing.
 */
const STAGE_MARKS = {
  validate: '◎',
  position: '✦',
  launch: '⌁',
  grow: '↗',
  raise: '◈',
} as const;

const coreNav: NavItem[] = [
  { path: '/app/home', label: 'Home', Icon: LayoutDashboard },
  /* Second, deliberately. It is the tutorial for everything under it, and it
     sat at the bottom of "Everything else" where nobody looking for help would
     think to open it. */
  { path: '/app/guide', label: 'How this works', Icon: Search },
  /* Third: everything the founder has already made.
     Until 2026-08-29 there was no such list. Each module stored its own
     output and the Reports section read only `reports`, which simulation
     runs write — so a founder with four website checks and a page rewrite
     saw an empty page and had to remember which stage produced what.
     Sits above the journey because it is about what is behind you. */
  { path: '/app/work', label: 'Your work', Icon: FileText },

  /* ── The journey ── */
  { path: '/app/validate', label: 'Validate', Mark: STAGE_MARKS.validate },
  /* The website check and its revision live here. The landing already
     describes them without jargon — "test the fix on the same room, and watch
     the delta" — so they are that sentence rather than a noun of their own. */
  { path: '/app/position', label: 'Position', Mark: STAGE_MARKS.position },
  /* Go-to-market: the messaging document, the outbound sequences, and the
     head-to-head message test that was a separate noun only because the
     comparison had no door when it shipped. */
  { path: '/app/launch', label: 'Launch', Mark: STAGE_MARKS.launch },
  { path: '/app/grow', label: 'Grow', Mark: STAGE_MARKS.grow },
  /* The family-office bank. Route stays `/app/capital` — every existing link
     to it keeps working — while the label joins the journey. */
  { path: '/app/capital', label: 'Raise', Mark: STAGE_MARKS.raise },

  /* After the journey, because it holds what the journey produced. */
  { path: '/app/dashboard', label: 'Your reports', Icon: FileText },
];

/**
 * The surfaces the rail does not lead to yet.
 *
 * Kept, and kept **reachable**, for two reasons. The first is that the rail
 * ships additively: if it turns out to be the wrong shape the fix is a
 * navigation change, not a revert of a night's work. The second is that
 * Audiences, Companies and the whole scoreboard once shipped with no route to
 * them at all — deployed, working, and reachable only by typing a URL, which is
 * the same as not having shipped them. Removing these links to make the sidebar
 * tidy would reproduce exactly that.
 *
 * Under a heading that says what they are, rather than pretending they are part
 * of the main path.
 */
const alsoNav: NavItem[] = [
  { path: '/app/projects', label: 'Everything you uploaded', Icon: FolderOpen },
  { path: '/app/audiences', label: 'Audiences you can reuse', Icon: Users },
  { path: '/app/simulations', label: 'Every run', Icon: Clock },
  /* Last, because it is the only entry here nobody visits to do work. */
  { path: '/app/settings', label: 'Settings', Icon: Settings },
];

/* **Companies is gone, and Message tests moved.**
 *
 * Companies: GTM discovery ranks candidates against a buyer archetype rather
 * than against intent to buy, and on a live security run it returned the
 * competitors building the same product — companies that would never be
 * customers. Founder's decision to drop it. Its routes and backend remain for
 * now, so the decision is reversible; only the way in is gone.
 *
 * Message tests: folded into Launch, where the landing page already sells it —
 * "up to eight versions of the message, head to head, in front of the same
 * room". It was a separate noun only because the comparison shipped without a
 * door, which is the same defect this whole restructure exists to close. */

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

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
        background: 'linear-gradient(135deg, #8b73ee, #286cf0)',
      }}
    >
      {getInitials(text)}
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="block px-3 pt-5 pb-1.5 font-mono text-[9px] font-semibold uppercase tracking-widest text-saibyl-muted select-none">
      {children}
    </span>
  );
}

function NavLink({ item, pathname, onClick }: { item: NavItem; pathname: string; onClick?: () => void }) {
  const isActive = pathname.startsWith(item.path);
  const { Icon, Mark } = item;
  const glyphTone = isActive ? 'text-saibyl-blue' : 'text-saibyl-muted';

  return (
    <Link
      to={item.path}
      onClick={onClick}
      className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] font-medium transition-all ${
        isActive
          ? 'bg-[rgba(40,108,240,0.10)] text-saibyl-ink'
          : 'text-saibyl-silver hover:bg-[#14294a]/[0.04] hover:text-saibyl-ink'
      }`}
    >
      {Mark ? (
        /* The landing page's mark, at the icon's width so the two kinds of row
           share one text column. `aria-hidden` because the label already says
           the word — a screen reader announcing "black circle Validate" is
           noise. */
        <span
          aria-hidden
          className={`w-4 shrink-0 text-center text-[12px] leading-4 ${glyphTone}`}
        >
          {Mark}
        </span>
      ) : (
        Icon && <Icon className={`w-4 h-4 shrink-0 ${glyphTone}`} />
      )}
      {item.label}
    </Link>
  );
}

function UsageSkeleton() {
  return (
    <div className="space-y-3 animate-pulse">
      {[1, 2].map((i) => (
        <div key={i} className="space-y-1">
          <div className="flex justify-between">
            <div className="h-3 w-16 rounded bg-[#14294a]/[0.06]" />
            <div className="h-3 w-20 rounded bg-[#14294a]/[0.06]" />
          </div>
          <div className="h-1.5 rounded-full bg-[#14294a]/[0.06]" />
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
  const [credits, setCredits] = useState<CreditBalance | null>(null);
  const [creditsLoading, setCreditsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    api
      .get<{
        balance: number;
        grant: number;
        standard_run_credits?: number;
        capped_run_credits?: number;
      }>('/billing/credits')
      .then(({ data }) => {
        if (cancelled) return;
        /*
          The price of a run **this account can actually configure**, not the
          100-agent reference. Dividing a free balance by the reference price
          printed "About 0 more runs" to every new signup while their 1,500
          grant covered a full capped run (1,273) with headroom — the app
          denying the free run that is the entire launch motion, on every
          page, in contradiction of the landing page and the pricing guide.
          `standard_run_credits` remains the fallback for an older backend.
        */
        const perRun = data.capped_run_credits ?? data.standard_run_credits;
        setCredits({
          balance: data.balance ?? 0,
          grant: data.grant ?? 0,
          // Floored, so it can only understate. Null rather than 0 when we do
          // not know the run price - "about 0 runs left" reads as a refusal.
          runs_left:
            typeof perRun === 'number' && perRun > 0
              ? Math.floor((data.balance ?? 0) / perRun)
              : null,
        });
      })
      .catch(() => {
        /* The bar simply does not draw. A balance we could not read must not
           render as a number, and 0 is the number that would frighten someone
           into not clicking. */
      })
      .finally(() => {
        if (!cancelled) setCreditsLoading(false);
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
      <div className="px-5 py-5 flex items-center gap-2.5 border-b border-saibyl-border">
        {/* The landing page's brand mark, not the dark-era logo asset. */}
        <span
          className="grid place-items-center w-8 h-8 rounded-[9px] text-white font-serif font-bold text-[19px] leading-none select-none"
          style={{
            background: 'linear-gradient(135deg, #2f75ef 5%, #705ee3 95%)',
            boxShadow: 'inset 0 1px rgba(255,255,255,.4), 0 5px 14px rgba(75,98,221,.28)',
          }}
        >
          S
        </span>
        <span className="flex flex-col select-none">
          <span className="text-saibyl-ink font-extrabold text-base leading-none" style={{ letterSpacing: '-0.04em' }}>
            Saibyl
          </span>
          <span className="font-mono text-[7.5px] tracking-[0.07em] text-saibyl-muted mt-0.5">
            BY SAIDO LABS
          </span>
        </span>
      </div>

      {/* Organization selector */}
      {org && (
        <div className="px-4 pt-4 pb-2">
          {/* TODO: Multi-org selector */}
          <button
            type="button"
            className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-[10px] bg-white border border-saibyl-border hover:border-saibyl-border-light transition-colors text-left"
          >
            <GradientAvatar text={org.name} size={28} />
            <div className="flex-1 min-w-0">
              <p className="text-[13px] font-medium text-saibyl-ink truncate">{org.name}</p>
              <p className="font-mono text-[9px] uppercase tracking-widest text-saibyl-blue">{org.plan}</p>
            </div>
            <ChevronDown className="w-3.5 h-3.5 text-saibyl-muted shrink-0" />
          </button>
        </div>
      )}

      {/* Navigation */}
      <nav className="flex-1 px-3 overflow-y-auto">
        {coreNav.map((item) => (
          <NavLink key={item.path} item={item} pathname={location.pathname} onClick={closeMobile} />
        ))}

        <SectionLabel>Everything else</SectionLabel>
        {alsoNav.map((item) => (
          <NavLink key={item.path} item={item} pathname={location.pathname} onClick={closeMobile} />
        ))}
      </nav>

      {/* What you have left, in the unit that is actually metered.

          This showed "Runs 3/15" and "People in the room 0/50K". Neither
          number constrained anything:

          - `simulations_limit` reads `PLAN_LIMITS`, whose keys are the V1 plan
            names. Signup creates every account on plan `free`, which is not a
            key, so every new founder saw the *starter* limit.
          - `agents_limit` is `agent_limits.get(plan, 50_000)` over a table of
            150,000 / 7,500,000 / 50,000,000. The 50K every signup saw was a
            hardcoded `.get()` default belonging to no plan at all.

          Credits are the metered unit (DECISIONS §15b) - they are what a run
          is charged against and what runs out. So that is what is shown, with
          what it buys next to it, because "1,317" means nothing on its own to
          someone deciding whether they can afford to click. */}
      <div className="px-4 py-3 border-t border-saibyl-border">
        {creditsLoading ? (
          <UsageSkeleton />
        ) : credits ? (
          <>
            <div className="flex items-center justify-between text-[11px] mb-1">
              <span className="text-saibyl-muted">Credits left</span>
              <span className="text-saibyl-silver font-mono tabular-nums">
                {credits.balance.toLocaleString()}
              </span>
            </div>
            {credits.grant > 0 && (
              <div className="h-1.5 rounded-full bg-[#14294a]/[0.08] overflow-hidden">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-[#8b73ee] to-[#286cf0] transition-all"
                  style={{
                    width: `${Math.min((credits.balance / credits.grant) * 100, 100)}%`,
                  }}
                />
              </div>
            )}
            <Link
              to="/app/settings"
              className="block text-[10.5px] text-saibyl-muted hover:text-saibyl-silver mt-1.5 leading-snug transition-colors"
            >
              {credits.runs_left !== null
                ? `About ${credits.runs_left} more ${credits.runs_left === 1 ? 'run' : 'runs'} \u2014 add more`
                : 'Add more'}
            </Link>
          </>
        ) : null}
      </div>

      {/* User footer */}
      <div className="px-4 py-3 border-t border-saibyl-border">
        <div className="flex items-center gap-2.5">
          <GradientAvatar text={user?.email ?? '??'} size={32} />
          <div className="flex-1 min-w-0">
            <p className="text-[13px] font-medium text-saibyl-ink truncate">{userName}</p>
            <p className="text-[11px] text-saibyl-muted truncate">{user?.email}</p>
          </div>
        </div>
        <button
          onClick={handleLogout}
          className="mt-2.5 flex items-center gap-2 text-[12px] text-saibyl-muted hover:text-saibyl-ink transition-colors px-1 py-1 group"
        >
          <LogOut className="w-3.5 h-3.5 group-hover:text-saibyl-negative transition-colors" />
          Sign out
        </button>
      </div>
    </div>
  );

  return (
    <div className="flex h-screen bg-saibyl-paper">
      {/* Mobile toggle button */}
      <button
        className="lg:hidden fixed top-4 left-4 z-50 p-2 rounded-lg bg-white border border-saibyl-border text-saibyl-silver hover:text-saibyl-ink shadow-sm transition-colors"
        onClick={() => setMobileOpen((o) => !o)}
      >
        {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
      </button>

      {/* Sidebar */}
      <aside
        className={`fixed top-0 left-0 h-screen w-[260px] bg-white/[0.78] backdrop-blur-xl border-r border-saibyl-border z-40 transition-transform ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        } lg:translate-x-0`}
      >
        {sidebarContent}
      </aside>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-[#14294a]/30 z-30 lg:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Main content */}
      <div className="flex-1 lg:ml-[260px] flex flex-col min-h-screen">
        {/* Mobile: clear the fixed menu toggle so page headings never sit under it. */}
        <main className="flex-1 overflow-auto pt-12 lg:pt-0">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
