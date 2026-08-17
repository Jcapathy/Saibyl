import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { AxiosError } from 'axios';
import { AlertTriangle, ArrowLeft, Check, Loader2, ShieldAlert, Trash2 } from 'lucide-react';
import api from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import type { GtmPurgeResult, GtmSettings, GtmSettingsUpdate } from '@/types';

/**
 * The two decisions about personal data, made deliberately.
 *
 * **The gate is not a feature flag.** `privacy.py` spells out what it separates:
 * with it off, discovery finds companies, and a company name with a headcount
 * band is not personal data. With it on, discovery finds *named people*, and a
 * name paired with a job title and an employer is — which makes Saibyl the
 * controller of records about people who never signed up for anything. That is a
 * different legal position, not a fuller product tier, and the founder turning
 * it on is the one taking it on. So enabling is a two-step act with the
 * consequence written out; disabling is a single click, because nothing should
 * ever stand between somebody and stopping collection.
 *
 * **A failed read is not "off".** `GET /gtm/settings` answers 503 rather than
 * `false` when it cannot read the column, precisely so a UI cannot show "off" to
 * an org that had turned it on. That 503 gets its own panel here saying the
 * setting is unknown, and the controls are withheld rather than defaulted.
 *
 * **Turning it off is not deletion, and the page says so.** Off stops future
 * collection; what was already collected stays until it is purged. Conflating
 * the two would mean a founder who wanted records gone had no way to say so
 * without also changing a setting — and one who only wanted to stop collecting
 * would silently destroy records they still needed.
 */

const cardClass = 'rounded-2xl border border-saibyl-border bg-white';
const PURGE_PHRASE = 'DELETE';

export default function ProspectSettingsPage() {
  const [settings, setSettings] = useState<GtmSettings | null>(null);
  const [loading, setLoading] = useState(true);
  /** Set only on a 503 — the setting could not be read, which is not "off". */
  const [unreadable, setUnreadable] = useState('');
  const [loadError, setLoadError] = useState('');

  const [confirmingEnable, setConfirmingEnable] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');

  const [purgePhrase, setPurgePhrase] = useState('');
  const [purging, setPurging] = useState(false);
  const [purgeError, setPurgeError] = useState('');
  const [purged, setPurged] = useState<GtmPurgeResult | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .get<GtmSettings>('/gtm/settings')
      .then(({ data }) => {
        if (!cancelled) setSettings(data);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof AxiosError && err.response?.status === 503) {
          setUnreadable(
            getErrorMessage(err, 'The contact setting could not be read right now.'),
          );
          return;
        }
        setLoadError(getErrorMessage(err, 'We could not load your data settings.'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function setEnabled(enabled: boolean) {
    setSaving(true);
    setSaveError('');
    try {
      const { data } = await api.patch<GtmSettingsUpdate>('/gtm/settings', { enabled });
      // Adopt what came back rather than what was sent: the server is the only
      // authority on what the setting now is.
      setSettings((prev) =>
        prev
          ? { ...prev, contact_discovery_enabled: data.contact_discovery_enabled }
          : prev,
      );
      setConfirmingEnable(false);
      setAcknowledged(false);
    } catch (err) {
      setSaveError(getErrorMessage(err, 'That setting could not be changed.'));
    } finally {
      setSaving(false);
    }
  }

  async function purge() {
    setPurging(true);
    setPurgeError('');
    try {
      const { data } = await api.post<GtmPurgeResult>('/gtm/purge', { confirm: true });
      setPurged(data);
      setPurgePhrase('');
    } catch (err) {
      setPurgeError(getErrorMessage(err, 'Nothing was deleted.'));
    } finally {
      setPurging(false);
    }
  }

  const enabled = settings?.contact_discovery_enabled ?? false;

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-5">
      <div>
        <Link
          to="/app/prospects"
          className="inline-flex items-center gap-1.5 text-[12px] text-saibyl-muted hover:text-saibyl-ink transition-colors mb-3"
        >
          <ArrowLeft className="w-3.5 h-3.5" /> All companies
        </Link>
        <h1 className="font-extrabold text-[22px] text-saibyl-ink">Data settings</h1>
        <p className="text-[13px] text-saibyl-silver mt-1.5 leading-relaxed max-w-2xl">
          What Saibyl is allowed to collect when it searches for companies, and how to
          delete what it has collected.
        </p>
      </div>

      {loading ? (
        <div className="h-56 rounded-2xl bg-[#14294a]/[0.04] animate-pulse" />
      ) : unreadable ? (
        /* A 503. Deliberately not rendered as "off" — the org may well have this
           on, and showing a switch in the off position would be a lie the
           founder would act on. */
        <section className="rounded-2xl border border-[#F59E0B]/30 bg-[#F59E0B]/[0.06] p-5">
          <p className="flex items-center gap-2 text-[13px] font-medium text-saibyl-warning">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            We cannot tell you what this is set to
          </p>
          <p className="text-[12px] text-saibyl-silver mt-2 leading-relaxed">
            The setting could not be read just now. We are not showing you a switch,
            because we would have to guess which way it points &mdash; and guessing
            &ldquo;off&rdquo; at a setting that is actually on is exactly the mistake worth
            avoiding here. Reload in a moment.
          </p>
          <p className="mt-2.5 rounded-lg bg-[#14294a]/[0.04] px-3 py-2 font-mono text-[11px] text-saibyl-silver break-words">
            {unreadable}
          </p>
        </section>
      ) : loadError ? (
        <div className="rounded-2xl border border-saibyl-negative/25 bg-saibyl-rose/[0.08] p-5">
          <p className="text-[12px] text-saibyl-negative leading-relaxed whitespace-pre-wrap">
            {loadError}
          </p>
        </div>
      ) : (
        settings && (
          <section className={`${cardClass} p-5`}>
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <h2 className="text-[14px] font-medium text-saibyl-ink">
                  Also find named people at these companies
                </h2>
                <p className="text-[12px] text-saibyl-silver mt-1.5 leading-relaxed">
                  {/* The server writes this sentence so the policy lives in one
                      place rather than being re-stated by every client. */}
                  {settings.note}
                </p>
              </div>
              <span
                className={`shrink-0 rounded-full px-3 py-1 text-[11px] font-medium ${
                  enabled
                    ? 'bg-saibyl-green/10 text-saibyl-positive'
                    : 'bg-[#14294a]/[0.05] text-saibyl-silver'
                }`}
              >
                {enabled ? 'On' : 'Off'}
              </span>
            </div>

            {saveError && (
              <p className="mt-3 rounded-lg border border-saibyl-negative/25 bg-saibyl-rose/[0.08] px-3 py-2 text-[12px] text-saibyl-negative">
                {saveError}
              </p>
            )}

            {enabled ? (
              <div className="mt-4 space-y-3">
                <div className="rounded-xl border border-saibyl-border bg-saibyl-elevated p-4">
                  <p className="text-[12px] text-saibyl-ink">While this is on</p>
                  <ul className="mt-2 space-y-1.5 text-[11px] text-saibyl-silver leading-relaxed">
                    <li>
                      &mdash; Saibyl stores names, job titles and employers of real people,
                      each with the public page it came from and when it was read.
                    </li>
                    <li>
                      &mdash; It never collects email addresses, phone numbers or postal
                      addresses, and it skips sites whose terms forbid this.
                    </li>
                    <li>
                      &mdash; You are responsible for those records. If one of those people
                      asks what you hold about them, or asks you to delete it, you need to
                      be able to answer.
                    </li>
                  </ul>
                </div>
                <button
                  type="button"
                  onClick={() => setEnabled(false)}
                  disabled={saving}
                  className="inline-flex items-center gap-2 rounded-lg border border-saibyl-border px-4 py-2 text-[12px] text-saibyl-silver hover:text-saibyl-ink hover:bg-[#14294a]/[0.04] disabled:opacity-40 transition-colors"
                >
                  {saving && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  Stop collecting people
                </button>
                <p className="text-[11px] text-saibyl-muted leading-relaxed">
                  Turning this off stops future collection. It does not delete what has
                  already been collected &mdash; that is the separate, irreversible action
                  below.
                </p>
              </div>
            ) : !confirmingEnable ? (
              <div className="mt-4">
                <button
                  type="button"
                  onClick={() => setConfirmingEnable(true)}
                  className="rounded-lg border border-saibyl-border px-4 py-2 text-[12px] text-saibyl-silver hover:text-saibyl-ink hover:bg-[#14294a]/[0.04] transition-colors"
                >
                  Turn this on&hellip;
                </button>
                <p className="text-[11px] text-saibyl-muted mt-2.5 leading-relaxed">
                  Finding companies works with this off, and finds exactly as much. This
                  only adds named people to those same companies.
                </p>
              </div>
            ) : (
              /* Not a bare toggle. What changes is a legal position, and the
                 person clicking is the one it changes for. */
              <div className="mt-4 rounded-xl border border-[#F59E0B]/30 bg-[#F59E0B]/[0.06] p-4">
                <p className="flex items-center gap-2 text-[12px] font-medium text-saibyl-warning">
                  <ShieldAlert className="w-4 h-4 shrink-0" />
                  Read this before you turn it on
                </p>
                <div className="mt-2.5 space-y-2 text-[12px] text-saibyl-silver leading-relaxed">
                  <p>
                    Saibyl will start storing information about <strong>real, named
                    people</strong> &mdash; their name, their job title, their employer, and
                    a link to a public professional page. Only that. Never an email address,
                    a phone number or a home address.
                  </p>
                  <p>
                    That information is personal data. In most places, including the UK, the
                    EU and California, storing it comes with obligations: you need a reason
                    to hold it, and if one of those people asks you what you have about them
                    or asks you to delete it, you have to be able to do that. Every record
                    Saibyl saves keeps the page it came from and the time it was read, so
                    you can answer.
                  </p>
                  <p className="text-saibyl-muted">
                    You do not need this to find companies. Company discovery is complete
                    without it.
                  </p>
                </div>

                <label className="mt-3.5 flex items-start gap-2.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={acknowledged}
                    onChange={(e) => setAcknowledged(e.target.checked)}
                    className="mt-0.5 w-3.5 h-3.5 accent-[#286cf0] cursor-pointer shrink-0"
                  />
                  <span className="text-[12px] text-saibyl-ink leading-relaxed">
                    I understand this stores information about named people, and that I am
                    responsible for it.
                  </span>
                </label>

                <div className="mt-3.5 flex items-center gap-4">
                  <button
                    type="button"
                    onClick={() => setEnabled(true)}
                    disabled={!acknowledged || saving}
                    className="inline-flex items-center gap-2 rounded-lg bg-saibyl-gold px-4 py-2 text-[12px] font-semibold text-white hover:bg-saibyl-gold-hover disabled:opacity-40 transition-colors"
                  >
                    {saving ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Check className="w-3.5 h-3.5" />
                    )}
                    Turn on people discovery
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setConfirmingEnable(false);
                      setAcknowledged(false);
                    }}
                    disabled={saving}
                    className="text-[12px] text-saibyl-silver hover:text-saibyl-ink disabled:opacity-40 transition-colors"
                  >
                    Leave it off
                  </button>
                </div>
              </div>
            )}
          </section>
        )
      )}

      {/* ---- Purge ---- */}
      <section className="rounded-2xl border border-saibyl-negative/25 bg-saibyl-rose/[0.05] p-5">
        <h2 className="flex items-center gap-2 text-[14px] font-medium text-saibyl-ink">
          <Trash2 className="w-4 h-4 text-saibyl-negative" />
          Delete every company and person
        </h2>
        <p className="text-[12px] text-saibyl-silver mt-2 leading-relaxed">
          Deletes every company Saibyl has found for you and every named person saved with
          them. The rows are deleted, not hidden or flagged &mdash; there is nothing to
          restore afterwards and no undo.
        </p>
        <p className="text-[11px] text-saibyl-muted mt-2 leading-relaxed">
          Your searches themselves are kept: they record what each one cost and how many
          searches it ran, which is your billing record, and none of it is information about
          anybody.
        </p>

        {purged ? (
          <div className="mt-4 rounded-xl border border-saibyl-border bg-saibyl-elevated p-4">
            <p className="flex items-center gap-2 text-[12px] font-medium text-saibyl-ink">
              <Check className="w-3.5 h-3.5 text-saibyl-positive" />
              Deleted
            </p>
            {/* Exactly what went, from the server's own count. */}
            <p className="text-[12px] text-saibyl-silver mt-1.5 leading-relaxed">
              {purged.candidates_deleted}{' '}
              {purged.candidates_deleted === 1 ? 'company' : 'companies'} and{' '}
              {purged.contacts_deleted}{' '}
              {purged.contacts_deleted === 1 ? 'named person' : 'named people'} were deleted.
              {purged.candidates_deleted === 0 && purged.contacts_deleted === 0 && (
                <> There was nothing stored to delete.</>
              )}
            </p>
          </div>
        ) : (
          <div className="mt-4 space-y-3">
            {purgeError && (
              <p className="rounded-lg border border-saibyl-negative/25 bg-saibyl-rose/[0.08] px-3 py-2 text-[12px] text-saibyl-negative">
                {purgeError}
              </p>
            )}
            <label className="block">
              <span className="block text-[12px] text-saibyl-silver mb-1.5">
                Type <span className="font-mono text-saibyl-ink">{PURGE_PHRASE}</span> to
                confirm
              </span>
              <input
                type="text"
                value={purgePhrase}
                onChange={(e) => setPurgePhrase(e.target.value)}
                autoComplete="off"
                className="w-48 rounded-lg border border-saibyl-border-light bg-white px-3 py-2 font-mono text-[13px] text-saibyl-ink placeholder:text-saibyl-muted/70 focus:outline-none focus:border-saibyl-negative focus:ring-2 focus:ring-saibyl-negative/20"
              />
            </label>
            <button
              type="button"
              onClick={purge}
              disabled={purgePhrase !== PURGE_PHRASE || purging}
              className="inline-flex items-center gap-2 rounded-lg bg-saibyl-negative px-4 py-2 text-[12px] font-semibold text-white hover:opacity-90 disabled:opacity-30 transition-opacity"
            >
              {purging ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Trash2 className="w-3.5 h-3.5" />
              )}
              Delete everything, permanently
            </button>
          </div>
        )}
      </section>
    </div>
  );
}
