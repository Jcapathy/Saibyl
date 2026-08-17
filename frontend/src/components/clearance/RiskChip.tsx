import type { ClearanceStatus, RiskTier } from './types';

/**
 * The two chips every clearance surface shares.
 *
 * Risk uses the codebase's status colours — positive green, warning amber,
 * negative red — so a founder who has read one Saibyl report already knows
 * what these mean. The words stay the skill's own tier words rather than a
 * softened synonym: a report that says RED should have a chip that says Red.
 */

const RISK_STYLES: Record<RiskTier, string> = {
  GREEN: 'border-saibyl-green/40 bg-saibyl-green/10 text-saibyl-positive',
  YELLOW: 'border-[#f59e0b]/40 bg-[#f59e0b]/10 text-saibyl-warning',
  RED: 'border-saibyl-rose/40 bg-saibyl-rose/10 text-saibyl-negative',
};

const RISK_WORDS: Record<RiskTier, string> = {
  GREEN: 'Green',
  YELLOW: 'Yellow',
  RED: 'Red',
};

export function RiskChip({ risk }: { risk: RiskTier }) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full border font-mono text-[10px] font-semibold uppercase tracking-widest ${RISK_STYLES[risk]}`}
    >
      {RISK_WORDS[risk]}
    </span>
  );
}

/* ------------------------------------------------------------------ */

const STATUS_STYLES: Record<ClearanceStatus, string> = {
  queued: 'border-saibyl-border-light bg-[#14294a]/[0.04] text-saibyl-silver',
  running: 'border-saibyl-gold/40 bg-saibyl-gold/10 text-saibyl-gold',
  complete: 'border-saibyl-green/40 bg-saibyl-green/10 text-saibyl-positive',
  failed: 'border-saibyl-rose/40 bg-saibyl-rose/10 text-saibyl-negative',
};

const STATUS_WORDS: Record<ClearanceStatus, string> = {
  queued: 'Waiting',
  running: 'Searching',
  complete: 'Done',
  failed: 'Did not finish',
};

export function StatusChip({ status }: { status: ClearanceStatus }) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full border text-[10.5px] font-medium ${STATUS_STYLES[status]}`}
    >
      {STATUS_WORDS[status]}
    </span>
  );
}
