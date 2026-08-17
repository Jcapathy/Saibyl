import { useState, useMemo, type FormEvent } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Eye, EyeOff, AlertCircle, Building2 } from 'lucide-react';
import { useAuthStore } from '@/store/auth';
import { supabase } from '@/lib/supabase';

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const PARTICLES = [
  { top: '12%', left: '18%', dur: '14s', delay: '0s', color: '#8b73ee' },
  { top: '28%', left: '72%', dur: '18s', delay: '-4s', color: '#286cf0' },
  { top: '55%', left: '25%', dur: '16s', delay: '-8s', color: '#8b73ee' },
  { top: '70%', left: '65%', dur: '20s', delay: '-2s', color: '#286cf0' },
  { top: '85%', left: '40%', dur: '15s', delay: '-6s', color: '#8b73ee' },
  { top: '40%', left: '85%', dur: '17s', delay: '-10s', color: '#286cf0' },
  { top: '18%', left: '50%', dur: '19s', delay: '-3s', color: '#8b73ee' },
  { top: '62%', left: '10%', dur: '13s', delay: '-7s', color: '#286cf0' },
];

const CONNECTION_NODES = [
  [18, 12], [72, 28], [25, 55], [65, 70],
  [40, 85], [85, 40], [50, 18], [10, 62],
] as const;

/* ── Paper ground with the landing page's radial washes ── */
const PAPER_WASH =
  'radial-gradient(circle at 87% 1%, rgba(127,184,255,.19), transparent 22rem), radial-gradient(circle at 2% 26%, rgba(143,119,245,.10), transparent 26rem), #f8fbff';

/* ── Brand mark — gradient square, Playfair "S" ── */
const BRAND_MARK_STYLE = {
  background: 'linear-gradient(135deg, #2f75ef 5%, #705ee3 95%)',
  boxShadow: 'inset 0 1px rgba(255,255,255,.4), 0 5px 14px rgba(75,98,221,.28)',
} as const;

/* The stats bar was four claims and three of them were false.

   "1M Max Agents" against an enforced ceiling of 1,000 - a 1,000x
   overstatement, and the exact claim the landing page was cleaned of in the
   same pass, still live on the page that CTA sends every visitor to. "8
   Platforms" contradicted this file's own hero copy ("across 12 platforms")
   and the 12 shipped adapters. "42 Archetypes" and "<3pp Precision" trace to
   no constant anywhere.

   Removed rather than corrected. A number on a signup page is an advertised
   claim, and the honest set here is empty until someone decides which numbers
   are worth advertising and checks them against `agent_pricing.TIER_CAPS`. */
const STATS: { value: string; label: string }[] = [];

const INPUT_CLASS =
  'w-full px-3.5 py-2.5 rounded-xl border border-saibyl-border-light bg-white text-[14px] text-saibyl-ink placeholder:text-saibyl-muted/70 outline-none transition-all duration-200 focus:outline-none focus:border-saibyl-blue focus:ring-2 focus:ring-saibyl-blue/20';

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

/* Strength colours double as bar fill and label text, so every value here
   must hold ≥4.5:1 on white — status-tier darks, not bright fills. */
function strengthMeta(score: number) {
  if (score <= 1) return { color: '#d92d3c', label: 'Weak' };
  if (score === 2) return { color: '#b45309', label: 'Fair' };
  if (score === 3) return { color: '#a16207', label: 'Good' };
  return { color: '#0e7d55', label: 'Strong' };
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
      /* `/app/home`, not `/app/dashboard`. This one line decided whether the
         staged rail existed for a new founder at all: a cold reader who had
         never seen the product signed up, landed on the superseded dashboard,
         and spent the whole session in the old UI without once reaching the
         five steps. Everything built for them was one unnoticed sidebar link
         away. */
      navigate('/app/home');
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
    <div
      className="grid grid-cols-1 lg:grid-cols-2 min-h-screen bg-saibyl-paper"
      style={{ background: PAPER_WASH }}
    >
      {/* ============================================================ */}
      {/*  LEFT PANEL — Brand                                          */}
      {/* ============================================================ */}
      <div className="hidden lg:flex relative flex-col justify-center items-center overflow-hidden px-12 py-16">
        {/* Radial gradients */}
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute top-[-20%] left-[-10%] w-[70%] h-[70%] rounded-full bg-[radial-gradient(ellipse,rgba(40,108,240,0.07)_0%,transparent_65%)]" />
          <div className="absolute bottom-[-15%] right-[-10%] w-[60%] h-[60%] rounded-full bg-[radial-gradient(ellipse,rgba(139,115,238,0.06)_0%,transparent_65%)]" />
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
                stroke="#8b73ee"
                strokeWidth="0.5"
                opacity="0.07"
              />
            );
          })}
        </svg>

        {/* Content */}
        <div className="relative z-10 max-w-lg space-y-10">
          {/* Logo lockup */}
          <div className="flex items-center gap-3">
            <div
              aria-hidden="true"
              className="w-8 h-8 rounded-[9px] flex items-center justify-center shrink-0"
              style={BRAND_MARK_STYLE}
            >
              <span className="font-serif font-bold text-white text-[19px] leading-none">S</span>
            </div>
            <span
              className="text-saibyl-ink font-extrabold text-[1.75rem]"
              style={{ letterSpacing: '-0.03em' }}
            >
              Saibyl
            </span>
          </div>

          {/* Trust line */}
          <div className="flex items-center gap-2">
            <span className="relative flex h-[6px] w-[6px]">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-saibyl-green opacity-75" />
              <span className="relative inline-flex rounded-full h-[6px] w-[6px] bg-saibyl-green" />
            </span>
            <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-saibyl-muted">
              Buyer intelligence for founders
            </span>
          </div>

          {/* Tagline */}
          <h2 className="text-[2.75rem] font-extrabold leading-[1.1] tracking-tight text-saibyl-ink">
            Test your startup on a{' '}
            <em className="font-serif italic text-saibyl-violet">synthetic market.</em>
          </h2>

          {/* Subtitle */}
          <p className="text-saibyl-silver text-base leading-relaxed">
            A room of AI buyers built from your own material reads your pitch —
            before you go live.
          </p>

          {/* Stats row */}
          <div className="grid grid-cols-4 gap-4 pt-4">
            {STATS.map((s) => (
              <div key={s.label} className="glass rounded-xl px-3 py-3 text-center">
                <p
                  className="text-saibyl-blue font-mono text-lg font-bold"
                  style={{ fontFamily: "'DM Mono', monospace" }}
                >
                  {s.value}
                </p>
                <p
                  className="text-saibyl-muted text-[10px] uppercase tracking-wider mt-1"
                  style={{ fontFamily: "'DM Mono', monospace" }}
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
      <div className="flex flex-col items-center justify-center lg:border-l lg:border-saibyl-border px-6 py-12">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="w-full max-w-[440px] glass rounded-2xl p-8 sm:p-9 shadow-[0_18px_40px_rgba(52,96,164,0.08)]"
        >
          {/* Mobile-only logo */}
          <div className="flex lg:hidden items-center justify-center gap-2 mb-8">
            <div
              aria-hidden="true"
              className="w-8 h-8 rounded-[9px] flex items-center justify-center shrink-0"
              style={BRAND_MARK_STYLE}
            >
              <span className="font-serif font-bold text-white text-[19px] leading-none">S</span>
            </div>
            <span
              className="text-saibyl-ink font-extrabold text-xl"
              style={{ letterSpacing: '-0.03em' }}
            >
              Saibyl
            </span>
          </div>

          {/* Header */}
          <h1 className="text-2xl font-extrabold tracking-tight text-saibyl-ink mb-1">
            Create your account
          </h1>
          <p className="text-sm text-saibyl-muted mb-8">
            Start simulating in minutes
          </p>

          {/* Error */}
          {error && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              className="mb-6 flex items-start gap-3 px-4 py-3 rounded-xl bg-saibyl-rose/10 border border-saibyl-negative/25 text-saibyl-negative text-sm"
            >
              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
              <span>{error}</span>
            </motion.div>
          )}

          {/* Google SSO */}
          <button
            type="button"
            onClick={handleGoogleSSO}
            className="w-full flex items-center justify-center gap-3 px-4 py-2.5 rounded-xl border border-saibyl-border-light bg-white text-saibyl-ink text-sm font-semibold transition-all duration-200 hover:border-saibyl-blue/40 hover:bg-saibyl-paper"
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
            <div className="flex-1 h-px bg-saibyl-border" />
            <span
              className="text-[11px] text-saibyl-silver uppercase tracking-[0.18em]"
              style={{ fontFamily: "'DM Mono', monospace" }}
            >
              or
            </span>
            <div className="flex-1 h-px bg-saibyl-border" />
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Organization */}
            <div>
              <label
                className="block text-[11px] font-medium text-saibyl-silver uppercase tracking-wider mb-1.5"
                style={{ fontFamily: "'DM Mono', monospace" }}
              >
                Organization
              </label>
              <div className="relative">
                <Building2 className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-saibyl-muted/60 pointer-events-none" />
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
                className="block text-[11px] font-medium text-saibyl-silver uppercase tracking-wider mb-1.5"
                style={{ fontFamily: "'DM Mono', monospace" }}
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
                className="block text-[11px] font-medium text-saibyl-silver uppercase tracking-wider mb-1.5"
                style={{ fontFamily: "'DM Mono', monospace" }}
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
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-saibyl-muted hover:text-saibyl-ink transition-colors"
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
                            i < pwStrength ? pwColor : 'rgba(20,41,74,0.10)',
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
              className="w-full py-2.5 rounded-xl bg-saibyl-blue text-white text-sm font-extrabold transition-all duration-200 hover:bg-saibyl-gold-hover hover:shadow-[0_6px_18px_rgba(40,108,240,0.30)] hover:-translate-y-[1px] disabled:opacity-60 disabled:hover:translate-y-0 disabled:hover:shadow-none flex items-center justify-center gap-2"
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
          <p className="mt-6 text-center text-sm text-saibyl-muted">
            Already have an account?{' '}
            <Link
              to="/login"
              className="text-saibyl-blue hover:text-saibyl-gold-hover transition-colors font-semibold"
            >
              Sign in
            </Link>
          </p>

          {/* Terms */}
          <p className="mt-4 text-center text-[11px] text-saibyl-muted leading-relaxed">
            By creating an account, you agree to our{' '}
            {/* TODO: Replace with actual Terms of Service URL */}
            <a href="/terms" className="text-saibyl-blue hover:text-saibyl-gold-hover transition-colors whitespace-nowrap">
              Terms of Service
            </a>{' '}
            and{' '}
            <a href="/privacy" className="text-saibyl-blue hover:text-saibyl-gold-hover transition-colors whitespace-nowrap">
              Privacy Policy
            </a>
          </p>

          {/* Was "256-bit TLS encryption · SOC 2 compliant". The TLS half is
              true and unremarkable; the SOC 2 half was an unearned compliance
              claim — there is no audit, no report and no auditor, and the only
              "SOC 2" anywhere in this codebase is a simulated enterprise buyer
              asking whether we have one. It was removed from the landing page in
              the same pass and survived here, which is the duplicated-claim
              pattern that kept "1M agents" alive for months. Nothing replaces it:
              a security badge that says nothing is better than one that is not
              true, and the right time to put it back is when there is a report to
              link to. */}
        </motion.div>
      </div>
    </div>
  );
}
