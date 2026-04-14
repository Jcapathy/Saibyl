const STATUS_CONFIG: Record<string, { bg: string; text: string; dot: string }> = {
  draft:          { bg: 'bg-[#818CF8]/10', text: 'text-[#818CF8]', dot: 'bg-[#818CF8]' },
  preparing:      { bg: 'bg-[#F59E0B]/10', text: 'text-[#F59E0B]', dot: 'bg-[#F59E0B]' },
  ready:          { bg: 'bg-[#3B82F6]/10', text: 'text-[#3B82F6]', dot: 'bg-[#3B82F6]' },
  running:        { bg: 'bg-[#3B82F6]/10', text: 'text-[#3B82F6]', dot: 'bg-[#3B82F6]' },
  complete:       { bg: 'bg-[#22C55E]/10', text: 'text-[#22C55E]', dot: 'bg-[#22C55E]' },
  completed:      { bg: 'bg-[#22C55E]/10', text: 'text-[#22C55E]', dot: 'bg-[#22C55E]' },
  failed:         { bg: 'bg-[#EF4444]/10', text: 'text-[#EF4444]', dot: 'bg-[#EF4444]' },
  stopped:        { bg: 'bg-[#5A6578]/10', text: 'text-[#5A6578]', dot: 'bg-[#5A6578]' },
  pending:        { bg: 'bg-[#818CF8]/10', text: 'text-[#818CF8]', dot: 'bg-[#818CF8]' },
  pending_review: { bg: 'bg-[#818CF8]/10', text: 'text-[#818CF8]', dot: 'bg-[#818CF8]' },
  approved:       { bg: 'bg-[#22C55E]/10', text: 'text-[#22C55E]', dot: 'bg-[#22C55E]' },
  generating:     { bg: 'bg-[#5B5FEE]/10', text: 'text-[#5B5FEE]', dot: 'bg-[#5B5FEE]' },
  processing:     { bg: 'bg-[#F59E0B]/10', text: 'text-[#F59E0B]', dot: 'bg-[#F59E0B]' },
  active:         { bg: 'bg-[#22C55E]/10', text: 'text-[#22C55E]', dot: 'bg-[#22C55E]' },
  queued:         { bg: 'bg-[#F59E0B]/10', text: 'text-[#F59E0B]', dot: 'bg-[#F59E0B]' },
  archived:       { bg: 'bg-[#5A6578]/10', text: 'text-[#5A6578]', dot: 'bg-[#5A6578]' },
};

const DEFAULT_CONFIG = { bg: 'bg-[#5A6578]/10', text: 'text-[#5A6578]', dot: 'bg-[#5A6578]' };

export default function StatusBadge({ status }: { status: string }) {
  const config = STATUS_CONFIG[status] ?? DEFAULT_CONFIG;
  const isRunning = status === 'running';

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md font-mono text-[11px] uppercase tracking-wide ${config.bg} ${config.text}`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${config.dot}${isRunning ? ' animate-pulse' : ''}`}
      />
      {status.replace('_', ' ')}
    </span>
  );
}
