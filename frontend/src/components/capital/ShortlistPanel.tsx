import { useCallback, useEffect, useRef, useState } from 'react';
import type { CSSProperties } from 'react';
import { AxiosError } from 'axios';
import { Link } from 'react-router-dom';

import api from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { Guarded } from '@/components/stages/StagePrimitives';
import PriceTag from '@/components/billing/PriceTag';
import { usePrices } from '@/lib/prices';
import {
  countedDimensions,
  formatDay,
  money,
  DIMENSION_SHORT,
  NO_CONTACT_DETAILS,
  STAGE_CHOICES,
  type CapitalShortlist,
  type ShortlistEntry,
} from '@/lib/capital';
import FirmRecord from './FirmRecord';
import {
  CalmNotice,
  MonoLabel,
  ReasonBlock,
  Withheld,
} from './CapitalPrimitives';

/**
 * The matched shortlist — the thing a founder actually buys.
 *
 * The list is not the product; the matching is. Anyone can buy a list of
 * family offices. What Saibyl has that a list vendor does not is the measured
 * evidence about this founder — the objections real buyers raised, ranked by
 * what costs deals — so every recommendation here carries both sides' actual
 * language and can be checked against two pages in ten seconds.
 *
 * Three things on this panel are load-bearing rather than decorative, and all
 * three are the parts a padded list would have removed:
 *
 *   **Refusals are shown.** A firm that publishes a stage range this founder
 *   is not in is reported quoting its own words, never dropped and never
 *   replaced with a firm that would have said the same thing on the call.
 *
 *   **Withheld records are counted and named.** A record past its verification
 *   date is not matched against and not shown as current — but a founder told
 *   "we hold three more and will not stand behind them" can go and check them.
 *
 *   **The denominator is printed.** Four matches out of forty records read
 *   differently from four out of four, and only one of those is a finding
 *   about the company rather than about the bank.
 *
 * Charged at create, like every other paid artifact here. The backend refuses
 * before it charges — empty bank first, then balance — so a click against an
 * unseeded bank costs nothing.
 */

const POLL_MS = 4000;

/** Stagger cap: past this the arrival is a wait rather than a flourish. */
const MAX_STAGGER = 8;

const inputBase =
  'w-full rounded-xl bg-white border border-saibyl-border-light px-3 py-2.5 text-[13.5px] text-saibyl-ink placeholder:text-saibyl-muted/70 focus:outline-none focus:border-saibyl-blue focus:ring-2 focus:ring-saibyl-blue/20';

interface PanelError {
  message: string;
  /** A credit shortfall — the one error that carries a way to fix it. */
  billing: boolean;
  /** The product working correctly and saying no. Never red. */
  calm: boolean;
}

export default function ShortlistPanel({
  product,
  runId,
  bankCurrent,
  bankWithheld,
  now,
}: {
  product: { id: string; name: string };
  /** The run whose measured objections build the bridge, or null. */
  runId: string | null;
  /** Current records in the whole bank, unfiltered. Null when unread. */
  bankCurrent: number | null;
  bankWithheld: number;
  now: Date;
}) {
  const prices = usePrices();
  const [shortlist, setShortlist] = useState<CapitalShortlist | null>(null);
  const [loading, setLoading] = useState(true);
  const [building, setBuilding] = useState(false);
  const [error, setError] = useState<PanelError | null>(null);
  const timer = useRef<number | null>(null);

  const [sector, setSector] = useState('');
  const [stage, setStage] = useState(STAGE_CHOICES[1]);
  const [checkSize, setCheckSize] = useState('');
  const [geography, setGeography] = useState('');
  const [material, setMaterial] = useState('');

  /* ── What is already there ──
     A 404 is the ordinary state before the first build, not a failure. */
  const load = useCallback(
    async (quiet = false) => {
      try {
        const { data } = await api.get<CapitalShortlist>(
          `/capital/shortlist/by-project/${product.id}`,
        );
        setShortlist(data);
      } catch (err) {
        const status = err instanceof AxiosError ? err.response?.status : undefined;
        if (status === 404) {
          setShortlist(null);
        } else if (!quiet) {
          setError({
            message: getErrorMessage(err, 'We could not load your shortlist.'),
            billing: false,
            calm: false,
          });
        }
      } finally {
        if (!quiet) setLoading(false);
      }
    },
    [product.id],
  );

  /* The page remounts this panel per product (`key`), so there is no stale
     state to reset here — a shortlist for one product can never be left on
     screen under another product's name. */
  useEffect(() => {
    void load();
  }, [load]);

  useEffect(
    () => () => {
      if (timer.current) window.clearTimeout(timer.current);
    },
    [],
  );

  /* ── Poll only while there is something to wait for ──
     The match itself is deterministic and runs inside the request, so this
     fires only in the one case the write-back did not come home: the row
     stays `building` and the founder would otherwise be looking at a
     half-finished artifact with no ending. */
  useEffect(() => {
    if (!shortlist || shortlist.status !== 'building') return;
    const id = shortlist.id;
    timer.current = window.setTimeout(() => {
      api
        .get<CapitalShortlist>(`/capital/shortlist/${id}`)
        .then(({ data }) => setShortlist(data))
        .catch(() => {
          /* One missed poll is not a failed build — the next tick tries. */
        });
    }, POLL_MS);
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [shortlist]);

  async function build() {
    setBuilding(true);
    setError(null);
    const needed = Number(checkSize.replace(/[^0-9]/g, ''));
    try {
      const { data } = await api.post<CapitalShortlist>('/capital/shortlist', {
        project_id: product.id,
        sector: sector.trim(),
        stage,
        check_size_needed: needed > 0 ? needed : null,
        geography: geography.trim() || null,
        material: material.trim(),
        simulation_id: runId,
      });
      setShortlist(data);
    } catch (err) {
      const status = err instanceof AxiosError ? err.response?.status : undefined;
      setError({
        message: getErrorMessage(err, 'We could not build your shortlist.'),
        // 402 is a credit shortfall, and the only error with a control.
        billing: status === 402,
        // 409 is an empty bank; 422 is a description we will not store. Both
        // are the product working correctly, so neither is rendered as a fault.
        calm: status === 409 || status === 422,
      });
    } finally {
      setBuilding(false);
    }
  }

  const complete = shortlist?.status === 'complete';
  const bankEmpty = bankCurrent === 0;

  /* Never a grey button: if it cannot run, the reason replaces it. */
  const blockedBy = bankEmpty
    ? {
        reason:
          'There is no current record in the bank to match against yet' +
          (bankWithheld > 0
            ? `, and ${bankWithheld} of the records we hold are past their verification date. We will not match against those.`
            : '. Nothing is charged until there is something to match.'),
      }
    : !sector.trim()
      ? {
          reason:
            'Tell us the sector you are in and we will match the bank against it — a few words is enough.',
        }
      : null;

  return (
    <section className="space-y-5">
      {/* ── What is already built ── */}
      {loading ? (
        <p className="text-[12.5px] text-saibyl-muted" aria-live="polite">
          Looking for a shortlist you have already built&hellip;
        </p>
      ) : (
        shortlist && (
          <>
            {shortlist.status === 'building' && (
              <p className="text-[13px] text-saibyl-silver" aria-live="polite">
                Matching the bank against what we know about {product.name}&hellip;
              </p>
            )}
            {shortlist.status === 'failed' && (
              <div className="rounded-xl border border-saibyl-negative/25 bg-saibyl-negative/[0.07] p-4">
                <p className="text-[13px] text-saibyl-negative leading-relaxed">
                  {shortlist.error_message ??
                    'This build did not finish, and nothing was matched.'}
                </p>
                <p className="font-mono text-[11px] tabular-nums text-saibyl-muted mt-2">
                  {shortlist.credits_charged.toLocaleString()} credits were
                  charged when it started &middot; {formatDay(shortlist.created_at)}
                </p>
              </div>
            )}
            {complete && <Result shortlist={shortlist} product={product} now={now} />}
          </>
        )
      )}

      {/* ── Build one, or build another ── */}
      <div className="rounded-2xl border border-saibyl-border bg-white p-5 space-y-4 capital-card">
        <div>
          <MonoLabel>{complete ? 'Ask again' : 'The question'}</MonoLabel>
          <h2 className="text-[15px] font-semibold text-saibyl-ink mt-1.5">
            {complete
              ? 'Match again with different numbers'
              : 'Who would fund this one'}
          </h2>
          <p className="text-[12.5px] text-saibyl-muted mt-1.5 leading-relaxed max-w-2xl">
            {complete
              ? 'A second match is a second answer and is charged again. Your last one stays where it is.'
              : 'The sector and the stage are the ordinary filter. What makes this more than a filter is everything else we already measured about ' +
                product.name +
                '.'}
          </p>
        </div>

        {/* What this match inherits — declared before any credits move. */}
        {runId ? (
          <p className="text-[12.5px] text-saibyl-silver leading-relaxed">
            This reads the objections measured in your last run of{' '}
            <Link
              to={`/app/products/${product.id}/reactions`}
              className="text-saibyl-blue hover:underline"
            >
              {product.name}
            </Link>
            . A firm whose published thesis names the thing buyers keep pushing
            back on is a materially better match than a generic investor, and we
            can show you why in their words and in yours.
          </p>
        ) : (
          <CalmNotice headline="No room has reacted to this yet">
            <p>
              The match will use the sector, the stage and what you write below.
              It will have no objection bridge &mdash; which is the strongest
              signal here and the one no list vendor can produce.
            </p>
            <p>
              <Link
                to={`/app/products/${product.id}/reactions`}
                className="text-saibyl-blue hover:underline font-medium"
              >
                Put it in front of a room first
              </Link>{' '}
              if you would rather have it.
            </p>
          </CalmNotice>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label
              htmlFor="capital-sector"
              className="block text-[12.5px] text-saibyl-silver mb-1.5"
            >
              What sector are you in?
            </label>
            <input
              id="capital-sector"
              value={sector}
              onChange={(e) => setSector(e.target.value)}
              placeholder="e.g. clinical software, energy storage"
              className={inputBase}
            />
          </div>
          <div>
            <label
              htmlFor="capital-stage"
              className="block text-[12.5px] text-saibyl-silver mb-1.5"
            >
              Where are you raising?
            </label>
            <select
              id="capital-stage"
              value={stage}
              onChange={(e) => setStage(e.target.value)}
              className={inputBase}
              style={{ colorScheme: 'light' }}
            >
              {STAGE_CHOICES.map((choice) => (
                <option key={choice} value={choice}>
                  {choice}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label
              htmlFor="capital-cheque"
              className="block text-[12.5px] text-saibyl-silver mb-1.5"
            >
              How much do you need?{' '}
              <span className="text-saibyl-muted">Optional</span>
            </label>
            <input
              id="capital-cheque"
              inputMode="numeric"
              value={checkSize}
              onChange={(e) => setCheckSize(e.target.value)}
              placeholder="750000"
              className={`${inputBase} font-mono tabular-nums`}
            />
            <p className="text-[11px] text-saibyl-muted mt-1 leading-relaxed">
              A firm that publishes a range you fall outside is reported as a
              refusal quoting that range, rather than left off.
            </p>
          </div>
          <div>
            <label
              htmlFor="capital-geography"
              className="block text-[12.5px] text-saibyl-silver mb-1.5"
            >
              Where are you? <span className="text-saibyl-muted">Optional</span>
            </label>
            <input
              id="capital-geography"
              value={geography}
              onChange={(e) => setGeography(e.target.value)}
              placeholder="e.g. Texas, the UK, the Nordics"
              className={inputBase}
            />
          </div>
        </div>

        <div>
          <label
            htmlFor="capital-material"
            className="block text-[12.5px] text-saibyl-silver mb-1.5"
          >
            In your own words, what is this?
          </label>
          <textarea
            id="capital-material"
            rows={4}
            value={material}
            onChange={(e) => setMaterial(e.target.value)}
            placeholder="A paragraph is enough. Your sentences are what gets quoted back to you next to theirs."
            className={`${inputBase} resize-y`}
          />
          <p className="text-[11px] text-saibyl-muted mt-1 leading-relaxed">
            {runId
              ? 'When your last run carries its own description, that is what the match reads and this is the fallback. '
              : ''}
            Leave out any email address or phone number &mdash; these sentences
            are stored on the shortlist, and Saibyl does not keep personal
            contact details anywhere.
          </p>
        </div>

        {error && (
          error.calm ? (
            <CalmNotice headline={error.message} />
          ) : (
            <div className="rounded-xl border border-saibyl-negative/25 bg-saibyl-negative/[0.07] p-4">
              <p className="text-[13px] text-saibyl-negative leading-relaxed">
                {error.message}
              </p>
              {error.billing && (
                <Link
                  to="/app/settings"
                  className="inline-block mt-2.5 text-[12px] font-semibold text-saibyl-blue hover:underline"
                >
                  Add credits
                </Link>
              )}
            </div>
          )
        )}

        <PriceTag entry={prices?.capital_shortlist} />

        <Guarded
          label={complete ? 'Match again' : 'Find who would fund this'}
          onClick={build}
          blockedBy={blockedBy}
          busy={building}
          busyLabel="Matching the bank…"
        />

        <p className="text-[11px] text-saibyl-muted leading-relaxed">
          {NO_CONTACT_DETAILS}
        </p>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/*  The answer                                                         */
/* ------------------------------------------------------------------ */

function Result({
  shortlist,
  product,
  now,
}: {
  shortlist: CapitalShortlist;
  product: { id: string; name: string };
  now: Date;
}) {
  /* The denominator sits beside the numerator on purpose: four matches out of
     forty records read differently from four out of four, and only one of
     those is a finding about the company rather than about the bank. */
  const stats: [string, string][] = [
    ['Matched', shortlist.matches_count.toLocaleString()],
    ['Ruled you out', shortlist.refusals_count.toLocaleString()],
    ['Withheld', shortlist.withheld_stale.length.toLocaleString()],
    ['Records read', shortlist.firms_considered.toLocaleString()],
  ];

  return (
    <div className="space-y-5">
      <div className="rounded-2xl border border-saibyl-border bg-white p-5 capital-hero">
        <MonoLabel>The answer, as of {formatDay(shortlist.as_of)}</MonoLabel>
        <h2 className="text-[17px] font-semibold text-saibyl-ink mt-1.5">
          Who would fund {product.name}
        </h2>
        <p className="text-[12.5px] text-saibyl-muted mt-1 leading-relaxed">
          {shortlist.sector} &middot; {shortlist.stage}
          {typeof shortlist.check_size_needed === 'number' && (
            <> &middot; {money(shortlist.check_size_needed)} needed</>
          )}
          {shortlist.simulation_id
            ? ' · matched against the objections your last room actually raised'
            : ' · matched on what you wrote, with no room behind it'}
        </p>

        <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4">
          {stats.map(([label, value]) => (
            <div
              key={label}
              className="rounded-xl border border-saibyl-border bg-saibyl-elevated px-3 py-2.5"
            >
              <dt className="font-mono text-[9.5px] uppercase tracking-[0.14em] text-saibyl-muted">
                {label}
              </dt>
              <dd className="font-mono tabular-nums text-[18px] text-saibyl-ink mt-0.5">
                {value}
              </dd>
            </div>
          ))}
        </dl>

        <p className="font-mono text-[10.5px] tabular-nums text-saibyl-muted mt-3">
          {shortlist.credits_charged.toLocaleString()} credits &middot; built{' '}
          {formatDay(shortlist.completed_at ?? shortlist.created_at)}
        </p>

        {shortlist.notes.length > 0 && (
          <ul className="mt-3 space-y-1.5">
            {shortlist.notes.map((note) => (
              <li
                key={note}
                className="text-[12px] text-saibyl-silver leading-relaxed border-l-2 border-saibyl-border-light pl-2.5"
              >
                {note}
              </li>
            ))}
          </ul>
        )}
      </div>

      {shortlist.matches.length > 0 && (
        <div className="space-y-3">
          <div>
            <MonoLabel>Worth your week</MonoLabel>
            <p className="text-[12px] text-saibyl-muted mt-1 leading-relaxed max-w-2xl">
              Ordered by how much of your evidence each firm&rsquo;s published
              position actually meets. The order is the only thing the score
              does &mdash; nothing here is hidden by it.
            </p>
          </div>
          {shortlist.matches.map((entry, index) => (
            <div
              key={`${entry.firm.firm_name}-${entry.firm.source_url}`}
              className="capital-arrive"
              style={{ '--i': Math.min(index, MAX_STAGGER) } as CSSProperties}
            >
              <Entry entry={entry} now={now} />
            </div>
          ))}
        </div>
      )}

      {shortlist.refusals.length > 0 && (
        <div className="space-y-3">
          <div>
            <MonoLabel>They publish a position that rules you out</MonoLabel>
            <p className="text-[12px] text-saibyl-muted mt-1 leading-relaxed max-w-2xl">
              Reported rather than dropped, quoting what they state. A list
              padded back to length with firms that would have said this on the
              call is worth less than a short list that says it now.
            </p>
          </div>
          {shortlist.refusals.map((entry) => (
            <Entry
              key={`${entry.firm.firm_name}-${entry.firm.source_url}`}
              entry={entry}
              now={now}
            />
          ))}
        </div>
      )}

      {shortlist.withheld_stale.length > 0 && (
        <Withheld records={shortlist.withheld_stale} now={now} />
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  One firm's place in the answer                                     */
/* ------------------------------------------------------------------ */

function Entry({ entry, now }: { entry: ShortlistEntry; now: Date }) {
  const refused = entry.verdict === 'refusal';
  // For a match the bridge is already the first reason, inserted there so it
  // reads first. For a refusal it is not, because the refusal leads instead —
  // so it is rendered here or it is lost.
  const bridgeInReasons = entry.reasons.some((r) => r.dimension === 'objection_bridge');
  const counted = countedDimensions(entry.score_components);

  return (
    <FirmRecord firm={entry.firm} now={now} tone={refused ? 'refused' : 'plain'}>
      <div className="space-y-3">
        {refused ? (
          <div className="rounded-xl border border-saibyl-warning/30 bg-saibyl-warning/[0.06] p-3.5">
            <MonoLabel>What they state</MonoLabel>
            <p className="text-[12.5px] text-saibyl-ink mt-1.5 leading-relaxed">
              {entry.refusal_reason}
            </p>
          </div>
        ) : (
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="font-mono text-[11px] tabular-nums text-saibyl-ink">
              {entry.score.toFixed(2)}
            </span>
            <span className="font-mono text-[9.5px] uppercase tracking-[0.14em] text-saibyl-muted">
              match strength
            </span>
            {counted.length > 0 && (
              <span className="text-[11.5px] text-saibyl-muted">
                on {counted.map((d) => DIMENSION_SHORT[d]).join(', ')}
              </span>
            )}
          </div>
        )}

        {entry.access_note && (
          <p className="text-[12px] text-saibyl-warning leading-relaxed">
            {entry.access_note}
            {!refused &&
              ' It is here because it fits, which is not the same as being reachable.'}
          </p>
        )}

        {entry.objection_bridge && !bridgeInReasons && (
          <ReasonBlock reason={entry.objection_bridge} bridge />
        )}

        {entry.reasons.length > 0 && (
          <div className="space-y-2">
            {refused && (
              <p className="text-[12px] text-saibyl-silver leading-relaxed">
                What did line up, so you can judge whether it is worth a warm
                introduction anyway:
              </p>
            )}
            {entry.reasons.map((reason) => (
              <ReasonBlock
                key={`${reason.dimension}-${reason.firm_quote}`}
                reason={reason}
                bridge={reason.dimension === 'objection_bridge'}
              />
            ))}
          </div>
        )}
      </div>
      {/*
        The entry's own `retrieved_at` and `stale_after` are computed from the
        firm record rather than copied, so they cannot disagree with it — and
        `FirmRecord` prints them a few lines below through `Provenance`.
        Rendering them again here would be the same fact twice in one card,
        which is noise rather than evidence.
      */}
    </FirmRecord>
  );
}

