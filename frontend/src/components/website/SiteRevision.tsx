import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertTriangle,
  ArrowDown,
  ArrowRight,
  ArrowUp,
  Check,
  Download,
  Loader2,
  Minus,
} from 'lucide-react';

import api from '@/lib/api';
import { scoreText } from './score';
import { DimensionCard } from './SiteCritique';
import {
  REVISION_PATH,
  dimensionWords,
  fixPrompts,
  overallScore,
  scoreDeltas,
  unsupportedClaims,
  type SiteRevisionRow,
  type UnsupportedClaim,
} from './types';

/**
 * A finished draft of the improved page: the numbers first, then the proof.
 *
 * The delta leads because it is the whole point — the same reviewers read
 * both pages, and the difference is the product's claim made measurable. An
 * unmoved or worse number renders as plainly as a better one; the honesty is
 * the feature.
 *
 * Every binary here — the two screenshots, the page itself — sits behind the
 * API's bearer token, which travels in a header the browser will not attach
 * to a plain link or `<img src>`. So each is fetched through the api client
 * and handed to the browser as a Blob URL. The page's code is fetched once
 * and shared by "open" and "copy"; the open control is a real anchor to the
 * Blob URL rather than a scripted `window.open`, so no popup blocker gets a
 * vote.
 */

const quietBtn =
  'inline-flex items-center gap-1.5 px-4 py-2 rounded-xl border border-saibyl-border-light text-saibyl-platinum text-[13px] hover:bg-[#14294a]/[0.04] transition-colors';

/* ------------------------------------------------------------------ */
/*  Small pieces                                                       */
/* ------------------------------------------------------------------ */

/** One of the two page pictures, labelled plainly. */
function Shot({
  label,
  url,
  failed,
}: {
  label: string;
  url?: string;
  failed?: boolean;
}) {
  return (
    <figure className="rounded-xl border border-saibyl-border bg-white overflow-hidden">
      <figcaption className="px-3 py-2 text-[11px] font-medium uppercase tracking-wider text-saibyl-silver border-b border-saibyl-border">
        {label}
      </figcaption>
      {url ? (
        <img
          src={url}
          alt={label === 'Before' ? 'The page as it is now' : 'The improved page'}
          className="block w-full h-auto"
        />
      ) : failed ? (
        <p className="p-4 text-[12px] text-saibyl-muted leading-relaxed">
          The picture did not come back &mdash; the numbers above still stand.
        </p>
      ) : (
        <p className="flex items-center gap-2 p-4 text-[12px] text-saibyl-muted">
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          Getting the picture&hellip;
        </p>
      )}
    </figure>
  );
}

/** Copy one prompt block. Failure is stated in words, never a dead control. */
function CopyPromptButton({ text }: { text: string }) {
  const [state, setState] = useState<'idle' | 'done' | 'failed'>('idle');
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setState('done');
    } catch {
      setState('failed');
    }
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setState('idle'), 2500);
  }

  if (state === 'done') {
    return (
      <span className="inline-flex items-center gap-1.5 text-[12px] text-saibyl-positive">
        <Check className="w-3.5 h-3.5" />
        Copied.
      </span>
    );
  }
  if (state === 'failed') {
    return (
      <span className="text-[12px] text-saibyl-negative">
        Copy did not reach your clipboard &mdash; select the text and copy it.
      </span>
    );
  }
  return (
    <button
      type="button"
      onClick={() => void copy()}
      className="text-[12px] text-saibyl-gold hover:underline"
    >
      Copy
    </button>
  );
}

/* ------------------------------------------------------------------ */
/*  The finished draft                                                 */
/* ------------------------------------------------------------------ */

export default function SiteRevision({
  revision,
  snapshotId,
}: {
  revision: SiteRevisionRow;
  /** The check this draft improves on — where the "before" picture lives. */
  snapshotId: string;
}) {
  const [shots, setShots] = useState<{
    before?: string;
    after?: string;
    beforeFailed?: boolean;
    afterFailed?: boolean;
  }>({});
  const [html, setHtml] = useState<{ text: string; url: string } | null>(null);
  const [htmlState, setHtmlState] = useState<'loading' | 'ready' | 'failed'>(
    'loading',
  );
  const [copyState, setCopyState] = useState<'idle' | 'busy' | 'done' | 'failed'>(
    'idle',
  );
  const [saveState, setSaveState] = useState<'idle' | 'busy' | 'failed'>('idle');

  /* Every Blob URL this component mints, revoked together on unmount. */
  const objectUrls = useRef<string[]>([]);
  const mint = useCallback((blob: Blob): string => {
    const url = URL.createObjectURL(blob);
    objectUrls.current.push(url);
    return url;
  }, []);
  useEffect(
    () => () => {
      for (const url of objectUrls.current) URL.revokeObjectURL(url);
      objectUrls.current = [];
    },
    [],
  );

  /* The two pictures. Authed endpoints, so fetched — not linked. A failed one
     degrades to a sentence in its frame; the other still renders. */
  useEffect(() => {
    let alive = true;
    const load = (path: string, which: string, key: 'before' | 'after') =>
      api
        .get<Blob>(path, { params: { which }, responseType: 'blob' })
        .then(({ data }) => {
          if (alive) setShots((s) => ({ ...s, [key]: mint(data) }));
        })
        .catch(() => {
          if (alive) setShots((s) => ({ ...s, [`${key}Failed`]: true }));
        });
    void load(`/website/check/${snapshotId}/screenshot`, 'desktop', 'before');
    void load(
      `${REVISION_PATH}/${revision.id}/screenshot`,
      'after_desktop',
      'after',
    );
    return () => {
      alive = false;
    };
  }, [snapshotId, revision.id, mint]);

  /* The page's code, fetched once and shared by "open" and "copy". Prefetched
     so the open control can be a real anchor to a Blob URL. All state moves
     happen in the promise's own callbacks — the initial state is already
     'loading', and only the retry click (below) needs to say so again. */
  const fetchHtml = useCallback(() => {
    return api
      .get<string>(`${REVISION_PATH}/${revision.id}/html`, {
        responseType: 'text',
        transformResponse: [(data: unknown) => data],
      })
      .then(({ data }) => {
        const text = String(data);
        const loaded = {
          text,
          url: mint(new Blob([text], { type: 'text/html' })),
        };
        setHtml(loaded);
        setHtmlState('ready');
        return loaded;
      })
      .catch(() => {
        setHtmlState('failed');
        return null;
      });
  }, [revision.id, mint]);

  useEffect(() => {
    void fetchHtml();
  }, [fetchHtml]);

  function retryHtml() {
    setHtmlState('loading');
    void fetchHtml();
  }

  /* The page and its style guide, as one zip the founder keeps.
     Fetched rather than linked for the same reason as everything else here —
     the endpoint is behind the bearer token — and the filename comes from the
     server's Content-Disposition so the download is named for their own
     domain rather than for a row id. */
  async function saveBundle() {
    setSaveState('busy');
    try {
      const response = await api.get<Blob>(
        `${REVISION_PATH}/${revision.id}/bundle`,
        { responseType: 'blob' },
      );
      const named = /filename="([^"]+)"/.exec(
        String(response.headers['content-disposition'] ?? ''),
      );
      const link = document.createElement('a');
      link.href = mint(response.data);
      link.download = named?.[1] ?? 'redesign.zip';
      link.click();
      setSaveState('idle');
    } catch {
      setSaveState('failed');
    }
  }

  async function copyCode() {
    setCopyState('busy');
    try {
      const source = html ?? (await fetchHtml());
      if (!source) {
        setCopyState('failed');
        return;
      }
      await navigator.clipboard.writeText(source.text);
      setCopyState('done');
    } catch {
      setCopyState('failed');
    }
    setTimeout(() => setCopyState('idle'), 2500);
  }

  const before = overallScore(revision.scores_before);
  const after = overallScore(revision.scores_after);
  const delta = before !== null && after !== null ? after - before : null;
  const deltas = scoreDeltas(revision.scores_before, revision.scores_after);
  const rounds = Number(revision.rounds);
  const bestRound = Number(revision.best_round);
  const prompts = fixPrompts(revision);
  const claims = unsupportedClaims(revision);
  const critiqueAfter =
    revision.critique_after &&
    Array.isArray(revision.critique_after.dimensions)
      ? revision.critique_after
      : null;
  const takeaway = critiqueAfter?.page_takeaway?.trim();

  const headerTone =
    delta === null || delta === 0
      ? 'border-saibyl-border bg-white'
      : delta > 0
        ? 'border-saibyl-positive/30 bg-saibyl-positive/[0.07]'
        : 'border-saibyl-negative/30 bg-saibyl-negative/[0.07]';

  return (
    <div className="space-y-4">
      {/* ── The numbers ── */}
      <div className={`rounded-2xl border p-6 ${headerTone}`}>
        {after === null && before === null ? (
          <p className="text-[13px] text-saibyl-warning leading-relaxed">
            The new page is drafted, but its scores did not come back with it.
            The page itself is below, and a refresh may bring the numbers up.
          </p>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              {before !== null && (
                <>
                  <span className="text-[26px] font-semibold leading-none text-saibyl-muted">
                    {before}
                  </span>
                  <ArrowRight className="w-4 h-4 text-saibyl-muted" />
                </>
              )}
              {after !== null && (
                <span
                  className={`text-[34px] font-semibold leading-none ${scoreText(after)}`}
                >
                  {after}
                </span>
              )}
              {delta !== null &&
                (delta === 0 ? (
                  <span className="text-[12px] text-saibyl-muted">
                    No change
                  </span>
                ) : (
                  <span
                    className={`text-[22px] font-semibold ${
                      delta > 0 ? 'text-saibyl-positive' : 'text-saibyl-negative'
                    }`}
                  >
                    {delta > 0 ? `+${delta}` : delta}
                  </span>
                ))}
            </div>
            <p className="text-[12px] text-saibyl-muted mt-1.5">
              out of 100 &mdash; the same reviewers scored both pages
            </p>
          </>
        )}

        {Number.isFinite(rounds) && rounds > 1 && (
          <p className="text-[11px] text-saibyl-muted/70 mt-2.5">
            {Number.isFinite(bestRound) && bestRound >= 1
              ? `Took ${rounds} passes; pass ${bestRound} scored best.`
              : `Took ${rounds} passes.`}
          </p>
        )}

        {takeaway && (
          <div className="mt-4">
            <p className="text-[11px] font-medium text-saibyl-silver uppercase tracking-wider">
              What a first-time reader takes away now
            </p>
            <p className="text-[13.5px] text-saibyl-platinum mt-1 leading-relaxed">
              &ldquo;{takeaway}&rdquo;
            </p>
          </div>
        )}

        {deltas.length > 0 && (
          <ul className="mt-4 pt-3 border-t border-saibyl-border space-y-1.5">
            {deltas.map(({ key, before: b, after: a }) => {
              const d = b !== null && a !== null ? a - b : null;
              return (
                <li
                  key={key}
                  className="flex items-center justify-between gap-3 text-[12.5px]"
                >
                  <span className="text-saibyl-silver truncate">
                    {dimensionWords(key).name}
                  </span>
                  <span className="flex items-center gap-1.5 shrink-0">
                    <span className="font-mono text-[11.5px] text-saibyl-muted">
                      {b ?? '—'} &rarr; {a ?? '—'}
                    </span>
                    {d === null ? null : d > 0 ? (
                      <ArrowUp className="w-3 h-3 text-saibyl-positive" />
                    ) : d < 0 ? (
                      <ArrowDown className="w-3 h-3 text-saibyl-negative" />
                    ) : (
                      <Minus className="w-3 h-3 text-saibyl-muted" />
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* ── Claims the new page makes that the old one never made ──
          Directly under the score on purpose. The score is the thing a founder
          reads first and trusts most, and it is precisely the number that
          cannot see this: the reviewers judge a screenshot of the new page and
          never read the old page's facts, so on the run that produced this
          check they scored an invented SOC 2 badge *up*. The warning has to sit
          against the number it contradicts, not below the fold. */}
      {claims.length > 0 && <ClaimsWarning claims={claims} />}

      {/* ── The proof, side by side ── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">
        <Shot label="Before" url={shots.before} failed={shots.beforeFailed} />
        <Shot label="After" url={shots.after} failed={shots.afterFailed} />
      </div>

      {/* ── The page itself ── */}
      <div className="flex flex-wrap items-center gap-3">
        {htmlState === 'ready' && html ? (
          <a
            href={html.url}
            target="_blank"
            rel="noopener noreferrer"
            className={quietBtn}
          >
            Open the new page
            <ArrowRight className="w-3.5 h-3.5" />
          </a>
        ) : htmlState === 'loading' ? (
          <span className={`${quietBtn} opacity-70`} aria-live="polite">
            Getting the new page ready&hellip;
          </span>
        ) : (
          <button type="button" onClick={retryHtml} className={quietBtn}>
            The new page did not come back &mdash; try again
          </button>
        )}

        {copyState === 'busy' ? (
          <span className={`${quietBtn} opacity-70`} aria-live="polite">
            Copying&hellip;
          </span>
        ) : copyState === 'done' ? (
          <span className="inline-flex items-center gap-1.5 text-[12.5px] text-saibyl-positive">
            <Check className="w-3.5 h-3.5" />
            Copied &mdash; paste it into your coding tool.
          </span>
        ) : (
          <button
            type="button"
            onClick={() => void copyCode()}
            className={quietBtn}
          >
            Copy the page&rsquo;s code
          </button>
        )}

        {saveState === 'busy' ? (
          <span className={`${quietBtn} opacity-70`} aria-live="polite">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            Packing it up&hellip;
          </span>
        ) : (
          <button
            type="button"
            onClick={() => void saveBundle()}
            className={quietBtn}
          >
            <Download className="w-3.5 h-3.5" />
            Download the page &amp; style guide
          </button>
        )}
      </div>
      {saveState === 'failed' && (
        <p className="text-[12px] text-saibyl-negative leading-relaxed">
          The download did not come back &mdash; try it again, or copy the
          page&rsquo;s code above in the meantime.
        </p>
      )}
      {copyState === 'failed' && (
        <p className="text-[12px] text-saibyl-negative leading-relaxed">
          Copy did not reach your clipboard &mdash; open the new page and copy
          it from there.
        </p>
      )}

      {/* ── Do it yourself instead ── */}
      {prompts.length > 0 && (
        <div className="rounded-xl border border-saibyl-border bg-white p-4">
          <p className="text-[13.5px] font-medium text-saibyl-platinum">
            Prefer to fix it yourself?
          </p>
          <p className="text-[12px] text-saibyl-muted mt-0.5 leading-relaxed">
            Paste these into your coding tool.
          </p>
          <div className="mt-3 space-y-2">
            {prompts.map((prompt, i) => (
              <details
                key={`${prompt.title}-${i}`}
                className="rounded-lg border border-saibyl-border bg-saibyl-elevated"
              >
                <summary className="cursor-pointer select-none px-3 py-2.5 text-[12.5px] font-medium text-saibyl-platinum hover:text-saibyl-blue">
                  {prompt.title}
                </summary>
                <div className="px-3 pb-3">
                  {prompt.scope && (
                    <p className="font-mono text-[10.5px] text-saibyl-muted/70">
                      {prompt.scope}
                    </p>
                  )}
                  <pre className="mt-2 rounded-md border border-saibyl-border-light bg-white p-3 font-mono text-[11.5px] text-saibyl-platinum leading-relaxed whitespace-pre-wrap break-words overflow-x-auto">
                    {prompt.prompt}
                  </pre>
                  <div className="mt-2">
                    <CopyPromptButton text={prompt.prompt} />
                  </div>
                </div>
              </details>
            ))}
          </div>
        </div>
      )}

      {/* ── What still stands against it ── */}
      {critiqueAfter && critiqueAfter.dimensions.length > 0 && (
        <details>
          <summary className="cursor-pointer text-[12.5px] text-saibyl-gold hover:underline select-none">
            What the reviewers still flagged on the new page
          </summary>
          <div className="mt-3 grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
            {critiqueAfter.dimensions.map((dimension) => (
              <DimensionCard key={dimension.key} dimension={dimension} />
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

const CLAIM_GROUPS: { kind: string; heading: string }[] = [
  { kind: 'certification', heading: 'Certifications, licences and regulators' },
  { kind: 'figure', heading: 'Prices and percentages' },
  { kind: 'scale', heading: 'Customer counts' },
];

/**
 * Statements on the new page that the founder's own page never made.
 *
 * Deliberately not a red error box. Some of these will be true and simply
 * absent from the page we read — a founder who genuinely holds SOC 2 but never
 * said so on their homepage should be prompted to say it somewhere provable,
 * not accused. The heading asks them to check; the certification group alone
 * gets the harder sentence, because that is the one a customer or a regulator
 * acts on.
 *
 * Never collapsed behind a `<details>`: a warning a founder has to click to
 * discover is a warning they publish without.
 */
function ClaimsWarning({ claims }: { claims: UnsupportedClaim[] }) {
  const known = new Set(CLAIM_GROUPS.map((g) => g.kind));
  const groups = CLAIM_GROUPS.map(({ kind, heading }) => ({
    heading,
    kind,
    rows: claims.filter((c) => c.kind === kind),
  }))
    // A kind this build has never heard of still describes a real claim, so it
    // is shown rather than dropped.
    .concat({
      heading: 'Other claims',
      kind: 'other',
      rows: claims.filter((c) => !known.has(c.kind)),
    })
    .filter((g) => g.rows.length > 0);

  const forged = claims.some((c) => c.kind === 'certification');

  return (
    <div className="rounded-2xl border border-saibyl-warning/40 bg-saibyl-warning/[0.06] p-5">
      <div className="flex items-start gap-2.5">
        <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0 text-saibyl-warning" />
        <div className="min-w-0">
          <p className="text-[13px] font-medium text-saibyl-platinum">
            Check these before you publish
          </p>
          <p className="text-[12.5px] text-saibyl-silver mt-1 leading-relaxed">
            The rewrite put the statements below on your page, and none of them
            appear in the words we read off your current site. Some may be true
            and simply missing from the page we captured &mdash; if so, this is
            your reminder to say them somewhere provable. Anything that
            isn&rsquo;t true has to come out first.
          </p>
          {forged && (
            <p className="text-[12.5px] text-saibyl-platinum mt-2 leading-relaxed">
              A certification, licence or regulator named on a page you
              haven&rsquo;t earned isn&rsquo;t a wording problem &mdash;
              customers and regulators act on it.
            </p>
          )}

          {groups.map((group) => (
            <div key={group.kind} className="mt-3.5">
              <p className="text-[11px] font-medium text-saibyl-silver uppercase tracking-wider">
                {group.heading}
              </p>
              <ul className="mt-1.5 space-y-1.5">
                {group.rows.map((claim, index) => (
                  <li
                    key={`${claim.kind}-${claim.text}-${index}`}
                    className="text-[12.5px] leading-relaxed"
                  >
                    <span className="font-medium text-saibyl-platinum">
                      {claim.text}
                    </span>
                    {claim.quote && (
                      <span className="text-saibyl-muted">
                        {' '}
                        &mdash; on the page as: &ldquo;{claim.quote}&rdquo;
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
