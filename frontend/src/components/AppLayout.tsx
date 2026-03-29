import { Link, Outlet, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  LayoutDashboard,
  FolderOpen,
  FlaskConical,
  TrendingUp,
  Settings,
  LogOut,
  Zap,
} from 'lucide-react';
import { useAuthStore } from '@/store/auth';

const navItems = [
  { path: '/app/dashboard',   label: 'Dashboard',   Icon: LayoutDashboard },
  { path: '/app/projects',    label: 'Projects',    Icon: FolderOpen },
  { path: '/app/simulations', label: 'Simulations', Icon: FlaskConical },
  { path: '/app/markets',     label: 'Markets',     Icon: TrendingUp },
  { path: '/app/settings',    label: 'Settings',    Icon: Settings },
];

export default function AppLayout() {
  const location = useLocation();
  const { user, org, logout } = useAuthStore();

  return (
    <div className="flex h-screen bg-saibyl-void">
      {/* Sidebar */}
      <aside className="w-[220px] flex flex-col border-r border-white/[0.05] bg-saibyl-deep relative overflow-hidden shrink-0">
        {/* Ambient glow */}
        <div className="absolute top-0 left-0 w-full h-48 bg-[radial-gradient(ellipse_at_top_left,rgba(91,95,238,0.08)_0%,transparent_70%)] pointer-events-none" />

        {/* Logo */}
        <div className="px-5 py-5 flex items-center gap-2.5">
          <img src="/logo-mark.svg" alt="" className="w-7 h-7" />
          <span
            className="font-display font-extrabold text-[17px] text-gradient select-none"
            style={{ letterSpacing: '-0.025em' }}
          >
            SAIBYL
          </span>
        </div>

        {/* Org label */}
        {org?.name && (
          <div className="px-5 pb-4">
            <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-white/[0.03] border border-white/[0.04]">
              <Zap className="w-3 h-3 text-saibyl-indigo shrink-0" />
              <span className="text-[11px] text-saibyl-muted truncate">{org.name}</span>
            </div>
          </div>
        )}

        {/* Nav */}
        <nav className="flex-1 px-3 space-y-0.5">
          {navItems.map(({ path, label, Icon }) => {
            const isActive = location.pathname.startsWith(path);
            return (
              <Link
                key={path}
                to={path}
                className="relative flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13px] font-medium transition-colors group"
              >
                {/* Active pill background */}
                <AnimatePresence>
                  {isActive && (
                    <motion.span
                      layoutId="sidebar-active"
                      className="absolute inset-0 rounded-xl bg-saibyl-elevated border border-saibyl-indigo/20"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.18 }}
                    />
                  )}
                </AnimatePresence>

                <Icon
                  className={`relative w-4 h-4 shrink-0 transition-colors ${
                    isActive ? 'text-saibyl-indigo' : 'text-saibyl-muted group-hover:text-saibyl-platinum'
                  }`}
                />
                <span
                  className={`relative transition-colors ${
                    isActive ? 'text-saibyl-platinum' : 'text-saibyl-muted group-hover:text-saibyl-platinum'
                  }`}
                >
                  {label}
                </span>

                {/* Active left accent */}
                {isActive && (
                  <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 rounded-full bg-saibyl-indigo" />
                )}
              </Link>
            );
          })}
        </nav>

        {/* Footer */}
        <div className="p-4 border-t border-white/[0.04] space-y-1">
          <p className="text-[11px] text-saibyl-muted truncate px-1">{user?.email}</p>
          <button
            onClick={logout}
            className="flex items-center gap-2 text-[12px] text-saibyl-muted hover:text-saibyl-platinum transition-colors px-1 py-0.5 group"
          >
            <LogOut className="w-3.5 h-3.5 group-hover:text-saibyl-negative transition-colors" />
            Sign out
          </button>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        {/* Top bar */}
        <header className="h-14 border-b border-white/[0.04] flex items-center px-6 shrink-0 bg-saibyl-void/80 backdrop-blur-sm">
          <div className="flex-1" />
          {org?.plan && (
            <div className="flex items-center gap-1.5 px-3 py-1 rounded-full border border-saibyl-indigo/20 bg-saibyl-indigo/5">
              <span className="w-1.5 h-1.5 rounded-full bg-saibyl-positive" />
              <span className="font-mono text-[10px] tracking-widest uppercase text-saibyl-indigo">
                {org.plan}
              </span>
            </div>
          )}
        </header>

        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
