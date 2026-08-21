import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ComponentType, ReactNode } from 'react';
import { AxiosError } from 'axios';
import { Link } from 'react-router-dom';
import { Check, Copy, Mail, MessageSquare, Phone } from 'lucide-react';

import api from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { formatCredits, presentList } from '@/lib/gtm';
import { Guarded } from '@/components/stages/StagePrimitives';
import PriceTag from '@/components/billing/PriceTag';
import { usePrices, type PriceEntry, type PricesResponse } from '@/lib/prices';

/**
 * The outbound sequences — two weeks of copy aimed at what the room measured.
 *
 * Sits on step 4 because that is the screen where a founder is looking at real
 * companies and asking what to send them. The backend has been complete,
 * deployed and priced with no surface at all, which meant a founder could not
 * buy it and did not know it existed.
 *
 * **Information design is the whole job here.** `services/gtm/outbound.py`
 * builds up to sixteen touches for up to four buyer types — sixty-four blocks
 * of copy in one payload. Rendered as one flat list it is unusable, so this
 * reads as: pick a buyer type, see the shape of the fortnight, see the three
 * measured objections it walks with the buyers' own sentences, then read the
 * touches grouped by the day they go out.
 *
 * **Every computed field is rendered.** A field the backend works out and the
 * UI silently drops is a logged defect class in this repo (`PRELAUNCH_BUGS.md`,
 * P2 — `maturity_level` and the GTM `excluded`/`delivery` fields). The two
 * places that rule bites here are `pains_addressed`, whose entries can outlive
 * the touches that carried them, and `placeholders_to_fill`, which is the
 * difference between a sequence that is finished and one that is not.
 *
 * **Nothing here sends anything, and it says so on the screen.** Saibyl holds
 * no list, no contact and no suppression state — `services/gtm/privacy.py` is
 * binding — so the merge tokens are resolved by the founder, in their own
 * tooling, out of their own inbox. A founder who assumed this had a send button
 * would be making a decision about a product that does not exist.
 */

/* ------------------------------------------------------------------ */
/*  The artifact, as the API returns it                                */
/* ------------------------------------------------------------------ */

interface OutboundTouch {
  step: number;
  /** Days after the first touch. The cadence's own offsets. */
  day: number;
  channel: string;
  purpose: string;

  /* Attached from the database by the builder, never echoed by the model. */
  objection_key: string | null;
  objection_label: string | null;
  agents_raising: number;
  load_bearing_score: number;
  evidence_quotes: string[];
  /** 1 = the objection head on. 2 = the same objection, framed differently. */
  angle: number | null;

  /** Empty on the non-email channels, where empty is the real value. */
  subject: string;
  body: string;
}

interface BuyerSequence {
  archetype_id: string;
  archetype_label: string;
  role: string;
  seniority: string;
  incumbent_tooling: string[];
  steps: OutboundTouch[];
  /** Objection keys in measured rank order — pain slot 1, 2, 3. */
  pains_addressed: string[];
  placeholders_to_fill: number;
  notes: string[];
}

interface OutboundBuild {
  id: string;
  status: 'queued' | 'building' | 'complete' | 'failed';
  sequences: BuyerSequence[];
  notes: string[];
  built_from_objections: number;
  winning_variant_key: string | null;
  winning_message: string | null;
  credits_charged: number;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

/**
 * `GET /billing/prices` does not yet carry an entry for this artifact, so
 * `PricesResponse` has no field for it — and `lib/prices.ts` is shared, so it
 * is not this component's to change. Declared optional here so the tag renders
 * the real price the moment the endpoint starts sending one, and the honest
 * sentence below stands in until then. Reported rather than patched around.
 */
type PricesWithOutbound = PricesResponse & { outbound_sequence?: PriceEntry };

const POLL_MS = 4000;

/* ------------------------------------------------------------------ */
/*  Vocabulary                                                         */
/* ------------------------------------------------------------------ */

/**
 * The three channels, named the way a founder would say them.
 *
 * Carried by icon and word rather than by colour: blue is reserved for actions,
 * and colour-coding three channels would spend the palette on decoration. It
 * also means the distinction survives a greyscale print of this screen.
 */
const CHANNELS: Record<
  string,
  {
    label: string;
    Icon: ComponentType<{ className?: string; 'aria-hidden'?: boolean }>;
  }
> = {
  email: { label: 'Email', Icon: Mail },
  linkedin: { label: 'LinkedIn', Icon: MessageSquare },
  phone: { label: 'Call', Icon: Phone },
};

/** The two framings of one measured objection. */
const ANGLE_COPY: Record<number, string> = {
  1: 'Answers it head on',
  2: 'Same objection, framed differently',
};

/**
 * The only personalization the copy may carry, mirroring
 * `outbound.MERGE_TOKENS`. Rendered rather than described because a founder has
 * to search their own tooling for exactly these strings, and a paraphrase of a
 * token is a token that does not resolve.
 */
const MERGE_TOKENS = ['{{first_name}}', '{{company}}', '{{sender.first_name}}'];

/**
 * The placeholders the builder writes where a fact is missing.
 *
 * Marked in the rendered copy rather than left to blend in: `outbound.py`
 * writes them exactly so a founder can find every one before the first send,
 * and cold email is the one place a fabricated number travels furthest.
 */
const TODO_SPLIT = /(\[TODO: your (?:number|example)\])/g;
const IS_TODO = /^\[TODO: your (?:number|example)\]$/;

/* ------------------------------------------------------------------ */
/*  Small pieces                                                       */
/* ------------------------------------------------------------------ */

/** A mono label wearing the brand's dot. Every mono label gets it. */
function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <p className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.16em] text-saibyl-muted">
      <span
        aria-hidden="true"
        className="h-[7px] w-[7px] shrink-0 rounded-full bg-saibyl-cyan shadow-[0_0_0_5px_rgba(53,199,213,0.12)]"
      />
      {children}
    </p>
  );
}

/** One block of copy, with its unfilled blanks marked. */
function CopyBlock({ text }: { text: string }) {
  return (
    <p className="mt-1.5 whitespace-pre-wrap text-[12.5px] leading-relaxed text-saibyl-ink">
      {text.split(TODO_SPLIT).map((part, i) =>
        IS_TODO.test(part) ? (
          <span
            key={i}
            className="rounded bg-[#f59e0b]/[0.16] px-1 py-px font-mono text-[11px] text-saibyl-warning"
          >
            {part}
          </span>
        ) : (
          part
        ),
      )}
    </p>
  );
}

function shortDate(iso: string | null): string | null {
  if (!iso) return null;
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return null;
  return when.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}

interface DayGroup {
  day: number;
  touches: OutboundTouch[];
}

/**
 * The touches, grouped into the days they go out on.
 *
 * A linear scan rather than a sort: the builder emits them in cadence order and
 * a test pins that, so re-sorting here would be a second opinion about an order
 * that is already decided — and would hide it if the two ever disagreed.
 */
function groupByDay(touches: OutboundTouch[]): DayGroup[] {
  const groups: DayGroup[] = [];
  for (const touch of touches) {
    const last = groups[groups.length - 1];
    if (last && last.day === touch.day) last.touches.push(touch);
    else groups.push({ day: touch.day, touches: [touch] });
  }
  return groups;
}

interface Pain {
  key: string;
  /** Null when no touch for this objection survived the build. */
  label: string | null;
  agents: number;
  score: number;
  quotes: string[];
}

/**
 * The measured objections this sequence walks, in the ranking the room set.
 *
 * `pains_addressed` is the order and the source of truth; the figures are read
 * off the touches, which carry them straight from `canonical_objections`. A key
 * with no surviving touch is kept and rendered as such rather than filtered
 * away — the builder drops a touch whose copy came back empty or carrying a
 * contact detail, and a pain that silently vanishes between the two lists is
 * exactly the kind of gap a founder finds by noticing something missing.
 */
function painsOf(sequence: BuyerSequence): Pain[] {
  const found = new Map<string, Pain>();
  for (const touch of sequence.steps) {
    if (!touch.objection_key || found.has(touch.objection_key)) continue;
    found.set(touch.objection_key, {
      key: touch.objection_key,
      label: touch.objection_label || null,
      agents: touch.agents_raising,
      score: touch.load_bearing_score,
      quotes: touch.evidence_quotes,
    });
  }
  return sequence.pains_addressed.map(
    (key) =>
      found.get(key) ?? { key, label: null, agents: 0, score: 0, quotes: [] },
  );
}

/* ------------------------------------------------------------------ */
/*  One buyer type's fortnight                                         */
/* ------------------------------------------------------------------ */

function SequenceView({ sequence }: { sequence: BuyerSequence }) {
  const days = useMemo(() => groupByDay(sequence.steps), [sequence.steps]);
  const pains = useMemo(() => painsOf(sequence), [sequence]);
  const tooling = presentList(sequence.incumbent_tooling);
  const lastDay = days.length > 0 ? days[days.length - 1].day : 0;

  /* Copy-to-clipboard, because every one of these blocks exists to be pasted
     somewhere else. One piece of state for the whole sequence: two touches
     cannot be the most-recently-copied one. */
  const [copied, setCopied] = useState<number | null>(null);
  const clearCopied = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (clearCopied.current) window.clearTimeout(clearCopied.current);
    },
    [],
  );

  const copyTouch = (touch: OutboundTouch) => {
    const clipboard = navigator.clipboard;
    if (!clipboard) return;
    const text = touch.subject
      ? `${touch.subject}\n\n${touch.body}`
      : touch.body;
    void clipboard.writeText(text).then(
      () => {
        setCopied(touch.step);
        if (clearCopied.current) window.clearTimeout(clearCopied.current);
        clearCopied.current = window.setTimeout(() => setCopied(null), 1600);
      },
      () => {
        /* The clipboard is unavailable outside a secure context. Failing
           silently is right: the copy is already on screen and selectable, so
           there is nothing the founder needs to do differently. */
      },
    );
  };

  return (
    <div className="space-y-4">
      {/* Who this fortnight is written to */}
      <div>
        <h3 className="text-[14px] font-semibold text-saibyl-ink">
          {sequence.archetype_label}
        </h3>
        {(sequence.role || sequence.seniority) && (
          <p className="mt-0.5 text-[12px] text-saibyl-silver">
            {[sequence.role, sequence.seniority].filter(Boolean).join(' · ')}
          </p>
        )}
        {tooling && (
          <p className="mt-1 text-[12px] leading-relaxed text-saibyl-muted">
            Runs today: {tooling.join(', ')}
          </p>
        )}
      </div>

      {/* The shape of the fortnight, before any of the words */}
      {days.length > 0 ? (
        <div className="rounded-xl border border-saibyl-border bg-saibyl-elevated px-4 py-3">
          <Eyebrow>The cadence</Eyebrow>
          <p className="mt-1.5 text-[12.5px] leading-relaxed text-saibyl-ink">
            <span className="font-mono tabular-nums">{sequence.steps.length}</span>{' '}
            {sequence.steps.length === 1 ? 'touch' : 'touches'} over{' '}
            <span className="font-mono tabular-nums">{lastDay}</span>{' '}
            {lastDay === 1 ? 'day' : 'days'}.
          </p>
          <p className="mt-1 font-mono text-[10.5px] tabular-nums leading-relaxed text-saibyl-muted">
            {days
              .map((group) => `Day ${group.day} ×${group.touches.length}`)
              .join(' · ')}
          </p>
        </div>
      ) : (
        <p className="text-[12.5px] leading-relaxed text-saibyl-warning">
          Not one touch survived the write for this buyer. Every block of copy
          came back empty or carrying something we will not store, so all of
          them were dropped rather than trimmed.
        </p>
      )}

      {/* What the room actually raised, in the order it made them matter */}
      {pains.length > 0 && (
        <div>
          <Eyebrow>What it walks</Eyebrow>
          <p className="mt-1.5 max-w-2xl text-[12px] leading-relaxed text-saibyl-muted">
            Ordered by how load-bearing each one measured &mdash; how many people
            raised it, how hard, and how widely it spread across kinds of buyer.
            That is deliberately not the same as how loudly it was said. The
            weight is a ranking figure, not a score out of anything.
          </p>
          <ol className="mt-2 space-y-2.5">
            {pains.map((pain, index) => (
              <li
                key={pain.key}
                className="border-l-2 border-[#8b73ee]/45 pl-3"
              >
                {pain.label ? (
                  <>
                    <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-0.5">
                      <span className="font-mono text-[10px] tabular-nums text-[#6a4fe0]">
                        {index + 1}
                      </span>
                      <p className="text-[13px] font-medium text-saibyl-ink">
                        {pain.label}
                      </p>
                      <span className="font-mono text-[10.5px] tabular-nums text-saibyl-muted">
                        {pain.agents} {pain.agents === 1 ? 'buyer' : 'buyers'} ·
                        weight {pain.score.toFixed(1)}
                      </span>
                    </div>
                    {pain.quotes.length > 0 && (
                      <ul className="mt-1 space-y-0.5">
                        {pain.quotes.map((quote, i) => (
                          <li
                            key={`${pain.key}-${i}`}
                            className="text-[12px] italic leading-relaxed text-saibyl-silver"
                          >
                            &ldquo;{quote}&rdquo;
                          </li>
                        ))}
                      </ul>
                    )}
                  </>
                ) : (
                  <p className="text-[12px] leading-relaxed text-saibyl-warning">
                    One of the objections this was built around has no touch in
                    the cadence below. Its copy came back empty or carrying
                    something we will not store, so it was dropped whole rather
                    than trimmed.
                  </p>
                )}
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* How finished it is */}
      {sequence.placeholders_to_fill > 0 ? (
        <div className="rounded-xl border border-[#f59e0b]/30 bg-[#f59e0b]/[0.07] p-3.5">
          <p className="text-[12.5px] leading-relaxed text-saibyl-warning">
            <span className="font-mono tabular-nums">
              {sequence.placeholders_to_fill}
            </span>{' '}
            blanks to fill before any of this goes out. Where a line needed a
            number, a customer or a benchmark your material did not carry, it
            says so instead of inventing one &mdash; the marked spans below.
          </p>
        </div>
      ) : (
        days.length > 0 && (
          <p className="text-[12px] leading-relaxed text-saibyl-positive">
            No blanks left. Every line stands on something your own material or
            the buyers&rsquo; own words already said.
          </p>
        )
      )}

      {/* The copy itself, by the day it goes out */}
      <ol className="space-y-4">
        {days.map((group) => (
          <li key={group.day}>
            <Eyebrow>Day {group.day}</Eyebrow>
            <ul className="mt-2 space-y-2">
              {group.touches.map((touch) => {
                const channel = CHANNELS[touch.channel];
                const Icon = channel?.Icon;
                const isCopied = copied === touch.step;
                return (
                  <li
                    key={touch.step}
                    className="rounded-xl border border-saibyl-border bg-white px-4 py-3.5"
                  >
                    <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
                      <span className="font-mono text-[10px] tabular-nums text-saibyl-muted">
                        {String(touch.step).padStart(2, '0')}
                      </span>
                      <span className="inline-flex items-center gap-1.5 text-[12.5px] font-semibold text-saibyl-ink">
                        {Icon && (
                          <Icon
                            aria-hidden
                            className="h-3.5 w-3.5 text-saibyl-muted"
                          />
                        )}
                        {channel?.label ?? touch.channel}
                      </span>
                      <button
                        type="button"
                        onClick={() => copyTouch(touch)}
                        className="ml-auto inline-flex items-center gap-1 rounded-lg border border-saibyl-border-light px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-saibyl-blue hover:bg-[#286cf0]/[0.06] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#286cf0]/50 motion-safe:transition-colors"
                      >
                        {isCopied ? (
                          <Check aria-hidden className="h-3 w-3" />
                        ) : (
                          <Copy aria-hidden className="h-3 w-3" />
                        )}
                        {isCopied ? 'Copied' : 'Copy'}
                      </button>
                    </div>

                    <p className="mt-1 text-[12px] leading-relaxed text-saibyl-muted">
                      {touch.purpose}
                    </p>

                    {touch.objection_label && (
                      <p className="mt-2 border-l-2 border-[#8b73ee]/45 pl-2.5 text-[11.5px] leading-relaxed text-[#6a4fe0]">
                        {touch.angle ? ANGLE_COPY[touch.angle] : 'Answers'}:{' '}
                        <span className="text-saibyl-ink">
                          {touch.objection_label}
                        </span>
                      </p>
                    )}

                    {touch.subject && (
                      <p className="mt-2.5 text-[12.5px] font-medium text-saibyl-ink">
                        <span className="font-mono text-[9.5px] uppercase tracking-[0.14em] text-saibyl-muted">
                          Subject
                        </span>{' '}
                        {touch.subject}
                      </p>
                    )}

                    <CopyBlock text={touch.body} />
                  </li>
                );
              })}
            </ul>
          </li>
        ))}
      </ol>

      {sequence.notes.length > 0 && (
        <ul className="space-y-1">
          {sequence.notes.map((note, i) => (
            <li
              key={`${sequence.archetype_id}-${i}`}
              className="text-[11.5px] leading-relaxed text-saibyl-muted"
            >
              {note}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  The panel                                                          */
/* ------------------------------------------------------------------ */

export default function OutboundPanel({ simulationId }: { simulationId: string }) {
  const prices = usePrices() as PricesWithOutbound | null;
  const [build, setBuild] = useState<OutboundBuild | null>(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<{ message: string; billing: boolean } | null>(null);
  const [openBuyer, setOpenBuyer] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  const load = useCallback(
    async (quiet = false) => {
      try {
        const { data } = await api.get<OutboundBuild>(
          `/outbound/by-simulation/${simulationId}`,
        );
        setBuild(data);
        return data;
      } catch (err) {
        // A 404 is the ordinary state before the first build, not a failure.
        const status = err instanceof AxiosError ? err.response?.status : undefined;
        if (status !== 404 && !quiet) {
          setError({
            message: getErrorMessage(err, 'We could not load your sequences.'),
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
    if (!build || (build.status !== 'queued' && build.status !== 'building')) return;
    timer.current = window.setTimeout(() => void load(true), POLL_MS);
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [build, load]);

  const start = async () => {
    setStarting(true);
    setError(null);
    try {
      const { data } = await api.post<OutboundBuild>('/outbound', {
        simulation_id: simulationId,
      });
      setBuild(data);
      setOpenBuyer(null);
    } catch (err) {
      const status = err instanceof AxiosError ? err.response?.status : undefined;
      setError({
        message: getErrorMessage(err, 'We could not start writing your sequences.'),
        billing: status === 402,
      });
    } finally {
      setStarting(false);
    }
  };

  if (loading) return null;

  const inFlight = build?.status === 'queued' || build?.status === 'building';
  const complete = build?.status === 'complete';
  const sequences = build?.sequences ?? [];

  /* Which buyer type is on screen. Derived rather than synced in an effect: an
     effect that copies a prop into state renders the stale value once, and the
     one it would render here is another buyer's fortnight. */
  const shown =
    sequences.find((s) => s.archetype_id === openBuyer) ?? sequences[0] ?? null;

  const written = shortDate(build?.completed_at ?? null);
  const started = shortDate(build?.created_at ?? null);
  const when = written ? `written ${written}` : started ? `started ${started}` : null;

  /* What it costs, said before the founder spends anything. `PriceTag` takes
     over the moment `/billing/prices` starts carrying an entry for this. */
  const price = prices?.outbound_sequence ? (
    <PriceTag entry={prices.outbound_sequence} />
  ) : (
    <p className="text-[12px] text-saibyl-silver">
      Credits are charged once, when the writing starts.
    </p>
  );

  return (
    <section className="rounded-xl border border-saibyl-border bg-white bg-[radial-gradient(circle_at_92%_0%,rgba(127,184,255,0.16),transparent_20rem)] p-5 shadow-[0_14px_44px_rgba(57,91,146,0.06)] space-y-4">
      <div>
        <Eyebrow>Cold outreach</Eyebrow>
        <h2 className="mt-1.5 text-[16px] font-semibold text-saibyl-ink">
          Two weeks of outreach, aimed at{' '}
          <em className="font-serif italic text-[#6a4fe0]">
            what they actually said
          </em>
          .
        </h2>
        <p className="mt-1.5 max-w-2xl text-[12.5px] leading-relaxed text-saibyl-muted">
          Every outbound playbook hands you the same skeleton and leaves the
          hardest part blank: which three pains to hit. You fill it by guessing,
          and a sequence built on guessed pain is one your list learns to
          ignore. Saibyl already measured the pain, so the slots are filled from
          the ranking the room set &mdash; hardest first, with the buyers&rsquo;
          own sentences attached.
        </p>
        <p className="mt-1.5 max-w-2xl text-[12.5px] leading-relaxed text-saibyl-muted">
          The cadence is fixed and ours: up to sixteen touches over fourteen
          days, three channels, each measured objection answered twice on two
          channels with a different framing the second time. Only the words are
          written for you, so there is nothing here that can quietly shrink to
          the four touches most sequences stop at.
        </p>
      </div>

      {error && (
        <div className="rounded-xl border border-saibyl-negative/25 bg-saibyl-negative/[0.07] p-4">
          <p className="text-[13px] leading-relaxed text-saibyl-negative">
            {error.message}
          </p>
          {error.billing && (
            <Link
              to="/app/settings"
              className="mt-2.5 inline-block text-[12px] font-semibold text-saibyl-blue hover:underline"
            >
              Add credits
            </Link>
          )}
        </div>
      )}

      {build?.status === 'failed' && (
        <div className="rounded-xl border border-saibyl-negative/25 bg-saibyl-negative/[0.07] p-4">
          <p className="text-[13px] leading-relaxed text-saibyl-negative">
            {build.error_message ?? 'We could not write your sequences.'}
          </p>
        </div>
      )}

      {inFlight && (
        <p
          className="flex items-center gap-2 text-[13px] text-saibyl-silver"
          aria-live="polite"
        >
          <span
            aria-hidden="true"
            className="h-[7px] w-[7px] shrink-0 rounded-full bg-saibyl-cyan motion-safe:animate-[pulse-dot_1.7s_ease-in-out_infinite]"
          />
          Writing the fortnight, one buyer type at a time…
        </p>
      )}

      {!complete && !inFlight && (
        <div>
          <div className="mb-3">{price}</div>
          <Guarded
            label="Write the sequences"
            onClick={start}
            busy={starting}
            busyLabel="Starting…"
          />
        </div>
      )}

      {complete && build && (
        <>
          {/* Where this came from and what it cost — the provenance a founder
              needs to trust the copy and to know it is not free. */}
          <p className="text-[11.5px] leading-relaxed text-saibyl-muted">
            Built from{' '}
            <span className="font-mono tabular-nums">
              {build.built_from_objections}
            </span>{' '}
            measured{' '}
            {build.built_from_objections === 1 ? 'objection' : 'objections'}
            {sequences.length > 0 && (
              <>
                {' '}
                for{' '}
                <span className="font-mono tabular-nums">{sequences.length}</span>{' '}
                of your buyer types
              </>
            )}
            {build.credits_charged > 0 && (
              <> · {formatCredits(build.credits_charged)} credits</>
            )}
            {when && <> · {when}</>}
          </p>

          {/* The message the room picked, if the scoreboard was willing to name
              one. Null is the common and honest state, and the note below says
              so rather than leaving the absence to be read as a bug. */}
          {build.winning_message && (
            <div className="rounded-xl border border-saibyl-border bg-saibyl-elevated p-4">
              <Eyebrow>
                The version your room picked
                {build.winning_variant_key
                  ? ` · ${build.winning_variant_key.toUpperCase()}`
                  : ''}
              </Eyebrow>
              <p className="mt-1.5 text-[12px] leading-relaxed text-saibyl-muted">
                The opening touches lead with this argument, in these words
                where they fit.
              </p>
              <p className="mt-2 border-l-2 border-saibyl-border-light pl-3 text-[12.5px] italic leading-relaxed text-saibyl-silver">
                {build.winning_message}
              </p>
            </div>
          )}

          {sequences.length === 0 && (
            <p className="text-[12.5px] leading-relaxed text-saibyl-warning">
              This finished without producing a sequence. That is a fault on our
              side, not a state you caused &mdash; write them again, and if it
              happens twice tell us and we will look.
            </p>
          )}

          {/* One buyer type at a time. Sixteen touches × four buyer types is
              sixty-four blocks of copy, and a flat list of that is a document
              nobody reads.

              Toggle buttons rather than ARIA tabs on purpose: a tablist owes
              the reader roving tabindex and arrow-key movement, and a
              half-implemented one is worse for a screen reader than an honest
              group of buttons that every keyboard already reaches. */}
          {sequences.length > 1 && (
            <div
              role="group"
              aria-label="Choose a buyer type"
              className="flex flex-wrap gap-2"
            >
              {sequences.map((sequence) => {
                const isShown = shown?.archetype_id === sequence.archetype_id;
                return (
                  <button
                    key={sequence.archetype_id}
                    type="button"
                    aria-pressed={isShown}
                    onClick={() => setOpenBuyer(sequence.archetype_id)}
                    className={`inline-flex items-center gap-2 rounded-xl px-3.5 py-1.5 text-[12.5px] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#286cf0]/50 motion-safe:transition-colors ${
                      isShown
                        ? 'border border-saibyl-border-light bg-white font-semibold text-saibyl-ink'
                        : 'border border-saibyl-border text-saibyl-muted hover:text-saibyl-ink'
                    }`}
                  >
                    <span
                      aria-hidden="true"
                      className={`h-[7px] w-[7px] shrink-0 rounded-full ${
                        isShown ? 'bg-saibyl-violet' : 'bg-saibyl-border-light'
                      }`}
                    />
                    {sequence.archetype_label}
                  </button>
                );
              })}
            </div>
          )}

          {shown && <SequenceView sequence={shown} />}

          {build.notes.length > 0 && (
            <ul className="space-y-1">
              {build.notes.map((note, i) => (
                <li
                  key={`${build.id}-${i}`}
                  className="text-[11.5px] leading-relaxed text-saibyl-muted"
                >
                  {note}
                </li>
              ))}
            </ul>
          )}

          {/* The boundary, stated where a founder is about to act on the copy
              rather than buried in a policy page. */}
          <p className="max-w-2xl text-[11.5px] leading-relaxed text-saibyl-muted">
            Saibyl sends none of this and holds no list. The only
            personalization the copy carries is{' '}
            {MERGE_TOKENS.map((token, i) => (
              <span key={token}>
                {i > 0 ? ', ' : ''}
                <span className="font-mono text-[11px] text-saibyl-silver">
                  {token}
                </span>
              </span>
            ))}{' '}
            &mdash; tokens, never values. You fill them in your own tooling, from
            your own contacts, and it goes out of your own inbox. Deliverability
            and inbox warm-up are yours too: they are the constraint that
            silently caps a whole engine, and we can neither see nor fix them
            from here.
          </p>

          <div className="border-t border-saibyl-border pt-4">
            <p className="mb-2.5 max-w-2xl text-[12px] leading-relaxed text-saibyl-muted">
              Answered one of these objections since? Write them again and the
              pains re-rank against what the room says now. This set stays on
              record as what you were sending before.
            </p>
            <div className="mb-3">{price}</div>
            <Guarded
              label="Write them again"
              onClick={start}
              busy={starting}
              busyLabel="Starting…"
              tone="quiet"
            />
          </div>
        </>
      )}
    </section>
  );
}
