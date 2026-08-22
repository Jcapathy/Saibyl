import { useCallback, useEffect, useRef, useState } from 'react';
import { AxiosError } from 'axios';
import { Link } from 'react-router-dom';

import api from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { Guarded } from '@/components/stages/StagePrimitives';
import PriceTag from '@/components/billing/PriceTag';
import { usePrices } from '@/lib/prices';

/**
 * The objection matrix — what to say when a real person pushes back.
 *
 * Sits on step 3 beside the inoculation loop, and the two are deliberately
 * different products of the same measurement. Inoculation drafts material you
 * *publish*, then re-runs the room to prove the objection moved. This is the
 * script for a live conversation, which no room can score. A founder needs
 * both and they are not substitutes.
 *
 * Every row carries the buyer's own sentence, because the quote is what makes
 * the row credible on a call — a founder who can say "the last four people
 * who looked at this said exactly that" is having a different conversation
 * from one reciting a rebuttal.
 */

interface MatrixRow {
  objection_key: string;
  label: string;
  agents_raising: number;
  load_bearing_score: number;
  evidence_quotes: string[];
  acknowledge: string;
  explore: string;
  respond: string;
  confirm: string;
  when_to_walk: string | null;
}

interface Battlecard {
  rival: string;
  they_say: string;
  the_honest_read: string;
  where_we_win: string;
  proof_needed: string | null;
}

interface AnswerPack {
  id: string;
  status: 'queued' | 'building' | 'complete' | 'failed';
  rows: MatrixRow[];
  battlecards: Battlecard[];
  notes: string[];
  built_from_objections: number;
  /**
   * Blanks left where the run measured nothing. The messaging doc and the
   * outbound sequences both surfaced this and the pack did not, so a pack
   * shipped with eleven `[TODO: …]` in it and no sign that it had.
   */
  placeholders_to_fill?: number;
  error_message: string | null;
}

const POLL_MS = 4000;

export default function AnswerPackPanel({ simulationId }: { simulationId: string }) {
  const prices = usePrices();
  const [pack, setPack] = useState<AnswerPack | null>(null);
  const [loading, setLoading] = useState(true);
  const [building, setBuilding] = useState(false);
  const [error, setError] = useState<{ message: string; billing: boolean } | null>(null);
  const timer = useRef<number | null>(null);

  const load = useCallback(
    async (quiet = false) => {
      try {
        const { data } = await api.get<AnswerPack>(
          `/answer-pack/by-simulation/${simulationId}`,
        );
        setPack(data);
        return data;
      } catch (err) {
        // A 404 is the ordinary state before the first build, not a failure.
        const status = err instanceof AxiosError ? err.response?.status : undefined;
        if (status !== 404 && !quiet) {
          setError({
            message: getErrorMessage(err, 'We could not load your answers.'),
            billing: false,
          });
        }
        return null;
      } finally {
        if (!quiet) setLoading(false);
      }
    },
    [simulationId],
  );

  useEffect(() => {
    void load();
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [load]);

  // Poll only while there is something to wait for, and stop the moment it
  // settles — a timer that keeps firing after the work is done is how a page
  // quietly hammers an API for the rest of the session.
  useEffect(() => {
    if (!pack || (pack.status !== 'queued' && pack.status !== 'building')) return;
    timer.current = window.setTimeout(() => void load(true), POLL_MS);
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [pack, load]);

  const build = async () => {
    setBuilding(true);
    setError(null);
    try {
      const { data } = await api.post<AnswerPack>('/answer-pack', {
        simulation_id: simulationId,
      });
      setPack(data);
    } catch (err) {
      const status = err instanceof AxiosError ? err.response?.status : undefined;
      setError({
        message: getErrorMessage(err, 'We could not start building your answers.'),
        billing: status === 402,
      });
    } finally {
      setBuilding(false);
    }
  };

  if (loading) return null;

  const inFlight = pack?.status === 'queued' || pack?.status === 'building';
  const complete = pack?.status === 'complete';

  return (
    <section className="rounded-xl border border-saibyl-border bg-white p-5 space-y-4">
      <div>
        <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-saibyl-muted">
          On a call
        </p>
        <h2 className="text-[15px] font-semibold text-saibyl-ink mt-1">
          What to say when they push back
        </h2>
        <p className="text-[12.5px] text-saibyl-muted mt-1.5 leading-relaxed max-w-2xl">
          The answers above are material you publish and re-test. This is the
          other half: what to say out loud when the objection comes up on a
          call, in the order the room said it matters &mdash; with the buyer&rsquo;s
          own sentence attached, so you can say four people put it exactly that
          way.
        </p>
      </div>

      {error && (
        <div className="rounded-xl border border-saibyl-negative/25 bg-saibyl-negative/[0.07] p-4">
          <p className="text-[13px] text-saibyl-negative leading-relaxed">{error.message}</p>
          {error.billing && (
            <Link
              to="/app/settings"
              className="inline-block mt-2.5 text-[12px] font-semibold text-saibyl-blue hover:underline"
            >
              Add credits
            </Link>
          )}
        </div>
      )}

      {pack?.status === 'failed' && (
        <div className="rounded-xl border border-saibyl-negative/25 bg-saibyl-negative/[0.07] p-4">
          <p className="text-[13px] text-saibyl-negative leading-relaxed">
            {pack.error_message ?? 'We could not build your answers.'}
          </p>
        </div>
      )}

      {inFlight && (
        <p className="text-[13px] text-saibyl-silver" aria-live="polite">
          Working through what the room objected to…
        </p>
      )}

      {!complete && !inFlight && (
        <div>
          <div className="mb-3">
            <PriceTag entry={prices?.answer_pack} />
          </div>
          <Guarded
            label="Build the answers"
            onClick={build}
            busy={building}
            busyLabel="Starting…"
          />
        </div>
      )}

      {complete && pack && (
        <>
          <p className="text-[11.5px] text-saibyl-muted">
            Built from{' '}
            <span className="font-mono tabular-nums">{pack.built_from_objections}</span>{' '}
            measured objections, hardest first.
            {(pack.placeholders_to_fill ?? 0) > 0 && (
              <>
                {' · '}
                <span className="text-saibyl-warning">
                  <span className="font-mono tabular-nums">
                    {pack.placeholders_to_fill}
                  </span>{' '}
                  {pack.placeholders_to_fill === 1 ? 'fact' : 'facts'} still to
                  fill in
                </span>
              </>
            )}
          </p>

          {(pack.placeholders_to_fill ?? 0) > 0 && (
            <p className="text-[11.5px] text-saibyl-muted leading-relaxed">
              The amber markers below are numbers this run did not measure —
              including any the draft supplied on its own. They are left visible
              on purpose: you would say these out loud to the one person who can
              check them.
            </p>
          )}

          <ol className="space-y-3">
            {pack.rows.map((row) => (
              <li
                key={row.objection_key}
                className="rounded-xl border border-saibyl-border bg-saibyl-elevated p-4"
              >
                <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
                  <h3 className="text-[13.5px] font-semibold text-saibyl-ink">
                    {row.label}
                  </h3>
                  <span className="font-mono text-[11px] tabular-nums text-saibyl-muted">
                    {row.agents_raising}{' '}
                    {row.agents_raising === 1 ? 'buyer' : 'buyers'}
                  </span>
                </div>

                {row.evidence_quotes.length > 0 && (
                  <ul className="mt-2 space-y-1">
                    {row.evidence_quotes.map((quote) => (
                      <li
                        key={quote}
                        className="text-[12px] text-saibyl-silver italic border-l-2 border-saibyl-border-light pl-2.5 leading-relaxed"
                      >
                        &ldquo;{quote}&rdquo;
                      </li>
                    ))}
                  </ul>
                )}

                <dl className="mt-3 space-y-2">
                  {([
                    ['Say first', row.acknowledge],
                    ['Then ask', row.explore],
                    ['Answer', row.respond],
                    ['Check it landed', row.confirm],
                  ] as const).map(([label, value]) => (
                    <div key={label}>
                      <dt className="font-mono text-[9.5px] uppercase tracking-[0.14em] text-saibyl-muted">
                        {label}
                      </dt>
                      <dd className="text-[12.5px] text-saibyl-ink leading-relaxed mt-0.5">
                        {value}
                      </dd>
                    </div>
                  ))}
                </dl>

                {row.when_to_walk && (
                  <p className="mt-3 text-[12px] text-saibyl-warning leading-relaxed">
                    <span className="font-semibold">When to walk:</span>{' '}
                    {row.when_to_walk}
                  </p>
                )}
              </li>
            ))}
          </ol>

          {pack.battlecards.length > 0 && (
            <div>
              <h3 className="text-[13.5px] font-semibold text-saibyl-ink mt-2">
                What they are really choosing between
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2">
                {pack.battlecards.map((card) => (
                  <div
                    key={card.rival}
                    className="rounded-xl border border-saibyl-border bg-saibyl-elevated p-4"
                  >
                    <p className="text-[13px] font-semibold text-saibyl-ink">
                      {card.rival}
                    </p>
                    <p className="text-[12px] text-saibyl-silver mt-1.5 leading-relaxed">
                      <span className="text-saibyl-muted">They say:</span>{' '}
                      {card.they_say}
                    </p>
                    <p className="text-[12px] text-saibyl-silver mt-1.5 leading-relaxed">
                      <span className="text-saibyl-muted">Where they win:</span>{' '}
                      {card.the_honest_read}
                    </p>
                    <p className="text-[12px] text-saibyl-ink mt-1.5 leading-relaxed">
                      <span className="text-saibyl-muted">Where you win:</span>{' '}
                      {card.where_we_win}
                    </p>
                    {card.proof_needed && (
                      <p className="text-[11.5px] text-saibyl-warning mt-1.5 leading-relaxed">
                        You will need: {card.proof_needed}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {pack.notes.length > 0 && (
            <ul className="space-y-1">
              {pack.notes.map((note) => (
                <li key={note} className="text-[11.5px] text-saibyl-muted leading-relaxed">
                  {note}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
