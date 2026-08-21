import { useEffect, useState } from 'react';

import api from '@/lib/api';

/**
 * What each paid thing costs, fetched once per session.
 *
 * Lives in `lib/` rather than beside the component because a file that
 * exports both a hook and a component breaks React Fast Refresh — and
 * because the price table is a fact about the business, not about any one
 * form that happens to display it.
 */

export interface PriceEntry {
  credits: number;
  label: string;
  affordable: boolean;
  shortfall: number;
  free: boolean;
  note?: string | null;
}

export interface PricesResponse {
  balance: number;
  plan: string;
  idea_evaluation: PriceEntry;
  website_check: PriceEntry;
  answer_pack: PriceEntry;
  website_revision: PriceEntry;
  /**
   * The family-office shortlist.
   *
   * Optional because a deployed backend older than the release that publishes
   * it answers without the key, and `PriceTag` renders nothing for an absent
   * entry rather than rendering a paid thing as free. The server prices the
   * work again at submit either way.
   */
  capital_shortlist?: PriceEntry;
  clearance: Record<string, PriceEntry>;
}

let cached: PricesResponse | null = null;

export function usePrices(): PricesResponse | null {
  const [prices, setPrices] = useState<PricesResponse | null>(cached);

  useEffect(() => {
    if (cached) return;
    let cancelled = false;
    api
      .get<PricesResponse>('/billing/prices')
      .then(({ data }) => {
        cached = data;
        if (!cancelled) setPrices(data);
      })
      .catch(() => {
        /* The form still works. A price we could not read must not render as
           free, and must not block the control either — the server prices the
           work again at submit, so silence here is safe. */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return prices;
}
