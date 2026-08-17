import { ACTIVE_STATUSES } from '@/lib/constants';

/* Light-ground chip palette: the dot carries the bright hue, the words carry a
   darker tone of the same hue so 11px text holds ≥4.5:1 on the tinted fill. */
const STATUS_CONFIG: Record<string, { bg: string; text: string; dot: string }> = {
  draft:          { bg: 'bg-[#8b73ee]/10', text: 'text-[#6a4fe0]', dot: 'bg-[#8b73ee]' },
  preparing:      { bg: 'bg-[#f59e0b]/10', text: 'text-[#b45309]', dot: 'bg-[#f59e0b]' },
  ready:          { bg: 'bg-[#286cf0]/10', text: 'text-[#1e5ad9]', dot: 'bg-[#286cf0]' },
  running:        { bg: 'bg-[#286cf0]/10', text: 'text-[#1e5ad9]', dot: 'bg-[#286cf0]' },
  analyzing:      { bg: 'bg-[#f59e0b]/10', text: 'text-[#b45309]', dot: 'bg-[#f59e0b]' },
  complete:       { bg: 'bg-[#2fbf8a]/10', text: 'text-[#0e7d55]', dot: 'bg-[#2fbf8a]' },
  completed:      { bg: 'bg-[#2fbf8a]/10', text: 'text-[#0e7d55]', dot: 'bg-[#2fbf8a]' },
  failed:         { bg: 'bg-[#ff6e79]/10', text: 'text-[#d92d3c]', dot: 'bg-[#ff6e79]' },
  stopped:        { bg: 'bg-[#60718e]/10', text: 'text-[#60718e]', dot: 'bg-[#60718e]' },
  pending:        { bg: 'bg-[#8b73ee]/10', text: 'text-[#6a4fe0]', dot: 'bg-[#8b73ee]' },
  pending_review: { bg: 'bg-[#8b73ee]/10', text: 'text-[#6a4fe0]', dot: 'bg-[#8b73ee]' },
  approved:       { bg: 'bg-[#2fbf8a]/10', text: 'text-[#0e7d55]', dot: 'bg-[#2fbf8a]' },
  generating:     { bg: 'bg-[#8b73ee]/10', text: 'text-[#6a4fe0]', dot: 'bg-[#8b73ee]' },
  processing:     { bg: 'bg-[#f59e0b]/10', text: 'text-[#b45309]', dot: 'bg-[#f59e0b]' },
  active:         { bg: 'bg-[#2fbf8a]/10', text: 'text-[#0e7d55]', dot: 'bg-[#2fbf8a]' },
  queued:         { bg: 'bg-[#f59e0b]/10', text: 'text-[#b45309]', dot: 'bg-[#f59e0b]' },
  archived:       { bg: 'bg-[#60718e]/10', text: 'text-[#60718e]', dot: 'bg-[#60718e]' },
};

const DEFAULT_CONFIG = { bg: 'bg-[#60718e]/10', text: 'text-[#60718e]', dot: 'bg-[#60718e]' };

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
