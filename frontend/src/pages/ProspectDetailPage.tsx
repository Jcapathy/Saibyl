import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { formatDistanceToNow } from 'date-fns';
import { ArrowLeft, Loader2, Trash2, Users } from 'lucide-react';
import api from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { ANGLE_COPY, SCORE_COMPONENT_COPY, present, presentList } from '@/lib/gtm';
import { EvidenceList, Fact, FactList, SourceLink } from '@/components/gtm/Evidence';
import type { CandidateDeleteResult, CandidateDetail } from '@/types';

/**
 * One company, and everything Saibyl can defend about it.
 *
 * The order of this page is an argument. **Evidence comes before analysis**, and
 * neither is behind a disclosure triangle. The founder's question is not "how
 * good is this lead" — no number here can answer that — it is "why should I
 * believe any of this", and the answer is a quote and a link. A candidate whose
 * evidence a founder cannot see is a lead they cannot act on.
 *
 * `match_score` is never printed. The five `score_components` are shown, headed
 * as what put this company where it did in the list, with the basis stated
 * underneath: declared weights, no outcome data behind them, an ordering and not
 * a measurement. That is the most the number supports and it is offered as the
 * arithmetic rather than as a verdict.
 *
 * Fields no source stated are simply not on the page. There is no "Unknown"
 * row, because the true statement is that nobody said, and a dash in a table
 * cell reads as data.
 */

const cardClass = 'rounded-2xl border border-saibyl-border bg-white';

export default function ProspectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [candidate, setCandidate] = useState<CandidateDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [deleted, setDeleted] = useState<CandidateDeleteResult | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setLoading(true);
    setError('');
    api
      .get<CandidateDetail>(`/gtm/candidates/${id}`)
      .then(({ data }) => {
        if (!cancelled) setCandidate(data);
      })
      .catch((err) => {
        if (!cancelled) setError(getErrorMessage(err, 'We could not load this company.'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  async function remove() {
    if (!candidate) return;
    const hasPeople = candidate.contacts.length > 0;
    const warning = hasPeople
      ? `Delete ${candidate.company_name} and the ${candidate.contacts.length} named ${
          candidate.contacts.length === 1 ? 'person' : 'people'
        } saved with it? This cannot be undone.`
      : `Delete ${candidate.company_name}? This cannot be undone.`;
    if (!window.confirm(warning)) return;

    setDeleting(true);
    try {
      const { data } = await api.delete<CandidateDeleteResult>(`/gtm/candidates/${candidate.id}`);
      setDeleted(data);
    } catch (err) {
      setError(getErrorMessage(err, 'This company could not be deleted.'));
    } finally {
      setDeleting(false);
    }
  }

  if (loading) {
    return (
      <div className="p-6 max-w-3xl mx-auto space-y-4">
        <div className="h-8 w-56 rounded bg-[#14294a]/[0.05] animate-pulse" />
        <div className="h-40 rounded-2xl bg-[#14294a]/[0.04] animate-pulse" />
        <div className="h-64 rounded-2xl bg-[#14294a]/[0.04] animate-pulse" />
      </div>
    );
  }

  if (deleted) {
    return (
      <div className="p-6 max-w-3xl mx-auto">
        <div className={`${cardClass} p-6`}>
          <h1 className="text-[15px] font-medium text-saibyl-ink">
            {present(deleted.company_name) ?? 'That company'} has been deleted
          </h1>
          <p className="text-[12px] text-saibyl-silver mt-2 leading-relaxed">
            The record is gone, not hidden &mdash; the rows were deleted.
            {deleted.contacts_deleted > 0 && (
              <>
                {' '}
                {deleted.contacts_deleted} named{' '}
                {deleted.contacts_deleted === 1 ? 'person' : 'people'} saved against it{' '}
                {deleted.contacts_deleted === 1 ? 'was' : 'were'} deleted with it.
              </>
            )}
          </p>
          <Link
            to="/app/prospects"
            className="mt-4 inline-block text-[12px] text-saibyl-gold hover:underline"
          >
            Back to all companies
          </Link>
        </div>
      </div>
    );
  }

  if (error && !candidate) {
    return (
      <div className="p-6 max-w-3xl mx-auto">
        <div className="rounded-2xl border border-saibyl-negative/25 bg-saibyl-rose/[0.08] p-6">
          <p className="text-[13px] text-saibyl-negative leading-relaxed whitespace-pre-wrap">
            {error}
          </p>
          <Link
            to="/app/prospects"
            className="mt-4 inline-block text-[12px] text-saibyl-silver hover:text-saibyl-ink"
          >
            Back to all companies
          </Link>
        </div>
      </div>
    );
  }

  if (!candidate) return null;

  const oneLiner = present(candidate.one_liner);
  const domain = present(candidate.domain);
  const reasons = presentList(candidate.match_reasons);
  const angle = ANGLE_COPY[candidate.angle];
  const retrieved = new Date(candidate.retrieved_at);
  const validRetrieved = Number.isFinite(retrieved.getTime());

  // Sorted so the strongest contribution reads first. Zeros are kept rather
  // than dropped: "we found no overlap with the tools your buyers use" is a
  // fact about this company, and hiding it would leave the ordering unexplained.
  const components = Object.entries(candidate.score_components).sort((a, b) => b[1] - a[1]);

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-5">
      <div>
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="inline-flex items-center gap-1.5 text-[12px] text-saibyl-muted hover:text-saibyl-ink transition-colors mb-3"
        >
          <ArrowLeft className="w-3.5 h-3.5" /> Back
        </button>

        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="min-w-0">
            <h1 className="font-extrabold text-[22px] text-saibyl-ink">
              {candidate.company_name}
            </h1>
            {domain && (
              <p className="mt-1 text-[12px]">
                <SourceLink
                  url={domain.startsWith('http') ? domain : `https://${domain}`}
                  label={domain}
                />
              </p>
            )}
            {oneLiner && (
              <p className="text-[13px] text-saibyl-silver mt-2 leading-relaxed max-w-2xl">
                {oneLiner}
              </p>
            )}
          </div>

          <button
            type="button"
            onClick={remove}
            disabled={deleting}
            className="inline-flex items-center gap-1.5 rounded-lg border border-saibyl-border px-3 py-2 text-[12px] text-saibyl-silver hover:border-saibyl-negative/40 hover:text-saibyl-negative disabled:opacity-40 transition-colors shrink-0"
          >
            {deleting ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Trash2 className="w-3.5 h-3.5" />
            )}
            Delete
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-saibyl-negative/25 bg-saibyl-rose/[0.08] p-4">
          <p className="text-[12px] text-saibyl-negative whitespace-pre-wrap">{error}</p>
        </div>
      )}

      {/* ---- Where this came from. First, because it is what makes the rest
              worth reading. ---- */}
      <section className={`${cardClass} p-5`}>
        <h2 className="text-[13px] font-medium text-saibyl-ink">Where this came from</h2>
        <p className="text-[12px] mt-2">
          <SourceLink url={candidate.source_url} label={candidate.source_title} />
        </p>
        <p className="text-[11px] text-saibyl-muted mt-1.5">
          {validRetrieved ? (
            <span title={retrieved.toLocaleString()}>
              Read {formatDistanceToNow(retrieved, { addSuffix: true })}. Pages change &mdash;
              open it and check before you act on anything here.
            </span>
          ) : (
            'Open it and check before you act on anything here.'
          )}
        </p>
      </section>

      {/* ---- What a source actually said ---- */}
      <section className={`${cardClass} p-5`}>
        <h2 className="text-[13px] font-medium text-saibyl-ink">What the page said</h2>
        <p className="text-[11px] text-saibyl-muted mt-1 mb-3 leading-relaxed">
          Every line below was quoted from a page we retrieved, and checked to appear on it
          word for word. Anything we could not quote is not here at all &mdash; we would
          rather leave a gap than fill it in.
        </p>
        <EvidenceList evidence={candidate.evidence} />
      </section>

      {/* ---- The facts, each one of them evidenced above ---- */}
      {(present(candidate.industry) ||
        present(candidate.employee_count_range) ||
        present(candidate.hq_location) ||
        presentList(candidate.incumbent_tooling)) && (
        <section className={`${cardClass} p-5`}>
          <h2 className="text-[13px] font-medium text-saibyl-ink mb-3">The company</h2>
          <dl className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <Fact label="Industry" value={candidate.industry} />
            <Fact label="Size" value={candidate.employee_count_range} />
            <Fact label="Where" value={candidate.hq_location} />
          </dl>
          {presentList(candidate.incumbent_tooling) && (
            <dl className="mt-4">
              <FactList label="Already uses" values={candidate.incumbent_tooling} />
            </dl>
          )}
        </section>
      )}

      {/* ---- Why it was put in front of you ---- */}
      {reasons && (
        <section className={`${cardClass} p-5`}>
          <h2 className="text-[13px] font-medium text-saibyl-ink">Why we thought of you</h2>
          <ul className="mt-2.5 space-y-1.5">
            {reasons.map((reason) => (
              <li key={reason} className="text-[12px] text-saibyl-silver leading-relaxed">
                &mdash; {reason}
              </li>
            ))}
          </ul>
          <p className="text-[10px] text-saibyl-muted mt-3 leading-relaxed">
            These are claims, not findings. Check them against the quotes above.
          </p>
        </section>
      )}

      {/* ---- The ordering, explained rather than scored ---- */}
      {components.length > 0 && (
        <section className={`${cardClass} p-5`}>
          <h2 className="text-[13px] font-medium text-saibyl-ink">
            Why it sits where it does in your list
          </h2>
          <p className="text-[11px] text-saibyl-muted mt-1 mb-3.5 leading-relaxed">
            We put companies in an order so you know which to open first. These are the
            things that decided it. This is an <strong className="text-saibyl-silver">order</strong>,
            not a score &mdash; it says look at this one before that one, and nothing about
            how likely they are to buy. Nobody has measured that yet.
          </p>
          <ul className="space-y-2.5">
            {components.map(([name, value]) => {
              const zero = value <= 0;
              return (
                <li key={name}>
                  <p
                    className={`text-[12px] ${zero ? 'text-saibyl-muted' : 'text-saibyl-ink'}`}
                  >
                    {SCORE_COMPONENT_COPY[name] ?? name.replace(/_/g, ' ')}
                    {zero && <span className="text-saibyl-muted"> &mdash; nothing matched</span>}
                  </p>
                  {!zero && (
                    <div className="mt-1 h-1 rounded-full bg-[#14294a]/[0.06] overflow-hidden">
                      <div
                        className="h-full rounded-full bg-saibyl-violet/60"
                        style={{ width: `${Math.min(100, Math.max(0, value * 100))}%` }}
                      />
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {/* ---- People. Only ever here when the org opted in. ---- */}
      {candidate.contacts.length > 0 && (
        <section className={`${cardClass} p-5`}>
          <h2 className="flex items-center gap-2 text-[13px] font-medium text-saibyl-ink">
            <Users className="w-3.5 h-3.5 text-saibyl-silver" />
            People at this company
          </h2>
          <p className="text-[11px] text-saibyl-muted mt-1 mb-3 leading-relaxed">
            Public professional information only &mdash; name, role, employer, and a public
            profile page. No email addresses and no phone numbers are collected or stored.
            Each one names the page it came from and when it was read.
          </p>
          <ul className="space-y-2">
            {candidate.contacts.map((contact) => (
              <li
                key={contact.id}
                className="rounded-xl border border-saibyl-border bg-saibyl-elevated p-3.5"
              >
                <p className="text-[13px] text-saibyl-ink">{contact.full_name}</p>
                {(present(contact.role_title) || present(contact.employer)) && (
                  <p className="text-[12px] text-saibyl-silver mt-0.5">
                    {[present(contact.role_title), present(contact.employer)]
                      .filter(Boolean)
                      .join(' · ')}
                  </p>
                )}
                <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px]">
                  {contact.public_profile_url && (
                    <SourceLink url={contact.public_profile_url} label="Public profile" />
                  )}
                  <SourceLink url={contact.source_url} label="Where we found them" />
                  <span className="text-saibyl-muted">
                    read{' '}
                    {Number.isFinite(new Date(contact.retrieved_at).getTime())
                      ? formatDistanceToNow(new Date(contact.retrieved_at), { addSuffix: true })
                      : 'at an unrecorded time'}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* ---- Traceability back to the audience and the search ---- */}
      <section className={`${cardClass} p-5`}>
        <h2 className="text-[13px] font-medium text-saibyl-ink mb-3">How we found them</h2>
        <dl className="space-y-3">
          <Fact label="Matched this kind of buyer" value={candidate.archetype_label} />
          {angle && <Fact label="By looking for" value={angle.label} />}
          {present(candidate.query) && (
            <div>
              <dt className="text-[10px] uppercase tracking-widest text-saibyl-muted">
                The search we ran
              </dt>
              <dd className="mt-0.5 font-mono text-[12px] text-saibyl-ink break-words">
                {candidate.query}
              </dd>
            </div>
          )}
        </dl>
        <Link
          to={`/app/prospects?discovery_run_id=${candidate.discovery_run_id}`}
          className="mt-3.5 inline-block text-[12px] text-saibyl-gold hover:underline"
        >
          See everything that search found
        </Link>
      </section>
    </div>
  );
}
