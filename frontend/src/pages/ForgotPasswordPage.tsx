import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { AlertCircle } from 'lucide-react';
import api from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { Action, Card, Ground, Notice, PageHeader, Rise } from '@/components/design';

/**
 * Step one of the only way back into a locked account.
 *
 * **Until this page existed there was no way back at all.** Not a broken flow —
 * none. `LoginPage` offered "Forgot password?" as a `mailto:`, and Settings →
 * Account said password changes were handled by email, so a founder locked out
 * of Saibyl waited on somebody reading a mailbox. `POST /auth/forgot-password`
 * and `POST /auth/reset-password` were added with these two pages.
 *
 * The confirmation replaces the form rather than sitting under it, because the
 * next action is not on this screen — it is in the reader's mail. Leaving a
 * live "Send reset link" button under a "check your mail" message invites a
 * second press, a second mail, and a first link that is now dead.
 *
 * The confirmation is the same whether or not the address has an account (the
 * server decides that; see `RESET_SENT_MESSAGE` in `api/auth.py`), so it echoes
 * the address back — a founder who mistyped their own can read it and see so.
 */

/* ── Brand mark — gradient square, Playfair "S" ──
   The artboard's lockup, value for value. This is the fourth copy; the note in
   `LoginPage.tsx` about wanting a `BrandMark` primitive in `components/design/`
   stands, and is a change to shared files rather than part of this one. */
const BRAND_MARK_STYLE = {
  background: 'linear-gradient(135deg, #2f75ef 5%, #705ee3 95%)',
  boxShadow: 'inset 0 1px rgba(255,255,255,.4), 0 5px 14px rgba(75,98,221,.28)',
} as const;

const INPUT_CLASS =
  'w-full px-3.5 py-2.5 rounded-xl border border-saibyl-border-light bg-white text-[14px] text-saibyl-ink placeholder:text-saibyl-muted/70 outline-none transition-all duration-200 focus:outline-none focus:border-saibyl-blue focus:ring-2 focus:ring-saibyl-blue/20';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [sentTo, setSentTo] = useState('');
  /* The server's own sentence, not a copy of it kept in sync by hand. The
     neutral "if an account exists…" wording is a security property decided in
     `api/auth.py`; restating it here would be a second place to change it. */
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    /* A form with a text input still submits on Enter, and there is no
       `disabled` on the rail to stop it — guarded here, the way LoginPage
       guards its own submit. */
    if (loading) return;
    setError('');
    setLoading(true);
    try {
      const { data } = await api.post('/auth/forgot-password', { email });
      setSentTo(email);
      if (typeof data?.message === 'string') setMessage(data.message);
    } catch (err: unknown) {
      setError(
        getErrorMessage(err, 'We could not send the reset link. Please try again.'),
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <Ground className="flex items-center justify-center min-h-screen px-6 py-12">
      <Rise className="w-full max-w-[440px]">
        <Card carries="stage" className="p-8 sm:p-9">
          <div className="flex items-center justify-center gap-2.5 mb-8">
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
            eyebrow="Account recovery"
            title="Forgot your password?"
            phrase="One link, and the room is yours again."
            className="mb-8"
          >
            Type the address you signed up with. We will send a link that lets you
            set a new password. It works once, and it stops working after an hour.
          </PageHeader>

          {sentTo ? (
            <>
              <Notice tone="live" title="Check your mail">
                {message || 'If an account exists for that address, a reset link is on its way.'}
                {' '}We sent it to <strong>{sentTo}</strong>. If that is not your
                address, go back and try the right one.
              </Notice>
              <Action as={Link} to="/login" className="w-full justify-center text-sm mt-6">
                Back to sign in
              </Action>
            </>
          ) : (
            <>
              {error && (
                <div
                  role="alert"
                  className="mb-6 flex items-start gap-3 px-4 py-3 rounded-xl border border-saibyl-negative/25 bg-saibyl-negative/[0.07]"
                >
                  <AlertCircle className="w-4 h-4 text-saibyl-negative mt-0.5 shrink-0" />
                  <span className="text-sm text-saibyl-negative">{error}</span>
                </div>
              )}

              <form onSubmit={handleSubmit} className="space-y-5">
                <div>
                  <label
                    htmlFor="forgot-email"
                    className="block font-mono text-[11px] font-medium text-saibyl-silver uppercase tracking-wider mb-2"
                  >
                    Email
                  </label>
                  <input
                    id="forgot-email"
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

                {/* The one gradient on this screen, and no `disabled` on it —
                    in flight the control is replaced by an announced span of
                    the same shape, the app's `Guarded` pattern. */}
                {loading ? (
                  <Action
                    as="span"
                    aria-live="polite"
                    className="w-full justify-center text-sm opacity-80 pointer-events-none"
                  >
                    <svg
                      className="animate-spin w-4 h-4"
                      viewBox="0 0 24 24"
                      fill="none"
                      aria-hidden="true"
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
                    Sending the link…
                  </Action>
                ) : (
                  <Action as="button" type="submit" className="w-full justify-center text-sm">
                    Send reset link
                  </Action>
                )}
              </form>

              <p className="mt-6 text-center text-sm text-saibyl-muted">
                Remembered it?{' '}
                <Link
                  to="/login"
                  className="text-saibyl-blue hover:underline transition-colors font-semibold"
                >
                  Sign in
                </Link>
              </p>
            </>
          )}
        </Card>
      </Rise>
    </Ground>
  );
}
