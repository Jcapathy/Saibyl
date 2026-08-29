import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import api from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { Card, Chapter, Deal, Ground, Hero, Longform, Reveal } from '@/components/design';
import { EmptyState, StageError } from '@/components/stages/StagePrimitives';

/**
 * Everything this founder has made, in one chronology.
 *
 * **Why this page exists.** Every module stored its output durably and none of
 * it was findable in one place. The founder who raised it had eight artifacts —
 * four website checks, three gallery entries, a page rewrite — and the Reports
 * section showed **zero**, because `reports` is written only by simulation runs.
 * A report was a child of a run rather than a record of work, so the rows were
 * addressed by *where you were standing* when you made them.
 *
 * His question was the right one: *"Shouldn't any and all reports or checks get
 * stored there as well, so somebody has a comprehensive list of all of the work
 * they've done that they can go back and refer to without having to go through
 * all the different pages?"*
 *
 * **Every row opens.** A website check has no page of its own — it renders
 * inside the audience stage — so its link carries `?check=<id>` and that page
 * opens it. A list that can only drop you on a stage page and leave you hunting
 * is worse than no list: it proves the thing exists and still makes you find it.
 */

type WorkItem = {
  id: string;
  kind: string;
  label: string;
  title: string;
  href: string;
  status: string | null;
  created_at: string | null;
  completed_at: string | null;
  credits: number | null;
};

/** The date a founder recognises, not an ISO string. */
function when(value: string | null): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

export default function WorkPage() {
  const [items, setItems] = useState<WorkItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    api
      .get<{ items: WorkItem[] }>('/work')
      .then(({ data }) => {
        setItems(data.items ?? []);
        setError('');
      })
      .catch((err) =>
        setError(getErrorMessage(err, 'We could not read your work.')),
      )
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const retry = useCallback(() => {
    setLoading(true);
    load();
  }, [load]);

  return (
    <Ground className="min-h-full pb-24">
      <Longform>
        {/* A nav page opens like the landing page — Longform, Hero, Chapter —
            per the founder's decision of 2026-08-23 and `ia.test.ts` §8.
            `How this works` is the built example this copies. */}
        <Hero
          eyebrow="Your work"
          title="Everything you've"
          serif="already made"
        >
          Every check, run, rewrite and search, newest first. Each row opens the
          thing itself, so you never have to remember which step produced it.
        </Hero>

        <Chapter
          kicker="The record"
          title={<>What you have <em>to show for it</em></>}
          lead="Newest first, across every part of the product. A row that is still working says so."
        >
        {error && <StageError message={error} retry={retry} />}

        {!error && loading && (
          <p className="text-[13px] text-saibyl-muted">Reading your work…</p>
        )}

        {!error && !loading && items.length === 0 && (
          /* The founder rule: a dead end is a defect, so the empty state
             carries the action that fills it. */
          <EmptyState
            headline="You haven't made anything yet"
            body="Run a check on your site, or put a product in front of a room. Whatever you make shows up here."
            action={{ label: 'Start something', href: '/app/home' }}
          />
        )}

        {!error && !loading && items.length > 0 && (
          <ul className="space-y-2">
            {items.map((item, index) => (
              <Reveal key={`${item.kind}-${item.id}`}>
                <Deal index={Math.min(index, 6)}>
                <Card carries="meaning" className="p-4">
                  <Link to={item.href} className="block group">
                    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                      <span className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-saibyl-blue">
                        {item.label}
                      </span>
                      <span className="text-[14px] font-medium text-saibyl-ink group-hover:underline truncate">
                        {item.title}
                      </span>
                    </div>
                    <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-saibyl-muted">
                      <span>{when(item.created_at)}</span>
                      {item.status && item.status !== 'complete' && (
                        <span className="text-saibyl-violet">{item.status}</span>
                      )}
                      {typeof item.credits === 'number' && item.credits > 0 && (
                        <span className="font-mono tabular-nums">
                          {item.credits.toLocaleString()} credits
                        </span>
                      )}
                    </div>
                  </Link>
                </Card>
                </Deal>
              </Reveal>
            ))}
          </ul>
        )}
        </Chapter>
      </Longform>
    </Ground>
  );
}
