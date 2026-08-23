import {
  revisionStatusWord,
  type SiteCheckStatus,
  type SiteFindingSeverity,
} from './types';

/**
 * The two chips of the site check, in the codebase's chip idiom — positive
 * green, warning amber, negative red — so a founder who has read one Saibyl
 * report already knows what these colours mean.
 *
 * Severity keeps plain words rather than the API's tier words: "critical"
 * reads like an incident page, and the person reading this built the site.
 */

const SEVERITY_STYLES: Record<SiteFindingSeverity, string> = {
  critical: 'border-saibyl-negative/40 bg-saibyl-negative/10 text-saibyl-negative',
  major: 'border-saibyl-warning/40 bg-saibyl-warning/10 text-saibyl-warning',
  minor: 'border-saibyl-border-light bg-[#14294a]/[0.04] text-saibyl-muted',
};

const SEVERITY_WORDS: Record<SiteFindingSeverity, string> = {
  critical: 'Serious',
  major: 'Worth fixing',
  minor: 'Small',
};

export function SeverityChip({ severity }: { severity: SiteFindingSeverity }) {
  const cls = SEVERITY_STYLES[severity] ?? SEVERITY_STYLES.minor;
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full border text-[10.5px] font-medium ${cls}`}
    >
      {SEVERITY_WORDS[severity] ?? severity}
    </span>
  );
}

/* ------------------------------------------------------------------ */

const STATUS_STYLES: Record<SiteCheckStatus, string> = {
  queued: 'border-saibyl-border-light bg-[#14294a]/[0.04] text-saibyl-silver',
  capturing: 'border-saibyl-blue/40 bg-saibyl-blue/10 text-saibyl-blue',
  judging: 'border-saibyl-blue/40 bg-saibyl-blue/10 text-saibyl-blue',
  complete: 'border-saibyl-positive/40 bg-saibyl-positive/10 text-saibyl-positive',
  failed: 'border-saibyl-negative/40 bg-saibyl-negative/10 text-saibyl-negative',
};

const STATUS_WORDS: Record<SiteCheckStatus, string> = {
  queued: 'Waiting',
  capturing: 'Reading the page',
  judging: 'Judging the page',
  complete: 'Done',
  failed: 'Did not finish',
};

export function SiteStatusChip({ status }: { status: SiteCheckStatus }) {
  const cls = STATUS_STYLES[status] ?? STATUS_STYLES.queued;
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full border text-[10.5px] font-medium ${cls}`}
    >
      {STATUS_WORDS[status] ?? status}
    </span>
  );
}

/* ------------------------------------------------------------------ */

/**
 * The draft's chip, in the same colours as the check's: gold while the worker
 * is on it, green when done, red when it died. Typed on `string` because the
 * revision contract is still settling — an unknown status renders in the
 * waiting style with the fallback words rather than throwing.
 */
const REVISION_STYLES: Record<string, string> = {
  queued: 'border-saibyl-border-light bg-[#14294a]/[0.04] text-saibyl-silver',
  generating: 'border-saibyl-blue/40 bg-saibyl-blue/10 text-saibyl-blue',
  judging: 'border-saibyl-blue/40 bg-saibyl-blue/10 text-saibyl-blue',
  complete: 'border-saibyl-positive/40 bg-saibyl-positive/10 text-saibyl-positive',
  failed: 'border-saibyl-negative/40 bg-saibyl-negative/10 text-saibyl-negative',
};

export function RevisionStatusChip({ status }: { status: string }) {
  const cls = REVISION_STYLES[status] ?? REVISION_STYLES.queued;
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full border text-[10.5px] font-medium ${cls}`}
    >
      {revisionStatusWord(status)}
    </span>
  );
}
