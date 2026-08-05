import { useOutletContext } from 'react-router-dom';

import type { ProductState, StageId, StageState } from '@/lib/stages';

/**
 * Reading the product a stage page is inside.
 *
 * `ProductLayout` fetches the whole rail once and puts it on the outlet
 * context; these are how a stage page reads it. In their own module because a
 * file that exports both a component and a hook loses fast refresh — the
 * component reloads and the hook does not, and the two disagree about state.
 */

export interface ProductContext {
  product: ProductState;
  /** Re-fetch after something changed. Stage pages call this after a write. */
  refresh: () => void;
}

export function useProduct(): ProductContext {
  return useOutletContext<ProductContext>();
}

export function useStage(id: StageId): StageState {
  const { product } = useProduct();
  const stage = product.stages.find((s) => s.id === id);
  // The server returns all five, always. A missing one means the contract
  // changed, and rendering a blank panel would hide that rather than show it.
  if (!stage) throw new Error(`Server returned no state for stage: ${id}`);
  return stage;
}
