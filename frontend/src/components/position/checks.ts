import { useCallback, useEffect, useState } from 'react';

import api, { unwrapList } from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import {
  isCheckUnderway,
  type SiteCheck,
  type SiteCheckListItem,
} from '@/components/website/types';

/**
 * The website check, as state a page can render.
 *
 * All of it was already spread across two screens. `WebsitePage` listed the
 * checks and opened them; `AudienceStagePage` did the same and *also* polled
 * the worker and resumed a check the founder had walked away from. The
 * difference was invisible until you used the weaker one: start a check on the
 * global page and the row sat on "Waiting" until you reloaded the browser,
 * because nothing ever asked the server again.
 *
 * So this is the stronger of the two behaviours, in one place, rather than a
 * third copy of the weaker one.
 *
 * ── Why every piece of state is stamped with the product it belongs to ──────
 *
 * The picker on a global page changes `productId` while the previous product's
 * checks are still in state. Clearing them in an effect renders the wrong
 * product's rows once before they disappear — a real flash, not a theoretical
 * one, and the reason `WebsitePage` reset its state from the picker's own
 * handler instead. That works until something else changes the selection.
 *
 * Stamping the state and *deriving* what belongs to the current product needs
 * no effect and no handler: a product with nothing loaded yet shows nothing,
 * which is what it has. The rule is the same one the rest of the app follows —
 * state that can be derived during render is not state to synchronise.
 */

/** How often the worker is asked where it has got to. */
const POLL_MS = 3000;

/** A value and the product it was read for. See the header. */
interface Scoped<T> {
  productId: string;
  value: T;
}

export interface SiteChecks {
  /** Newest first. Empty for a product whose list has not arrived yet. */
  rows: SiteCheckListItem[];
  /** The check on screen — being read, finished, or failed. */
  active: SiteCheck | null;
  /** True while the worker is still reading a page. */
  underway: boolean;
  /** The row a click has opened but the server has not answered for yet. */
  opening: string;
  error: string;
  reload: () => void;
  open: (id: string) => void;
  /** A freshly queued check, seeded so the list shows it before the next read. */
  started: (check: SiteCheck) => void;
}

export function useSiteChecks(productId: string): SiteChecks {
  const [loaded, setLoaded] = useState<Scoped<SiteCheckListItem[]> | null>(null);
  const [opened, setOpened] = useState<Scoped<SiteCheck> | null>(null);
  const [failure, setFailure] = useState<Scoped<string> | null>(null);
  const [opening, setOpening] = useState('');

  const rows = loaded && loaded.productId === productId ? loaded.value : [];
  const active = opened && opened.productId === productId ? opened.value : null;
  const error = failure && failure.productId === productId ? failure.value : '';

  /* ── The list ── */
  const reload = useCallback(() => {
    if (!productId) return;
    api
      .get('/website/check', { params: { project_id: productId } })
      .then((r) => {
        const items = [...unwrapList<SiteCheckListItem>(r.data).items].sort(
          (a, b) => b.created_at.localeCompare(a.created_at),
        );
        setLoaded({ productId, value: items });
        setFailure(null);
      })
      .catch((err) =>
        setFailure({
          productId,
          value: getErrorMessage(err, 'We could not read your checks.'),
        }),
      );
  }, [productId]);

  useEffect(() => {
    reload();
  }, [reload]);

  /* ── While the worker is still reading ──
     Keyed on the id and on whether it is still moving, not on the check object,
     so the interval survives its own responses instead of being torn down and
     rebuilt on every tick. It stops the moment the check settles: a timer that
     keeps firing after the work is done is how a page quietly hammers an API
     for the rest of the session. */
  const activeId = active?.id ?? '';
  const activeUnderway = active !== null && isCheckUnderway(active.status);

  useEffect(() => {
    if (!activeId || !activeUnderway) return;
    const timer = window.setInterval(() => {
      api
        .get<SiteCheck>(`/website/check/${activeId}`)
        .then(({ data }) => {
          setOpened({ productId, value: data });
          // The finished check carries a score the list row does not have yet.
          if (data.status === 'complete') reload();
        })
        .catch(() => {
          // A missed tick is not a failed check. The next one asks again, and
          // the row keeps its last known state meanwhile.
        });
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [activeId, activeUnderway, productId, reload]);

  /* ── Coming back to it ──
     A founder who started a check and closed the tab resumes where the worker
     is, and one who finished a check last week sees what it found without
     hunting for the row. Failing quietly costs a click, not an answer. */
  useEffect(() => {
    if (active !== null || rows.length === 0) return;
    const candidate = rows.find(
      (row) => isCheckUnderway(row.status) || row.status === 'complete',
    );
    if (!candidate) return;
    let cancelled = false;
    api
      .get<SiteCheck>(`/website/check/${candidate.id}`)
      .then(({ data }) => {
        if (!cancelled) setOpened({ productId, value: data });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [active, rows, productId]);

  const open = useCallback(
    (id: string) => {
      setOpening(id);
      api
        .get<SiteCheck>(`/website/check/${id}`)
        .then(({ data }) => setOpened({ productId, value: data }))
        .catch((err) =>
          setFailure({
            productId,
            value: getErrorMessage(err, 'We could not open that check.'),
          }),
        )
        .finally(() => setOpening(''));
    },
    [productId],
  );

  const started = useCallback(
    (check: SiteCheck) => {
      setOpened({ productId, value: check });
      setLoaded((current) => {
        const items =
          current && current.productId === productId ? current.value : [];
        if (items.some((row) => row.id === check.id)) return current;
        return {
          productId,
          value: [
            {
              id: check.id,
              url: check.url,
              status: check.status,
              // Nothing has been read yet, so there is no score to show. The
              // poll above carries the row the rest of the way.
              overall_score: null,
              created_at: check.created_at,
            },
            ...items,
          ],
        };
      });
    },
    [productId],
  );

  return {
    rows,
    active,
    underway: activeUnderway,
    opening,
    error,
    reload,
    open,
    started,
  };
}
