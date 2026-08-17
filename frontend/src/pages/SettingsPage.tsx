import { useCallback, useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';

import api from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { useAuthStore } from '@/store/auth';
import CreditTopUp from '@/components/billing/CreditTopUp';
import ValueCase from '@/components/billing/ValueCase';
import type { BillingStatus } from '@/types';

/**
 * Two tabs. It had seven.
 *
 * The five that went were General ("coming soon"), Team, API keys, Webhooks,
 * Notifications ("coming soon") and Security ("coming soon"), plus the payment
 * method card and the invoice history inside Billing.
 *
 * They were not removed to tidy up. Each was **actively misleading**:
 *
 * - *Invite team member* wrote a row and sent no email. Nobody was ever
 *   invited, and the screen said it had worked.
 * - *Invoice history* called `GET /billing/invoices`, an endpoint that does not
 *   exist. The list could only ever be empty.
 * - *Payment method* offered to store a card. Stripe Checkout holds the card;
 *   this product never sees one, so the form could not have worked.
 * - *API keys* was real, and `verify_api_key` had **zero callers** — a key
 *   issued from it authenticated nothing.
 * - *Notifications* and *Security* had no backend at all.
 *
 * The reader this product is for has never asked for an API key or a webhook.
 * Showing them seven tabs where four say "coming soon" tells them the product
 * is half-built, and in those four cases they were right.
 *
 * The rule for adding a tab back: it does something today, for the founder this
 * product is written for. "Coming soon" is not a feature, it is an apology
 * taking up a nav slot.
 */

type SettingsTab = 'billing' | 'account';

const TABS: { id: SettingsTab; label: string }[] = [
  { id: 'billing', label: 'Plan & credits' },
  { id: 'account', label: 'Account' },
];

/* ------------------------------------------------------------------ */
/*  Plan reference                                                     */
/* ------------------------------------------------------------------ */

/*
  ⚠ EVERY NUMBER HERE IS AN ADVERTISED CAP AND MUST MATCH `agent_pricing.TIER_CAPS`.

  This block once advertised 5,000–500,000 agents against enforced caps of
  100–1,000. Transcribed rather than imported because it renders before any run
  is priced, which makes it a second source of truth — written down as one,
  knowingly, rather than pretended away.

  TIER_CAPS at time of writing — agents, rounds, platforms, variants:
    founder      100,  8,  3, 3
    growth       150, 10,  4, 5
    agency       250, 12,  6, 8
    enterprise 1,000, 20, 12, 8

  Monthly run counts are deliberately NOT advertised: `PLAN_LIMITS` is still
  keyed on the V1 names, so there is no enforced number to print, and printing
  one anyway is how this block went wrong the first time.
*/
const PLAN_PRICE: Record<string, string> = {
  founder: '$99',
  growth: '$299',
  agency: '$999',
  enterprise: 'Custom',
};

const PLAN_AGENT_CAP: Record<string, string> = {
  founder: '100',
  growth: '150',
  agency: '250',
  enterprise: '1,000',
};

const PLAN_ORDER = ['founder', 'growth', 'agency', 'enterprise'];

/** V1 plan names still in the database, mapped to what they became. */
const LEGACY_PLAN_ALIAS: Record<string, string> = {
  starter: 'founder',
  analyst: 'founder',
  pro: 'growth',
  strategist: 'growth',
  war_room: 'agency',
  free: 'founder',
  trial: 'founder',
};

function resolvePlan(plan: string | undefined | null): string {
  const key = (plan ?? '').toLowerCase();
  if (PLAN_ORDER.includes(key)) return key;
  return LEGACY_PLAN_ALIAS[key] ?? 'founder';
}

function getNextPlan(current: string): string | null {
  const idx = PLAN_ORDER.indexOf(resolvePlan(current));
  if (idx === -1 || idx >= PLAN_ORDER.length - 1) return null;
  return PLAN_ORDER[idx + 1];
}

const cardClass = 'bg-white border border-saibyl-border rounded-2xl';
const goldBtnClass =
  'bg-saibyl-blue text-white px-5 py-2.5 rounded-xl font-semibold text-[13px] hover:bg-[#1e5ad9] transition-colors';

/* ------------------------------------------------------------------ */
/*  Plan & credits                                                     */
/* ------------------------------------------------------------------ */

function BillingTab() {
  const [billing, setBilling] = useState<BillingStatus | null>(null);
  // The balance the top-up panel adds to. Absent renders as no balance rather
  // than as zero, which would read as "you have none".
  const [credits, setCredits] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [leaving, setLeaving] = useState(false);

  const load = useCallback(() => {
    api
      .get<BillingStatus>('/billing/status')
      .then((res) => {
        setBilling(res.data);
        setError('');
      })
      .catch((err) => setError(getErrorMessage(err, 'Could not load your plan.')))
      .finally(() => setLoading(false));
    api
      .get('/billing/credits')
      .then((res) => setCredits(res.data?.balance ?? null))
      .catch(() => setCredits(null));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  /**
   * Everything about a subscription — upgrading, changing card, cancelling —
   * happens in Stripe's own portal.
   *
   * One button rather than five screens we would have to build, keep correct,
   * and keep in step with what Stripe already believes. The cancel button this
   * replaces called nothing at all: it opened a `window.confirm` and then ran a
   * TODO comment, so a founder could confirm a cancellation that never happened.
   */
  const openPortal = async () => {
    setLeaving(true);
    setError('');
    try {
      const { data } = await api.post<{ portal_url: string }>('/billing/portal');
      window.location.href = data.portal_url;
    } catch (err) {
      setError(
        getErrorMessage(
          err,
          'We could not open the billing portal. If you have never paid, there is nothing there yet.',
        ),
      );
      setLeaving(false);
    }
  };

  if (loading) return <p className="text-saibyl-muted py-8">Loading…</p>;

  const planKey = resolvePlan(billing?.plan);
  const price = PLAN_PRICE[planKey] ?? 'Custom';
  const agentCap = PLAN_AGENT_CAP[planKey];
  const nextPlan = getNextPlan(planKey);

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-saibyl-blue/45 bg-saibyl-blue/[0.05] p-6">
        <div className="flex items-start justify-between flex-wrap gap-4">
          <div>
            <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-saibyl-blue">
              Your plan
            </span>
            <h2 className="font-semibold text-[26px] text-saibyl-ink capitalize mt-1">
              {planKey}
            </h2>
            <p className="font-mono tabular-nums text-[15px] text-saibyl-silver mt-1">
              {price}
              {price !== 'Custom' && <span className="text-[13px]">/mo</span>}
            </p>
            {agentCap && (
              <p className="text-[13px] text-saibyl-muted mt-2">
                Up to {agentCap} people in the room per run
              </p>
            )}
          </div>

          <div className="flex flex-wrap gap-3 items-start">
            <button
              onClick={openPortal}
              className="border border-saibyl-border-light text-saibyl-silver px-4 py-2.5 rounded-xl text-[13px] hover:text-saibyl-ink hover:border-saibyl-blue/40 transition"
            >
              {leaving ? 'Opening…' : 'Manage billing'}
            </button>
            {nextPlan && (
              <Link to="/#pricing" className={goldBtnClass}>
                See the {nextPlan} plan
              </Link>
            )}
          </div>
        </div>
        <p className="text-[11px] text-saibyl-muted mt-4 leading-relaxed">
          Payments, cards, receipts and cancellation are all handled in Stripe.
          We never see your card.
        </p>
      </div>

      {error && <p className="text-[13px] text-saibyl-negative">{error}</p>}

      <CreditTopUp balance={credits} />
      <ValueCase />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Account                                                            */
/* ------------------------------------------------------------------ */

function AccountTab() {
  const { user, org, logout } = useAuthStore();

  return (
    <div className="space-y-6">
      <div className={`${cardClass} p-6 space-y-4`}>
        <div>
          <p className="text-[12px] text-saibyl-muted">Signed in as</p>
          <p className="text-[15px] text-saibyl-ink mt-0.5">{user?.email ?? '—'}</p>
        </div>
        {org?.name && (
          <div>
            <p className="text-[12px] text-saibyl-muted">Workspace</p>
            <p className="text-[15px] text-saibyl-ink mt-0.5">{org.name}</p>
          </div>
        )}
        <button
          onClick={logout}
          className="border border-saibyl-border-light text-saibyl-silver px-4 py-2.5 rounded-xl text-[13px] hover:text-saibyl-negative hover:border-saibyl-negative/30 transition"
        >
          Sign out
        </button>
      </div>

      {/* Said plainly rather than shown as a "coming soon" tab. A founder who
          needs their password changed can do it; a nav item that promises it
          and does nothing is what this replaces. */}
      <div className={`${cardClass} p-6`}>
        <h3 className="text-[15px] font-medium text-saibyl-ink">
          Password and account deletion
        </h3>
        <p className="text-[13px] text-saibyl-silver mt-1.5 leading-relaxed max-w-xl">
          Both are handled by email rather than in the app. Write to{' '}
          <a
            href="mailto:info@saidolabs.com"
            className="text-saibyl-blue hover:underline"
          >
            info@saidolabs.com
          </a>{' '}
          and we will action it. If your account is deleted, your uploads, runs
          and reports go with it.
        </p>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Shell                                                              */
/* ------------------------------------------------------------------ */

export default function SettingsPage() {
  const location = useLocation();
  // `/app/settings/billing` and `/app/settings` both land on billing. The route
  // is a splat, so the segment is read here rather than routed separately.
  const segment = location.pathname.split('/').filter(Boolean).pop();
  const initial: SettingsTab = segment === 'account' ? 'account' : 'billing';
  const [tab, setTab] = useState<SettingsTab>(initial);

  return (
    <div className="p-6 lg:p-8 bg-saibyl-void min-h-full">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-h1 text-saibyl-white">Settings</h1>

        <div className="flex gap-1 p-1 glass rounded-xl w-fit my-6">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              aria-pressed={tab === t.id}
              className={`px-5 py-2 rounded-lg text-[13px] font-medium transition-all ${
                tab === t.id
                  ? 'bg-saibyl-gold text-saibyl-void'
                  : 'text-saibyl-muted hover:text-saibyl-platinum'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {tab === 'billing' ? <BillingTab /> : <AccountTab />}
      </div>
    </div>
  );
}
