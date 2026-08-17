import { useEffect, useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import api from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import type { Objective } from '@/lib/analysis';

const GOLD = '#286cf0';
const BLUE = '#286cf0';

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
        if (!cancelled) setError(getErrorMessage(err, 'We could not load your versions.'));
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
      setError(getErrorMessage(err, 'We could not save your versions.'));
    } finally {
      setSaving(false);
    }
  };

  const filled = variants.filter((v) => v.content.trim()).length;

  if (!editable) {
    return (
      <div className="rounded-2xl border border-saibyl-border bg-saibyl-elevated p-5">
        <p className="text-[12px] text-saibyl-silver">
          This run has already started, so the wording is locked. The whole
          claim of the comparison is that the only thing that differed was the
          words &mdash; an edit now would describe a test nobody ran. Copy the
          run if you want to try different wording.
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
          className="w-full rounded-xl bg-white border border-saibyl-border-light px-3 py-2 text-[13px] text-saibyl-ink focus:outline-none focus:border-saibyl-blue focus:ring-2 focus:ring-saibyl-blue/20"
        >
          <option value="">Nothing in particular — just how people react</option>
          {objectives.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label} — {opt.question}
            </option>
          ))}
        </select>
        <p className="text-[11px] text-saibyl-muted mt-1.5 leading-relaxed">
          This decides the number at the top of your report. We measure how the
          room felt either way — but a post meant to get people signing up and
          one meant to get them talking succeed in different ways, and scoring
          both on mood measures neither.
        </p>
      </div>

      <div className="space-y-3">
        {variants.map((variant, i) => (
          <div
            key={i}
            className="rounded-2xl border border-saibyl-border bg-saibyl-elevated p-4"
          >
            <div className="flex items-center gap-2 mb-2">
              <span
                className="px-2 py-0.5 rounded text-[10px] font-semibold"
                style={{ backgroundColor: `${BLUE}1A`, color: '#1e5ad9' }}
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
                className="flex-1 bg-transparent text-[13px] text-saibyl-ink placeholder:text-saibyl-muted/70 outline-none"
              />
              <button
                type="button"
                onClick={() => update(variants.filter((_, j) => j !== i))}
                className="text-saibyl-muted hover:text-saibyl-negative"
                aria-label={`Remove version ${String.fromCharCode(65 + i)}`}
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
            <textarea
              value={variant.content}
              maxLength={MAX_CONTENT}
              rows={3}
              placeholder="The words this version puts in front of the room…"
              onChange={(e) => {
                const next = [...variants];
                next[i] = { ...variant, content: e.target.value };
                update(next);
              }}
              className="w-full rounded-xl bg-white border border-saibyl-border-light px-3 py-2 text-[12px] text-saibyl-ink placeholder:text-saibyl-muted/70 focus:outline-none focus:border-saibyl-blue focus:ring-2 focus:ring-saibyl-blue/20 resize-y"
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
          Add another version
        </button>
      )}

      {/* The honesty line. A marketer must see the cost shape before committing,
          not discover it on the invoice. */}
      {filled > 1 && (
        <div
          className="rounded-xl border px-3 py-2"
          style={{ borderColor: `${GOLD}33`, backgroundColor: `${GOLD}0D` }}
        >
          <p className="text-[11px] leading-relaxed" style={{ color: '#1e5ad9' }}>
            {filled} versions means the room does this {filled} times over. The
            same people react to each one from scratch, so this run costs about
            {' '}{filled}&times; what a single message costs. You&rsquo;ll see the exact
            credit cost before you start it.
          </p>
        </div>
      )}

      {filled === 1 && (
        <p className="text-[11px] text-saibyl-warning">
          One version on its own is not a comparison &mdash; there is nothing to
          compare it against. Add a second, or delete it and the run goes ahead
          with a single message.
        </p>
      )}

      {error && <p className="text-[12px] text-saibyl-negative">{error}</p>}

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={save}
          disabled={saving || filled === 1}
          className="px-4 py-2 rounded-xl text-[12px] font-semibold disabled:opacity-40"
          style={{ backgroundColor: GOLD, color: '#ffffff' }}
        >
          {saving ? 'Saving…' : 'Save these versions'}
        </button>
        {saved && (
          <span className="text-[11px] text-saibyl-muted">
            Saved. These lock the moment the run starts.
          </span>
        )}
      </div>
    </div>
  );
}
