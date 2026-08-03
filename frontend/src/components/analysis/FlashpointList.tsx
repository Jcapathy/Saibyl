import { Zap } from 'lucide-react';
import { formatSigned, type Flashpoint } from '@/lib/analysis';
import Panel, { NoData } from './Panel';

/**
 * Rounds where sentiment moved, with the events that moved it.
 *
 * A move is only called significant when the two rounds' confidence intervals
 * do not overlap. Everything else is labelled directional and shown greyed —
 * the reader gets to see it without being told it means something the data
 * cannot support.
 */
export default function FlashpointList({
  flashpoints,
  objectionLabels,
  onDrillDown,
}: {
  flashpoints: Flashpoint[];
  objectionLabels?: Record<string, string>;
  onDrillDown?: (eventIds: string[], label: string) => void;
}) {
  if (flashpoints.length === 0) {
    return (
      <Panel title="Flashpoints">
        <NoData>
          Sentiment never moved by more than 0.15 between rounds. The
          conversation held its shape — which is itself worth knowing before a
          launch.
        </NoData>
      </Panel>
    );
  }

  return (
    <Panel
      title="Flashpoints"
      note="Round-to-round shifts larger than 0.15. Only shifts whose confidence intervals separate are marked measured."
    >
      <div className="space-y-3">
        {flashpoints.map((flash) => (
          <div
            key={`${flash.round_number}-${flash.delta}`}
            className={`rounded-xl border p-4 ${
              flash.significant
                ? 'border-saibyl-negative/25 bg-saibyl-negative/[0.06]'
                : 'border-saibyl-border bg-saibyl-void'
            }`}
          >
            <div className="flex items-start gap-2.5">
              <Zap
                className={`w-4 h-4 mt-0.5 shrink-0 ${
                  flash.significant ? 'text-saibyl-negative' : 'text-saibyl-muted'
                }`}
              />
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-[13px] font-semibold text-saibyl-platinum">
                    Round {flash.round_number}
                  </span>
                  <span
                    className={`text-[12px] font-mono whitespace-nowrap ${
                      flash.delta < 0 ? 'text-saibyl-negative' : 'text-saibyl-positive'
                    }`}
                  >
                    {formatSigned(flash.valence_before)} →{' '}
                    {formatSigned(flash.valence_after)}
                  </span>
                </div>
                <p className="text-[11px] text-saibyl-silver mt-1 leading-relaxed">
                  {flash.description}
                </p>

                <div className="flex flex-wrap items-center gap-2 mt-2">
                  <span
                    className={`text-[10px] px-1.5 py-0.5 rounded ${
                      flash.significant
                        ? 'bg-saibyl-negative/15 text-saibyl-negative'
                        : 'bg-white/[0.04] text-saibyl-muted'
                    }`}
                  >
                    {flash.significant ? 'measured shift' : 'within the bands'}
                  </span>
                  {flash.objection_keys.map((key) => (
                    <span
                      key={key}
                      className="text-[10px] px-1.5 py-0.5 rounded bg-saibyl-gold/10 text-saibyl-gold"
                    >
                      {objectionLabels?.[key] ?? key}
                    </span>
                  ))}
                  {onDrillDown && flash.trigger_event_ids.length > 0 && (
                    <button
                      type="button"
                      onClick={() =>
                        onDrillDown(
                          flash.trigger_event_ids,
                          `Round ${flash.round_number} shift`,
                        )
                      }
                      className="text-[10px] text-saibyl-signal-blue hover:underline"
                    >
                      what caused it →
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}
