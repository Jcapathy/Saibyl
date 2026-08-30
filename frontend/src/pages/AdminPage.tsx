import { useCallback, useEffect, useState } from 'react';

import api from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { Action, Card, Chapter, Ground, Hero, Longform, Notice, Reveal } from '@/components/design';

/**
 * The founder's console: who signed up, what they hold, and granting credits.
 *
 * **Deliberately not in the navigation.** `require_platform_admin` refuses with
 * a 404 rather than a 403 precisely so a probe cannot confirm the surface
 * exists; putting "Admin" in the sidebar for every customer would announce it
 * to exactly the people the 404 is hiding it from, and hand them a link that
 * fails. Reached by typing `/app/admin`.
 *
 * **Why it exists.** Two comped grants were applied by hand against the
 * database because there was no other way to do it, leaving no record of who
 * granted what or why. That works once. `credit_grants` (migration 046) and
 * `POST /api/admin/credits` are the replacement, and this is the surface.
 *
 * The people table carries activity beside each address on purpose: a mailer
 * needs to segment on "signed up and did nothing" against "ran four checks",
 * and a column of email addresses cannot do that.
 */

type Overview = {
  organizations: number;
  people: number;
  credits_outstanding: number;
  credits_comped: number;
  revenue_cents: number;
  purchases: number;
  website_checks: number;
  runs: number;
  page_revisions: number;
};

type Person = {
  user_id: string;
  email: string | null;
  signed_up_at: string;
  last_sign_in_at: string | null;
  organization_id: string | null;
  organization: string | null;
  plan: string | null;
  credits_balance: number | null;
  checks: number;
  runs: number;
  revisions: number;
};

type Grant = {
  id: string;
  organization: string | null;
  credits: number;
  reason: string | null;
  granted_by_email: string | null;
  balance_after: number | null;
  created_at: string;
};

function day(value: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? '—'
    : date.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: '2-digit' });
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Card carries="meaning" className="p-4">
      <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-saibyl-muted">
        {label}
      </div>
      <div className="mt-1.5 text-[24px] font-extrabold tracking-[-0.03em] text-saibyl-ink tabular-nums">
        {value}
      </div>
    </Card>
  );
}

export default function AdminPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [people, setPeople] = useState<Person[]>([]);
  const [grants, setGrants] = useState<Grant[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  /* The grant form. `target` is an organisation id, prefilled by clicking a
     row — typing a uuid by hand is how credits reach the wrong account. */
  const [target, setTarget] = useState('');
  const [targetName, setTargetName] = useState('');
  const [credits, setCredits] = useState('');
  const [reason, setReason] = useState('');
  const [granting, setGranting] = useState(false);
  const [granted, setGranted] = useState('');

  const load = useCallback(() => {
    Promise.all([
      api.get<Overview>('/admin/overview'),
      api.get<{ items: Person[] }>('/admin/people'),
      api.get<{ items: Grant[] }>('/admin/grants'),
    ])
      .then(([o, p, g]) => {
        setOverview(o.data);
        setPeople(p.data.items ?? []);
        setGrants(g.data.items ?? []);
        setError('');
      })
      .catch((err) =>
        setError(
          getErrorMessage(
            err,
            'We could not read the console. If this is a 404, ADMIN_ORGANIZATION_ID is unset or names a different organisation.',
          ),
        ),
      )
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const grant = async () => {
    if (granting) return;
    setGranted('');
    setGranting(true);
    try {
      const { data } = await api.post('/admin/credits', {
        organization_id: target,
        credits: Number(credits),
        reason,
      });
      setGranted(
        `${data.credits_granted.toLocaleString()} credits to ${data.organization}: ${data.balance_before.toLocaleString()} → ${data.balance_after.toLocaleString()}`,
      );
      setCredits('');
      setReason('');
      load();
    } catch (err) {
      setError(getErrorMessage(err, 'The grant did not go through.'));
    } finally {
      setGranting(false);
    }
  };

  const input =
    'w-full px-3 py-2 rounded-xl border border-saibyl-border-light bg-white text-[13px] text-saibyl-ink placeholder:text-saibyl-muted/70 outline-none focus:border-saibyl-blue focus:ring-2 focus:ring-saibyl-blue/20';

  return (
    <Ground className="min-h-full pb-24">
      <Longform>
        <Hero eyebrow="Console" title="How the business is" serif="actually doing">
          Every signup, what they hold, and what they have done with it. Granting
          credits here writes a record; doing it in the database does not.
        </Hero>

        {error && (
          <Notice tone="blocked" title="The console did not load">
            {error}
          </Notice>
        )}

        {loading && !error && (
          <p className="text-[13px] text-saibyl-muted">Reading…</p>
        )}

        {overview && (
          <Chapter kicker="At a glance" title={<>The <em>numbers</em></>}>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Stat label="People" value={overview.people.toLocaleString()} />
              <Stat label="Organisations" value={overview.organizations.toLocaleString()} />
              <Stat label="Revenue" value={`$${(overview.revenue_cents / 100).toFixed(2)}`} />
              <Stat label="Purchases" value={overview.purchases.toLocaleString()} />
              <Stat label="Website checks" value={overview.website_checks.toLocaleString()} />
              <Stat label="Runs" value={overview.runs.toLocaleString()} />
              <Stat label="Credits outstanding" value={overview.credits_outstanding.toLocaleString()} />
              <Stat label="Credits comped" value={overview.credits_comped.toLocaleString()} />
            </div>
          </Chapter>
        )}

        {people.length > 0 && (
          <Chapter
            kicker="Everyone"
            title={<>Who has <em>signed up</em></>}
            lead="Newest first. Click a row to aim the grant form at that account — typing a uuid by hand is how credits reach the wrong one."
          >
            <div className="overflow-x-auto">
              <table className="w-full text-[12.5px] border-collapse">
                <thead>
                  <tr className="text-left font-mono text-[10px] uppercase tracking-[0.14em] text-saibyl-muted">
                    <th className="py-2 pr-3 font-normal">Email</th>
                    <th className="py-2 pr-3 font-normal">Organisation</th>
                    <th className="py-2 pr-3 font-normal">Joined</th>
                    <th className="py-2 pr-3 font-normal">Last seen</th>
                    <th className="py-2 pr-3 font-normal text-right">Credits</th>
                    <th className="py-2 pr-3 font-normal text-right">Checks</th>
                    <th className="py-2 font-normal text-right">Runs</th>
                  </tr>
                </thead>
                <tbody>
                  {people.map((p) => (
                    <tr
                      key={p.user_id}
                      onClick={() => {
                        setTarget(p.organization_id ?? '');
                        setTargetName(p.organization ?? p.email ?? '');
                      }}
                      className={`border-t border-saibyl-border cursor-pointer hover:bg-saibyl-blue/[0.04] ${
                        target && target === p.organization_id ? 'bg-saibyl-blue/[0.07]' : ''
                      }`}
                    >
                      <td className="py-2 pr-3 text-saibyl-ink">{p.email}</td>
                      <td className="py-2 pr-3 text-saibyl-muted">{p.organization ?? '—'}</td>
                      <td className="py-2 pr-3 text-saibyl-muted">{day(p.signed_up_at)}</td>
                      <td className="py-2 pr-3 text-saibyl-muted">{day(p.last_sign_in_at)}</td>
                      <td className="py-2 pr-3 text-right tabular-nums">
                        {(p.credits_balance ?? 0).toLocaleString()}
                      </td>
                      <td className="py-2 pr-3 text-right tabular-nums">{p.checks}</td>
                      <td className="py-2 text-right tabular-nums">{p.runs}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Chapter>
        )}

        {overview && (
          <Chapter
            kicker="Grant"
            title={<>Give somebody <em>credits</em></>}
            lead="The reason is required, and it is the whole point: a grant nobody can explain in three months is the state this replaced."
          >
            <Reveal>
              <Card carries="stage" className="p-5 space-y-3 max-w-xl">
                <div>
                  <label className="block font-mono text-[10px] uppercase tracking-[0.14em] text-saibyl-muted mb-1">
                    Organisation
                  </label>
                  <input
                    className={input}
                    value={targetName || target}
                    onChange={(e) => {
                      setTarget(e.target.value);
                      setTargetName('');
                    }}
                    placeholder="Click a row above, or paste an organisation id"
                  />
                </div>
                <div className="flex gap-3">
                  <div className="w-40">
                    <label className="block font-mono text-[10px] uppercase tracking-[0.14em] text-saibyl-muted mb-1">
                      Credits
                    </label>
                    <input
                      className={input}
                      inputMode="numeric"
                      value={credits}
                      onChange={(e) => setCredits(e.target.value.replace(/[^0-9]/g, ''))}
                      placeholder="30000"
                    />
                  </div>
                  <div className="flex-1">
                    <label className="block font-mono text-[10px] uppercase tracking-[0.14em] text-saibyl-muted mb-1">
                      Reason
                    </label>
                    <input
                      className={input}
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      placeholder="Comped for a design partner"
                    />
                  </div>
                </div>

                {/* No `disabled`: the founder's rule. Either it runs, or it says
                    what is missing and stays pressable once that is fixed. */}
                {granting ? (
                  <Action as="span" aria-live="polite" className="text-[12.5px] opacity-80 pointer-events-none">
                    Granting…
                  </Action>
                ) : target && credits && reason.trim().length >= 3 ? (
                  <Action as="button" type="button" onClick={grant} className="text-[12.5px]">
                    Grant {Number(credits).toLocaleString()} credits
                  </Action>
                ) : (
                  <Notice tone="blocked" title="Not ready to grant">
                    Pick an organisation, an amount, and a reason of at least three
                    characters.
                  </Notice>
                )}

                {granted && (
                  <Notice tone="live" title="Granted">
                    {granted}
                  </Notice>
                )}
              </Card>
            </Reveal>
          </Chapter>
        )}

        {grants.length > 0 && (
          <Chapter
            kicker="History"
            title={<>What has been <em>given away</em></>}
            lead="Every comped grant, newest first — the answer to 'why does this account have these credits'."
          >
            <ul className="space-y-2">
              {grants.map((g) => (
                <Reveal key={g.id}>
                  <Card carries="meaning" className="p-3.5">
                    <div className="flex flex-wrap items-baseline gap-x-3 text-[12.5px]">
                      <span className="font-mono tabular-nums text-saibyl-blue">
                        +{g.credits.toLocaleString()}
                      </span>
                      <span className="text-saibyl-ink font-medium">{g.organization ?? '—'}</span>
                      <span className="text-saibyl-muted">{day(g.created_at)}</span>
                      {g.granted_by_email && (
                        <span className="text-saibyl-muted">by {g.granted_by_email}</span>
                      )}
                    </div>
                    {g.reason && (
                      <p className="mt-1 text-[12px] text-saibyl-muted">{g.reason}</p>
                    )}
                  </Card>
                </Reveal>
              ))}
            </ul>
          </Chapter>
        )}
      </Longform>
    </Ground>
  );
}
