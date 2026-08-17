import { SeverityChip } from './chips';
import {
  dimensionWords,
  isDesignDimension,
  maturityLevel,
  type SiteCheck,
  type SiteDimension,
  type SiteFinding,
} from './types';

/**
 * A finished site check, rendered from the row and nothing else.
 *
 * The overall score leads, the takeaway sentence sits beside it — that
 * sentence is the whole product in miniature: what a stranger actually took
 * away from the page, which is rarely what the founder meant. Six cards
 * follow, one per way of looking at the page, each with what to fix and what
 * to keep. Every finding carries the page's own words as evidence, so nothing
 * here asks to be taken on faith.
 *
 * The design card is the newest of the six and the only one whose evidence is
 * a measurement rather than a sentence off the page — "your value, theirs" —
 * so its quotes render in the mono style the codebase already uses for
 * numbers, not in quotation marks. When the founder named a site they admire,
 * the banner says whose numbers theirs were held against, and the design card
 * leads the grid because it is the card that comparison produced.
 *
 * A failed check renders the API's own sentence with a way forward, because a
 * dead end after handing over an address is where a founder closes the tab.
 */

const SEVERITY_ORDER: Record<string, number> = { critical: 0, major: 1, minor: 2 };

/** Findings shown before the rest fold away. */
const VISIBLE_FINDINGS = 3;

function scoreText(score: number): string {
  if (score >= 75) return 'text-saibyl-positive';
  if (score >= 50) return 'text-saibyl-warning';
  return 'text-saibyl-negative';
}

function bannerTone(score: number): string {
  if (score >= 75) return 'border-saibyl-positive/30 bg-saibyl-positive/[0.07]';
  if (score >= 50) return 'border-saibyl-warning/30 bg-saibyl-warning/[0.07]';
  return 'border-saibyl-negative/30 bg-saibyl-negative/[0.07]';
}

/**
 * The reference site's hostname, for the "Measured against" line.
 *
 * The form always stores the address with a scheme, but this row could have
 * been written by an older worker or a bare-handed API call, so a schemeless
 * or unparseable address degrades to being shown as it was stored rather
 * than throwing away the whole critique.
 */
function referenceHostname(url: string): string {
  try {
    const parsed = new URL(/^[a-z][a-z0-9+.-]*:/i.test(url) ? url : `https://${url}`);
    return parsed.hostname || url;
  } catch {
    return url;
  }
}

/* ------------------------------------------------------------------ */
/*  One finding                                                        */
/* ------------------------------------------------------------------ */

function Finding({
  finding,
  measured = false,
}: {
  finding: SiteFinding;
  /**
   * True on the design card, where `quote` is not the page's words but the
   * measurement — "your value, theirs". Numbers render in the codebase's
   * mono idiom, on the input-well background, and without quotation marks:
   * quoting a measurement would present it as prose.
   */
  measured?: boolean;
}) {
  return (
    <li className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
      <div className="flex flex-wrap items-center gap-2">
        <SeverityChip severity={finding.severity} />
        {finding.region && (
          <span className="font-mono text-[10.5px] text-saibyl-muted/70 truncate">
            {finding.region}
          </span>
        )}
      </div>
      {finding.quote &&
        (measured ? (
          <p className="mt-2 rounded-md border border-white/[0.06] bg-[#0B1120] px-2.5 py-2 font-mono text-[11.5px] text-saibyl-platinum leading-relaxed">
            {finding.quote}
          </p>
        ) : (
          <p className="text-[12.5px] italic text-saibyl-silver mt-2 leading-relaxed">
            &ldquo;{finding.quote}&rdquo;
          </p>
        ))}
      <p className="text-[12.5px] text-saibyl-muted mt-1.5 leading-relaxed">
        {finding.why}
      </p>
      <p className="text-[12.5px] text-saibyl-platinum mt-1.5 leading-relaxed">
        <span className="font-medium text-saibyl-gold">What to change: </span>
        {finding.fix}
      </p>
    </li>
  );
}

/* ------------------------------------------------------------------ */
/*  One dimension                                                      */
/* ------------------------------------------------------------------ */

function DimensionCard({ dimension }: { dimension: SiteDimension }) {
  const words = dimensionWords(dimension.key);
  const measured = isDesignDimension(dimension.key);
  // Worst first: the serious finding is the one worth the founder's next hour,
  // and the API's ordering is not guaranteed to agree.
  const ordered = [...dimension.findings].sort(
    (a, b) => (SEVERITY_ORDER[a.severity] ?? 3) - (SEVERITY_ORDER[b.severity] ?? 3),
  );
  const visible = ordered.slice(0, VISIBLE_FINDINGS);
  const rest = ordered.slice(VISIBLE_FINDINGS);

  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[13.5px] font-medium text-saibyl-platinum">
            {words.name}
          </p>
          {words.help && (
            <p className="text-[11.5px] text-saibyl-muted mt-0.5 leading-relaxed">
              {words.help}
            </p>
          )}
        </div>
        <p className="shrink-0 text-right">
          <span
            className={`text-[20px] font-semibold ${scoreText(dimension.score)}`}
          >
            {Math.round(dimension.score)}
          </span>
          <span className="text-[11px] text-saibyl-muted">/100</span>
        </p>
      </div>

      {ordered.length === 0 ? (
        <p className="text-[12px] text-saibyl-muted mt-3 leading-relaxed">
          Nothing on this front stopped a buyer.
        </p>
      ) : (
        <ul className="mt-3 space-y-2">
          {visible.map((finding, i) => (
            <Finding
              key={`${dimension.key}-${i}`}
              finding={finding}
              measured={measured}
            />
          ))}
        </ul>
      )}

      {rest.length > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer text-[12px] text-saibyl-gold hover:underline select-none">
            Show {rest.length} more
          </summary>
          <ul className="mt-2 space-y-2">
            {rest.map((finding, i) => (
              <Finding
                key={`${dimension.key}-more-${i}`}
                finding={finding}
                measured={measured}
              />
            ))}
          </ul>
        </details>
      )}

      {dimension.strengths.length > 0 && (
        <div className="mt-3 rounded-lg border border-saibyl-positive/25 bg-saibyl-positive/[0.05] p-3">
          <p className="text-[11px] font-medium text-saibyl-positive uppercase tracking-wider">
            Keep these
          </p>
          <ul className="mt-1.5 space-y-1">
            {dimension.strengths.map((s) => (
              <li key={s} className="text-[12.5px] text-saibyl-muted leading-relaxed">
                {s}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  The critique                                                       */
/* ------------------------------------------------------------------ */

export default function SiteCritique({
  check,
  onRetry,
}: {
  check: SiteCheck;
  /** Reopens the address form — the way forward from a check that died. */
  onRetry?: () => void;
}) {
  if (check.status === 'failed') {
    return (
      <div className="rounded-xl border border-saibyl-negative/25 bg-saibyl-negative/[0.07] p-4">
        <p className="text-[13px] text-saibyl-negative leading-relaxed">
          {check.error_message?.trim() ||
            'We could not read that page. The site may have been down for a moment, or it may be turning away readers like ours.'}
        </p>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="mt-2.5 text-[12px] text-saibyl-gold hover:underline"
          >
            Try the address again, or paste a different one
          </button>
        )}
      </div>
    );
  }

  if (check.status !== 'complete') return null;

  const critique = check.critique;
  if (!critique) {
    // The contract says complete carries a critique. If it ever does not,
    // say so rather than rendering a scoreless shell that reads as an answer.
    return (
      <div className="rounded-xl border border-saibyl-warning/30 bg-saibyl-warning/[0.07] p-4">
        <p className="text-[13px] text-saibyl-warning leading-relaxed">
          The check finished, but what it found did not come back with it.
          Refresh the page; if that does not bring it up, run the check again.
        </p>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="mt-2.5 text-[12px] text-saibyl-gold hover:underline"
          >
            Run the check again
          </button>
        )}
      </div>
    );
  }

  const overall = Math.round(critique.overall_score);

  const reference = check.reference_url?.trim() ?? '';
  const referenceHost = reference ? referenceHostname(reference) : null;
  const maturity = maturityLevel(check);

  // When the founder named a site to be measured against, the design card is
  // the card that comparison produced, so it leads. The sort is stable, so
  // the other five keep the API's order behind it.
  const dimensions = referenceHost
    ? [...critique.dimensions].sort(
        (a, b) =>
          Number(isDesignDimension(b.key)) - Number(isDesignDimension(a.key)),
      )
    : critique.dimensions;

  return (
    <div className="space-y-4">
      {/* ── The score and the takeaway ── */}
      <div className={`rounded-2xl border p-6 ${bannerTone(overall)}`}>
        <div className="flex flex-wrap items-baseline gap-2">
          <span
            className={`text-[34px] font-semibold leading-none ${scoreText(overall)}`}
          >
            {overall}
          </span>
          <span className="text-[12px] text-saibyl-muted">
            out of 100 &mdash; how the page held up under a buyer&rsquo;s eye
          </span>
        </div>
        {(referenceHost !== null || maturity !== null) && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 mt-2.5">
            {referenceHost !== null && (
              <p className="text-[11px] text-saibyl-muted/70">
                Measured against {referenceHost}
              </p>
            )}
            {maturity !== null && (
              <span
                title="Where the look sits on a seven-level ladder: 1 is untouched defaults, 7 is a look nobody could mistake for another site."
                className="inline-flex items-center px-2 py-0.5 rounded-full border border-white/[0.12] bg-white/[0.04] text-[10.5px] font-medium text-saibyl-silver"
              >
                Design maturity: level {maturity} of 7
              </span>
            )}
          </div>
        )}
        <div className="mt-4">
          <p className="text-[11px] font-medium text-saibyl-silver uppercase tracking-wider">
            What a first-time reader takes away
          </p>
          <p className="text-[13.5px] text-saibyl-platinum mt-1 leading-relaxed">
            &ldquo;{critique.page_takeaway}&rdquo;
          </p>
        </div>
        {check.document_id && (
          <p className="text-[11px] text-saibyl-muted/70 mt-3 leading-relaxed">
            The page&rsquo;s words have joined your product&rsquo;s material
            &mdash; the audience step reads them the same way it reads anything
            you upload.
          </p>
        )}
      </div>

      {/* ── The six ways of looking at it ── */}
      {/* Two columns once there is room, one on a phone. `items-start` keeps a
          short card from being stretched to its neighbour's height. */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
        {dimensions.map((dimension) => (
          <DimensionCard key={dimension.key} dimension={dimension} />
        ))}
      </div>
    </div>
  );
}
