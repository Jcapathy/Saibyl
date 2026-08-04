import { useEffect, useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import api from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import type { Objective } from '@/lib/analysis';

const GOLD = '#C9A227';
const BLUE = '#2563EB';

interface ObjectiveOption {
  value: Objective;
  label: string;
  question: string;
  counts_intents: string[];
}

interface VariantDraft {
  label: string;
  content: string;
}

const MAX_CONTENT = 4000;

/**
 * Configure the copy under test, before the run starts.
 *
 * Two things this surface has to say out loud, because both are surprising and
 * both cost money:
 *
 * **Every variant is a full arena.** The same swarm reacts to each one, so N
 * variants is N times the agent actions. A marketer reading "8 variants" as a
 * dropdown choice rather than as an 8x cost is the mistake this component
 * exists to prevent — PRICING_GUIDE §1.3's honesty line, applied to variants.
 *
 * **Variants are frozen once the run starts.** The scoreboard's whole claim is
 * that the arenas differed only in their copy; an edit afterwards would leave
 * the artifact describing an experiment nobody ran.
 */
export default function VariantSetup({
  simulationId,
  onSavedChange,
}: {
  simulationId: string;
  /**
   * How many variants are *stored* carrying copy — on load, and after each
   * successful save.
   *
   * Deliberately not fired while typing. The start guard downstream mirrors a
   * server-side check that counts rows in `simulation_variants`, and an
   * un-saved textarea is not a row: reporting the draft count would clear the
   * guard on a run the server will still refuse, which is the same class of
   * defect as the guard existing at all.
   */
  onSavedChange?: (variantsWithCopy: number) => void;
}) {
  const [objectives, setObjectives] = useState<ObjectiveOption[]>([]);
  const [objective, setObjective] = useState<Objective | ''>('');
  const [variants, setVariants] = useState<VariantDraft[]>([]);
  const [editable, setEditable] = useState(true);
  const [maxVariants, setMaxVariants] = useState(8);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [opts, current] = await Promise.all([
          api.get('/variants/objectives'),
          api.get(`/variants/${simulationId}`),
        ]);
        if (cancelled) return;
        setObjectives(opts.data.objectives ?? []);
        setObjective(current.data.objective ?? '');
        setEditable(current.data.editable ?? true);
        setMaxVariants(current.data.max_variants ?? 8);
        const stored: VariantDraft[] = (current.data.variants ?? []).map(
          (v: { label: string; content: string }) => ({
            label: v.label ?? '',
            content: v.content ?? '',
          }),
        );
        setVariants(stored);
        onSavedChange?.(stored.filter((v) => v.content.trim()).length);
      } catch (err) {
        if (!cancelled) setError(getErrorMessage(err, 'Could not load variants'));
      }
    })();
    return () => {
      cancelled = true;
    };
    // `onSavedChange` is intentionally not a dependency: it is a notification
    // out of this component, and re-running the fetch when the parent happens
    // to re-render would refetch on every keystroke upstream.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [simulationId]);

  const update = (next: VariantDraft[]) => {
    setVariants(next);
    setSaved(false);
  };

  const save = async () => {
    setSaving(true);
    setError('');
    const payload = variants
      .filter((v) => v.content.trim())
      .map((v) => ({ label: v.label.trim(), content: v.content.trim() }));
    try {
      await api.put(`/variants/${simulationId}`, {
        objective: objective || null,
        variants: payload,
      });
      setSaved(true);
      onSavedChange?.(payload.length);
    } catch (err) {
      setError(getErrorMessage(err, 'Could not save variants'));
    } finally {
      setSaving(false);
    }
  };

  const filled = variants.filter((v) => v.content.trim()).length;

  if (!editable) {
    return (
      <div className="rounded-2xl border border-white/10 bg-white/5 p-5">
        <p className="text-[12px] text-saibyl-silver">
          This run has started. Variants are fixed once a run begins — the
          comparison&rsquo;s claim is that the arenas differed only in their
          copy. Clone the run to test different variants.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div>
        <label className="block text-[11px] text-saibyl-muted mb-1.5">
          What are you testing for?
        </label>
        <select
          value={objective}
          onChange={(e) => {
            setObjective(e.target.value as Objective | '');
            setSaved(false);
          }}
          className="w-full rounded-xl bg-white/5 border border-white/10 px-3 py-2 text-[13px] text-saibyl-pearl"
        >
          <option value="">Sentiment only (no objective)</option>
          {objectives.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label} — {opt.question}
            </option>
          ))}
        </select>
        <p className="text-[11px] text-saibyl-muted mt-1.5 leading-relaxed">
          The objective decides the headline metric. Sentiment stays measured and
          reported, but an ad meant to drive foot traffic and one meant to sell a
          service succeed differently — scoring both on sentiment measures
          neither.
        </p>
      </div>

      <div className="space-y-3">
        {variants.map((variant, i) => (
          <div
            key={i}
            className="rounded-2xl border border-white/10 bg-white/5 p-4"
          >
            <div className="flex items-center gap-2 mb-2">
              <span
                className="px-2 py-0.5 rounded text-[10px] font-semibold"
                style={{ backgroundColor: `${BLUE}1A`, color: '#9CB4E8' }}
              >
                {String.fromCharCode(65 + i)}
              </span>
              <input
                value={variant.label}
                maxLength={80}
                placeholder="Name it — “Bold”, “Price-led”…"
                onChange={(e) => {
                  const next = [...variants];
                  next[i] = { ...variant, label: e.target.value };
                  update(next);
                }}
                className="flex-1 bg-transparent text-[13px] text-saibyl-pearl placeholder:text-saibyl-muted outline-none"
              />
              <button
                type="button"
                onClick={() => update(variants.filter((_, j) => j !== i))}
                className="text-saibyl-muted hover:text-red-400"
                aria-label={`Remove variant ${String.fromCharCode(65 + i)}`}
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
            <textarea
              value={variant.content}
              maxLength={MAX_CONTENT}
              rows={3}
              placeholder="The copy this arena's agents will react to…"
              onChange={(e) => {
                const next = [...variants];
                next[i] = { ...variant, content: e.target.value };
                update(next);
              }}
              className="w-full rounded-xl bg-black/20 border border-white/10 px-3 py-2 text-[12px] text-saibyl-silver placeholder:text-saibyl-muted outline-none resize-y"
            />
          </div>
        ))}
      </div>

      {variants.length < maxVariants && (
        <button
          type="button"
          onClick={() => update([...variants, { label: '', content: '' }])}
          className="flex items-center gap-2 text-[12px]"
          style={{ color: BLUE }}
        >
          <Plus className="w-3.5 h-3.5" />
          Add variant
        </button>
      )}

      {/* The honesty line. A marketer must see the cost shape before committing,
          not discover it on the invoice. */}
      {filled > 1 && (
        <div
          className="rounded-xl border px-3 py-2"
          style={{ borderColor: `${GOLD}33`, backgroundColor: `${GOLD}0D` }}
        >
          <p className="text-[11px] leading-relaxed" style={{ color: GOLD }}>
            {filled} variants means {filled} arenas. The same audience reacts to
            each one, so this run costs about {filled}× the agent actions of a
            single-variant run. You&rsquo;ll see the exact credit cost before you
            start it.
          </p>
        </div>
      )}

      {filled === 1 && (
        <p className="text-[11px] text-amber-400/90">
          One variant is not a comparison. Add a second, or remove it to run an
          ordinary single-arena simulation.
        </p>
      )}

      {error && <p className="text-[12px] text-red-400">{error}</p>}

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={save}
          disabled={saving || filled === 1}
          className="px-4 py-2 rounded-xl text-[12px] font-semibold disabled:opacity-40"
          style={{ backgroundColor: GOLD, color: '#0A0F1C' }}
        >
          {saving ? 'Saving…' : 'Save variants'}
        </button>
        {saved && (
          <span className="text-[11px] text-saibyl-muted">
            Saved. Variants freeze when the run starts.
          </span>
        )}
      </div>
    </div>
  );
}
