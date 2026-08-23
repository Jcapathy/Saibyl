import { useState, type FormEvent } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Eye, EyeOff, AlertCircle } from 'lucide-react';
import { useAuthStore } from '@/store/auth';
import { getErrorMessage } from '@/lib/errors';
import { Action, Card, Eyebrow, Ground, PageHeader, Rise } from '@/components/design';

/**
 * The way in — and the handover from the public page to the app.
 *
 * **Restyled onto the design system on 2026-08-23.** It was on neither system:
 * it never imported `pages/landing.css`, and it never imported the app's
 * primitives. What it had instead were hand-rolled *copies* of the landing
 * page's values — a `PAPER_WASH` constant retyping the two radial gradients, a
 * serif-italic `<em>` retyping the accent, a flat `bg-saibyl-blue` submit — and
 * copies are how one system becomes two dialects of itself.
 *
 * Four things went with the restyle, and each is worth naming:
 *
 * 1. **The particle field and the node-graph SVG.** Eight drifting dots and
 *    twenty-eight connecting lines, animating forever. They are a dark-era
 *    "AI network" motif: the landing page has no such thing, no artboard has
 *    one, and — the part that actually mattered — `animate-drift` is not
 *    covered by any `prefers-reduced-motion` block, so a reader with
 *    vestibular sensitivity got permanent motion on the one screen with no
 *    navigation to leave by.
 * 2. **The framer-motion entrances**, replaced by `Rise`. One arrival
 *    vocabulary per product; `design.css` collapses this one under a
 *    reduced-motion preference and framer-motion's `initial/animate` did not.
 * 3. **The `<h1>` moved into the form column.** It used to live in the brand
 *    panel, which is `hidden lg:flex` — so below 1024px this page had no
 *    heading at all. The form renders at every width, so the heading now does.
 * 4. **"Forgot password?" was a button with a TODO and no handler.** A control
 *    that does nothing is worse than the grey button the founder's rule bans,
 *    because it looks like it worked. Settings already states that password
 *    changes are handled by email, so this now does the thing that surface
 *    promises rather than pretending to a flow that does not exist.
 */

/* ── Brand mark — gradient square, Playfair "S" ──
   The artboard's own lockup (`design/Main.dc.html`, the rail header), value
   for value. It is duplicated on the signup page and in `AppLayout`; three
   copies of one mark wants a `BrandMark` primitive in `components/design/`,
   which is a separate change to a shared file. */
const BRAND_MARK_STYLE = {
  background: 'linear-gradient(135deg, #2f75ef 5%, #705ee3 95%)',
  boxShadow: 'inset 0 1px rgba(255,255,255,.4), 0 5px 14px rgba(75,98,221,.28)',
} as const;

/* ── Shared input class ── */
const INPUT_CLASS =
  'w-full px-3.5 py-2.5 rounded-xl border border-saibyl-border-light bg-white text-[14px] text-saibyl-ink placeholder:text-saibyl-muted/70 outline-none transition-all duration-200 focus:outline-none focus:border-saibyl-blue focus:ring-2 focus:ring-saibyl-blue/20';

/* A stats bar of four claims used to sit under the tagline, and three of them
   were false: "1M Max Agents" against an enforced ceiling of 1,000, "8
   Platforms" against this file's own copy and the 12 shipped adapters, and two
   figures that traced to no constant anywhere. It was deleted rather than
   corrected, and nothing replaces it. A number on the way-in page is an
   advertised claim; the honest set is empty until somebody decides which
   numbers are worth advertising and checks them against
   `agent_pricing.TIER_CAPS`. */

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
    /* The submit control is replaced by an announced "Signing you in…" for the
       duration, so it cannot be pressed twice — but a form with a text input
       still submits on Enter, and the `disabled` attribute this replaced was
       what stopped that. Guarded here instead. Not a silent no-op: the screen
       is already saying what is happening. */
    if (loading) return;
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

  return (
    /* Canvas rule 1, through the primitive rather than through a copy of its
       numbers. `<body>` already carries this wash; the page paints its own so
       the grid is opaque over it at every breakpoint. */
    <Ground className="grid grid-cols-1 lg:grid-cols-2 min-h-screen">
      {/* ═══════════════════════════════════════════════════
          LEFT PANEL — Brand. Hidden below lg, which is exactly why the page's
          heading lives on the right.
         ═══════════════════════════════════════════════════ */}
      <Rise className="hidden lg:flex flex-col justify-center px-16 xl:px-20">
        {/* Logo lockup — the rail's, including the line that says whose
            product this is. */}
        <div className="flex items-center gap-3 mb-10">
          <div
            aria-hidden="true"
            className="w-8 h-8 rounded-[9px] flex items-center justify-center shrink-0"
            style={BRAND_MARK_STYLE}
          >
            <span className="font-serif font-bold text-white text-[19px] leading-none">S</span>
          </div>
          <span className="flex flex-col">
            <span
              className="text-saibyl-ink font-extrabold text-[1.75rem] leading-none"
              style={{ letterSpacing: '-0.04em' }}
            >
              Saibyl
            </span>
            <span className="font-mono text-[9px] uppercase tracking-[0.14em] text-saibyl-muted mt-1">
              By Saido Labs
            </span>
          </span>
        </div>

        <Eyebrow>Buyer intelligence for founders</Eyebrow>

        {/* The tagline the landing page hands over, in Manrope. The page's one
            Playfair line is spent in the header on the right — rule 4 is one
            accent phrase per heading, and this panel is not a heading. */}
        <p className="mt-5 text-[2.5rem] font-extrabold tracking-[-0.04em] leading-[1.1] text-saibyl-ink">
          Test your startup on a synthetic market.
        </p>

        <p className="mt-5 max-w-md text-[15px] leading-relaxed text-saibyl-silver">
          A room of AI buyers built from your own material reads your pitch.
          Every number traces back to something a buyer said.
        </p>
      </Rise>

      {/* ═══════════════════════════════════════════════════
          RIGHT PANEL — Form
         ═══════════════════════════════════════════════════ */}
      <div className="flex items-center justify-center lg:border-l lg:border-saibyl-border px-6 py-12">
        <Rise className="w-full max-w-[440px]" delayMs={70}>
          {/* `stage` — the one panel this screen is about. The glass, the
              hairline and the deep shadow are the artboard's, rather than a
              `.glass` div wearing a hand-typed box-shadow. */}
          <Card carries="stage" className="p-8 sm:p-9">
            {/* Mobile logo — only where the brand panel is not rendered. */}
            <div className="flex lg:hidden items-center justify-center gap-2.5 mb-8">
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

            <PageHeader
              eyebrow="Sign in"
              title="Welcome back"
              phrase="The room is exactly where you left it."
              className="mb-8"
            />

            {/* Error display */}
            {error && (
              <div
                role="alert"
                className="mb-6 flex items-start gap-3 px-4 py-3 rounded-xl border border-saibyl-negative/25 bg-saibyl-negative/[0.07]"
              >
                <AlertCircle className="w-4 h-4 text-saibyl-negative mt-0.5 shrink-0" />
                <span className="text-sm text-saibyl-negative">{error}</span>
              </div>
            )}

            {/* "Continue with Google" stood here, on both way-in pages.

                **It could not sign anybody in, and it was worse than a button
                that does nothing.** `handleGoogleSSO` called
                `supabase.auth.signInWithOAuth`, which really does redirect to
                Google — and there is no callback route in `App.tsx` to exchange
                the returned Supabase session for this app's JWTs. The TODO
                above the call said so. A founder who pressed it left Saibyl,
                authenticated with Google, came back to the `*` catch-all and
                landed on the marketing page, signed out, with no explanation.

                Removed rather than disabled: there is no capability to lose.
                When the callback exists this comes back with it. */}

            {/* Divider */}
            <div className="flex items-center gap-4 my-6">
              <div className="flex-1 h-px bg-saibyl-border" />
              <span className="font-mono text-[11px] text-saibyl-silver uppercase tracking-[0.18em]">
                or
              </span>
              <div className="flex-1 h-px bg-saibyl-border" />
            </div>

            {/* Login form */}
            <form onSubmit={handleSubmit} className="space-y-5">
              {/* Email */}
              <div>
                {/* `htmlFor`, which none of these labels carried: an unassociated
                    <label> is announced as loose text and clicking it does not
                    focus the field. */}
                <label
                  htmlFor="login-email"
                  className="block font-mono text-[11px] font-medium text-saibyl-silver uppercase tracking-wider mb-2"
                >
                  Email
                </label>
                <input
                  id="login-email"
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
                    htmlFor="login-password"
                    className="block font-mono text-[11px] font-medium text-saibyl-silver uppercase tracking-wider"
                  >
                    Password
                  </label>
                  {/* Was a `<button type="button">` with a TODO and no handler
                      — a control that silently did nothing. Password changes
                      really are handled by email today (Settings → Account says
                      so), so this says the same thing and works. */}
                  <a
                    href="mailto:info@saidolabs.com?subject=Password%20reset"
                    className="text-[11px] font-semibold text-saibyl-blue hover:underline transition-colors"
                  >
                    Forgot password?
                  </a>
                </div>
                <div className="relative">
                  <input
                    id="login-password"
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

              {/* The one gradient on this screen, and no `disabled` on it.
                  While the request is in flight the control is replaced by an
                  announced span carrying the same shape — the app's `Guarded`
                  pattern — rather than by a greyed-out rectangle that says
                  nothing about why it stopped working. */}
              {loading ? (
                <Action
                  as="span"
                  aria-live="polite"
                  className="w-full justify-center text-sm opacity-80 pointer-events-none"
                >
                  <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none" aria-hidden="true">
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
                  Signing you in…
                </Action>
              ) : (
                <Action
                  as="button"
                  type="submit"
                  className="w-full justify-center text-sm"
                >
                  Sign in
                </Action>
              )}
            </form>

            {/* Signup link */}
            <p className="mt-6 text-center text-sm text-saibyl-muted">
              Don&apos;t have an account?{' '}
              <Link
                to="/signup"
                className="text-saibyl-blue hover:underline transition-colors font-semibold"
              >
                Start free
              </Link>
            </p>

            {/* Was "256-bit TLS encryption · SOC 2 compliant". The TLS half is
                true and unremarkable; the SOC 2 half was an unearned compliance
                claim — there is no audit, no report and no auditor, and the only
                "SOC 2" anywhere in this codebase is an enterprise buyer in a run
                asking whether we have one. It was removed from the landing page in
                the same pass and survived here, which is the duplicated-claim
                pattern that kept "1M agents" alive for months. Nothing replaces it:
                a security badge that says nothing is better than one that is not
                true, and the right time to put it back is when there is a report to
                link to. */}
          </Card>
        </Rise>
      </div>
    </Ground>
  );
}
