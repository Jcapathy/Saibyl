import { useCallback, useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';

import api from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { useAuthStore } from '@/store/auth';
import CreditTopUp from '@/components/billing/CreditTopUp';
import ValueCase from '@/components/billing/ValueCase';
import type { BillingStatus } from '@/types';
import {
  Action,
  Card,
  Chapter,
  Deal,
  Eyebrow,
  Ground,
  Hero,
  Longform,
  Notice,
  Reveal,
} from '@/components/design';

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
 *
 * ---
 *
 * **Restyled onto the design system on 2026-08-23.** It painted
 * `bg-saibyl-void` over the washed ground, headed itself in `saibyl-white`,
 * and marked the selected tab in `bg-saibyl-gold` on `text-saibyl-void` —
 * three legacy dark-theme aliases that still resolve to light values, which is
 * why a page nobody had converted still looked converted.
 *
 * The one thing genuinely missing rather than merely mis-styled: **the credit
 * balance had no meter here.** The rail footer draws it — a violet-to-blue bar
 * over the grant — and Settings, the page a founder opens *because* they are
 * thinking about credits, printed the same number as a bare integer inside the
 * top-up panel. The artboard's own treatment is now on both.
 *
 * ---
 *
 * **And re-framed as a longform page later the same day.** Founder's decision:
 * every page behind the login opens the way the public site opens — a hero,
 * large type, then scroll. `GuidePage` is the approved example; this page copies
 * its shape. The hero renders once, above the tab strip, so the two panels no
 * longer each have to say what the page is. The tab strip is one chapter and
 * the selected panel is the next — and that second chapter's *heading* changes
 * with the tab rather than the chapter itself being swapped for another one,
 * so a tab click re-letters a section that is already on screen instead of
 * fading a whole new one in under the reader.
 *
 * Nothing inside either panel moved. The cards, the meter and the top-up form
 * are the same density they were — the frame grew, the work did not.
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

  TIER_CAPS at time of writing — agents, rounds, platforms, variants (the
  backend's own field order; the last of those renders to a founder as the
  number of message versions a test may carry):
    founder      100,  8,  3, 3
    growth       150, 10,  4, 5
    agency       250, 12,  6, 8
    enterprise 1,000, 20, 12, 8

  Monthly run counts are deliberately NOT advertised: `PLAN_LIMITS` is still
  keyed on the V1 names, so there is no enforced number to print, and printing
  one anyway is how this block went wrong the first time.
*/
const PLAN_PRICE: Record<string, string> = {
  free: 'Free',
  founder: '$99',
  growth: '$299',
  agency: '$999',
  enterprise: 'Custom',
};

const PLAN_AGENT_CAP: Record<string, string> = {
  free: '25',
  founder: '100',
  growth: '150',
  agency: '250',
  enterprise: '1,000',
};

const PLAN_ORDER = ['founder', 'growth', 'agency', 'enterprise'];

/**
 * V1 plan names still in the database, mapped to what they became.
 *
 * `free` and `trial` are **deliberately not here.** They aliased to `founder`,
 * so an account that had paid nothing was shown "Your plan: Founder · $99/mo"
 * — a fabricated billing fact, one panel away from the sidebar rendering the
 * same account's plan as "FREE". Every signup lands on `free`
 * (`DEFAULT_SIGNUP_PLAN`), so this was the default reading of the page that
 * asks for money.
 */
const LEGACY_PLAN_ALIAS: Record<string, string> = {
  starter: 'founder',
  analyst: 'founder',
  pro: 'growth',
  strategist: 'growth',
  war_room: 'agency',
};

/** The free tier is a real state, not a missing paid one. */
const FREE_PLANS = ['free', 'trial'];

function resolvePlan(plan: string | undefined | null): string {
  const key = (plan ?? '').toLowerCase();
  if (PLAN_ORDER.includes(key)) return key;
  if (FREE_PLANS.includes(key)) return 'free';
  return LEGACY_PLAN_ALIAS[key] ?? 'free';
}

function getNextPlan(current: string): string | null {
  const key = resolvePlan(current);
  // A free account's next step is the first paid tier. `free` is not in
  // PLAN_ORDER (it is not a rung on the paid ladder), so without this the
  // upgrade CTA disappeared for exactly the account it is meant for.
  if (key === 'free') return PLAN_ORDER[0];
  const idx = PLAN_ORDER.indexOf(key);
  if (idx === -1 || idx >= PLAN_ORDER.length - 1) return null;
  return PLAN_ORDER[idx + 1];
}

/**
 * What the account has, and what it started with.
 *
 * The grant is read because a bar needs a denominator: "1,317" says nothing
 * about whether that is a lot, and a meter with no scale is decoration. Same
 * request, same endpoint, one more field — the rail footer already reads it.
 */
interface Credits {
  balance: number;
  grant: number;
}

/** Below a quarter of the original grant, the page says so rather than waits. */
const LOW_CREDIT_FRACTION = 0.25;

/* ------------------------------------------------------------------ */
/*  Plan & credits                                                     */
/* ------------------------------------------------------------------ */

function BillingTab() {
  const [billing, setBilling] = useState<BillingStatus | null>(null);
  // The balance the top-up panel adds to. Absent renders as no balance rather
  // than as zero, which would read as "you have none".
  const [credits, setCredits] = useState<Credits | null>(null);
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
      .then((res) =>
        setCredits(
          typeof res.data?.balance === 'number'
            ? { balance: res.data.balance, grant: res.data.grant ?? 0 }
            : null,
        ),
      )
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

  const meterPct =
    credits && credits.grant > 0
      ? Math.min((credits.balance / credits.grant) * 100, 100)
      : null;
  const runningLow =
    credits !== null &&
    credits.grant > 0 &&
    credits.balance / credits.grant < LOW_CREDIT_FRACTION;

  return (
    <div className="space-y-6">
      {/* `stage` — the one panel this screen is about, and the only one on it
          with the deepest shadow. It used to be a blue-tinted rectangle with
          no depth at all; the glass and the shadow are the artboard's own way
          of saying "this is the subject", which frees the blue to mean
          "action" everywhere else on the page. */}
      <Deal index={0}>
        <Card carries="stage" className="p-6">
          <div className="flex items-start justify-between flex-wrap gap-4">
            <div>
              <Eyebrow>Your plan</Eyebrow>
              <h2 className="font-semibold text-[26px] text-saibyl-ink capitalize mt-1">
                {planKey}
              </h2>
              <p className="font-mono tabular-nums text-[15px] text-saibyl-silver mt-1">
                {price}
                {price !== 'Custom' && price !== 'Free' && (
                  <span className="text-[13px]">/mo</span>
                )}
              </p>
              {agentCap && (
                <p className="text-[13px] text-saibyl-muted mt-2">
                  Up to {agentCap} people in the room per run
                </p>
              )}

              {/* The rail footer's meter, on the page a founder opens because
                  they are thinking about credits. Same violet→blue gradient,
                  same 6px bar, same denominator — one treatment, so the number
                  in the sidebar and the number here are visibly the same fact. */}
              {credits && (
                <div className="mt-5 max-w-[15rem]">
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="text-saibyl-muted">Credits left</span>
                    <span className="font-mono tabular-nums text-saibyl-silver">
                      {credits.balance.toLocaleString()}
                    </span>
                  </div>
                  {meterPct !== null && (
                    <div className="h-1.5 mt-1.5 rounded-full bg-[#14294a]/[0.08] overflow-hidden">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-[#8b73ee] to-[#286cf0] transition-all"
                        style={{ width: `${meterPct}%` }}
                      />
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="flex flex-wrap gap-3 items-start">
              {/* No `disabled` while the portal opens — it says what it is
                  doing instead. */}
              <Action kind="quiet" onClick={openPortal}>
                {leaving ? 'Opening…' : 'Manage billing'}
              </Action>
              {nextPlan && (
                /* The one gradient on this screen. There is exactly one thing
                   here the page recommends, and the artboard never draws that
                   as a flat fill. */
                <Action as={Link} to="/#pricing">
                  See the {nextPlan} plan
                </Action>
              )}
            </div>
          </div>
          <p className="text-[11px] text-saibyl-muted mt-4 leading-relaxed">
            Payments, cards, receipts and cancellation are all handled in Stripe.
            We never see your card.
          </p>
        </Card>
      </Deal>

      {/* Amber, not grey. A balance heading toward zero is a state the founder
          has to act on, and the way out is the panel directly below — so the
          notice points at it rather than sending them somewhere else. */}
      {runningLow && (
        <Deal index={1}>
          <Notice
            tone="thin"
            title="Credits are running low"
            action={
              <Action as="a" href="#add-credits" kind="quiet">
                Add more
              </Action>
            }
          >
            Runs are charged against this balance. Top it up whenever you like —
            it is a one-off payment, nothing renews, and the credits do not
            expire.
          </Notice>
        </Deal>
      )}

      {error && <p className="text-[13px] text-saibyl-negative">{error}</p>}

      <div id="add-credits" className="scroll-mt-8">
        <CreditTopUp balance={credits?.balance ?? null} />
      </div>
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
      <Deal index={0}>
        <Card carries="meaning" className="p-6 space-y-4">
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
          <Action
            kind="quiet"
            onClick={logout}
            className="hover:text-saibyl-negative"
          >
            Sign out
          </Action>
        </Card>
      </Deal>

      {/* Said plainly rather than shown as a "coming soon" tab. A founder who
          needs their password changed can do it; a nav item that promises it
          and does nothing is what this replaces. */}
      <Deal index={1}>
        <Card carries="meaning" className="p-6">
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
        </Card>
      </Deal>
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

  /* One chapter, two headings. Computed rather than written as two `<Chapter>`
     elements in a ternary, so switching tabs re-letters the section that is
     already on screen instead of tearing one down and fading another in. */
  const panel =
    tab === 'billing'
      ? {
          kicker: 'Plan and credits',
          title: (
            <>
              What a run is <em>charged against</em>
            </>
          ),
          lead: 'The plan sets how many people can be in a room. The balance is what each run is drawn from, and topping it up is a one-off payment — nothing renews, and the credits do not expire.',
        }
      : {
          kicker: 'Account',
          title: (
            <>
              Who is <em>signed in</em>
            </>
          ),
          lead: 'The email these runs belong to, and the workspace they sit in. A password change or a deletion is handled by email rather than in the app, because neither is a button we would trust ourselves to build once and never look at again.',
        };

  return (
    <Ground className="min-h-full pb-24">
      <Longform>
        {/* Never wrapped in `Reveal`: it is the first screen, and a page whose
            opening fades in looks broken for 700ms. */}
        <Hero
          eyebrow="Your workspace"
          title="What you are on,"
          serif="and what is left."
        >
          <p>
            Two things live here and nothing else does: the plan and the credit
            balance a run is charged against, and the account those runs belong
            to. Everything to do with cards, receipts and cancellation happens in
            Stripe &mdash; we never see a card.{' '}
            <b className="text-saibyl-ink font-semibold">
              What you are paying for, and who is signed in.
            </b>
          </p>
        </Hero>

        {/* ── The tab strip ── */}
        <Chapter
          kicker="What is in here"
          title={
            <>
              Two things, and <em>nothing else</em>
            </>
          }
          lead="There is nothing else on purpose. A tab that promises something and then does nothing is worse than not having the tab, and this page carried five of those."
        >
          <Reveal>
            {/* The selected tab used to be `bg-saibyl-gold` on `text-saibyl-void`
                — a dark-era pairing that resolved to blue-on-paper and therefore
                never looked broken. It is now the artboard's own active-nav
                treatment: a 10% blue wash under ink, so the accent still reads as
                "the thing you pressed" without spending the page's one gradient. */}
            <div className="flex gap-1 p-1 glass rounded-xl w-fit">
              {TABS.map((t) => (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  aria-pressed={tab === t.id}
                  className={`px-5 py-2 rounded-lg text-[13px] font-medium transition-colors ${
                    tab === t.id
                      ? 'bg-saibyl-blue/10 text-saibyl-ink'
                      : 'text-saibyl-muted hover:text-saibyl-ink'
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </Reveal>
        </Chapter>

        {/* ── The selected panel ──
            Not wrapped in `Reveal`. Both panels already carry their own arrival
            with `Deal`, a mount animation that fires when the tab is switched —
            a scroll reveal on top of it would be a second, contradictory
            arrival for the same content. It also keeps `#add-credits` honest:
            an anchor jump has to land on something already painted, and this
            panel is painted the moment it mounts. */}
        <Chapter kicker={panel.kicker} title={panel.title} lead={panel.lead}>
          {tab === 'billing' ? <BillingTab /> : <AccountTab />}
        </Chapter>
      </Longform>
    </Ground>
  );
}
