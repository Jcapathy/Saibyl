import { useCallback, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { AxiosError } from 'axios';
import { Link } from 'react-router-dom';

import api from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { Guarded } from '@/components/stages/StagePrimitives';
import PriceTag from '@/components/billing/PriceTag';
import { usePrices, type PriceEntry, type PricesResponse } from '@/lib/prices';

/**
 * The messaging worksheet — the document every other asset is derived from.
 *
 * Sits on step 5 beside the version comparison, and the two answer different
 * questions from the same measurement. The comparison says *which wording won*.
 * This says what the messaging is: the problem, the one-sentence solution, who
 * it is for and who it is not for, three value propositions, three
 * differentiators with the set-level test run over them, the pitch, and what
 * the messaging has to survive on contact with a buyer.
 *
 * Two rules the render obeys, both inherited from the module it displays.
 *
 * **Every field the backend computes is on screen.** `services/gtm/
 * messaging_doc.py` attaches measured facts — the objection counts, the
 * weights, the verbatim quotes, the winning version, the scoreboard's refusal
 * — from the database rather than from the model, and a field that is computed
 * and never rendered is a known defect class in this repo. The one place that
 * required a judgement call is `evidence_objection_keys`, which the backend
 * carries as keys; they are resolved to the objection's own label where the
 * document also carries that objection, and shown as the key otherwise.
 *
 * **A placeholder stays visible.** The generator writes `[TODO: your number]`
 * where a sentence needed a fact the run did not measure, precisely so the
 * founder does not say an invented statistic out loud to somebody who can
 * check it. `Filled` marks those in amber wherever they appear instead of
 * letting them read as prose, and the count sits in the header.
 */

/* ------------------------------------------------------------------ */
/*  The document, as the backend writes it                             */
/* ------------------------------------------------------------------ */

type DocStatus = 'queued' | 'building' | 'complete' | 'failed';

interface ProblemDimension {
  name: string;
  sub_causes: string[];
}

interface Problem {
  headline: string;
  dimensions: ProblemDimension[];
  impact: string;
  evidence_objection_keys: string[];
}

interface Solution {
  what_we_do_high_level: string;
  what_we_do_specific: string;
  how_we_do_it: string;
}

interface Audience {
  who: string;
  not_for: string;
}

interface ValueProp {
  category: string;
  statement: string;
  source: string;
  source_objection_key: string | null;
}

interface Differentiator {
  distinction: string;
  client_benefit: string;
  rivals_who_can_claim_it: string[];
}

interface ElevatorPitch {
  problem: string;
  solution: string;
  value: string;
  differentiator: string;
  call_to_action: string;
  from_variant_key: string | null;
  from_variant_label: string | null;
  caveat: string | null;
}

interface ObjectionLine {
  objection_key: string;
  label: string;
  agents_raising: number;
  load_bearing_score: number;
  quotes: string[];
  how_the_messaging_answers_it: string;
}

interface MessageTest {
  versions_tested: number;
  winner_variant_key: string | null;
  winner_label: string | null;
  verdict: string;
  named_a_winner: boolean;
}

interface Worksheet {
  problem: Problem;
  solution: Solution;
  icp: Audience;
  value_props: ValueProp[];
  differentiators: Differentiator[];
  differentiation_verdict: string;
  elevator_pitch: ElevatorPitch;
  objections: ObjectionLine[];
  message_test: MessageTest | null;
  alternatives: string[];
  built_from_objections: number;
  placeholders_to_fill: number;
  notes: string[];
}

interface MessagingDocRow {
  id: string;
  status: DocStatus;
  /** `{}` in the database until the worker finishes, the worksheet after. */
  document: Partial<Worksheet> | null;
  built_from_objections: number;
  credits_charged: number;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

/**
 * The build price.
 *
 * `PricesResponse` has no `messaging_doc` entry because `GET /billing/prices`
 * does not return one — `backend/app/api/billing.py` builds its table from
 * four named prices and this module is not among them, though
 * `messaging_doc_credits()` exists and the route charges it. Both files are
 * shared and owned by other work in flight, so this reads through a widened
 * type instead of editing them: the tag renders nothing today and lights up
 * the moment the server starts returning the entry, with no third change here.
 */
type PricesWithMessagingDoc = PricesResponse & { messaging_doc?: PriceEntry };

const POLL_MS = 4000;

/* ------------------------------------------------------------------ */
/*  Reading it safely                                                  */
/* ------------------------------------------------------------------ */

/**
 * The worksheet, with every top-level section guaranteed present.
 *
 * The column defaults to `{}` and no route in this backend declares a
 * `response_model`, so the frontend has no served contract to rely on. A
 * missing section must render as a quiet gap on a page the founder has already
 * paid for, never as a blank screen — so the shape is normalised once, here,
 * rather than guarded at forty call sites.
 */
function readWorksheet(raw: Partial<Worksheet> | null | undefined): Worksheet | null {
  if (!raw || Object.keys(raw).length === 0) return null;
  return {
    problem: {
      headline: raw.problem?.headline ?? '',
      dimensions: raw.problem?.dimensions ?? [],
      impact: raw.problem?.impact ?? '',
      evidence_objection_keys: raw.problem?.evidence_objection_keys ?? [],
    },
    solution: {
      what_we_do_high_level: raw.solution?.what_we_do_high_level ?? '',
      what_we_do_specific: raw.solution?.what_we_do_specific ?? '',
      how_we_do_it: raw.solution?.how_we_do_it ?? '',
    },
    icp: { who: raw.icp?.who ?? '', not_for: raw.icp?.not_for ?? '' },
    value_props: raw.value_props ?? [],
    differentiators: raw.differentiators ?? [],
    differentiation_verdict: raw.differentiation_verdict ?? '',
    elevator_pitch: {
      problem: raw.elevator_pitch?.problem ?? '',
      solution: raw.elevator_pitch?.solution ?? '',
      value: raw.elevator_pitch?.value ?? '',
      differentiator: raw.elevator_pitch?.differentiator ?? '',
      call_to_action: raw.elevator_pitch?.call_to_action ?? '',
      from_variant_key: raw.elevator_pitch?.from_variant_key ?? null,
      from_variant_label: raw.elevator_pitch?.from_variant_label ?? null,
      caveat: raw.elevator_pitch?.caveat ?? null,
    },
    objections: raw.objections ?? [],
    message_test: raw.message_test ?? null,
    alternatives: raw.alternatives ?? [],
    built_from_objections: raw.built_from_objections ?? 0,
    placeholders_to_fill: raw.placeholders_to_fill ?? 0,
    notes: raw.notes ?? [],
  };
}

/** A date, or nothing at all. An "Invalid Date" in a header is worse than none. */
function builtOn(stamp: string | null): string {
  if (!stamp) return '';
  const parsed = new Date(stamp);
  return Number.isNaN(parsed.getTime())
    ? ''
    : parsed.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}

/** `pricing_objection` → `pricing objection`, for a key with no label behind it. */
function humanKey(key: string): string {
  return key.replace(/_/g, ' ').trim();
}

/* ------------------------------------------------------------------ */
/*  Pieces                                                             */
/* ------------------------------------------------------------------ */

/**
 * Prose with its unfilled facts still showing.
 *
 * The generator writes `[TODO: your number]` and `[TODO: your example]` rather
 * than inventing a statistic or a customer. Rendered as flat text those read
 * as part of the sentence; in amber mono they read as an open item, which is
 * the whole reason the generator writes them.
 */
function Filled({ text }: { text: string }) {
  const trimmed = text.trim();
  if (!trimmed) return null;
  return (
    <>
      {trimmed
        .split(/(\[TODO: your (?:number|example)\])/g)
        .map((part, i) =>
          part.startsWith('[TODO:') ? (
            <span
              key={`${i}-${part}`}
              className="font-mono text-[11.5px] text-saibyl-warning"
            >
              {part}
            </span>
          ) : (
            <span key={`${i}-${part}`}>{part}</span>
          ),
        )}
    </>
  );
}

/**
 * One section of the worksheet.
 *
 * The heading is a mono label wearing the cyan dot, which is the house eyebrow
 * — see `docs/DESIGN_GUIDE.md`. Numbers stay mono without a dot: the dot marks
 * a *label*, and putting one beside every figure would turn a rhythm into
 * confetti.
 */
function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.16em] text-saibyl-muted">
        <span
          aria-hidden="true"
          className="w-[7px] h-[7px] rounded-full bg-saibyl-cyan shadow-[0_0_0_5px_rgba(53,199,213,0.12)] shrink-0"
        />
        {title}
      </h3>
      {children}
    </section>
  );
}

/** A labelled line inside a card. Same eyebrow rule, one size down. */
function Line({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <p className="flex items-center gap-1.5 font-mono text-[9.5px] uppercase tracking-[0.14em] text-saibyl-muted">
        <span
          aria-hidden="true"
          className="w-[5px] h-[5px] rounded-full bg-saibyl-cyan shadow-[0_0_0_3px_rgba(53,199,213,0.12)] shrink-0"
        />
        {label}
      </p>
      <div className="text-[12.5px] text-saibyl-ink leading-relaxed mt-0.5">
        {children}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  The panel                                                          */
/* ------------------------------------------------------------------ */

export default function MessagingDocPanel({ simulationId }: { simulationId: string }) {
  const prices = usePrices();
  const [doc, setDoc] = useState<MessagingDocRow | null>(null);
  const [loading, setLoading] = useState(true);
  const [building, setBuilding] = useState(false);
  const [error, setError] = useState<{ message: string; billing: boolean } | null>(null);
  const timer = useRef<number | null>(null);

  const load = useCallback(
    async (quiet = false) => {
      try {
        const { data } = await api.get<MessagingDocRow>(
          `/messaging-doc/by-simulation/${simulationId}`,
        );
        setDoc(data);
        return data;
      } catch (err) {
        // A 404 is the ordinary state before the first build, not a failure.
        const status = err instanceof AxiosError ? err.response?.status : undefined;
        if (status !== 404 && !quiet) {
          setError({
            message: getErrorMessage(err, 'We could not load your messaging document.'),
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
    if (!doc || (doc.status !== 'queued' && doc.status !== 'building')) return;
    timer.current = window.setTimeout(() => void load(true), POLL_MS);
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [doc, load]);

  const build = async () => {
    setBuilding(true);
    setError(null);
    try {
      const { data } = await api.post<MessagingDocRow>('/messaging-doc', {
        simulation_id: simulationId,
      });
      setDoc(data);
    } catch (err) {
      const status = err instanceof AxiosError ? err.response?.status : undefined;
      setError({
        message: getErrorMessage(err, 'We could not start building your messaging document.'),
        billing: status === 402,
      });
    } finally {
      setBuilding(false);
    }
  };

  if (loading) return null;

  const price = (prices as PricesWithMessagingDoc | null)?.messaging_doc;
  const inFlight = doc?.status === 'queued' || doc?.status === 'building';
  const complete = doc?.status === 'complete';
  const sheet = complete ? readWorksheet(doc.document) : null;

  // Objection labels, for the two places the backend hands over a bare key.
  const labelFor = new Map((sheet?.objections ?? []).map((o) => [o.objection_key, o.label]));
  const built = builtOn(doc?.completed_at ?? doc?.created_at ?? null);

  return (
    <section className="rounded-2xl border border-saibyl-border bg-white p-6 space-y-5 shadow-[0_14px_44px_rgba(57,91,146,0.06)]">
      <div>
        <p className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.16em] text-saibyl-muted">
          <span
            aria-hidden="true"
            className="w-[7px] h-[7px] rounded-full bg-saibyl-cyan shadow-[0_0_0_5px_rgba(53,199,213,0.12)] shrink-0"
          />
          Your messaging
        </p>
        <h2 className="text-[19px] font-semibold text-saibyl-ink mt-1.5 tracking-[-0.02em]">
          Everything else you write{' '}
          {/* The one serif italic phrase on this surface, and `#6a4fe0` rather
              than the `saibyl-violet` token: the token carries violet's *fill*
              value, which the design guide forbids for text. */}
          <span className="font-serif italic font-normal text-[20px] text-[#6a4fe0]">
            inherits this
          </span>
        </h2>
        <p className="text-[12.5px] text-saibyl-muted mt-2 leading-relaxed max-w-2xl">
          Your deck, your demo, your home page and every email you send restate
          the same handful of claims, so a weak line here is inherited by all of
          them. The blank version of this worksheet gets filled in from memory.
          This one is filled in from what the room actually said &mdash; the
          objections that cost you the deal, in the order they cost it, and the
          buyers&rsquo; own words underneath.
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

      {doc?.status === 'failed' && (
        <div className="rounded-xl border border-saibyl-negative/25 bg-saibyl-negative/[0.07] p-4">
          <p className="text-[13px] text-saibyl-negative leading-relaxed">
            {doc.error_message ?? 'We could not build your messaging document.'}
          </p>
          {/* The sentence the server does not say. Credits are taken when a
              build starts, not when it succeeds, and nothing refunds them —
              so "try building it again" costs the same as the first one, and
              a founder should read that here rather than discover it on their
              balance. */}
          {doc.credits_charged > 0 && (
            <p className="text-[11.5px] text-saibyl-muted mt-2 leading-relaxed">
              That build was charged{' '}
              <span className="font-mono tabular-nums">
                {doc.credits_charged.toLocaleString()}
              </span>{' '}
              credits when it started, and starting another charges the same
              again.
            </p>
          )}
        </div>
      )}

      {inFlight && (
        <p
          className="flex items-center gap-2 text-[13px] text-saibyl-silver"
          aria-live="polite"
        >
          {/* The one piece of motion on this panel, and it collapses under
              `prefers-reduced-motion` because `motion-safe:` is the only place
              the animation is named. */}
          <span
            aria-hidden="true"
            className="w-[7px] h-[7px] rounded-full bg-saibyl-cyan shrink-0 motion-safe:animate-[pulse-dot_1.7s_ease-in-out_infinite]"
          />
          Filling the worksheet in from what the room said&hellip;
        </p>
      )}

      {!complete && !inFlight && (
        <div>
          <div className="mb-3">
            <PriceTag entry={price} />
          </div>
          <Guarded
            label="Fill in the worksheet"
            onClick={build}
            busy={building}
            busyLabel="Starting…"
          />
        </div>
      )}

      {/* A row that says `complete` over an empty blob should be unreachable —
          the worker writes the document and the status in one update. It is
          handled anyway, with the way out attached: a founder who has paid for
          this must never be left reading a sentence with no control under it. */}
      {complete && !sheet && (
        <div className="space-y-3">
          <p className="text-[12.5px] text-saibyl-muted leading-relaxed">
            This document finished but came back empty, which is a fault on our
            side rather than anything you did. Your run and its objections are
            untouched.
          </p>
          <PriceTag entry={price} />
          <Guarded
            label="Build it again"
            onClick={build}
            busy={building}
            busyLabel="Starting…"
          />
        </div>
      )}

      {complete && sheet && doc && (
        <>
          {/* What it was built from, and what it still owes you. Both are read
              off the row rather than recomputed: `built_from_objections` is
              denormalised out of the blob for exactly this line. */}
          <p className="text-[11.5px] text-saibyl-muted leading-relaxed">
            Filled in from{' '}
            <span className="font-mono tabular-nums">{doc.built_from_objections}</span>{' '}
            measured objections
            {built ? ` · built ${built}` : ''}
            {doc.credits_charged > 0
              ? ` · ${doc.credits_charged.toLocaleString()} credits`
              : ''}
            {sheet.placeholders_to_fill > 0 ? ' · ' : ''}
            {sheet.placeholders_to_fill > 0 && (
              <span className="text-saibyl-warning">
                <span className="font-mono tabular-nums">
                  {sheet.placeholders_to_fill}
                </span>{' '}
                {sheet.placeholders_to_fill === 1 ? 'fact' : 'facts'} still to fill
                in
              </span>
            )}
          </p>

          {sheet.placeholders_to_fill > 0 && (
            <p className="text-[11.5px] text-saibyl-muted leading-relaxed">
              The amber markers below are numbers and examples this run did not
              measure. They are left visible on purpose: an invented figure is
              one you would say out loud to somebody who can check it.
            </p>
          )}

          {/* ── The problem ─────────────────────────────────────────── */}
          <Section title="The problem you solve">
            <div className="rounded-xl border border-saibyl-border bg-saibyl-elevated p-4 space-y-3">
              {sheet.problem.headline && (
                <p className="text-[14px] font-semibold text-saibyl-ink leading-snug">
                  <Filled text={sheet.problem.headline} />
                </p>
              )}

              {sheet.problem.dimensions.length > 0 && (
                <ul className="space-y-2">
                  {sheet.problem.dimensions.map((dimension) => (
                    <li key={dimension.name}>
                      <p className="text-[12.5px] font-semibold text-saibyl-ink">
                        <Filled text={dimension.name} />
                      </p>
                      {dimension.sub_causes.length > 0 && (
                        <ul className="mt-0.5 space-y-0.5">
                          {dimension.sub_causes.map((cause) => (
                            <li
                              key={cause}
                              className="text-[12px] text-saibyl-silver leading-relaxed border-l-2 border-saibyl-border-light pl-2.5"
                            >
                              <Filled text={cause} />
                            </li>
                          ))}
                        </ul>
                      )}
                    </li>
                  ))}
                </ul>
              )}

              {sheet.problem.impact && (
                <Line label="What it costs them">
                  <Filled text={sheet.problem.impact} />
                </Line>
              )}

              {sheet.problem.evidence_objection_keys.length > 0 && (
                <p className="text-[11.5px] text-saibyl-muted leading-relaxed">
                  Buyers proved this by raising:{' '}
                  {sheet.problem.evidence_objection_keys
                    .map((key) => labelFor.get(key) ?? humanKey(key))
                    .join(' · ')}
                </p>
              )}
            </div>
          </Section>

          {/* ── The solution ────────────────────────────────────────── */}
          <Section title="What you do about it">
            <div className="rounded-xl border border-saibyl-border bg-saibyl-elevated p-4 space-y-2.5">
              {sheet.solution.what_we_do_high_level && (
                <Line label="In one sentence">
                  <Filled text={sheet.solution.what_we_do_high_level} />
                </Line>
              )}
              {sheet.solution.what_we_do_specific && (
                <Line label="Specifically">
                  <Filled text={sheet.solution.what_we_do_specific} />
                </Line>
              )}
              {sheet.solution.how_we_do_it && (
                <Line label="Why that is believable">
                  <Filled text={sheet.solution.how_we_do_it} />
                </Line>
              )}
            </div>
          </Section>

          {/* ── Who it is for ───────────────────────────────────────── */}
          {(sheet.icp.who || sheet.icp.not_for) && (
            <Section title="Who it is for">
              <div className="rounded-xl border border-saibyl-border bg-saibyl-elevated p-4 space-y-2.5">
                {sheet.icp.who && (
                  <Line label="For">
                    <Filled text={sheet.icp.who} />
                  </Line>
                )}
                {sheet.icp.not_for && (
                  <Line label="Not for">
                    <Filled text={sheet.icp.not_for} />
                  </Line>
                )}
              </div>
            </Section>
          )}

          {/* ── Value propositions ──────────────────────────────────── */}
          {sheet.value_props.length > 0 && (
            <Section title="The three things they get">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {sheet.value_props.map((prop) => (
                  <div
                    key={`${prop.category}-${prop.statement}`}
                    className="rounded-xl border border-saibyl-border bg-saibyl-elevated p-4"
                  >
                    <p className="flex items-center gap-1.5 font-mono text-[9.5px] uppercase tracking-[0.14em] text-saibyl-muted">
                      <span
                        aria-hidden="true"
                        className="w-[5px] h-[5px] rounded-full bg-saibyl-cyan shadow-[0_0_0_3px_rgba(53,199,213,0.12)] shrink-0"
                      />
                      {prop.category}
                    </p>
                    <p className="text-[12.5px] text-saibyl-ink leading-relaxed mt-1.5">
                      <Filled text={prop.statement} />
                    </p>
                    {prop.source && (
                      <p className="text-[11.5px] text-saibyl-silver leading-relaxed mt-1.5">
                        <span className="text-saibyl-muted">Where it comes from:</span>{' '}
                        <Filled text={prop.source} />
                      </p>
                    )}
                    {prop.source_objection_key && (
                      <p className="text-[11.5px] text-saibyl-muted leading-relaxed mt-1.5">
                        Answers:{' '}
                        {labelFor.get(prop.source_objection_key) ??
                          humanKey(prop.source_objection_key)}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </Section>
          )}

          {/* ── Differentiators, and the set-level test ─────────────── */}
          {(sheet.differentiators.length > 0 || sheet.differentiation_verdict) && (
            <Section title="What makes you different">
              <div className="space-y-2">
                {sheet.differentiators.map((diff) => (
                  <div
                    key={diff.distinction}
                    className="rounded-xl border border-saibyl-border bg-saibyl-elevated p-4"
                  >
                    <p className="text-[13px] font-semibold text-saibyl-ink leading-snug">
                      <Filled text={diff.distinction} />
                    </p>
                    {diff.client_benefit && (
                      <p className="text-[12px] text-saibyl-silver leading-relaxed mt-1.5">
                        <span className="text-saibyl-muted">So the customer gets:</span>{' '}
                        <Filled text={diff.client_benefit} />
                      </p>
                    )}
                    <p className="text-[11.5px] text-saibyl-muted leading-relaxed mt-1.5">
                      {diff.rivals_who_can_claim_it.length > 0
                        ? `Can also be claimed by: ${diff.rivals_who_can_claim_it.join(' · ')}`
                        : 'None of the alternatives listed below can claim this one.'}
                    </p>
                  </div>
                ))}
              </div>

              {/*
                Rendered in ink rather than tinted pass/fail. The sentence
                already says which way it went, and tinting it would mean
                pattern-matching the backend's prose to pick a colour — a
                claim about the result made by a regular expression.
              */}
              {sheet.differentiation_verdict && (
                <div className="rounded-xl border border-saibyl-border bg-white p-4 mt-2">
                  <Line label="The three-way test">{sheet.differentiation_verdict}</Line>
                  <p className="text-[11.5px] text-saibyl-muted leading-relaxed mt-1.5">
                    Most alternatives should be able to claim one of the three,
                    some two, and none all three. That combination is what holds
                    up when a buyer puts you side by side with somebody else.
                  </p>
                </div>
              )}
            </Section>
          )}

          {/* ── The pitch ───────────────────────────────────────────── */}
          <Section title="The pitch, for someone who has seconds">
            <div className="rounded-xl border border-saibyl-border bg-saibyl-elevated p-4 space-y-2.5">
              {sheet.elevator_pitch.problem && (
                <Line label="Problem">
                  <Filled text={sheet.elevator_pitch.problem} />
                </Line>
              )}
              {sheet.elevator_pitch.solution && (
                <Line label="Solution">
                  <Filled text={sheet.elevator_pitch.solution} />
                </Line>
              )}
              {sheet.elevator_pitch.value && (
                <Line label="Value">
                  <Filled text={sheet.elevator_pitch.value} />
                </Line>
              )}
              {sheet.elevator_pitch.differentiator && (
                <Line label="Why you">
                  <Filled text={sheet.elevator_pitch.differentiator} />
                </Line>
              )}
              {sheet.elevator_pitch.call_to_action && (
                <Line label="The ask">
                  <Filled text={sheet.elevator_pitch.call_to_action} />
                </Line>
              )}

              {sheet.elevator_pitch.from_variant_key && (
                <p className="text-[11.5px] text-saibyl-muted leading-relaxed">
                  Written from the wording that came out ahead:{' '}
                  <span className="text-saibyl-silver">
                    {sheet.elevator_pitch.from_variant_label ??
                      sheet.elevator_pitch.from_variant_key}
                  </span>
                </p>
              )}

              {/* The scoreboard's refusal, carried into the pitch. Amber, because
                  it is the line that stops a founder building six months of
                  assets on a difference the measurement would not confirm. */}
              {sheet.elevator_pitch.caveat && (
                <p className="text-[11.5px] text-saibyl-warning leading-relaxed">
                  {sheet.elevator_pitch.caveat}
                </p>
              )}
            </div>
          </Section>

          {/* ── What the messaging has to survive ───────────────────── */}
          {sheet.objections.length > 0 && (
            <Section title="What this messaging has to survive">
              <p className="text-[11.5px] text-saibyl-muted leading-relaxed">
                Hardest first. The weight combines how many people raised it, how
                strongly they meant it, and how far it spread across the room
                &mdash; it ranks what kills deals, and it is not a probability.
              </p>
              <ol className="space-y-2">
                {sheet.objections.map((line) => (
                  <li
                    key={line.objection_key}
                    className="rounded-xl border border-saibyl-border bg-saibyl-elevated p-4"
                  >
                    <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
                      <h4 className="text-[13px] font-semibold text-saibyl-ink">
                        {line.label}
                      </h4>
                      <span className="font-mono text-[11px] tabular-nums text-saibyl-muted">
                        {line.agents_raising}{' '}
                        {line.agents_raising === 1 ? 'buyer' : 'buyers'}
                      </span>
                      <span className="font-mono text-[11px] tabular-nums text-saibyl-muted">
                        weight {line.load_bearing_score.toFixed(1)}
                      </span>
                    </div>

                    {line.quotes.length > 0 && (
                      <ul className="mt-2 space-y-1">
                        {line.quotes.map((quote) => (
                          <li
                            key={quote}
                            className="text-[12px] text-saibyl-silver italic border-l-2 border-saibyl-border-light pl-2.5 leading-relaxed"
                          >
                            &ldquo;{quote}&rdquo;
                          </li>
                        ))}
                      </ul>
                    )}

                    {line.how_the_messaging_answers_it && (
                      <div className="mt-2.5">
                        <Line label="What the messaging does about it">
                          <Filled text={line.how_the_messaging_answers_it} />
                        </Line>
                      </div>
                    )}
                  </li>
                ))}
              </ol>
            </Section>
          )}

          {/* ── The message test ────────────────────────────────────── */}
          {sheet.message_test && (
            <Section title="When several wordings met the same room">
              <div className="rounded-xl border border-saibyl-border bg-saibyl-elevated p-4 space-y-2">
                <p className="text-[12.5px] text-saibyl-ink leading-relaxed">
                  <span className="font-mono tabular-nums">
                    {sheet.message_test.versions_tested}
                  </span>{' '}
                  wordings were read by one room.
                </p>

                {sheet.message_test.named_a_winner ? (
                  <p className="text-[12.5px] text-saibyl-positive leading-relaxed">
                    One came out ahead:{' '}
                    {sheet.message_test.winner_label ??
                      sheet.message_test.winner_variant_key ??
                      'the winning wording'}
                    .
                  </p>
                ) : (
                  <p className="text-[12.5px] text-saibyl-warning leading-relaxed">
                    The measurement would not name a winner, so this document
                    does not claim one.
                  </p>
                )}

                {sheet.message_test.verdict && (
                  <p className="text-[12px] text-saibyl-silver leading-relaxed">
                    {sheet.message_test.verdict}
                  </p>
                )}
              </div>
            </Section>
          )}

          {/* ── The names it is allowed to argue against ────────────── */}
          {sheet.alternatives.length > 0 && (
            <Section title="The only alternatives this argues against">
              <div className="flex flex-wrap gap-1.5">
                {sheet.alternatives.map((name) => (
                  <span
                    key={name}
                    className="rounded-full border border-saibyl-border bg-saibyl-elevated px-2.5 py-1 text-[11.5px] text-saibyl-silver"
                  >
                    {name}
                  </span>
                ))}
              </div>
              <p className="text-[11.5px] text-saibyl-muted leading-relaxed">
                Names you gave us, plus any a buyer said out loud, plus the two
                every founder is really up against. Nothing here was invented by
                a model &mdash; a rebuttal aimed at a company that does not exist
                is worse than no rebuttal.
              </p>
            </Section>
          )}

          {/* ── Notes ───────────────────────────────────────────────── */}
          {sheet.notes.length > 0 && (
            <Section title="Worth knowing">
              <ul className="space-y-1">
                {sheet.notes.map((note) => (
                  <li
                    key={note}
                    className="text-[11.5px] text-saibyl-muted leading-relaxed"
                  >
                    <Filled text={note} />
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {/* ── Rebuild ─────────────────────────────────────────────── */}
          <div className="border-t border-saibyl-border pt-4 space-y-3">
            <p className="text-[11.5px] text-saibyl-muted leading-relaxed max-w-2xl">
              Messaging is never finished. When the pitch changes, run the room
              again and build this from the new measurement &mdash; the document
              above is kept as the record of what your messaging used to say.
            </p>
            <PriceTag entry={price} />
            <Guarded
              label="Build it again"
              onClick={build}
              busy={building}
              busyLabel="Starting…"
              tone="quiet"
            />
          </div>
        </>
      )}
    </section>
  );
}
