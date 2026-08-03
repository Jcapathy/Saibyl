import type { ReactNode } from 'react';

/**
 * The shared card shell for every measured surface.
 *
 * `note` is where a component states what its numbers rest on. Every panel in
 * the report carries one, because a chart without its n and its interval is the
 * failure mode this whole layer exists to remove.
 */
export default function Panel({
  title,
  note,
  action,
  children,
  className = '',
}: {
  title: string;
  note?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`bg-saibyl-surface border border-saibyl-border rounded-2xl p-6 ${className}`}
    >
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <h3 className="text-[16px] font-bold text-saibyl-platinum">{title}</h3>
          {note && <p className="text-[11px] text-saibyl-muted mt-1 leading-relaxed">{note}</p>}
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </div>
      {children}
    </div>
  );
}

/**
 * Shown instead of a chart when the artifact has nothing to plot.
 *
 * Deliberately blunt. The old viewer filled empty slots with plausible-looking
 * generated data, which is strictly worse than an empty state: the reader
 * cannot tell the difference, so every real chart inherits the doubt.
 */
export function NoData({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-saibyl-border px-4 py-6 text-[12px] text-saibyl-muted leading-relaxed">
      {children}
    </div>
  );
}
