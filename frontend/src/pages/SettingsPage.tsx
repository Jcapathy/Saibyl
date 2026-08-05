import { useEffect, useState, type FormEvent } from 'react';
import {
  Check,
  CreditCard,
  Download,
  Users,
  Key,
  Bell,
  Shield,
  Settings as SettingsIcon,
  Webhook,
} from 'lucide-react';
import api from '@/lib/api';
import { useAuthStore } from '@/store/auth';
import type { ApiKey, BillingStatus, CreatedApiKey } from '@/types';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type SettingsTab =
  | 'general'
  | 'team'
  | 'billing'
  | 'api-keys'
  | 'webhooks'
  | 'notifications'
  | 'security';

interface PaymentMethod {
  brand: string;
  last4: string;
  exp_month: number;
  exp_year: number;
}

interface Invoice {
  id: string;
  date: string;
  description: string;
  amount: string;
  status: string;
  pdf_url?: string;
}

interface Member {
  id: string;
  email: string;
  role: string;
}

interface WebhookItem {
  id: string;
  url: string;
  events: string[];
  active: boolean;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatCount(n: number | undefined | null): string {
  if (n == null) return '—';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n % 1_000_000 === 0 ? 0 : 1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(n % 1_000 === 0 ? 0 : 1)}K`;
  return n.toString();
}

// ⚠ EVERY NUMBER HERE IS AN ADVERTISED CAP AND MUST MATCH `agent_pricing.TIER_CAPS`.
//
// This block advertised 5,000 / 25,000 / 100,000 / 500,000+ agents per
// simulation against enforced caps of 100 / 150 / 250 / 1,000 — a 50-500x
// overstatement, on tier names (analyst / strategist / war_room) the product
// does not use. `PLAN_PRICES[org.plan]` was therefore undefined for every real
// org, which is why the Upgrade button never drew.
//
// TIER_CAPS at time of writing — agents, rounds, platforms, variants:
//   founder      100,  8,  3, 3
//   growth       150, 10,  4, 5
//   agency       250, 12,  6, 8
//   enterprise 1,000, 20, 12, 8
//
// Transcribed rather than imported because this renders before any run is
// priced. That makes it a second source of truth, so it is written down as one
// — §2a's "two sources of truth for one value", accepted knowingly.
//
// Monthly simulation counts are NOT advertised: `PLAN_LIMITS` is still keyed on
// the V1 names, so a founder/growth/agency org falls through to the starter
// limit. There is no enforced number to print, and printing one anyway is how
// this block went wrong the first time.
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

/** V1 plan names still present in the database, mapped to what they became. */
const LEGACY_PLAN_ALIAS: Record<string, string> = {
  starter: 'founder',
  analyst: 'founder',
  pro: 'growth',
  strategist: 'growth',
  war_room: 'agency',
  free: 'founder',
  trial: 'founder',
};

/** The tier a plan string resolves to, tolerating the V1 vocabulary.
 *
 * Not exported: this file exports a component, and a second export breaks
 * fast refresh. If another surface needs this, it belongs in `lib/`, not
 * re-declared — the duplicated tier table on the landing page is what this
 * whole block exists to stop repeating.
 */
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

const PLAN_FEATURES: Record<string, string[]> = {
  founder: [
    'Up to 100 agents per simulation',
    'Up to 8 rounds',
    '3 platforms',
    '3 message variants per test',
    'Audience derived from your own material',
    'Full measured reports',
    'Email support',
  ],
  growth: [
    'Up to 150 agents per simulation',
    'Up to 10 rounds',
    '4 platforms',
    '5 message variants per test',
    'All 16 persona packs',
    'PDF/CSV export',
    'API access',
    'Priority support',
  ],
  agency: [
    'Up to 250 agents per simulation',
    'Up to 12 rounds',
    '6 platforms',
    '8 message variants per test',
    'All 16 persona packs',
    'Custom report templates',
    'Webhook integrations',
    'Dedicated account manager',
  ],
  enterprise: [
    'Up to 1,000 agents per simulation',
    'Up to 20 rounds',
    'All 12 platforms',
    'Custom persona creation',
    'White-label reports',
    'SSO/SAML',
    'SLA guarantee',
    'Dedicated infrastructure',
  ],
};

const TIERS = [
  {
    name: 'Founder',
    slug: 'founder',
    price: '$99',
    period: '/mo',
    desc: 'Validating an idea before building it',
    agentCap: '100',
    features: PLAN_FEATURES.founder,
  },
  {
    name: 'Growth',
    slug: 'growth',
    price: '$299',
    period: '/mo',
    desc: 'Testing messages before you spend on them',
    agentCap: '150',
    featured: true,
    features: PLAN_FEATURES.growth,
  },
  {
    name: 'Agency',
    slug: 'agency',
    price: '$999',
    period: '/mo',
    desc: 'Running work across multiple clients',
    agentCap: '250',
    features: PLAN_FEATURES.agency,
  },
  {
    name: 'Enterprise',
    slug: 'enterprise',
    price: 'Custom',
    period: '',
    desc: 'Maximum-scale analysis',
    agentCap: '1,000',
    features: PLAN_FEATURES.enterprise,
  },
];

const WEBHOOK_EVENTS = [
  'simulation.started',
  'simulation.completed',
  'simulation.failed',
  'report.ready',
];

// Shared styling tokens
const inputClass =
  'w-full bg-white/[0.03] border border-[#1E293B] rounded-lg px-4 py-2.5 text-sm text-[#E8ECF2] placeholder:text-[#5A6578]/60 focus:border-[#8B5CF6]/50 focus:ring-[#8B5CF6]/10 focus:outline-none transition';
const cardClass = 'bg-[#111827] border border-[#1E293B] rounded-2xl';
const goldBtnClass =
  'bg-[#C9A227] text-[#0A0F1C] font-semibold px-4 py-2 rounded-lg text-sm hover:bg-[#D4AF37] disabled:opacity-50 transition';
const outlineBtnClass =
  'bg-transparent border border-[#1E293B] text-[#8B97A8] px-4 py-2 rounded-lg text-sm hover:text-[#E8ECF2] hover:border-[#8B97A8]/40 transition';

// ---------------------------------------------------------------------------
// Usage Meter
// ---------------------------------------------------------------------------

function UsageMeter({
  label,
  used,
  limit,
  todo,
}: {
  label: string;
  used: number | null;
  limit: number | null;
  todo?: boolean;
}) {
  if (todo || used === null || limit === null) {
    return (
      <div className={`${cardClass} p-5`}>
        <div className="font-mono uppercase text-[10px] tracking-wider text-[#5A6578] mb-2">
          {label}
        </div>
        <div className="text-xl font-bold text-[#E8ECF2]">
          &mdash;{' '}
          <span className="text-sm font-normal text-[#5A6578]">coming soon</span>
        </div>
        {/* TODO: wire {label} usage meter to billing API */}
      </div>
    );
  }

  const pct = Math.round((used / Math.max(limit, 1)) * 100);
  const overThreshold = pct > 80;

  return (
    <div className={`${cardClass} p-5`}>
      <div className="font-mono uppercase text-[10px] tracking-wider text-[#5A6578] mb-2">
        {label}
      </div>
      <div className="text-xl font-bold text-[#E8ECF2]">
        {formatCount(used)}{' '}
        <span className="text-sm font-normal text-[#5A6578]">/ {formatCount(limit)}</span>
      </div>
      <div className="mt-3 h-2 bg-[#0A0F1C] rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${
            overThreshold
              ? 'bg-gradient-to-r from-[#F59E0B] to-[#EF4444]'
              : 'bg-gradient-to-r from-[#8B5CF6] to-[#2563EB]'
          }`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
      <div className="mt-1.5 text-xs text-[#5A6578]">{pct}% used</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// BILLING TAB
// ---------------------------------------------------------------------------

function BillingTab() {
  const [billing, setBilling] = useState<BillingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [upgrading, setUpgrading] = useState(false);
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [invoicesLoaded, setInvoicesLoaded] = useState(false);
  const [pmLoaded, setPmLoaded] = useState(false);

  useEffect(() => {
    api
      .get('/billing/status')
      .then((res) => setBilling(res.data))
      .catch(() => {})
      .finally(() => setLoading(false));

    api
      .get('/billing/payment-method')
      .then((res) => setPaymentMethod(res.data))
      .catch(() => {})
      .finally(() => setPmLoaded(true));

    api
      .get('/billing/invoices')
      .then((res) => setInvoices(res.data.items || res.data || []))
      .catch(() => {})
      .finally(() => setInvoicesLoaded(true));
  }, []);

  // TODO: NewSimulationPage.tsx agent slider max must read from billing/status agents_per_sim_limit instead of hardcoded 100

  const handleUpgrade = async (planSlug: string) => {
    if (planSlug === 'enterprise') {
      window.location.href = 'mailto:info@saidolabs.com';
      return;
    }
    setUpgrading(true);
    try {
      const { data } = await api.post('/billing/checkout', { plan: planSlug });
      if (data.checkout_url) window.location.href = data.checkout_url;
    } catch {
      // TODO: toast error
    } finally {
      setUpgrading(false);
    }
  };

  const handleCancel = () => {
    if (window.confirm('Cancel your subscription? You will lose access at the end of the billing period.')) {
      // TODO: call api.post('/billing/cancel') then refresh status
    }
  };

  if (loading) {
    return <p className="text-[#5A6578] py-8">Loading billing info...</p>;
  }
  if (!billing) {
    return <p className="text-[#EF4444] py-8">Could not load billing info.</p>;
  }

  const planKey = billing.plan.toLowerCase().replace(/\s+/g, '_');
  const price = PLAN_PRICE[planKey] || '$—';
  const agentCap = PLAN_AGENT_CAP[planKey] || '—';
  const currentFeatures = PLAN_FEATURES[planKey] || [];
  const nextPlan = getNextPlan(planKey);

  return (
    <div className="space-y-8">
      {/* ---- Current Plan Card ---- */}
      <div className={`${cardClass} p-6`}>
        <div className="flex items-start justify-between flex-wrap gap-4">
          <div>
            <span className="inline-block mb-3 text-[11px] font-bold tracking-wider uppercase px-3 py-1 rounded-full bg-gradient-to-r from-[#8B5CF6] to-[#2563EB] text-white">
              Current Plan
            </span>
            <h2 className="font-extrabold text-[28px] text-[#E8ECF2] capitalize">
              {billing.plan}
            </h2>
            <p className="font-mono text-lg text-[#8B97A8] mt-1">
              {price}
              {price !== 'Custom' && (
                <span className="text-sm text-[#5A6578]">/mo</span>
              )}
            </p>
            <p className="text-sm text-[#5A6578] mt-2">
              Up to {agentCap} agents per simulation
            </p>
          </div>

          <div className="flex gap-3 items-start">
            <button onClick={handleCancel} className="bg-transparent border border-[#1E293B] text-[#8B97A8] px-4 py-2 rounded-lg text-sm hover:text-[#EF4444] hover:border-[#EF4444]/30 transition">
              Cancel Plan
            </button>
            {nextPlan && (
              <button
                onClick={() => handleUpgrade(nextPlan)}
                disabled={upgrading}
                className={goldBtnClass}
              >
                {upgrading ? 'Redirecting...' : `Upgrade to ${nextPlan.replace('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase())}`}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ---- Usage Meters ---- */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <UsageMeter
          label="Simulations"
          used={billing.simulations_used}
          limit={billing.simulations_limit}
        />
        {billing.agents_used !== undefined && billing.agents_limit !== undefined ? (
          <UsageMeter
            label="Agents"
            used={billing.agents_used}
            limit={billing.agents_limit}
          />
        ) : (
          <UsageMeter label="Agents" used={null} limit={null} todo />
        )}
        <UsageMeter label="Reports" used={null} limit={null} todo />
        <UsageMeter label="API Calls" used={null} limit={null} todo />
      </div>

      {/* ---- Plan Features ---- */}
      {currentFeatures.length > 0 && (
        <div className={`${cardClass} p-6`}>
          <h3 className="font-bold text-[#E8ECF2] mb-4">Your Plan Features</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {currentFeatures.map((f) => (
              <div key={f} className="flex items-center gap-2">
                <Check size={14} className="text-[#22C55E] shrink-0" />
                <span className="text-sm text-[#8B97A8]">{f}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ---- Compare Plans ---- */}
      <div>
        <h3 className="font-bold text-lg text-[#E8ECF2] mb-4">Compare Plans</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {TIERS.map((tier) => {
            const isCurrent = tier.slug === planKey;
            const currentIdx = PLAN_ORDER.indexOf(planKey);
            const tierIdx = PLAN_ORDER.indexOf(tier.slug);
            const isLower = tierIdx < currentIdx;

            return (
              <div
                key={tier.slug}
                className={`${cardClass} p-5 flex flex-col relative ${
                  tier.featured ? 'border-[#8B5CF6]/40' : ''
                }`}
              >
                {tier.featured && (
                  <span className="absolute -top-3 left-1/2 -translate-x-1/2 text-[10px] font-bold tracking-wider uppercase px-3 py-1 rounded-full bg-gradient-to-r from-[#8B5CF6] to-[#2563EB] text-white whitespace-nowrap">
                    Most Popular
                  </span>
                )}
                <h4 className="font-bold text-[#E8ECF2] mt-2">{tier.name}</h4>
                <p className="font-mono text-xl font-bold text-[#E8ECF2] mt-1">
                  {tier.price}
                  {tier.period && (
                    <span className="text-sm font-normal text-[#5A6578]">{tier.period}</span>
                  )}
                </p>
                <p className="text-xs text-[#5A6578] mt-1 mb-4">{tier.desc}</p>

                <div className="flex-1 space-y-1.5 mb-5">
                  {tier.features.map((f) => (
                    <div key={f} className="flex items-start gap-2">
                      <Check size={12} className="text-[#22C55E] mt-0.5 shrink-0" />
                      <span className="text-xs text-[#8B97A8]">{f}</span>
                    </div>
                  ))}
                </div>

                {isCurrent ? (
                  <button disabled className="w-full py-2 rounded-lg text-sm font-semibold bg-[#1E293B] text-[#5A6578] cursor-not-allowed">
                    Current Plan
                  </button>
                ) : tier.slug === 'enterprise' ? (
                  <button
                    onClick={() => {
                      window.location.href = 'mailto:info@saidolabs.com';
                    }}
                    className={`w-full ${outlineBtnClass}`}
                  >
                    Contact Sales
                  </button>
                ) : isLower ? (
                  <button
                    className={`w-full ${outlineBtnClass}`}
                    onClick={() => {
                      // TODO: implement downgrade flow
                    }}
                  >
                    Downgrade
                  </button>
                ) : (
                  <button
                    onClick={() => handleUpgrade(tier.slug)}
                    disabled={upgrading}
                    className={`w-full ${goldBtnClass}`}
                  >
                    Upgrade Now
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* ---- Payment Method ---- */}
      <div className={`${cardClass} p-6`}>
        <h3 className="font-bold text-[#E8ECF2] mb-4 flex items-center gap-2">
          <CreditCard size={16} className="text-[#8B97A8]" />
          Payment Method
        </h3>
        {!pmLoaded ? (
          <p className="text-sm text-[#5A6578]">Loading...</p>
        ) : paymentMethod ? (
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-7 rounded bg-[#0A0F1C] flex items-center justify-center">
                <CreditCard size={16} className="text-[#8B97A8]" />
              </div>
              <div>
                <p className="text-sm text-[#E8ECF2] font-medium capitalize">
                  {paymentMethod.brand} &bull;&bull;&bull;&bull; {paymentMethod.last4}
                </p>
                <p className="text-xs text-[#5A6578]">
                  Expires {String(paymentMethod.exp_month).padStart(2, '0')}/{paymentMethod.exp_year}
                </p>
              </div>
            </div>
            <div className="flex gap-2">
              {/* TODO: open Stripe Customer Portal for update */}
              <button className={outlineBtnClass}>Update</button>
              {/* TODO: open Stripe Customer Portal for remove */}
              <button className="bg-transparent border border-[#1E293B] text-[#8B97A8] px-4 py-2 rounded-lg text-sm hover:text-[#EF4444] hover:border-[#EF4444]/30 transition">
                Remove
              </button>
            </div>
          </div>
        ) : (
          <div className="text-center py-6">
            <p className="text-sm text-[#5A6578] mb-3">No payment method on file</p>
            {/* TODO: open Stripe Customer Portal to add payment method */}
            <button className={goldBtnClass}>Add Payment Method</button>
          </div>
        )}
      </div>

      {/* ---- Invoice History ---- */}
      <div className={`${cardClass} p-6`}>
        <h3 className="font-bold text-[#E8ECF2] mb-4">Invoice History</h3>
        {!invoicesLoaded ? (
          <p className="text-sm text-[#5A6578]">Loading...</p>
        ) : invoices.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#1E293B]">
                  <th className="text-left py-2 pr-4 text-[#5A6578] font-medium text-xs uppercase tracking-wider">Date</th>
                  <th className="text-left py-2 pr-4 text-[#5A6578] font-medium text-xs uppercase tracking-wider">Description</th>
                  <th className="text-left py-2 pr-4 text-[#5A6578] font-medium text-xs uppercase tracking-wider">Amount</th>
                  <th className="text-left py-2 pr-4 text-[#5A6578] font-medium text-xs uppercase tracking-wider">Status</th>
                  <th className="text-right py-2 text-[#5A6578] font-medium text-xs uppercase tracking-wider">Download</th>
                </tr>
              </thead>
              <tbody>
                {invoices.map((inv) => (
                  <tr key={inv.id} className="border-b border-[#1E293B]/50">
                    <td className="py-3 pr-4 text-[#E8ECF2]">{inv.date}</td>
                    <td className="py-3 pr-4 text-[#8B97A8]">{inv.description}</td>
                    <td className="py-3 pr-4 text-[#E8ECF2] font-mono">{inv.amount}</td>
                    <td className="py-3 pr-4">
                      <span
                        className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                          inv.status.toLowerCase() === 'paid'
                            ? 'bg-[#22C55E]/10 text-[#22C55E]'
                            : 'bg-[#F59E0B]/10 text-[#F59E0B]'
                        }`}
                      >
                        {inv.status}
                      </span>
                    </td>
                    <td className="py-3 text-right">
                      {inv.pdf_url && (
                        <button
                          onClick={() => window.open(inv.pdf_url, '_blank')}
                          className="text-[#8B97A8] hover:text-[#E8ECF2] transition"
                        >
                          <Download size={14} />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center py-6">
            <p className="text-sm text-[#5A6578]">
              Invoice history will appear here once billing is active
            </p>
            {/* TODO: backend endpoint GET /billing/invoices needs implementation */}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// GENERAL TAB (placeholder)
// ---------------------------------------------------------------------------

function GeneralTab() {
  return (
    <div className={`${cardClass} p-6`}>
      <h3 className="font-bold text-[#E8ECF2] mb-2 flex items-center gap-2">
        <SettingsIcon size={16} className="text-[#8B97A8]" />
        Organization Settings
      </h3>
      <p className="text-sm text-[#5A6578]">
        Coming soon &mdash; org name, logo, and workspace preferences will be configurable here.
      </p>
      {/* TODO: implement General settings — org name, logo upload, workspace prefs */}
    </div>
  );
}

// ---------------------------------------------------------------------------
// TEAM TAB (logic preserved, restyled)
// ---------------------------------------------------------------------------

function TeamTab() {
  const org = useAuthStore((s) => s.org);
  const [members, setMembers] = useState<Member[]>([]);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviting, setInviting] = useState(false);

  useEffect(() => {
    if (!org?.id) return;
    api
      .get(`/organizations/${org.id}/members`)
      .then((res) => setMembers(res.data.items || res.data))
      .catch(() => {});
  }, [org?.id]);

  const handleInvite = async (e: FormEvent) => {
    e.preventDefault();
    if (!org?.id) return;
    setInviting(true);
    try {
      await api.post(`/organizations/${org.id}/invite`, {
        email: inviteEmail,
        role: 'member',
      });
      setInviteEmail('');
      const res = await api.get(`/organizations/${org.id}/members`);
      setMembers(res.data.items || res.data);
    } catch {
      // TODO: toast error
    } finally {
      setInviting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className={`${cardClass} p-5`}>
        <h3 className="font-bold text-[#E8ECF2] mb-4 flex items-center gap-2">
          <Users size={16} className="text-[#8B97A8]" />
          Invite Team Member
        </h3>
        <form onSubmit={handleInvite} className="flex gap-3">
          <input
            type="email"
            required
            value={inviteEmail}
            onChange={(e) => setInviteEmail(e.target.value)}
            placeholder="colleague@company.com"
            className={`flex-1 ${inputClass}`}
          />
          <button type="submit" disabled={inviting} className={goldBtnClass}>
            {inviting ? 'Inviting...' : 'Invite'}
          </button>
        </form>
      </div>

      <div className={`${cardClass} overflow-hidden`}>
        <div className="px-5 py-3 border-b border-[#1E293B]">
          <h3 className="font-bold text-[#E8ECF2] text-sm">Members</h3>
        </div>
        <ul className="divide-y divide-[#1E293B]">
          {members.map((m) => (
            <li key={m.id} className="px-5 py-3 flex items-center justify-between hover:bg-[#1A2233] transition">
              <span className="text-sm text-[#E8ECF2]">{m.email}</span>
              <span className="text-xs text-[#5A6578] capitalize">{m.role}</span>
            </li>
          ))}
          {members.length === 0 && (
            <li className="px-5 py-6 text-sm text-[#5A6578] text-center">No team members yet.</li>
          )}
        </ul>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// API KEYS TAB (logic preserved, restyled)
// ---------------------------------------------------------------------------

function ApiKeysTab() {
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [keyName, setKeyName] = useState('');
  const [newKeyValue, setNewKeyValue] = useState('');
  const [creating, setCreating] = useState(false);

  const fetchKeys = () => {
    api
      .get('/api-keys')
      .then((res) => setKeys(res.data.items || res.data))
      .catch(() => {});
  };

  useEffect(() => {
    fetchKeys();
  }, []);

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault();
    setCreating(true);
    try {
      const { data } = await api.post<CreatedApiKey>('/api-keys', { name: keyName });
      setNewKeyValue(data.key);
      setKeyName('');
      fetchKeys();
    } catch {
      // TODO: toast error
    } finally {
      setCreating(false);
    }
  };

  const handleRevoke = async (id: string) => {
    try {
      await api.delete(`/api-keys/${id}`);
      fetchKeys();
    } catch {
      // TODO: toast error
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h3 className="font-bold text-[#E8ECF2] flex items-center gap-2">
          <Key size={16} className="text-[#8B97A8]" />
          API Keys
        </h3>
        <button
          onClick={() => {
            setShowModal(true);
            setNewKeyValue('');
          }}
          className={goldBtnClass}
        >
          + Create API Key
        </button>
      </div>

      <div className={`${cardClass} overflow-hidden`}>
        <ul className="divide-y divide-[#1E293B]">
          {keys.map((k) => (
            <li key={k.id} className="px-5 py-3 flex items-center justify-between hover:bg-[#1A2233] transition">
              <div>
                <span className="text-sm font-medium text-[#E8ECF2]">{k.name}</span>
                <span className="text-xs text-[#5A6578] ml-2 font-mono">{k.key_prefix}...</span>
              </div>
              <button
                onClick={() => handleRevoke(k.id)}
                className="text-xs text-[#EF4444]/80 hover:text-[#EF4444] transition"
              >
                Revoke
              </button>
            </li>
          ))}
          {keys.length === 0 && (
            <li className="px-5 py-6 text-sm text-[#5A6578] text-center">No API keys yet.</li>
          )}
        </ul>
      </div>

      {/* Create Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-[#0D1424] rounded-2xl p-6 w-full max-w-md border border-[#1E293B]">
            <h2 className="text-lg font-semibold text-[#E8ECF2] mb-4">Create API Key</h2>
            {newKeyValue ? (
              <div className="space-y-4">
                <p className="text-sm text-[#5A6578]">
                  Copy this key now. It will not be shown again.
                </p>
                <div className="bg-[#0A0F1C] p-3 rounded-lg font-mono text-sm break-all text-[#E8ECF2]">
                  {newKeyValue}
                </div>
                <button
                  onClick={() => {
                    setShowModal(false);
                    setNewKeyValue('');
                  }}
                  className={goldBtnClass}
                >
                  Done
                </button>
              </div>
            ) : (
              <form onSubmit={handleCreate} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-[#E8ECF2] mb-1">
                    Key Name
                  </label>
                  <input
                    required
                    value={keyName}
                    onChange={(e) => setKeyName(e.target.value)}
                    className={inputClass}
                  />
                </div>
                <div className="flex justify-end gap-3">
                  <button
                    type="button"
                    onClick={() => setShowModal(false)}
                    className="px-4 py-2 text-[#5A6578] hover:text-[#E8ECF2] transition text-sm"
                  >
                    Cancel
                  </button>
                  <button type="submit" disabled={creating} className={goldBtnClass}>
                    {creating ? 'Creating...' : 'Create'}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------
// WEBHOOKS TAB (logic preserved, restyled)
// ---------------------------------------------------------------------------

function WebhooksTab() {
  const [hooks, setHooks] = useState<WebhookItem[]>([]);
  const [url, setUrl] = useState('');
  const [selectedEvents, setSelectedEvents] = useState<string[]>([]);
  const [creating, setCreating] = useState(false);

  const fetchHooks = () => {
    api
      .get('/webhooks')
      .then((res) => setHooks(res.data.items || res.data))
      .catch(() => {});
  };

  useEffect(() => {
    fetchHooks();
  }, []);

  const toggleEvent = (evt: string) => {
    setSelectedEvents((prev) =>
      prev.includes(evt) ? prev.filter((e) => e !== evt) : [...prev, evt],
    );
  };

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault();
    setCreating(true);
    try {
      await api.post('/webhooks', { url, events: selectedEvents });
      setUrl('');
      setSelectedEvents([]);
      fetchHooks();
    } catch {
      // TODO: toast error
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await api.delete(`/webhooks/${id}`);
      fetchHooks();
    } catch {
      // TODO: toast error
    }
  };

  return (
    <div className="space-y-6">
      <div className={`${cardClass} p-5 space-y-4`}>
        <h3 className="font-bold text-[#E8ECF2] flex items-center gap-2">
          <Webhook size={16} className="text-[#8B97A8]" />
          Add Webhook
        </h3>
        <form onSubmit={handleCreate} className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-[#E8ECF2] mb-1">Webhook URL</label>
            <input
              type="url"
              required
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com/webhook"
              className={inputClass}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-[#E8ECF2] mb-1">Events</label>
            <div className="flex flex-wrap gap-2">
              {WEBHOOK_EVENTS.map((evt) => (
                <button
                  key={evt}
                  type="button"
                  onClick={() => toggleEvent(evt)}
                  className={`text-xs px-3 py-1.5 rounded-lg border transition ${
                    selectedEvents.includes(evt)
                      ? 'bg-[#C9A227] text-[#0A0F1C] border-[#C9A227] font-semibold'
                      : 'border-[#1E293B] text-[#5A6578] hover:border-[#8B97A8]/40 hover:text-[#8B97A8]'
                  }`}
                >
                  {evt}
                </button>
              ))}
            </div>
          </div>
          <button
            type="submit"
            disabled={creating || selectedEvents.length === 0}
            className={goldBtnClass}
          >
            {creating ? 'Creating...' : 'Add Webhook'}
          </button>
        </form>
      </div>

      <div className={`${cardClass} overflow-hidden`}>
        <ul className="divide-y divide-[#1E293B]">
          {hooks.map((h) => (
            <li key={h.id} className="px-5 py-3 flex items-center justify-between hover:bg-[#1A2233] transition">
              <div>
                <div className="text-sm font-medium text-[#E8ECF2]">{h.url}</div>
                <div className="text-xs text-[#5A6578] mt-0.5">{h.events.join(', ')}</div>
              </div>
              <button
                onClick={() => handleDelete(h.id)}
                className="text-xs text-[#EF4444]/80 hover:text-[#EF4444] transition"
              >
                Delete
              </button>
            </li>
          ))}
          {hooks.length === 0 && (
            <li className="px-5 py-6 text-sm text-[#5A6578] text-center">
              No webhooks configured.
            </li>
          )}
        </ul>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// NOTIFICATIONS TAB (placeholder)
// ---------------------------------------------------------------------------

function NotificationsTab() {
  return (
    <div className={`${cardClass} p-6`}>
      <h3 className="font-bold text-[#E8ECF2] mb-2 flex items-center gap-2">
        <Bell size={16} className="text-[#8B97A8]" />
        Notifications
      </h3>
      <p className="text-sm text-[#5A6578]">
        Coming soon &mdash; email digests, simulation alerts, and team notifications will be
        configurable here.
      </p>
      {/* TODO: implement notification preferences — email digests, sim alerts, team notifications */}
    </div>
  );
}

// ---------------------------------------------------------------------------
// SECURITY TAB (placeholder)
// ---------------------------------------------------------------------------

function SecurityTab() {
  return (
    <div className={`${cardClass} p-6`}>
      <h3 className="font-bold text-[#E8ECF2] mb-2 flex items-center gap-2">
        <Shield size={16} className="text-[#8B97A8]" />
        Security
      </h3>
      <p className="text-sm text-[#5A6578]">
        Coming soon &mdash; password changes, two-factor authentication, and session management will
        be configurable here.
      </p>
      {/* TODO: implement security settings — password change, 2FA, session management */}
    </div>
  );
}

// ---------------------------------------------------------------------------
// MAIN SETTINGS PAGE
// ---------------------------------------------------------------------------

const TABS: { key: SettingsTab; label: string; icon: typeof SettingsIcon }[] = [
  { key: 'general', label: 'General', icon: SettingsIcon },
  { key: 'team', label: 'Team', icon: Users },
  { key: 'billing', label: 'Billing', icon: CreditCard },
  { key: 'api-keys', label: 'API Keys', icon: Key },
  { key: 'webhooks', label: 'Webhooks', icon: Webhook },
  { key: 'notifications', label: 'Notifications', icon: Bell },
  { key: 'security', label: 'Security', icon: Shield },
];

export default function SettingsPage() {
  const [tab, setTab] = useState<SettingsTab>('billing');

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <h1 className="font-extrabold text-[22px] text-[#E8ECF2]">Settings</h1>
        <p className="text-sm text-[#5A6578] mt-1">
          Manage your workspace, team, and billing
        </p>
      </div>

      {/* Tab Bar */}
      <div className="flex gap-0 border-b border-[#1E293B] mb-6 overflow-x-auto">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-5 py-3 text-[13px] font-semibold transition-all whitespace-nowrap ${
              tab === t.key
                ? 'text-[#E8ECF2] border-b-2 border-[#2563EB]'
                : 'text-[#5A6578] hover:text-[#8B97A8]'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {tab === 'general' && <GeneralTab />}
      {tab === 'team' && <TeamTab />}
      {tab === 'billing' && <BillingTab />}
      {tab === 'api-keys' && <ApiKeysTab />}
      {tab === 'webhooks' && <WebhooksTab />}
      {tab === 'notifications' && <NotificationsTab />}
      {tab === 'security' && <SecurityTab />}
    </div>
  );
}
