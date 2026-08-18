import { useState, type FormEvent } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Eye, EyeOff, AlertCircle } from 'lucide-react';
import { useAuthStore } from '@/store/auth';
import { getErrorMessage } from '@/lib/errors';
import { supabase } from '@/lib/supabase';

/* ── Particle data for the brand panel ── */
const PARTICLES: { x: string; y: string; color: string; duration: string; delay: string }[] = [
  { x: '12%', y: '18%', color: '#8b73ee', duration: '14s', delay: '0s' },
  { x: '78%', y: '24%', color: '#286cf0', duration: '18s', delay: '-3s' },
  { x: '34%', y: '65%', color: '#8b73ee', duration: '16s', delay: '-7s' },
  { x: '88%', y: '72%', color: '#286cf0', duration: '20s', delay: '-2s' },
  { x: '22%', y: '85%', color: '#8b73ee', duration: '15s', delay: '-5s' },
  { x: '62%', y: '42%', color: '#286cf0', duration: '17s', delay: '-9s' },
  { x: '48%', y: '12%', color: '#8b73ee', duration: '19s', delay: '-4s' },
  { x: '92%', y: '52%', color: '#286cf0', duration: '13s', delay: '-6s' },
];

const NODE_POSITIONS = [
  [12, 18], [78, 24], [34, 65], [88, 72],
  [22, 85], [62, 42], [48, 12], [92, 52],
] as const;

/* ── Paper ground with the landing page's radial washes ── */
const PAPER_WASH =
  'radial-gradient(circle at 87% 1%, rgba(127,184,255,.19), transparent 22rem), radial-gradient(circle at 2% 26%, rgba(143,119,245,.10), transparent 26rem), #f8fbff';

/* ── Brand mark — gradient square, Playfair "S" ── */
const BRAND_MARK_STYLE = {
  background: 'linear-gradient(135deg, #2f75ef 5%, #705ee3 95%)',
  boxShadow: 'inset 0 1px rgba(255,255,255,.4), 0 5px 14px rgba(75,98,221,.28)',
} as const;

/* ── Shared input class ── */
const INPUT_CLASS =
  'w-full px-3.5 py-2.5 rounded-xl border border-saibyl-border-light bg-white text-[14px] text-saibyl-ink placeholder:text-saibyl-muted/70 outline-none transition-all duration-200 focus:outline-none focus:border-saibyl-blue focus:ring-2 focus:ring-saibyl-blue/20';

/* ── Stats data ── */
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
      /* `/app/home`, not `/app/dashboard`. This one line decided whether the
         staged rail existed for a new founder at all: a cold reader who had
         never seen the product signed up, landed on the superseded dashboard,
         and spent the whole session in the old UI without once reaching the
         five steps. Everything built for them was one unnoticed sidebar link
         away. */
      navigate('/app/home');
    } catch (err: unknown) {
      /*
        Through `getErrorMessage`, not a hand-rolled cast. The cast asserted
        `detail` was a string; FastAPI returns an **array** of validation
        objects on a 422, so `setError(array)` reached the JSX and threw
        "Objects are not valid as a React child" — blanking the login page,
        the one screen with no navigation to escape from.
      */
      setError(getErrorMessage(err, 'We could not sign you in. Please try again.'));
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleSSO = async () => {
    // TODO: After Supabase OAuth callback, exchange session for app JWT tokens via backend endpoint
    await supabase.auth.signInWithOAuth({ provider: 'google' });
  };

  return (
    <div
      className="grid grid-cols-1 lg:grid-cols-2 min-h-screen bg-saibyl-paper"
      style={{ background: PAPER_WASH }}
    >
      {/* ═══════════════════════════════════════════════════
          LEFT PANEL — Brand
         ═══════════════════════════════════════════════════ */}
      <div className="hidden lg:flex relative flex-col justify-center px-16 xl:px-20 overflow-hidden">
        {/* Radial gradient accents */}
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute top-[20%] left-[10%] w-[60%] h-[60%] rounded-full bg-[radial-gradient(ellipse,rgba(40,108,240,0.07)_0%,transparent_70%)]" />
          <div className="absolute bottom-[10%] right-[5%] w-[50%] h-[50%] rounded-full bg-[radial-gradient(ellipse,rgba(139,115,238,0.06)_0%,transparent_70%)]" />
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
              opacity: 0.5,
            }}
          />
        ))}

        {/* Connection lines SVG */}
        <svg className="absolute inset-0 w-full h-full pointer-events-none" style={{ opacity: 0.07 }}>
          {NODE_POSITIONS.map(([x1, y1], i) =>
            NODE_POSITIONS.slice(i + 1).map(([x2, y2], j) => (
              <line
                key={`${i}-${j}`}
                x1={`${x1}%`}
                y1={`${y1}%`}
                x2={`${x2}%`}
                y2={`${y2}%`}
                stroke="#8b73ee"
                strokeWidth="1"
              />
            )),
          )}
        </svg>

        {/* Content */}
        <div className="relative z-10">
          {/* Logo lockup */}
          <div className="flex items-center gap-3 mb-10">
            <div
              aria-hidden="true"
              className="w-8 h-8 rounded-[9px] flex items-center justify-center shrink-0"
              style={BRAND_MARK_STYLE}
            >
              <span className="font-serif font-bold text-white text-[19px] leading-none">S</span>
            </div>
            <span
              className="text-saibyl-ink font-extrabold text-[1.75rem]"
              style={{ letterSpacing: '-0.04em' }}
            >
              Saibyl
            </span>
          </div>

          {/* Trust line */}
          <div className="flex items-center gap-2 mb-6">
            <span className="block w-[6px] h-[6px] rounded-full bg-saibyl-green animate-pulse-dot" />
            <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-saibyl-muted">
              Buyer intelligence for founders
            </span>
          </div>

          {/* Tagline */}
          <h1 className="text-[2.75rem] font-extrabold tracking-tight leading-[1.1] text-saibyl-ink mb-5">
            Test your startup on a{' '}
            <em className="font-serif italic text-saibyl-violet">synthetic market.</em>
          </h1>

          {/* Subtitle */}
          <p className="text-saibyl-silver text-base leading-relaxed max-w-md mb-12">
            A room of AI buyers built from your own material reads your pitch.
            Every number traces to what a buyer said.
          </p>

          {/* Stats row */}
          <div className="grid grid-cols-4 gap-6">
            {STATS.map((s) => (
              <div key={s.label} className="glass rounded-xl px-4 py-3">
                <div
                  className="text-saibyl-blue text-2xl font-bold"
                  style={{ fontFamily: "'DM Mono', monospace" }}
                >
                  {s.value}
                </div>
                <div
                  className="text-saibyl-muted text-[10px] uppercase tracking-widest mt-1"
                  style={{ fontFamily: "'DM Mono', monospace" }}
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
      <div className="flex items-center justify-center lg:border-l lg:border-saibyl-border px-6 py-12">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: [0.25, 0.46, 0.45, 0.94] }}
          className="w-full max-w-[440px] glass rounded-2xl p-8 sm:p-9 shadow-[0_18px_40px_rgba(52,96,164,0.08)]"
        >
          {/* Mobile logo — only on small screens */}
          <div className="flex lg:hidden items-center justify-center gap-2.5 mb-10">
            <div
              aria-hidden="true"
              className="w-8 h-8 rounded-[9px] flex items-center justify-center shrink-0"
              style={BRAND_MARK_STYLE}
            >
              <span className="font-serif font-bold text-white text-[19px] leading-none">S</span>
            </div>
            <span
              className="text-saibyl-ink font-extrabold text-xl"
              style={{ letterSpacing: '-0.04em' }}
            >
              Saibyl
            </span>
          </div>

          {/* Header */}
          <h2 className="text-2xl font-extrabold tracking-tight text-saibyl-ink mb-1">Welcome back</h2>
          <p className="text-sm text-saibyl-muted mb-8">
            Sign in to access your intelligence dashboard
          </p>

          {/* Error display */}
          {error && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              className="mb-6 flex items-start gap-3 px-4 py-3 rounded-xl bg-saibyl-rose/10 border border-saibyl-negative/25"
            >
              <AlertCircle className="w-4 h-4 text-saibyl-negative mt-0.5 shrink-0" />
              <span className="text-sm text-saibyl-negative">{error}</span>
            </motion.div>
          )}

          {/* Google SSO */}
          <button
            type="button"
            onClick={handleGoogleSSO}
            className="w-full flex items-center justify-center gap-3 px-4 py-2.5 rounded-xl border border-saibyl-border-light bg-white text-sm font-semibold text-saibyl-ink transition-all duration-200 hover:border-saibyl-blue/40 hover:bg-saibyl-paper"
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
            <div className="flex-1 h-px bg-saibyl-border" />
            <span
              className="text-[11px] text-saibyl-silver uppercase tracking-[0.18em]"
              style={{ fontFamily: "'DM Mono', monospace" }}
            >
              or
            </span>
            <div className="flex-1 h-px bg-saibyl-border" />
          </div>

          {/* Login form */}
          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Email */}
            <div>
              <label
                className="block text-[11px] font-medium text-saibyl-silver uppercase tracking-wider mb-2"
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
              <div className="flex items-center justify-between mb-2">
                <label
                  className="block text-[11px] font-medium text-saibyl-silver uppercase tracking-wider"
                  style={{ fontFamily: "'DM Mono', monospace" }}
                >
                  Password
                </label>
                {/* TODO: Wire to password reset flow */}
                <button
                  type="button"
                  className="text-[11px] font-semibold text-saibyl-blue hover:text-saibyl-gold-hover transition-colors"
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
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-saibyl-muted hover:text-saibyl-ink transition-colors"
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
              className="w-full py-2.5 rounded-xl bg-saibyl-blue text-white text-sm font-extrabold transition-all duration-200 hover:bg-saibyl-gold-hover hover:shadow-[0_6px_18px_rgba(40,108,240,0.30)] hover:-translate-y-[1px] disabled:opacity-60 disabled:hover:translate-y-0 disabled:hover:shadow-none flex items-center justify-center gap-2"
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
          <p className="mt-6 text-center text-sm text-saibyl-muted">
            Don&apos;t have an account?{' '}
            <Link
              to="/signup"
              className="text-saibyl-blue hover:text-saibyl-gold-hover hover:underline transition-colors font-semibold"
            >
              Start free
            </Link>
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
