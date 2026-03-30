import { useEffect, useState, type FormEvent } from 'react';
import api from '@/lib/api';
import { useAuthStore } from '@/store/auth';

type SettingsTab = 'billing' | 'team' | 'api-keys' | 'integrations' | 'webhooks';

// --- Billing ---
interface BillingInfo {
  plan: string;
  simulations_used: number;
  simulations_limit: number;
  agents_used: number;
  agents_limit: number;
}

function BillingTab() {
  const [billing, setBilling] = useState<BillingInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [upgrading, setUpgrading] = useState(false);

  useEffect(() => {
    api.get('/billing/status').then((res) => setBilling(res.data)).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const handleUpgrade = async () => {
    setUpgrading(true);
    try {
      const { data } = await api.post('/billing/checkout', { plan: 'pro' });
      if (data.checkout_url) window.location.href = data.checkout_url;
    } catch {
      // handle error
    } finally {
      setUpgrading(false);
    }
  };

  if (loading) return <p className="text-saibyl-muted">Loading billing info...</p>;
  if (!billing) return <p className="text-red-500">Could not load billing info.</p>;

  const simPct = Math.round((billing.simulations_used / Math.max(billing.simulations_limit, 1)) * 100);
  const agentPct = Math.round((billing.agents_used / Math.max(billing.agents_limit, 1)) * 100);

  return (
    <div className="space-y-6">
      <div>
        <h3 className="font-medium text-saibyl-platinum mb-1">Current Plan: <span className="text-saibyl-indigo">{billing.plan}</span></h3>
      </div>
      <div>
        <div className="text-sm text-saibyl-muted mb-1">Simulations: {billing.simulations_used} / {billing.simulations_limit}</div>
        <div className="w-full bg-saibyl-surface rounded-full h-2.5 overflow-hidden">
          <div className="h-2.5 rounded-full" style={{ width: `${Math.min(simPct, 100)}%`, background: 'linear-gradient(90deg, #5B5FEE, #00D4FF)' }} />
        </div>
      </div>
      <div>
        <div className="text-sm text-saibyl-muted mb-1">Agents: {billing.agents_used} / {billing.agents_limit}</div>
        <div className="w-full bg-saibyl-surface rounded-full h-2.5 overflow-hidden">
          <div className="h-2.5 rounded-full" style={{ width: `${Math.min(agentPct, 100)}%`, background: 'linear-gradient(90deg, #A78BFA, #5B5FEE)' }} />
        </div>
      </div>
      <button
        onClick={handleUpgrade}
        disabled={upgrading}
        className="bg-saibyl-indigo text-white px-4 py-2 rounded-lg hover:bg-[#4B4FDE] disabled:opacity-50 transition"
      >
        {upgrading ? 'Redirecting...' : 'Upgrade Plan'}
      </button>
    </div>
  );
}

// --- Team ---
interface Member {
  id: string;
  email: string;
  role: string;
}

function TeamTab() {
  const org = useAuthStore((s) => s.org);
  const [members, setMembers] = useState<Member[]>([]);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviting, setInviting] = useState(false);

  useEffect(() => {
    if (!org?.id) return;
    api.get(`/organizations/${org.id}/members`).then((res) => setMembers(res.data.items || res.data)).catch(() => {});
  }, [org?.id]);

  const handleInvite = async (e: FormEvent) => {
    e.preventDefault();
    if (!org?.id) return;
    setInviting(true);
    try {
      await api.post(`/organizations/${org.id}/invite`, { email: inviteEmail, role: 'member' });
      setInviteEmail('');
      const res = await api.get(`/organizations/${org.id}/members`);
      setMembers(res.data.items || res.data);
    } catch {
      // handle error
    } finally {
      setInviting(false);
    }
  };

  return (
    <div className="space-y-6">
      <form onSubmit={handleInvite} className="flex gap-3">
        <input
          type="email"
          required
          value={inviteEmail}
          onChange={(e) => setInviteEmail(e.target.value)}
          placeholder="colleague@company.com"
          className="flex-1 bg-saibyl-surface border border-saibyl-border rounded-lg px-3 py-2 text-sm text-saibyl-platinum placeholder-saibyl-muted focus:outline-none focus:ring-2 focus:ring-saibyl-indigo"
        />
        <button
          type="submit"
          disabled={inviting}
          className="bg-saibyl-indigo text-white px-4 py-2 rounded-lg text-sm hover:bg-[#4B4FDE] disabled:opacity-50"
        >
          {inviting ? 'Inviting...' : 'Invite'}
        </button>
      </form>
      <ul className="divide-y divide-saibyl-border bg-saibyl-deep rounded-2xl border border-saibyl-border">
        {members.map((m) => (
          <li key={m.id} className="px-4 py-3 flex items-center justify-between">
            <span className="text-sm text-saibyl-platinum">{m.email}</span>
            <span className="text-xs text-saibyl-muted capitalize">{m.role}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// --- API Keys ---
interface ApiKey {
  id: string;
  name: string;
  prefix: string;
  created_at: string;
}

function ApiKeysTab() {
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [keyName, setKeyName] = useState('');
  const [newKeyValue, setNewKeyValue] = useState('');
  const [creating, setCreating] = useState(false);

  const fetchKeys = () => {
    api.get('/api-keys').then((res) => setKeys(res.data.items || res.data)).catch(() => {});
  };

  useEffect(() => { fetchKeys(); }, []);

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault();
    setCreating(true);
    try {
      const { data } = await api.post('/api-keys', { name: keyName });
      setNewKeyValue(data.key);
      setKeyName('');
      fetchKeys();
    } catch {
      // handle error
    } finally {
      setCreating(false);
    }
  };

  const handleRevoke = async (id: string) => {
    try {
      await api.delete(`/api-keys/${id}`);
      fetchKeys();
    } catch {
      // handle error
    }
  };

  return (
    <div className="space-y-6">
      <button
        onClick={() => { setShowModal(true); setNewKeyValue(''); }}
        className="bg-saibyl-indigo text-white px-4 py-2 rounded-lg text-sm hover:bg-[#4B4FDE]"
      >
        + Create API Key
      </button>

      <ul className="divide-y divide-saibyl-border bg-saibyl-deep rounded-2xl border border-saibyl-border">
        {keys.map((k) => (
          <li key={k.id} className="px-4 py-3 flex items-center justify-between">
            <div>
              <span className="text-sm font-medium text-saibyl-platinum">{k.name}</span>
              <span className="text-xs text-saibyl-muted ml-2">{k.prefix}...</span>
            </div>
            <button onClick={() => handleRevoke(k.id)} className="text-xs text-saibyl-negative hover:text-red-400 transition-colors">
              Revoke
            </button>
          </li>
        ))}
        {keys.length === 0 && <li className="px-4 py-3 text-sm text-saibyl-muted">No API keys yet.</li>}
      </ul>

      {/* Create Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-saibyl-deep rounded-2xl p-6 w-full max-w-md border border-saibyl-border">
            <h2 className="text-lg font-semibold text-saibyl-platinum mb-4">Create API Key</h2>
            {newKeyValue ? (
              <div className="space-y-4">
                <p className="text-sm text-saibyl-muted">Copy this key now. It will not be shown again.</p>
                <div className="bg-saibyl-surface p-3 rounded-lg font-mono text-sm break-all text-saibyl-platinum">{newKeyValue}</div>
                <button onClick={() => { setShowModal(false); setNewKeyValue(''); }} className="bg-saibyl-indigo text-white px-4 py-2 rounded-lg text-sm">
                  Done
                </button>
              </div>
            ) : (
              <form onSubmit={handleCreate} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-saibyl-platinum mb-1">Key Name</label>
                  <input
                    required
                    value={keyName}
                    onChange={(e) => setKeyName(e.target.value)}
                    className="w-full bg-saibyl-surface border border-saibyl-border rounded-lg px-3 py-2 text-saibyl-platinum placeholder-saibyl-muted focus:outline-none focus:ring-2 focus:ring-saibyl-indigo"
                  />
                </div>
                <div className="flex justify-end gap-3">
                  <button type="button" onClick={() => setShowModal(false)} className="px-4 py-2 text-saibyl-muted hover:text-saibyl-platinum">Cancel</button>
                  <button type="submit" disabled={creating} className="bg-saibyl-indigo text-white px-4 py-2 rounded-lg hover:bg-[#4B4FDE] disabled:opacity-50">
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

// --- Webhooks ---
interface Webhook {
  id: string;
  url: string;
  events: string[];
  active: boolean;
}

const WEBHOOK_EVENTS = [
  'simulation.started',
  'simulation.completed',
  'simulation.failed',
  'report.ready',
];

function WebhooksTab() {
  const [hooks, setHooks] = useState<Webhook[]>([]);
  const [url, setUrl] = useState('');
  const [selectedEvents, setSelectedEvents] = useState<string[]>([]);
  const [creating, setCreating] = useState(false);

  const fetchHooks = () => {
    api.get('/webhooks').then((res) => setHooks(res.data.items || res.data)).catch(() => {});
  };

  useEffect(() => { fetchHooks(); }, []);

  const toggleEvent = (evt: string) => {
    setSelectedEvents((prev) =>
      prev.includes(evt) ? prev.filter((e) => e !== evt) : [...prev, evt]
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
      // handle error
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await api.delete(`/webhooks/${id}`);
      fetchHooks();
    } catch {
      // handle error
    }
  };

  return (
    <div className="space-y-6">
      <form onSubmit={handleCreate} className="bg-saibyl-deep rounded-2xl p-4 space-y-3 border border-saibyl-border">
        <div>
          <label className="block text-sm font-medium text-saibyl-platinum mb-1">Webhook URL</label>
          <input
            type="url"
            required
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://example.com/webhook"
            className="w-full bg-saibyl-surface border border-saibyl-border rounded-lg px-3 py-2 text-sm text-saibyl-platinum placeholder-saibyl-muted focus:outline-none focus:ring-2 focus:ring-saibyl-indigo"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-saibyl-platinum mb-1">Events</label>
          <div className="flex flex-wrap gap-2">
            {WEBHOOK_EVENTS.map((evt) => (
              <button
                key={evt}
                type="button"
                onClick={() => toggleEvent(evt)}
                className={`text-xs px-3 py-1.5 rounded-lg border transition ${
                  selectedEvents.includes(evt)
                    ? 'bg-saibyl-indigo text-white border-saibyl-indigo'
                    : 'border-saibyl-border text-saibyl-muted hover:border-saibyl-border'
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
          className="bg-saibyl-indigo text-white px-4 py-2 rounded-lg text-sm hover:bg-[#4B4FDE] disabled:opacity-50"
        >
          {creating ? 'Creating...' : 'Add Webhook'}
        </button>
      </form>

      <ul className="divide-y divide-saibyl-border bg-saibyl-deep rounded-2xl border border-saibyl-border">
        {hooks.map((h) => (
          <li key={h.id} className="px-4 py-3 flex items-center justify-between">
            <div>
              <div className="text-sm font-medium text-saibyl-platinum">{h.url}</div>
              <div className="text-xs text-saibyl-muted mt-0.5">{h.events.join(', ')}</div>
            </div>
            <button onClick={() => handleDelete(h.id)} className="text-xs text-saibyl-negative hover:text-red-400 transition-colors">
              Delete
            </button>
          </li>
        ))}
        {hooks.length === 0 && <li className="px-4 py-3 text-sm text-saibyl-muted">No webhooks configured.</li>}
      </ul>
    </div>
  );
}

// --- Integrations (Market API Keys) ---
function IntegrationsTab() {
  const [keys, setKeys] = useState<{ platform: string; key_preview: string }[]>([]);
  const [platform] = useState('kalshi');
  const [apiKey, setApiKey] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    api.get('/markets/keys').then((r) => setKeys(Array.isArray(r.data) ? r.data : [])).catch(() => {});
  }, []);

  const handleSave = async (e: FormEvent) => {
    e.preventDefault();
    if (!apiKey.trim()) return;
    setSaving(true);
    setError('');
    try {
      await api.post('/markets/keys', { platform, api_key: apiKey });
      setApiKey('');
      const r = await api.get('/markets/keys');
      setKeys(Array.isArray(r.data) ? r.data : []);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save key');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (p: string) => {
    try {
      await api.delete(`/markets/keys/${p}`);
      setKeys((prev) => prev.filter((k) => k.platform !== p));
    } catch { /* ignore */ }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-saibyl-platinum mb-1">Market Integrations</h2>
        <p className="text-sm text-saibyl-muted">Connect prediction market platforms to run AI-powered predictions.</p>
      </div>

      {error && <div className="text-sm text-saibyl-negative bg-saibyl-negative/10 px-4 py-2 rounded-lg">{error}</div>}

      <div className="bg-saibyl-deep rounded-2xl p-5 border border-saibyl-border space-y-4">
        <div className="flex items-start gap-4">
          <div className="flex-1">
            <p className="text-sm font-medium text-saibyl-platinum">Polymarket</p>
            <p className="text-xs text-saibyl-muted mt-0.5">No API key required — uses public APIs. Import markets and run predictions immediately.</p>
          </div>
          <span className="text-xs px-2 py-1 rounded bg-saibyl-positive/15 text-saibyl-positive">Connected</span>
        </div>

        <div className="border-t border-saibyl-border pt-4">
          <div className="flex items-start gap-4 mb-3">
            <div className="flex-1">
              <p className="text-sm font-medium text-saibyl-platinum">Kalshi</p>
              <p className="text-xs text-saibyl-muted mt-0.5">Requires API key for market data access. Get yours at kalshi.com/account/api.</p>
            </div>
            {keys.some((k) => k.platform === 'kalshi') ? (
              <div className="flex items-center gap-2">
                <span className="text-xs px-2 py-1 rounded bg-saibyl-positive/15 text-saibyl-positive">
                  Connected (•••{keys.find((k) => k.platform === 'kalshi')?.key_preview})
                </span>
                <button onClick={() => handleDelete('kalshi')} className="text-xs text-saibyl-negative hover:text-red-400">Remove</button>
              </div>
            ) : (
              <span className="text-xs px-2 py-1 rounded bg-saibyl-elevated text-saibyl-muted">Not connected</span>
            )}
          </div>

          {!keys.some((k) => k.platform === 'kalshi') && (
            <form onSubmit={handleSave} className="flex gap-2">
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="Kalshi API key"
                className="flex-1 bg-saibyl-surface border border-saibyl-border rounded-lg px-3 py-2 text-sm text-saibyl-platinum placeholder-saibyl-muted focus:outline-none focus:ring-2 focus:ring-saibyl-indigo"
              />
              <button
                type="submit"
                disabled={saving || !apiKey.trim()}
                className="bg-saibyl-indigo text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-[#4B4FDE] disabled:opacity-50"
              >
                {saving ? 'Saving...' : 'Connect'}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}

// --- Main Settings Page ---
export default function SettingsPage() {
  const [tab, setTab] = useState<SettingsTab>('billing');

  const tabs: { key: SettingsTab; label: string }[] = [
    { key: 'billing', label: 'Billing' },
    { key: 'team', label: 'Team' },
    { key: 'api-keys', label: 'API Keys' },
    { key: 'integrations', label: 'Integrations' },
    { key: 'webhooks', label: 'Webhooks' },
  ];

  return (
    <div className="p-6 max-w-4xl mx-auto bg-saibyl-void">
      <h1 className="text-2xl font-bold text-saibyl-platinum mb-6">Settings</h1>

      <div className="flex border-b border-saibyl-border mb-6">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 -mb-px text-sm font-medium transition ${
              tab === t.key
                ? 'border-b-2 border-saibyl-border-active text-saibyl-indigo'
                : 'text-saibyl-muted hover:text-saibyl-platinum'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'billing' && <BillingTab />}
      {tab === 'team' && <TeamTab />}
      {tab === 'api-keys' && <ApiKeysTab />}
      {tab === 'integrations' && <IntegrationsTab />}
      {tab === 'webhooks' && <WebhooksTab />}
    </div>
  );
}
