import { SeverityChip } from './chips';
import {
  dimensionWords,
  type SiteCheck,
  type SiteDimension,
  type SiteFinding,
} from './types';

/**
 * A finished site check, rendered from the row and nothing else.
 *
 * The overall score leads, the takeaway sentence sits beside it — that
 * sentence is the whole product in miniature: what a stranger actually took
 * away from the page, which is rarely what the founder meant. Five cards
 * follow, one per way of looking at the page, each with what to fix and what
 * to keep. Every finding carries the page's own words as evidence, so nothing
 * here asks to be taken on faith.
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

/* ------------------------------------------------------------------ */
/*  One finding                                                        */
/* ------------------------------------------------------------------ */

function Finding({ finding }: { finding: SiteFinding }) {
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
      {finding.quote && (
        <p className="text-[12.5px] italic text-saibyl-silver mt-2 leading-relaxed">
          &ldquo;{finding.quote}&rdquo;
        </p>
      )}
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
            <Finding key={`${dimension.key}-${i}`} finding={finding} />
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

      {/* ── The five ways of looking at it ── */}
      {critique.dimensions.map((dimension) => (
        <DimensionCard key={dimension.key} dimension={dimension} />
      ))}
    </div>
  );
}
