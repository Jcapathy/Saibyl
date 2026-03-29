import { Link, Outlet, useLocation } from 'react-router-dom';
import { useAuthStore } from '@/store/auth';

const navItems = [
  { path: '/app/dashboard', label: 'Dashboard', icon: '📊' },
  { path: '/app/projects', label: 'Projects', icon: '📁' },
  { path: '/app/simulations', label: 'Simulations', icon: '🧪' },
  { path: '/app/markets', label: 'Markets', icon: '📈' },
  { path: '/app/settings', label: 'Settings', icon: '⚙️' },
];

export default function AppLayout() {
  const location = useLocation();
  const { user, org, logout } = useAuthStore();

  return (
    <div className="flex h-screen bg-saibyl-void">
      {/* Sidebar */}
      <aside className="w-64 bg-saibyl-deep flex flex-col border-r border-saibyl-border">
        <div className="p-6">
          <div className="flex items-center gap-3 mb-1">
            <img src="/logo-mark.svg" alt="" className="w-8 h-8" />
            <span className="text-lg font-display font-extrabold text-gradient" style={{ letterSpacing: '-0.02em' }}>SAIBYL</span>
          </div>
          <p className="text-xs text-saibyl-muted ml-11">{org?.name || 'Swarm Intelligence'}</p>
        </div>
        <nav className="flex-1 px-3">
          {navItems.map((item) => {
            const isActive = location.pathname.startsWith(item.path);
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg mb-1 text-sm transition-colors ${
                  isActive
                    ? 'bg-saibyl-elevated text-saibyl-platinum border-l-[3px] border-saibyl-indigo'
                    : 'text-saibyl-muted hover:bg-saibyl-elevated/50 hover:text-saibyl-platinum'
                }`}
              >
                <span className={isActive ? 'text-saibyl-indigo' : ''}>{item.icon}</span>
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="p-4 border-t border-saibyl-border">
          <p className="text-sm text-saibyl-muted truncate">{user?.email}</p>
          <button onClick={logout} className="text-xs text-saibyl-muted hover:text-saibyl-platinum mt-1 transition-colors">
            Sign out
          </button>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top bar */}
        <header className="h-14 bg-saibyl-void border-b border-[rgba(255,255,255,0.04)] flex items-center px-6 shrink-0">
          <div className="flex-1" />
          <span className="text-label text-saibyl-muted">{org?.plan?.toUpperCase() || 'STARTER'}</span>
        </header>

        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
