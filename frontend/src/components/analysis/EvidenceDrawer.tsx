import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import api from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { PLATFORM_NAMES, sentimentBarColor } from '@/lib/constants';
import { formatSigned, type EvidenceEvent } from '@/lib/analysis';

/**
 * The word-for-word quotes behind a finding.
 *
 * This drawer is what makes a measured number defensible: every figure in the
 * report traces back to the things people actually said, and the reader can go
 * and read them. A number that cannot be opened is an assertion regardless of
 * how it was computed.
 */
export default function EvidenceDrawer({
  simulationId,
  eventIds,
  label,
  onClose,
}: {
  simulationId: string;
  eventIds: string[];
  label: string;
  onClose: () => void;
}) {
  // `null` means still loading. An empty finding is resolved here rather than
  // in the effect so there is no synchronous setState on mount.
  const [events, setEvents] = useState<EvidenceEvent[] | null>(
    eventIds.length === 0 ? [] : null,
  );
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    if (eventIds.length === 0) return;
    api
      // The endpoint caps at 200; asking for more would silently truncate and
      // the drawer would claim to show "all" of something it did not.
      .get(`/simulations/${simulationId}/evidence`, {
        params: { event_ids: eventIds.slice(0, 200).join(',') },
      })
      .then((res) => {
        if (!cancelled) setEvents(res.data);
      })
      .catch((err) => {
        if (!cancelled)
          setError(getErrorMessage(err, 'We could not load what was said here.'));
      });
    return () => {
      cancelled = true;
    };
  }, [simulationId, eventIds]);

  const truncated = eventIds.length > 200;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <button
        type="button"
        aria-label="Close this panel"
        className="flex-1 bg-[#14294a]/25 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="w-full max-w-[520px] h-full bg-saibyl-void border-l border-saibyl-border flex flex-col shadow-2xl">
        <div className="flex items-start justify-between gap-3 px-5 py-4 border-b border-saibyl-border">
          <div className="min-w-0">
            <p className="text-[10px] uppercase tracking-wider text-saibyl-muted">
              What was actually said
            </p>
            <h3 className="text-[15px] font-semibold text-saibyl-platinum truncate">
              {label}
            </h3>
            <p className="text-[11px] text-saibyl-muted mt-0.5">
              {eventIds.length.toLocaleString()}{' '}
              {eventIds.length === 1 ? 'post or reply' : 'posts and replies'}
              {truncated ? ' — showing the first 200' : ''}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-lg text-saibyl-muted hover:text-saibyl-platinum hover:bg-saibyl-surface transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-3">
          {error && <p className="text-[12px] text-saibyl-negative">{error}</p>}
          {!error && events === null && (
            <p className="text-[12px] text-saibyl-muted">Loading…</p>
          )}
          {events?.length === 0 && (
            <p className="text-[12px] text-saibyl-muted">
              Nothing anyone said is linked to this, so there is nothing to read.
            </p>
          )}
          {events?.map((event) => (
            <div
              key={event.id}
              className="bg-saibyl-surface border border-saibyl-border rounded-xl p-4"
            >
              <div className="flex items-baseline justify-between gap-3 mb-1.5">
                <span className="text-[12px] font-semibold text-saibyl-platinum truncate">
                  @{event.agent.username ?? 'unknown'}
                  {event.agent.archetype ? (
                    <span className="text-saibyl-muted font-normal">
                      {' '}· {event.agent.archetype}
                    </span>
                  ) : null}
                </span>
                {event.valence != null && (
                  <span
                    className="text-[11px] font-mono whitespace-nowrap"
                    style={{ color: sentimentBarColor(event.valence) }}
                  >
                    {formatSigned(event.valence)}
                  </span>
                )}
              </div>

              {event.content ? (
                <p className="text-[12px] text-saibyl-silver leading-relaxed whitespace-pre-wrap">
                  {event.content}
                </p>
              ) : (
                <p className="text-[12px] text-saibyl-muted italic">
                  {event.event_type} — no words, just a reaction
                </p>
              )}

              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-2 text-[10px] text-saibyl-muted">
                {event.platform && (
                  <span>{PLATFORM_NAMES[event.platform] ?? event.platform}</span>
                )}
                {event.round_number != null && <span>round {event.round_number}</span>}
                {event.stance && <span>{event.stance.replace('_', '-')}</span>}
                {event.intensity != null && (
                  <span>how strongly they meant it: {event.intensity.toFixed(2)}</span>
                )}
                {event.is_novel_claim && (
                  <span className="text-saibyl-insight-violet">brought up something new</span>
                )}
              </div>

              {event.objections?.length > 0 && (
                <p className="text-[10px] text-saibyl-muted mt-1.5">
                  Pushed back on: {event.objections.join(' · ')}
                </p>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
