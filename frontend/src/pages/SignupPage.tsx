import { useState, useMemo, type FormEvent } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Eye, EyeOff, AlertCircle, Building2 } from 'lucide-react';
import { useAuthStore } from '@/store/auth';
import { getErrorMessage } from '@/lib/errors';
import { Action, Card, Eyebrow, Ground, PageHeader, Rise } from '@/components/design';

/**
 * The first screen anybody who buys this ever fills in.
 *
 * **Restyled onto the design system on 2026-08-23**, alongside the login page
 * it mirrors. The same four things were true of both, and the reasoning for
 * each is written out once, in `LoginPage.tsx`:
 *
 * 1. It was on neither system — not `pages/landing.css`, not the app's
 *    primitives — but carried hand-typed copies of the landing page's values.
 * 2. A drifting particle field and a node-graph SVG animated forever with no
 *    `prefers-reduced-motion` collapse anywhere covering them.
 * 3. framer-motion entrances, a second arrival vocabulary beside `Rise`.
 * 4. The `<h1>` was in the form column here and in the brand panel there, so
 *    the two halves of one flow disagreed about what the page was called.
 *
 * One thing is this page's alone: **the show-password toggle carried
 * `tabIndex={-1}` and no `aria-label`**, so a keyboard user could not reach the
 * only control that reveals what they have typed into a field they cannot see.
 * Both are fixed; the login page already had the label.
 */

/* ── Brand mark — gradient square, Playfair "S" ──
   The artboard's own lockup (`design/Main.dc.html`), value for value. See the
   note in `LoginPage.tsx`: three copies of this want a `BrandMark` primitive. */
const BRAND_MARK_STYLE = {
  background: 'linear-gradient(135deg, #2f75ef 5%, #705ee3 95%)',
  boxShadow: 'inset 0 1px rgba(255,255,255,.4), 0 5px 14px rgba(75,98,221,.28)',
} as const;

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
    /* The submit control is replaced by an announced "Creating your account…"
       for the duration, so it cannot be pressed twice — but a form with a text
       input still submits on Enter, and the `disabled` attribute this replaced
       was what stopped that. Guarded here instead. Not a silent no-op: the
       screen is already saying what is happening. */
    if (loading) return;
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
      // Same 422-array trap as the login page: `detail` is an array of
      // validation objects, and setting it as state renders an object as a
      // React child. `getErrorMessage` flattens both shapes.
      setError(getErrorMessage(err, 'We could not create your account. Please try again.'));
    } finally {
      setLoading(false);
    }
  };

  /* ================================================================ */
  /*  RENDER                                                           */
  /* ================================================================ */

  return (
    /* Canvas rule 1, through the primitive rather than through a copy of its
       numbers. */
    <Ground className="grid grid-cols-1 lg:grid-cols-2 min-h-screen">
      {/* ============================================================ */}
      {/*  LEFT PANEL — Brand. Hidden below lg, which is exactly why    */}
      {/*  the page's heading lives on the right.                       */}
      {/* ============================================================ */}
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
              style={{ letterSpacing: '-0.03em' }}
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
          A room of AI buyers built from your own material reads your pitch —
          before you go live.
        </p>
      </Rise>

      {/* ============================================================ */}
      {/*  RIGHT PANEL — Form                                          */}
      {/* ============================================================ */}
      <div className="flex flex-col items-center justify-center lg:border-l lg:border-saibyl-border px-6 py-12">
        <Rise className="w-full max-w-[440px]" delayMs={70}>
          {/* `stage` — the one panel this screen is about. */}
          <Card carries="stage" className="p-8 sm:p-9">
            {/* Mobile-only logo — where the brand panel is not rendered. */}
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

            <PageHeader
              eyebrow="Start free"
              title="Create your account"
              phrase="Know who buys this before the quarter is gone."
              className="mb-8"
            >
              <p>
                One workspace, five steps. Upload what you have already written
                — a deck, a landing page, a pricing page — and a room of buyers
                reads it back to you.
              </p>
            </PageHeader>

            {/* Error */}
            {error && (
              <div
                role="alert"
                className="mb-6 flex items-start gap-3 px-4 py-3 rounded-xl border border-saibyl-negative/25 bg-saibyl-negative/[0.07] text-saibyl-negative text-sm"
              >
                <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                <span>{error}</span>
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

            {/* Form */}
            <form onSubmit={handleSubmit} className="space-y-5">
              {/* Organization */}
              <div>
                {/* `htmlFor`, which none of these labels carried: an
                    unassociated <label> is announced as loose text and clicking
                    it does not focus the field. */}
                <label
                  htmlFor="signup-org"
                  className="block font-mono text-[11px] font-medium text-saibyl-silver uppercase tracking-wider mb-1.5"
                >
                  Organization
                </label>
                <div className="relative">
                  <Building2 className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-saibyl-muted/60 pointer-events-none" />
                  <input
                    id="signup-org"
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
                  htmlFor="signup-email"
                  className="block font-mono text-[11px] font-medium text-saibyl-silver uppercase tracking-wider mb-1.5"
                >
                  Email
                </label>
                <input
                  id="signup-email"
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
                  htmlFor="signup-password"
                  className="block font-mono text-[11px] font-medium text-saibyl-silver uppercase tracking-wider mb-1.5"
                >
                  Password
                </label>
                <div className="relative">
                  <input
                    id="signup-password"
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
                  {/* Was `tabIndex={-1}` with no label: the only control that
                      reveals a field you cannot read, unreachable by keyboard
                      and unnamed to a screen reader. */}
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-saibyl-muted hover:text-saibyl-ink transition-colors"
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
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
                    <p className="text-[11px] mt-1" style={{ color: pwColor }}>
                      {pwLabel}
                    </p>
                  </div>
                )}
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
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none" aria-hidden="true">
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
                  Creating your account…
                </Action>
              ) : (
                <Action
                  as="button"
                  type="submit"
                  className="w-full justify-center text-sm"
                >
                  Create account
                </Action>
              )}
            </form>

            {/* Sign in link */}
            <p className="mt-6 text-center text-sm text-saibyl-muted">
              Already have an account?{' '}
              <Link
                to="/login"
                className="text-saibyl-blue hover:underline transition-colors font-semibold"
              >
                Sign in
              </Link>
            </p>

            {/* Terms. `Link`, not `<a href>`: both are React Router routes
                (`App.tsx` renders `TermsPage` and `PrivacyPage`), and a bare
                anchor threw away the SPA and reloaded the bundle. The TODO that
                sat here asking for "the actual URL" was stale — the pages have
                existed since the landing rewrite. */}
            <p className="mt-4 text-center text-[11px] text-saibyl-muted leading-relaxed">
              By creating an account, you agree to our{' '}
              <Link to="/terms" className="text-saibyl-blue hover:underline whitespace-nowrap">
                Terms of Service
              </Link>{' '}
              and{' '}
              <Link to="/privacy" className="text-saibyl-blue hover:underline whitespace-nowrap">
                Privacy Policy
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
