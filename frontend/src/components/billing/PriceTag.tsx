import { Link } from 'react-router-dom';

import type { PriceEntry } from '@/lib/prices';

/**
 * What this costs, said before the founder does the work.
 *
 * Every paid surface used to refuse at submit with a 402 — "this check needs
 * 1,750; you have 1,500" — which arrives *after* the URL is typed and the
 * form filled. That reads as a wall. The price belongs next to the button,
 * and when the balance is short the sentence should be an offer with the way
 * to take it, not a rejection.
 *
 * The shape of the business is the reason this exists: the idea evaluation is
 * the free thing, and the checks that save a founder real money — the page
 * read, the USPTO search — are what they pay for. The moment a founder sees
 * that price is the moment the model is either persuasive or not, so it must
 * never be a surprise at the end.
 */
export default function PriceTag({ entry }: { entry: PriceEntry | undefined }) {
  if (!entry) return null;

  if (entry.free) {
    return (
      <p className="text-[12px] text-saibyl-positive">
        Free{entry.note ? ` — ${entry.note}` : ''}
      </p>
    );
  }

  if (entry.affordable) {
    return (
      <p className="text-[12px] text-saibyl-silver">
        <span className="font-mono tabular-nums text-saibyl-ink">
          {entry.credits.toLocaleString()}
        </span>{' '}
        credits, charged once when it starts.
      </p>
    );
  }

  return (
    <p className="text-[12px] text-saibyl-warning leading-relaxed">
      This costs{' '}
      <span className="font-mono tabular-nums">{entry.credits.toLocaleString()}</span>{' '}
      credits and you are{' '}
      <span className="font-mono tabular-nums">{entry.shortfall.toLocaleString()}</span>{' '}
      short.{' '}
      <Link to="/app/settings" className="text-saibyl-blue hover:underline">
        Add credits
      </Link>{' '}
      and it will run.
    </p>
  );
}
