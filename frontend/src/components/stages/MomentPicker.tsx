import { useEffect, useState } from 'react';

import api from '@/lib/api';

/**
 * Axis B — where the company is right now.
 *
 * Asked **per run**, defaulting to whatever the last run used. Not set once on
 * the product and never revisited: a founder moves from pre-launch to growth
 * without starting over, and the same material at a different moment wants a
 * different mix of people in the room. That is the difference between a tool
 * used once and one that is opened again next quarter.
 *
 * The options come from the server (`GET /simulations/founder-stages`), which is
 * the same registry the run configurator and the report planner read. A second
 * hardcoded list here is how a sixth moment would ship to the engine and never
 * appear on screen.
 */

interface StageOption {
  id: string;
  label: string;
  question: string;
}

export default function MomentPicker({
  value,
  onChange,
  source,
}: {
  value: string;
  onChange: (next: string) => void;
  /** `default` means nothing has run yet — say so rather than imply a memory. */
  source: 'last_run' | 'default';
}) {
  const [options, setOptions] = useState<StageOption[]>([]);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .get<StageOption[] | { items: StageOption[] }>('/simulations/founder-stages')
      .then(({ data }) => {
        if (cancelled) return;
        const list = Array.isArray(data) ? data : data.items;
        setOptions(Array.isArray(list) ? list : []);
      })
      .catch(() => {
        // Logged as a visible state rather than swallowed. A picker that
        // silently renders zero options looks identical to one the founder has
        // already answered, and they would run at whatever was defaulted.
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (failed) {
    return (
      <p className="text-[12px] text-saibyl-muted leading-relaxed">
        We could not load the list of moments, so this run will use{' '}
        <span className="text-saibyl-platinum">
          {source === 'last_run' ? 'the same one as last time' : 'our default'}
        </span>
        . Reload the page to pick a different one.
      </p>
    );
  }

  const selected = options.find((o) => o.id === value);

  return (
    <div>
      <p className="text-[12.5px] text-saibyl-platinum">Where is the company right now?</p>
      <p className="text-[11.5px] text-saibyl-muted mt-0.5 mb-2.5 leading-relaxed">
        {source === 'last_run'
          ? 'Set to whatever you picked last time. Change it if things have moved on.'
          : 'This changes who is in the room — a pre-launch audience argues about different things than a growth one.'}
      </p>
      <div className="flex flex-wrap gap-2">
        {options.map((option) => {
          const active = option.id === value;
          return (
            <button
              key={option.id}
              type="button"
              aria-pressed={active}
              onClick={() => onChange(option.id)}
              className={`px-3.5 py-1.5 rounded-lg border text-[12.5px] transition-colors ${
                active
                  ? 'border-saibyl-gold/50 bg-saibyl-gold/10 text-saibyl-white'
                  : 'border-white/[0.08] bg-white/[0.02] text-saibyl-muted hover:border-white/[0.16] hover:text-saibyl-platinum'
              }`}
            >
              {option.label}
            </button>
          );
        })}
      </div>
      {selected?.question && (
        <p className="text-[11.5px] text-saibyl-silver mt-2.5 leading-relaxed">
          {selected.question}
        </p>
      )}
    </div>
  );
}
