import { useCallback, useEffect, useState } from 'react';

import api from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';

/**
 * Put $10 on, without committing to $99 a month.
 *
 * This is a standalone purchase, not a plan. A founder deciding whether the
 * product is worth a subscription should be able to spend a little and find
 * out — asking for the monthly commitment is asking for the big decision at
 * the exact moment they have the least evidence.
 *
 * **Every number here comes from the server.** The amounts, the credits, the
 * runs, and the fact that subscribing is better value are all priced by
 * `services/billing/topups.py`, by the same function that prices the real
 * checkout. A client that did its own arithmetic would be a second rate table,
 * and the symptom of that is a founder quoted one number and charged another.
 *
 * The comparison against subscribing is shown rather than hidden. A founder
 * who works out for themselves that they are paying a premium and were not
 * told trusts nothing else on the page.
 */

interface TopupQuote {
  amount_cents: number;
  amount_usd: number;
  credits: number;
  subscription_is_cheaper_by_pct: number;
}

interface TopupOptions {
  min_cents: number;
  max_cents: number;
  suggested: TopupQuote[];
}

export default function CreditTopUp({
  balance,
  onPurchased,
}: {
  /** Current credit balance, so the founder sees what they are adding to. */
  balance: number | null;
  onPurchased?: () => void;
}) {
  const [options, setOptions] = useState<TopupOptions | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [custom, setCustom] = useState('');
  const [customQuote, setCustomQuote] = useState<TopupQuote | null>(null);
  const [error, setError] = useState('');
  const [sending, setSending] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .get<TopupOptions>('/billing/topup/options')
      .then(({ data }) => {
        if (cancelled) return;
        setOptions(data);
        if (data.suggested.length > 1) setSelected(data.suggested[1].amount_cents);
      })
      .catch(() => {
        // Surfaced, not swallowed. A top-up panel that renders empty looks
        // identical to one the founder has already used.
        if (!cancelled) setError('We could not load the top-up amounts.');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Price whatever they typed, server-side. Debounced because it is a keystroke
  // handler hitting an endpoint, not because the endpoint is slow.
  useEffect(() => {
    const cents = Math.round(parseFloat(custom) * 100);
    /* Cleared inside the timer rather than synchronously, so this effect never
       sets state on the render that scheduled it. Same reason as the stage
       pages: a synchronous setState in an effect body is a cascading render. */
    const timer = setTimeout(() => {
      if (!custom || !Number.isFinite(cents)) {
        setCustomQuote(null);
        return;
      }
      api
        .post<TopupQuote>('/billing/topup/quote', { amount_cents: cents })
        .then(({ data }) => {
          setCustomQuote(data);
          setError('');
        })
        .catch((err) => {
          setCustomQuote(null);
          // The server writes this sentence — it is the one that explains the
          // floor and the ceiling in words rather than as a validation code.
          setError(getErrorMessage(err, 'That amount cannot be charged.'));
        });
    }, 350);
    return () => clearTimeout(timer);
  }, [custom]);

  const active: TopupQuote | null =
    customQuote ??
    options?.suggested.find((q) => q.amount_cents === selected) ??
    null;

  const buy = useCallback(async () => {
    if (!active) return;
    setSending(true);
    setError('');
    try {
      const { data } = await api.post<{ checkout_url: string }>('/billing/topup', {
        amount_cents: active.amount_cents,
      });
      onPurchased?.();
      window.location.href = data.checkout_url;
    } catch (err) {
      setError(getErrorMessage(err, 'We could not open the payment page.'));
      setSending(false);
    }
  }, [active, onPurchased]);

  return (
    <div className="rounded-2xl border border-saibyl-border bg-white p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-[17px] font-semibold text-saibyl-ink">Add credits</h3>
        {balance !== null && (
          <span className="text-[12px] text-saibyl-silver tabular-nums">
            You have {balance.toLocaleString()} now
          </span>
        )}
      </div>
      <p className="text-[13px] text-saibyl-silver mt-1.5 leading-relaxed max-w-xl">
        A one-off payment, not a plan. Nothing renews, nothing is cancelled
        later, and the credits do not expire. Use this to try the product before
        deciding whether a monthly plan is worth it.
      </p>

      {options && (
        <>
          <div className="flex flex-wrap gap-2 mt-5">
            {options.suggested.map((q) => {
              const isActive = !customQuote && selected === q.amount_cents;
              return (
                <button
                  key={q.amount_cents}
                  type="button"
                  aria-pressed={isActive}
                  onClick={() => {
                    setSelected(q.amount_cents);
                    setCustom('');
                    setCustomQuote(null);
                    setError('');
                  }}
                  className={`px-4 py-2.5 rounded-xl border text-left transition-colors ${
                    isActive
                      ? 'border-saibyl-blue/50 bg-saibyl-blue/10'
                      : 'border-saibyl-border bg-white hover:border-saibyl-border-light'
                  }`}
                >
                  <span
                    className={`block text-[15px] font-semibold tabular-nums ${
                      isActive ? 'text-saibyl-ink' : 'text-saibyl-silver'
                    }`}
                  >
                    ${q.amount_usd.toFixed(0)}
                  </span>
                  <span className="block text-[11px] text-saibyl-muted mt-0.5 tabular-nums">
                    {q.credits.toLocaleString()} credits
                  </span>
                </button>
              );
            })}

            <label className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-saibyl-border-light bg-white focus-within:border-saibyl-blue focus-within:ring-2 focus-within:ring-saibyl-blue/20">
              <span className="text-[15px] text-saibyl-silver">$</span>
              <input
                inputMode="decimal"
                value={custom}
                onChange={(e) => setCustom(e.target.value)}
                placeholder="Other"
                aria-label="A different amount, in dollars"
                className="w-20 bg-transparent text-[15px] text-saibyl-ink placeholder:text-saibyl-muted/70 focus:outline-none tabular-nums"
              />
            </label>
          </div>

          {/* The runs comparison that sat here is gone by request. It told a
              founder "$20 buys about 0.9 of a full-size run", which is
              arithmetically true and reads as a warning on the button they are
              being asked to press. The credit count is on every amount above;
              what a run costs is on the plan page. */}
        </>
      )}

      {error && (
        <p className="mt-4 text-[12.5px] text-saibyl-negative leading-relaxed">{error}</p>
      )}

      <div className="mt-5">
        {sending ? (
          <span
            aria-live="polite"
            className="inline-block px-5 py-2.5 rounded-xl bg-saibyl-blue/70 text-white font-semibold text-[13px]"
          >
            Opening payment&hellip;
          </span>
        ) : active ? (
          <button
            type="button"
            onClick={buy}
            className="px-5 py-2.5 rounded-xl bg-saibyl-blue text-white font-semibold text-[13px] tabular-nums hover:bg-[#1e5ad9] transition-colors"
          >
            Add ${active.amount_usd.toFixed(2)} of credits
          </button>
        ) : (
          /* Never a grey button: no amount is chosen, so the screen says that
             rather than presenting a control that does nothing. */
          <p className="text-[12.5px] text-saibyl-silver">
            Pick an amount above, or type your own.
          </p>
        )}
      </div>

      <p className="text-[11px] text-saibyl-muted mt-3 leading-relaxed">
        Card payment handled by Stripe. We never see your card details.
      </p>
    </div>
  );
}
