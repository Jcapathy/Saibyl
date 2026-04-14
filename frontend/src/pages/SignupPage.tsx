import { useState, useMemo, type FormEvent } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Eye, EyeOff, Lock, AlertCircle, Building2 } from 'lucide-react';
import { useAuthStore } from '@/store/auth';
import { supabase } from '@/lib/supabase';

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const PARTICLES = [
  { top: '12%', left: '18%', dur: '14s', delay: '0s', color: '#5B5FEE' },
  { top: '28%', left: '72%', dur: '18s', delay: '-4s', color: '#00D4FF' },
  { top: '55%', left: '25%', dur: '16s', delay: '-8s', color: '#5B5FEE' },
  { top: '70%', left: '65%', dur: '20s', delay: '-2s', color: '#00D4FF' },
  { top: '85%', left: '40%', dur: '15s', delay: '-6s', color: '#5B5FEE' },
  { top: '40%', left: '85%', dur: '17s', delay: '-10s', color: '#00D4FF' },
  { top: '18%', left: '50%', dur: '19s', delay: '-3s', color: '#5B5FEE' },
  { top: '62%', left: '10%', dur: '13s', delay: '-7s', color: '#00D4FF' },
];

const CONNECTION_NODES = [
  [18, 12], [72, 28], [25, 55], [65, 70],
  [40, 85], [85, 40], [50, 18], [10, 62],
] as const;

const STATS = [
  { value: '1M', label: 'Max Agents' },
  { value: '8', label: 'Platforms' },
  { value: '42', label: 'Archetypes' },
  { value: '<3pp', label: 'Precision' },
];

const INPUT_CLASS =
  'w-full px-4 py-[0.6875rem] rounded-[10px] border border-white/[0.06] bg-white/[0.025] text-[#E8ECF2] text-sm placeholder:text-[#94A3B8]/40 outline-none transition-all duration-200 focus:border-[rgba(91,95,238,0.5)] focus:shadow-[0_0_0_3px_rgba(91,95,238,0.1),0_0_20px_rgba(91,95,238,0.05)] focus:bg-white/[0.04]';

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function calcStrength(pw: string): number {
  let s = 0;
  if (pw.length >= 8) s++;
  if (/[A-Z]/.test(pw)) s++;
  if (/\d/.test(pw)) s++;
  if (/[^A-Za-z0-9]/.test(pw)) s++;
  return s;
}

function strengthMeta(score: number) {
  if (score <= 1) return { color: '#EF4444', label: 'Weak' };
  if (score === 2) return { color: '#F59E0B', label: 'Fair' };
  if (score === 3) return { color: '#EAB308', label: 'Good' };
  return { color: '#22C55E', label: 'Strong' };
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function SignupPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [orgName, setOrgName] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const signup = useAuthStore((s) => s.signup);
  const navigate = useNavigate();

  const pwStrength = useMemo(() => calcStrength(password), [password]);
  const { color: pwColor, label: pwLabel } = strengthMeta(pwStrength);

  /* ---- handlers -------------------------------------------------- */

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await signup(email, password, orgName);
      navigate('/app/dashboard');
    } catch (err: unknown) {
      const axiosDetail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;
      const msg = axiosDetail || (err instanceof Error ? err.message : 'Signup failed');
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleSSO = async () => {
    // TODO: After Supabase OAuth callback, exchange session for app JWT tokens via backend endpoint
    await supabase.auth.signInWithOAuth({ provider: 'google' });
  };

  /* ================================================================ */
  /*  RENDER                                                           */
  /* ================================================================ */

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 min-h-screen">
      {/* ============================================================ */}
      {/*  LEFT PANEL — Brand                                          */}
      {/* ============================================================ */}
      <div className="hidden lg:flex relative flex-col justify-center items-center bg-[#070B14] overflow-hidden px-12 py-16">
        {/* Radial gradients */}
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute top-[-20%] left-[-10%] w-[70%] h-[70%] rounded-full bg-[radial-gradient(ellipse,rgba(91,95,238,0.08)_0%,transparent_65%)]" />
          <div className="absolute bottom-[-15%] right-[-10%] w-[60%] h-[60%] rounded-full bg-[radial-gradient(ellipse,rgba(0,212,255,0.06)_0%,transparent_65%)]" />
        </div>

        {/* Particles */}
        {PARTICLES.map((p, i) => (
          <span
            key={i}
            className="absolute w-[4px] h-[4px] rounded-full animate-drift"
            style={{
              top: p.top,
              left: p.left,
              background: p.color,
              animationDuration: p.dur,
              animationDelay: p.delay,
            }}
          />
        ))}

        {/* Connection lines */}
        <svg
          className="absolute inset-0 w-full h-full pointer-events-none"
          preserveAspectRatio="none"
        >
          {CONNECTION_NODES.map(([x1, y1], i) => {
            const next = CONNECTION_NODES[(i + 1) % CONNECTION_NODES.length];
            return (
              <line
                key={i}
                x1={`${x1}%`}
                y1={`${y1}%`}
                x2={`${next[0]}%`}
                y2={`${next[1]}%`}
                stroke="#5B5FEE"
                strokeWidth="0.5"
                opacity="0.06"
              />
            );
          })}
        </svg>

        {/* Content */}
        <div className="relative z-10 max-w-lg space-y-10">
          {/* Logo lockup */}
          <div className="flex items-center gap-3">
            <img src="/logo-mark.svg" alt="" className="w-12 h-12" />
            <span
              className="text-gradient-brand font-extrabold text-[1.75rem]"
              style={{ letterSpacing: '-0.03em' }}
            >
              SAIBYL
            </span>
          </div>

          {/* Trust line */}
          <div className="flex items-center gap-2">
            <span className="relative flex h-[6px] w-[6px]">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-[6px] w-[6px] bg-green-500" />
            </span>
            <span className="text-sm text-[#8B97A8]">
              Predictive intelligence for decision-makers
            </span>
          </div>

          {/* Tagline */}
          <h2 className="text-[2.75rem] font-bold leading-[1.1] tracking-tight text-white">
            Know the conversation{' '}
            <span className="text-gradient-brand">before it happens.</span>
          </h2>

          {/* Subtitle */}
          <p className="text-[#8B97A8] text-base leading-relaxed">
            Simulate public reactions across 8 platforms with up to 1,000,000
            synthetic agents, all before you go live.
          </p>

          {/* Stats row */}
          <div className="grid grid-cols-4 gap-4 pt-4">
            {STATS.map((s) => (
              <div key={s.label} className="text-center">
                <p
                  className="text-gradient-brand font-mono text-lg font-bold"
                  style={{ fontFamily: "'JetBrains Mono', monospace" }}
                >
                  {s.value}
                </p>
                <p
                  className="text-[#8B97A8] text-[10px] uppercase tracking-wider mt-1"
                  style={{ fontFamily: "'JetBrains Mono', monospace" }}
                >
                  {s.label}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ============================================================ */}
      {/*  RIGHT PANEL — Form                                          */}
      {/* ============================================================ */}
      <div className="flex flex-col items-center justify-center bg-[#0D1117] lg:border-l lg:border-[#1B2433] px-6 py-12">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="w-full max-w-[400px]"
        >
          {/* Mobile-only logo */}
          <div className="flex lg:hidden items-center justify-center gap-2 mb-8">
            <img src="/logo-mark.svg" alt="" className="w-9 h-9" />
            <span
              className="text-gradient-brand font-extrabold text-xl"
              style={{ letterSpacing: '-0.03em' }}
            >
              SAIBYL
            </span>
          </div>

          {/* Header */}
          <h1 className="text-2xl font-bold text-white mb-1">
            Create your account
          </h1>
          <p className="text-sm text-[#8B97A8] mb-8">
            Start simulating in minutes
          </p>

          {/* Error */}
          {error && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              className="mb-6 flex items-start gap-3 px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm"
            >
              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
              <span>{error}</span>
            </motion.div>
          )}

          {/* Google SSO */}
          <button
            type="button"
            onClick={handleGoogleSSO}
            className="w-full flex items-center justify-center gap-3 px-4 py-[0.6875rem] rounded-[10px] border border-white/[0.12] bg-transparent text-[#E8ECF2] text-sm font-medium transition-all duration-200 hover:bg-white/[0.04] hover:border-white/[0.2]"
          >
            {/* Google "G" icon */}
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
              <path
                d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844a4.14 4.14 0 01-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z"
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

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Organization */}
            <div>
              <label
                className="block text-[11px] font-medium text-[#8B97A8] uppercase tracking-wider mb-1.5"
                style={{ fontFamily: "'JetBrains Mono', monospace" }}
              >
                Organization
              </label>
              <div className="relative">
                <Building2 className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-[#94A3B8]/50 pointer-events-none" />
                <input
                  type="text"
                  name="org_name"
                  autoComplete="organization"
                  required
                  value={orgName}
                  onChange={(e) => setOrgName(e.target.value)}
                  placeholder="Acme Corp"
                  className={`${INPUT_CLASS} pl-10`}
                />
              </div>
            </div>

            {/* Email */}
            <div>
              <label
                className="block text-[11px] font-medium text-[#8B97A8] uppercase tracking-wider mb-1.5"
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
              <label
                className="block text-[11px] font-medium text-[#8B97A8] uppercase tracking-wider mb-1.5"
                style={{ fontFamily: "'JetBrains Mono', monospace" }}
              >
                Password
              </label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  name="password"
                  autoComplete="new-password"
                  required
                  minLength={8}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Min. 8 characters"
                  className={`${INPUT_CLASS} pr-10`}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-[#94A3B8]/50 hover:text-[#94A3B8] transition-colors"
                  tabIndex={-1}
                >
                  {showPassword ? (
                    <EyeOff className="w-4 h-4" />
                  ) : (
                    <Eye className="w-4 h-4" />
                  )}
                </button>
              </div>

              {/* Password strength indicator */}
              {password.length > 0 && (
                <div className="mt-2">
                  <div className="flex gap-1">
                    {[0, 1, 2, 3].map((i) => (
                      <div
                        key={i}
                        className="h-1 flex-1 rounded-full transition-colors duration-200"
                        style={{
                          backgroundColor:
                            i < pwStrength ? pwColor : 'rgba(255,255,255,0.06)',
                        }}
                      />
                    ))}
                  </div>
                  <p
                    className="text-[11px] mt-1"
                    style={{ color: pwColor }}
                  >
                    {pwLabel}
                  </p>
                </div>
              )}
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="w-full py-[0.6875rem] rounded-[10px] bg-[#C9A227] text-[#070B14] text-sm font-semibold transition-all duration-200 hover:bg-[#D4AF37] hover:shadow-[0_4px_20px_rgba(201,162,39,0.3)] hover:-translate-y-[1px] disabled:opacity-60 disabled:hover:translate-y-0 disabled:hover:shadow-none flex items-center justify-center gap-2"
            >
              {loading && (
                <svg
                  className="animate-spin h-4 w-4"
                  viewBox="0 0 24 24"
                  fill="none"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                  />
                </svg>
              )}
              {loading ? 'Creating account...' : 'Create Account'}
            </button>
          </form>

          {/* Sign in link */}
          <p className="mt-6 text-center text-sm text-[#8B97A8]">
            Already have an account?{' '}
            <Link
              to="/login"
              className="text-[#C9A227] hover:text-[#D4AF37] transition-colors font-medium"
            >
              Sign in
            </Link>
          </p>

          {/* Terms */}
          <p className="mt-4 text-center text-[11px] text-[#8B97A8]/60 leading-relaxed">
            By creating an account, you agree to our{' '}
            {/* TODO: Replace with actual Terms of Service URL */}
            <a href="#" className="text-[#C9A227]/80 hover:text-[#C9A227] transition-colors">
              Terms of Service
            </a>{' '}
            and{' '}
            {/* TODO: Replace with actual Privacy Policy URL */}
            <a href="#" className="text-[#C9A227]/80 hover:text-[#C9A227] transition-colors">
              Privacy Policy
            </a>
          </p>

          {/* Security badge */}
          <div className="mt-6 flex items-center justify-center gap-2 text-[11px] text-[#8B97A8]/40">
            <Lock className="w-3 h-3" />
            <span>256-bit TLS encryption &middot; SOC 2 compliant</span>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
