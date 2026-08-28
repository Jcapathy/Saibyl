import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Eye, EyeOff, AlertCircle } from 'lucide-react';
import api from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { Action, Card, Ground, Notice, PageHeader, Rise } from '@/components/design';

/**
 * Step two: set the new password, using the token from the emailed link.
 *
 * **The token arrives in the URL fragment, and is taken out of the URL
 * immediately.** GoTrue redirects here as
 * `…/reset-password#access_token=…&type=recovery`, and a fragment is not sent
 * to any server — but it is written into browser history, it rides along on
 * anything the reader copies out of the address bar, and it is a live
 * credential for this account until it is spent. `history.replaceState` on
 * mount is what keeps a shoulder-read of the address bar from being a
 * password reset. The token lives in component state from then on.
 *
 * The same redirect carries failures — `#error=…&error_description=…` for a
 * link that expired before it was opened — so this page has three renderings
 * and not two: a working form, a dead link with the way to get a fresh one,
 * and the confirmation.
 */

/* ── Brand mark — gradient square, Playfair "S" ──
   Fifth copy; see the note in `LoginPage.tsx`. */
const BRAND_MARK_STYLE = {
  background: 'linear-gradient(135deg, #2f75ef 5%, #705ee3 95%)',
  boxShadow: 'inset 0 1px rgba(255,255,255,.4), 0 5px 14px rgba(75,98,221,.28)',
} as const;

const INPUT_CLASS =
  'w-full px-3.5 py-2.5 rounded-xl border border-saibyl-border-light bg-white text-[14px] text-saibyl-ink placeholder:text-saibyl-muted/70 outline-none transition-all duration-200 focus:outline-none focus:border-saibyl-blue focus:ring-2 focus:ring-saibyl-blue/20';

/** Kept in step with `MIN_PASSWORD_LENGTH` in `backend/app/api/auth.py`.
 *  Checked in both places on purpose: here so the reader is told before a round
 *  trip, there because a client-side check is not a rule. */
const MIN_PASSWORD_LENGTH = 8;

/**
 * Read the recovery token out of the fragment, then scrub the fragment.
 *
 * Returns the token, or the reason there isn't one. Runs once, on mount —
 * after `replaceState` the hash is gone, so a second read would find nothing
 * and report a valid link as broken.
 */
function takeRecoveryToken(): { token: string; error: string } {
  const hash = window.location.hash.startsWith('#') ? window.location.hash.slice(1) : '';
  const params = new URLSearchParams(hash);

  if (window.location.hash) {
    window.history.replaceState(
      null,
      '',
      window.location.pathname + window.location.search,
    );
  }

  const described = params.get('error_description');
  if (described) return { token: '', error: described.replace(/\+/g, ' ') };
  if (params.get('error')) {
    return {
      token: '',
      error: 'This reset link has expired or has already been used.',
    };
  }

  const token = params.get('access_token');
  if (!token) {
    return {
      token: '',
      error:
        'This page needs the link from your reset email. Open that link, and it will bring you back here ready to go.',
    };
  }
  return { token, error: '' };
}

export default function ResetPasswordPage() {
  const [token, setToken] = useState('');
  const [linkError, setLinkError] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const { token: found, error: why } = takeRecoveryToken();
    setToken(found);
    setLinkError(why);
  }, []);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (loading) return;
    setError('');

    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Choose a password of at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }
    if (password !== confirm) {
      setError('Those two passwords are not the same.');
      return;
    }

    setLoading(true);
    try {
      await api.post('/auth/reset-password', { access_token: token, password });
      setDone(true);
    } catch (err: unknown) {
      setError(
        getErrorMessage(err, 'We could not set that password. Please try again.'),
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

          {done ? (
            <>
              <PageHeader
                eyebrow="Account recovery"
                title="That's done"
                phrase="Back where you left off."
                className="mb-8"
              >
                Your password is set, and every other session on this account has
                been signed out. Sign in with the new one.
              </PageHeader>
              <Action
                as="button"
                type="button"
                onClick={() => navigate('/login')}
                className="w-full justify-center text-sm"
              >
                Sign in
              </Action>
            </>
          ) : linkError ? (
            <>
              <PageHeader
                eyebrow="Account recovery"
                title="This link won't work"
                phrase="One more try, and you're in."
                className="mb-8"
              />
              {/* A dead end is a defect: the reason comes with the control that
                  resolves it, never on its own. */}
              <Notice
                tone="blocked"
                title="The link has expired or was already used"
                action={
                  <Action as={Link} to="/forgot-password" className="text-[12px]">
                    Send a new link
                  </Action>
                }
              >
                {linkError} Reset links are good for one hour and work once.
              </Notice>
            </>
          ) : (
            <>
              <PageHeader
                eyebrow="Account recovery"
                title="Set a new password"
                phrase="Choose it once, and you're back."
                className="mb-8"
              >
                At least {MIN_PASSWORD_LENGTH} characters. Setting it signs out
                every other session on the account, so anyone else holding the old
                password is out.
              </PageHeader>

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
                    htmlFor="reset-password"
                    className="block font-mono text-[11px] font-medium text-saibyl-silver uppercase tracking-wider mb-2"
                  >
                    New password
                  </label>
                  <div className="relative">
                    <input
                      id="reset-password"
                      type={showPassword ? 'text' : 'password'}
                      name="new-password"
                      autoComplete="new-password"
                      required
                      minLength={MIN_PASSWORD_LENGTH}
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

                <div>
                  <label
                    htmlFor="reset-confirm"
                    className="block font-mono text-[11px] font-medium text-saibyl-silver uppercase tracking-wider mb-2"
                  >
                    Type it again
                  </label>
                  <input
                    id="reset-confirm"
                    type={showPassword ? 'text' : 'password'}
                    name="confirm-password"
                    autoComplete="new-password"
                    required
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    placeholder="••••••••"
                    className={INPUT_CLASS}
                  />
                </div>

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
                    Setting your password…
                  </Action>
                ) : (
                  <Action as="button" type="submit" className="w-full justify-center text-sm">
                    Set password
                  </Action>
                )}
              </form>
            </>
          )}
        </Card>
      </Rise>
    </Ground>
  );
}
