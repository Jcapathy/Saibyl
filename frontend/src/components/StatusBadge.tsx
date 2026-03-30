const statusColors: Record<string, string> = {
  draft: 'bg-saibyl-elevated text-saibyl-muted',
  preparing: 'bg-saibyl-indigo/15 text-saibyl-indigo',
  ready: 'bg-saibyl-indigo/15 text-saibyl-cyan',
  running: 'bg-saibyl-indigo/20 text-saibyl-indigo',
  complete: 'bg-saibyl-positive/15 text-saibyl-positive',
  completed: 'bg-saibyl-positive/15 text-saibyl-positive',
  failed: 'bg-saibyl-negative/15 text-saibyl-negative',
  stopped: 'bg-saibyl-elevated text-saibyl-muted',
  pending: 'bg-saibyl-violet/15 text-saibyl-violet',
  pending_review: 'bg-saibyl-violet/15 text-saibyl-violet',
  approved: 'bg-saibyl-positive/15 text-saibyl-positive',
  generating: 'bg-saibyl-violet/15 text-saibyl-violet',
  processing: 'bg-saibyl-indigo/15 text-saibyl-indigo',
  active: 'bg-saibyl-positive/15 text-saibyl-positive',
  archived: 'bg-saibyl-elevated text-saibyl-muted',
};

export default function StatusBadge({ status }: { status: string }) {
  const color = statusColors[status] || 'bg-saibyl-elevated text-saibyl-muted';
  return (
    <span className={`text-label inline-flex items-center px-2.5 py-1 rounded-md font-mono text-xs ${color}`}>
      {status}
    </span>
  );
}
