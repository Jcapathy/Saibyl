import { useState } from 'react';
import { Link } from 'react-router-dom';
import { AxiosError } from 'axios';
import { ArrowRight } from 'lucide-react';

import api from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { Guarded } from '@/components/stages/StagePrimitives';
import PriceTag from '@/components/billing/PriceTag';
import { usePrices } from '@/lib/prices';
import { Card } from '@/components/design';
import {
  TIER_LABELS,
  type ClearanceRun,
  type ClearanceTier,
} from './types';

/**
 * The run form: what to check, and how deep to look.
 *
 * The API is the only authority on money. This form never computes a price —
 * on a credit shortfall the backend answers 402 with the sentence to show,
 * and the form shows that sentence with the way to fix it. The same goes for
 * the free-tier daily cap (429) and an unconfigured search service (503):
 * all three arrive as plain language in `detail` and are rendered as given.
 */

interface ProductOption {
  id: string;
  name: string;
}

interface TierChoice {
  value: ClearanceTier;
  label: string;
  help: string;
}

const TIERS: TierChoice[] = [
  {
    value: 'QUICK',
    label: TIER_LABELS.QUICK,
    help: 'An exact-name trademark check and a quick sweep of patent titles. One screen, about a minute.',
  },
  {
    value: 'STANDARD',
    label: TIER_LABELS.STANDARD,
    help: 'Trademarks, granted patents and published filings, with close readings of the claims nearest to yours. Uses credits from your balance.',
  },
  {
    value: 'COMPREHENSIVE',
    label: TIER_LABELS.COMPREHENSIVE,
    help: 'Everything in the full search, plus sweeps of who owns what in this field, examiner history, and a watch-list of filings to keep an eye on. Uses more credits.',
  },
];

const inputBase =
  'w-full rounded-xl bg-white border border-saibyl-border-light px-3 py-2.5 text-[13.5px] text-saibyl-ink placeholder:text-saibyl-muted/70 focus:outline-none focus:border-saibyl-blue focus:ring-2 focus:ring-saibyl-blue/20';

export default function ClearanceRunForm({
  products,
  initialItem = '',
  initialTier = 'QUICK',
  onStarted,
}: {
  products: ProductOption[];
  initialItem?: string;
  initialTier?: ClearanceTier;
  onStarted: (run: ClearanceRun) => void;
}) {
  const [item, setItem] = useState(initialItem);
  const [productId, setProductId] = useState('');
  const [field, setField] = useState('');
  const [rivals, setRivals] = useState('');
  const [tier, setTier] = useState<ClearanceTier>(initialTier);
  const prices = usePrices();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<{ message: string; billing: boolean } | null>(
    null,
  );

  async function start() {
    const trimmed = item.trim();
    if (!trimmed) {
      // Stated, never a greyed-out control: the founder gets the sentence
      // that unblocks them instead of a button that ignores the click.
      setError({
        message:
          'Tell us what to check first — the name, the idea, or both. A sentence is enough.',
        billing: false,
      });
      return;
    }
    setSubmitting(true);
    setError(null);

    const competitors = rivals
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    const body: Record<string, unknown> = { item: trimmed, tier };
    if (productId) body.project_id = productId;
    if (field.trim()) body.field = field.trim();
    if (competitors.length > 0) body.competitors = competitors;

    try {
      const { data } = await api.post<ClearanceRun>('/clearance', body);
      onStarted(data);
    } catch (err) {
      const status = err instanceof AxiosError ? err.response?.status : undefined;
      setError({
        message: getErrorMessage(err, 'We could not start that search.'),
        // 402 is a credit shortfall. The API's own sentence says what is
        // short; this adds the one control that fixes it.
        billing: status === 402,
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card carries="stage" className="p-6 space-y-5">
      <div>
        <label
          htmlFor="clearance-item"
          className="block text-[13px] font-medium text-saibyl-ink mb-1.5"
        >
          What should we check?
        </label>
        <textarea
          id="clearance-item"
          rows={3}
          value={item}
          onChange={(e) => setItem(e.target.value)}
          placeholder="Your product name, your idea, or both — a sentence is enough"
          className={`${inputBase} resize-y`}
        />
      </div>

      {products.length > 0 && (
        <div>
          <label
            htmlFor="clearance-product"
            className="block text-[12.5px] text-saibyl-silver mb-1.5"
          >
            Which of your products is this for? <span className="text-saibyl-muted">Optional</span>
          </label>
          <select
            id="clearance-product"
            value={productId}
            onChange={(e) => setProductId(e.target.value)}
            className="w-full rounded-xl border border-saibyl-border-light bg-white px-3 py-2.5 text-[13.5px] text-saibyl-ink focus:outline-none focus:border-saibyl-blue focus:ring-2 focus:ring-saibyl-blue/20"
            style={{ colorScheme: 'light' }}
          >
            <option value="">None — just checking</option>
            {products.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label
            htmlFor="clearance-field"
            className="block text-[12.5px] text-saibyl-silver mb-1.5"
          >
            What field is this in? <span className="text-saibyl-muted">Optional</span>
          </label>
          <input
            id="clearance-field"
            value={field}
            onChange={(e) => setField(e.target.value)}
            placeholder="e.g. consumer robotics, food delivery"
            className={inputBase}
          />
        </div>
        <div>
          <label
            htmlFor="clearance-rivals"
            className="block text-[12.5px] text-saibyl-silver mb-1.5"
          >
            Anyone already in this space? <span className="text-saibyl-muted">Optional</span>
          </label>
          <input
            id="clearance-rivals"
            value={rivals}
            onChange={(e) => setRivals(e.target.value)}
            placeholder="Company names, separated by commas"
            className={inputBase}
          />
        </div>
      </div>

      <div>
        <p className="text-[13px] font-medium text-saibyl-ink mb-2">
          How deep should we look?
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          {TIERS.map((option) => {
            const selected = tier === option.value;
            return (
              <button
                key={option.value}
                type="button"
                aria-pressed={selected}
                onClick={() => setTier(option.value)}
                className={`text-left p-3 rounded-lg border transition-all ${
                  selected
                    ? 'border-saibyl-blue/50 bg-saibyl-blue/10'
                    : 'border-saibyl-border bg-white hover:border-saibyl-border-light'
                }`}
              >
                <span
                  className={`block text-[13px] font-medium ${
                    selected ? 'text-saibyl-ink' : 'text-saibyl-ink'
                  }`}
                >
                  {option.label}
                </span>
                <span className="block text-[11px] text-saibyl-muted mt-0.5 leading-relaxed">
                  {option.help}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-saibyl-negative/25 bg-saibyl-negative/[0.07] p-4">
          <p className="text-[13px] text-saibyl-negative leading-relaxed">
            {error.message}
          </p>
          {error.billing && (
            <Link
              to="/app/settings/billing"
              className="inline-flex items-center gap-1.5 mt-3 px-3.5 py-1.5 rounded-lg bg-saibyl-blue text-saibyl-paper text-[12px] font-semibold hover:bg-saibyl-blue-hover transition-colors"
            >
              Add credits
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          )}
        </div>
      )}

      {/* The price of the tier they have selected, before they click it —
          not a 402 after the subject is written. */}
      <PriceTag entry={prices?.clearance?.[tier]} />

      <Guarded
        label="Search the USPTO"
        onClick={start}
        busy={submitting}
        busyLabel="Sending it to the search queue…"
      />
    </Card>
  );
}
