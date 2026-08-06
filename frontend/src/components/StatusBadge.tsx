import { ACTIVE_STATUSES } from '@/lib/constants';

const STATUS_CONFIG: Record<string, { bg: string; text: string; dot: string }> = {
  draft:          { bg: 'bg-[#8B5CF6]/10', text: 'text-[#8B5CF6]', dot: 'bg-[#8B5CF6]' },
  preparing:      { bg: 'bg-[#F59E0B]/10', text: 'text-[#F59E0B]', dot: 'bg-[#F59E0B]' },
  ready:          { bg: 'bg-[#2563EB]/10', text: 'text-[#2563EB]', dot: 'bg-[#2563EB]' },
  running:        { bg: 'bg-[#2563EB]/10', text: 'text-[#2563EB]', dot: 'bg-[#2563EB]' },
  analyzing:      { bg: 'bg-[#F59E0B]/10', text: 'text-[#F59E0B]', dot: 'bg-[#F59E0B]' },
  complete:       { bg: 'bg-[#22C55E]/10', text: 'text-[#22C55E]', dot: 'bg-[#22C55E]' },
  completed:      { bg: 'bg-[#22C55E]/10', text: 'text-[#22C55E]', dot: 'bg-[#22C55E]' },
  failed:         { bg: 'bg-[#EF4444]/10', text: 'text-[#EF4444]', dot: 'bg-[#EF4444]' },
  stopped:        { bg: 'bg-[#5A6578]/10', text: 'text-[#5A6578]', dot: 'bg-[#5A6578]' },
  pending:        { bg: 'bg-[#8B5CF6]/10', text: 'text-[#8B5CF6]', dot: 'bg-[#8B5CF6]' },
  pending_review: { bg: 'bg-[#8B5CF6]/10', text: 'text-[#8B5CF6]', dot: 'bg-[#8B5CF6]' },
  approved:       { bg: 'bg-[#22C55E]/10', text: 'text-[#22C55E]', dot: 'bg-[#22C55E]' },
  generating:     { bg: 'bg-[#8B5CF6]/10', text: 'text-[#8B5CF6]', dot: 'bg-[#8B5CF6]' },
  processing:     { bg: 'bg-[#F59E0B]/10', text: 'text-[#F59E0B]', dot: 'bg-[#F59E0B]' },
  active:         { bg: 'bg-[#22C55E]/10', text: 'text-[#22C55E]', dot: 'bg-[#22C55E]' },
  queued:         { bg: 'bg-[#F59E0B]/10', text: 'text-[#F59E0B]', dot: 'bg-[#F59E0B]' },
  archived:       { bg: 'bg-[#5A6578]/10', text: 'text-[#5A6578]', dot: 'bg-[#5A6578]' },
};

const DEFAULT_CONFIG = { bg: 'bg-[#5A6578]/10', text: 'text-[#5A6578]', dot: 'bg-[#5A6578]' };

/**
 * What each state is called on screen.
 *
 * The badge used to render `status.replace('_', ' ')` uppercased — the database
 * column, shown to a founder. Two consequences, both reported from the
 * deployed app: the same finished run read `COMPLETED` on one screen and
 * `COMPLETE` on another, because the table genuinely holds both spellings; and
 * `ANALYZING` told somebody nothing about what was happening to their run.
 *
 * An unmapped status falls through to the raw value rather than to a blank. An
 * unknown state is something to notice; a blank badge reads as "no state",
 * which is a different and untrue claim.
 */
const STATUS_WORD: Record<string, string> = {
  draft: 'Not started',
  preparing: 'Building the room',
  ready: 'Ready to run',
  pending: 'Waiting',
  queued: 'Waiting',
  running: 'Running',
  processing: 'Working',
  generating: 'Writing it up',
  analyzing: 'Working out what happened',
  complete: 'Finished',
  completed: 'Finished',
  approved: 'Finished',
  active: 'Active',
  failed: 'Did not finish',
  stopped: 'Stopped',
  archived: 'Archived',
  pending_review: 'Waiting for review',
};

export default function StatusBadge({ status }: { status: string }) {
  const config = STATUS_CONFIG[status] ?? DEFAULT_CONFIG;
  // Anything still in flight pulses, not just `running` — `analyzing` is work
  // in progress too, and a still dot there reads as a stalled run.
  const isRunning = ACTIVE_STATUSES.includes(status);

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium tracking-wide ${config.bg} ${config.text}`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${config.dot}${isRunning ? ' animate-pulse' : ''}`}
      />
      {STATUS_WORD[status] ?? status.replace('_', ' ')}
    </span>
  );
}
