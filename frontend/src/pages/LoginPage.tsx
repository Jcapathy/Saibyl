import { useState, type FormEvent } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Eye, EyeOff, Lock, AlertCircle } from 'lucide-react';
import { useAuthStore } from '@/store/auth';
import { supabase } from '@/lib/supabase';

/* ── Particle data for the brand panel ── */
const PARTICLES: { x: string; y: string; color: string; duration: string; delay: string }[] = [
  { x: '12%', y: '18%', color: '#5B5FEE', duration: '14s', delay: '0s' },
  { x: '78%', y: '24%', color: '#00D4FF', duration: '18s', delay: '-3s' },
  { x: '34%', y: '65%', color: '#5B5FEE', duration: '16s', delay: '-7s' },
  { x: '88%', y: '72%', color: '#00D4FF', duration: '20s', delay: '-2s' },
  { x: '22%', y: '85%', color: '#5B5FEE', duration: '15s', delay: '-5s' },
  { x: '62%', y: '42%', color: '#00D4FF', duration: '17s', delay: '-9s' },
  { x: '48%', y: '12%', color: '#5B5FEE', duration: '19s', delay: '-4s' },
  { x: '92%', y: '52%', color: '#00D4FF', duration: '13s', delay: '-6s' },
];

const NODE_POSITIONS = [
  [12, 18], [78, 24], [34, 65], [88, 72],
  [22, 85], [62, 42], [48, 12], [92, 52],
] as const;

/* ── Shared input class ── */
const INPUT_CLASS =
  'w-full px-4 py-[0.6875rem] rounded-[10px] border border-white/[0.06] bg-white/[0.025] text-[#E8ECF2] text-sm placeholder:text-[#94A3B8]/40 outline-none transition-all duration-200 focus:border-[rgba(91,95,238,0.5)] focus:shadow-[0_0_0_3px_rgba(91,95,238,0.1),0_0_20px_rgba(91,95,238,0.05)] focus:bg-white/[0.04]';

/* ── Stats data ── */
const STATS: { value: string; label: string }[] = [
  { value: '1M', label: 'Max Agents' },
  { value: '8', label: 'Platforms' },
  { value: '42', label: 'Archetypes' },
  { value: '<3pp', label: 'Precision' },
];

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const login = useAuthStore((s) => s.login);
  const navigate = useNavigate();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(email, password);
      navigate('/app/dashboard');
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? (err as Error & { response?: { data?: { detail?: string } } }).response?.data?.detail ||
            err.message
          : 'Login failed';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleSSO = async () => {
    // TODO: After Supabase OAuth callback, exchange session for app JWT tokens via backend endpoint
    await supabase.auth.signInWithOAuth({ provider: 'google' });
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 min-h-screen">
      {/* ═══════════════════════════════════════════════════
          LEFT PANEL — Brand
         ═══════════════════════════════════════════════════ */}
      <div className="hidden lg:flex relative flex-col justify-center px-16 xl:px-20 bg-[#070B14] overflow-hidden">
        {/* Radial gradient accents */}
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute top-[20%] left-[10%] w-[60%] h-[60%] rounded-full bg-[radial-gradient(ellipse,rgba(91,95,238,0.08)_0%,transparent_70%)]" />
          <div className="absolute bottom-[10%] right-[5%] w-[50%] h-[50%] rounded-full bg-[radial-gradient(ellipse,rgba(0,212,255,0.06)_0%,transparent_70%)]" />
        </div>

        {/* Particle animation */}
        {PARTICLES.map((p, i) => (
          <div
            key={i}
            className="absolute w-[4px] h-[4px] rounded-full animate-drift"
            style={{
              left: p.x,
              top: p.y,
              backgroundColor: p.color,
              animationDuration: p.duration,
              animationDelay: p.delay,
              opacity: 0.6,
            }}
          />
        ))}

        {/* Connection lines SVG */}
        <svg className="absolute inset-0 w-full h-full pointer-events-none" style={{ opacity: 0.06 }}>
          {NODE_POSITIONS.map(([x1, y1], i) =>
            NODE_POSITIONS.slice(i + 1).map(([x2, y2], j) => (
              <line
                key={`${i}-${j}`}
                x1={`${x1}%`}
                y1={`${y1}%`}
                x2={`${x2}%`}
                y2={`${y2}%`}
                stroke="#5B5FEE"
                strokeWidth="1"
              />
            )),
          )}
        </svg>

        {/* Content */}
        <div className="relative z-10">
          {/* Logo lockup */}
          <div className="flex items-center gap-3 mb-10">
            <img src="/logo-mark.svg" alt="" className="w-12 h-12" />
            <span
              className="text-gradient-brand font-extrabold text-[1.75rem]"
              style={{ letterSpacing: '-0.03em' }}
            >
              SAIBYL
            </span>
          </div>

          {/* Trust line */}
          <div className="flex items-center gap-2 mb-6">
            <span className="block w-[6px] h-[6px] rounded-full bg-emerald-400 animate-pulse-dot" />
            <span className="text-sm text-[#8B97A8]">
              Predictive intelligence for decision-makers
            </span>
          </div>

          {/* Tagline */}
          <h1 className="text-[2.75rem] font-bold tracking-tight leading-[1.1] text-white mb-5">
            Know the conversation{' '}
            <span className="text-gradient-brand">before it happens.</span>
          </h1>

          {/* Subtitle */}
          <p className="text-[#8B97A8] text-base leading-relaxed max-w-md mb-12">
            Simulate public reactions across 8 platforms with up to 1,000,000
            synthetic agents powered by swarm intelligence.
          </p>

          {/* Stats row */}
          <div className="grid grid-cols-4 gap-6">
            {STATS.map((s) => (
              <div key={s.label}>
                <div
                  className="text-gradient-brand text-2xl font-bold"
                  style={{ fontFamily: "'JetBrains Mono', monospace" }}
                >
                  {s.value}
                </div>
                <div
                  className="text-[#8B97A8] text-[10px] uppercase tracking-widest mt-1"
                  style={{ fontFamily: "'JetBrains Mono', monospace" }}
                >
                  {s.label}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ═══════════════════════════════════════════════════
          RIGHT PANEL — Form
         ═══════════════════════════════════════════════════ */}
      <div className="flex items-center justify-center bg-[#0D1117] lg:border-l lg:border-[#1B2433] px-6 py-12">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: [0.25, 0.46, 0.45, 0.94] }}
          className="w-full max-w-[400px]"
        >
          {/* Mobile logo — only on small screens */}
          <div className="flex lg:hidden items-center justify-center gap-2.5 mb-10">
            <img src="/logo-mark.svg" alt="" className="w-9 h-9" />
            <span
              className="text-gradient-brand font-extrabold text-xl"
              style={{ letterSpacing: '-0.03em' }}
            >
              SAIBYL
            </span>
          </div>

          {/* Header */}
          <h2 className="text-2xl font-bold text-white mb-1">Welcome back</h2>
          <p className="text-sm text-[#8B97A8] mb-8">
            Sign in to access your intelligence dashboard
          </p>

          {/* Error display */}
          {error && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              className="mb-6 flex items-start gap-3 px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/20"
            >
              <AlertCircle className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />
              <span className="text-sm text-red-400">{error}</span>
            </motion.div>
          )}

          {/* Google SSO */}
          <button
            type="button"
            onClick={handleGoogleSSO}
            className="w-full flex items-center justify-center gap-3 px-4 py-[0.6875rem] rounded-[10px] border border-white/[0.12] bg-transparent text-sm font-medium text-[#E8ECF2] transition-all duration-200 hover:bg-white/[0.04] hover:border-white/[0.18]"
          >
            {/* Google "G" icon */}
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
              <path
                d="M17.64 9.205c0-.639-.057-1.252-.164-1.841H9v3.481h4.844a4.14 4.14 0 01-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z"
                fill="#4285F4"
              />
              <path
                d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 009 18z"
                fill="#34A853"
              />
              <path
                d="M3.964 10.71A5.41 5.41 0 013.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.997 8.997 0 000 9c0 1.452.348 2.827.957 4.042l3.007-2.332z"
                fill="#FBBC05"
              />
              <path
                d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 00.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z"
                fill="#EA4335"
              />
            </svg>
            Continue with Google
          </button>

          {/* Divider */}
          <div className="flex items-center gap-4 my-6">
            <div className="flex-1 h-px bg-white/[0.06]" />
            <span
              className="text-[11px] text-[#8B97A8] uppercase"
              style={{ fontFamily: "'JetBrains Mono', monospace" }}
            >
              or
            </span>
            <div className="flex-1 h-px bg-white/[0.06]" />
          </div>

          {/* Login form */}
          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Email */}
            <div>
              <label
                className="block text-[11px] font-medium text-[#8B97A8] uppercase tracking-wider mb-2"
                style={{ fontFamily: "'JetBrains Mono', monospace" }}
              >
                Email
              </label>
              <input
                type="email"
                name="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                className={INPUT_CLASS}
              />
            </div>

            {/* Password */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label
                  className="block text-[11px] font-medium text-[#8B97A8] uppercase tracking-wider"
                  style={{ fontFamily: "'JetBrains Mono', monospace" }}
                >
                  Password
                </label>
                {/* TODO: Wire to password reset flow */}
                <button
                  type="button"
                  className="text-[11px] text-[#C9A227] hover:text-[#D4AF37] transition-colors"
                >
                  Forgot password?
                </button>
              </div>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  name="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className={INPUT_CLASS}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-[#8B97A8] hover:text-[#E8ECF2] transition-colors"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* Sign In button */}
            <button
              type="submit"
              disabled={loading}
              className="w-full py-[0.6875rem] rounded-[10px] bg-[#C9A227] text-[#070B14] text-sm font-semibold transition-all duration-200 hover:bg-[#D4AF37] hover:shadow-[0_4px_20px_rgba(201,162,39,0.3)] hover:-translate-y-[1px] disabled:opacity-60 disabled:hover:translate-y-0 disabled:hover:shadow-none flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <svg
                    className="animate-spin w-4 h-4"
                    viewBox="0 0 24 24"
                    fill="none"
                  >
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="3"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                    />
                  </svg>
                  Signing in...
                </>
              ) : (
                'Sign In'
              )}
            </button>
          </form>

          {/* Signup link */}
          <p className="mt-6 text-center text-sm text-[#8B97A8]">
            Don&apos;t have an account?{' '}
            <Link
              to="/signup"
              className="text-[#C9A227] hover:text-[#D4AF37] hover:underline transition-colors font-medium"
            >
              Start free trial
            </Link>
          </p>

          {/* Security badge */}
          <div className="mt-8 pt-6 border-t border-white/[0.06] flex items-center justify-center gap-2">
            <Lock className="w-3 h-3 text-[#8B97A8]" />
            <span className="text-[11px] text-[#8B97A8]">
              256-bit TLS encryption · SOC 2 compliant
            </span>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
