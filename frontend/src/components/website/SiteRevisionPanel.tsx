import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { AxiosError } from 'axios';
import { ArrowRight, Loader2 } from 'lucide-react';

import api, { unwrapList } from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { Guarded } from '@/components/stages/StagePrimitives';
import { RevisionStatusChip } from './chips';
import SiteRevision from './SiteRevision';
import {
  REVISION_PATH,
  WEBSITE_ROOM_PATH,
  asEligibility,
  asRevisionListItem,
  childRunId,
  isRevisionUnderway,
  revisionStatusWord,
  type RoomEligibility,
  type SiteRevisionListItem,
  type SiteRevisionRow,
} from './types';

/**
 * The fix-and-prove panel under a finished check.
 *
 * One button starts the draft; the row is polled every four seconds until the
 * reviewers have scored the new page, and the finished draft renders through
 * `SiteRevision`. The backend for all of this is being built in parallel, so
 * every request here fails soft: a missing listing router costs nothing but
 * the resume-on-return nicety, and the POST is the probe that reports what is
 * actually wrong, in the API's own sentence.
 *
 * Money and gates stay the API's call, the same contract the check form
 * follows: 402 arrives with the sentence to show plus the one control that
 * fixes it, and a 409 (a draft already underway, or one too many) shows its
 * sentence and re-reads the listing so the panel adopts whatever the server
 * says exists.
 *
 * Callers should key this panel by the check's id so a different check gets a
 * fresh panel rather than an inherited one.
 */

export default function SiteRevisionPanel({
  snapshotId,
  productId,
}: {
  /** The finished check this draft would improve on. */
  snapshotId: string;
  /** Lets the panel ask whether the room can read the new page. */
  productId?: string;
}) {
  const [list, setList] = useState<SiteRevisionListItem[]>([]);
  const [revision, setRevision] = useState<SiteRevisionRow | null>(null);
  const [starting, setStarting] = useState(false);
  const [panelError, setPanelError] = useState<{
    message: string;
    billing: boolean;
  } | null>(null);

  const loadList = useCallback(() => {
    return api
      .get(REVISION_PATH, { params: { snapshot_id: snapshotId } })
      .then(({ data }) => {
        const items = unwrapList<unknown>(data)
          .items.map(asRevisionListItem)
          .filter((row): row is SiteRevisionListItem => row !== null)
          .sort((a, b) => b.created_at.localeCompare(a.created_at));
        setList(items);
        return items;
      });
  }, [snapshotId]);

  /* A founder who left mid-draft and came back resumes where the worker is:
     a draft still underway starts polling again, otherwise the newest
     finished one opens without another click. Failing quietly is deliberate —
     with no listing to read, the panel is simply a fresh start. */
  useEffect(() => {
    let alive = true;
    loadList()
      .then((items) => {
        if (!alive) return;
        const candidate =
          items.find((row) => isRevisionUnderway(row.status)) ??
          items.find((row) => row.status === 'complete');
        if (!candidate) return;
        return api
          .get<SiteRevisionRow>(`${REVISION_PATH}/${candidate.id}`)
          .then(({ data }) => {
            if (alive) setRevision(data);
          });
      })
      .catch(() => {
        // No listing yet — the draft button below is the probe that matters.
      });
    return () => {
      alive = false;
    };
  }, [loadList]);

  /* Poll the draft that is underway. A missed poll is not a failed draft —
     the next tick asks again, and the row keeps its last known state. */
  const revisionId = revision?.id;
  const revisionStatus = revision?.status;
  useEffect(() => {
    if (!revisionId || !isRevisionUnderway(revisionStatus)) return;
    const timer = setInterval(() => {
      api
        .get<SiteRevisionRow>(`${REVISION_PATH}/${revisionId}`)
        .then(({ data }) => setRevision(data))
        .catch(() => {});
    }, 4000);
    return () => clearInterval(timer);
  }, [revisionId, revisionStatus]);

  async function start() {
    setStarting(true);
    setPanelError(null);
    try {
      const { data } = await api.post<SiteRevisionRow>(REVISION_PATH, {
        snapshot_id: snapshotId,
      });
      setRevision(data);
      void loadList().catch(() => {});
    } catch (err) {
      const status = err instanceof AxiosError ? err.response?.status : undefined;
      setPanelError({
        message: getErrorMessage(err, 'We could not start drafting the page.'),
        billing: status === 402,
      });
      if (status === 409) {
        // The server says a draft already exists — adopt it rather than argue.
        void loadList()
          .then((items) => {
            const existing =
              items.find((row) => isRevisionUnderway(row.status)) ?? items[0];
            if (!existing) return;
            return api
              .get<SiteRevisionRow>(`${REVISION_PATH}/${existing.id}`)
              .then(({ data }) => setRevision(data));
          })
          .catch(() => {});
      }
    } finally {
      setStarting(false);
    }
  }

  function openDraft(id: string) {
    api
      .get<SiteRevisionRow>(`${REVISION_PATH}/${id}`)
      .then(({ data }) => setRevision(data))
      .catch((err) =>
        setPanelError({
          message: getErrorMessage(err, 'We could not open that draft.'),
          billing: false,
        }),
      );
  }

  /* While a draft is moving, the polled copy wins over its stale list row. */
  const rows = list.map((row) =>
    revision && row.id === revision.id
      ? { ...row, status: revision.status }
      : row,
  );
  const underway = revision !== null && isRevisionUnderway(revision.status);
  const complete = revision?.status === 'complete';
  const failed = revision?.status === 'failed';

  return (
    <div className="space-y-4">
      {panelError && (
        <div className="rounded-xl border border-saibyl-negative/25 bg-saibyl-negative/[0.07] p-4">
          <p className="text-[13px] text-saibyl-negative leading-relaxed">
            {panelError.message}
          </p>
          {panelError.billing && (
            <Link
              to="/app/settings/billing"
              className="inline-flex items-center gap-1.5 mt-3 px-3.5 py-1.5 rounded-lg bg-saibyl-gold text-saibyl-void text-[12px] font-semibold hover:bg-saibyl-gold-hover transition-colors"
            >
              Add credits
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          )}
        </div>
      )}

      {/* ── The way in ── */}
      {revision === null && (
        <div className="rounded-xl border border-saibyl-border bg-white p-5">
          <p className="text-[14px] font-medium text-saibyl-platinum">Fix it</p>
          <p className="text-[12.5px] text-saibyl-muted mt-1 leading-relaxed">
            Have Saibyl draft the improved page &mdash; the reviewers score it
            again so you see the difference in numbers.
          </p>
          <div className="mt-4">
            <Guarded
              label="Draft the improved page"
              onClick={start}
              busy={starting}
              busyLabel="Drafting and judging…"
            />
          </div>
        </div>
      )}

      {/* ── Underway ── */}
      {underway && revision && (
        <p
          className="flex items-center gap-2 text-[12.5px] text-saibyl-muted"
          aria-live="polite"
        >
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          {revisionStatusWord(revision.status)}&hellip;
        </p>
      )}

      {/* ── Did not finish ── */}
      {failed && revision && (
        <div className="rounded-xl border border-saibyl-negative/25 bg-saibyl-negative/[0.07] p-4">
          <p className="text-[13px] text-saibyl-negative leading-relaxed">
            {revision.error_message?.trim() ||
              'The draft did not finish. Your own page is untouched — drafting again starts fresh.'}
          </p>
          <div className="mt-3">
            <Guarded
              label="Draft the page again"
              onClick={start}
              busy={starting}
              busyLabel="Drafting and judging…"
            />
          </div>
        </div>
      )}

      {/* ── Done ── */}
      {complete && revision && (
        <>
          {/* Keyed so opening a different draft remounts the view — its Blob
              URLs and cached code belong to exactly one draft. */}
          <SiteRevision
            key={revision.id}
            revision={revision}
            snapshotId={snapshotId}
          />
          {productId && (
            <RoomRun
              key={revision.id}
              revisionId={revision.id}
              productId={productId}
            />
          )}
          <div className="flex flex-wrap items-center gap-3">
            <Guarded
              tone="quiet"
              label="Draft another pass"
              onClick={start}
              busy={starting}
              busyLabel="Drafting and judging…"
            />
          </div>
        </>
      )}

      {/* ── Earlier drafts ── */}
      {rows.length > 1 && (
        <div>
          <p className="text-[12px] text-saibyl-muted">
            Every draft of this page
          </p>
          <ul className="mt-1.5 space-y-1.5">
            {rows.map((row) => (
              <li
                key={row.id}
                className="flex flex-wrap items-center gap-2.5 text-[12.5px]"
              >
                <RevisionStatusChip status={row.status} />
                {row.overall_after !== null && (
                  <span className="font-mono text-[11.5px] text-saibyl-muted">
                    {row.overall_before ?? '—'} &rarr; {row.overall_after}
                  </span>
                )}
                {datePart(row.created_at) && (
                  <span className="text-[11px] text-saibyl-muted/70">
                    {datePart(row.created_at)}
                  </span>
                )}
                {row.status === 'complete' && revision?.id !== row.id && (
                  <button
                    type="button"
                    onClick={() => openDraft(row.id)}
                    className="text-saibyl-gold hover:underline"
                  >
                    See this draft
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/** The row's day, or nothing when the stamp is missing or unreadable. */
function datePart(createdAt: string): string {
  if (!createdAt) return '';
  const stamp = new Date(createdAt);
  return Number.isNaN(stamp.getTime()) ? '' : stamp.toLocaleDateString();
}

/* ------------------------------------------------------------------ */
/*  Prove it with the room                                             */
/* ------------------------------------------------------------------ */

/**
 * The room re-reads the new page — same buyers, same setup, so the difference
 * in what they say is attributable to the page and nothing else.
 *
 * Eligibility is the server's call. Not eligible with a reason renders the
 * reason quietly; not eligible without one, or an eligibility router that is
 * not there yet, renders nothing — an absent feature is not a finding.
 */
function RoomRun({
  revisionId,
  productId,
}: {
  revisionId: string;
  productId: string;
}) {
  const [eligibility, setEligibility] = useState<RoomEligibility | null>(null);
  const [running, setRunning] = useState(false);
  /** `{ childId }` once the room has the page; empty childId means the reply
   *  carried no id this frontend recognised, so the stage page is the link. */
  const [started, setStarted] = useState<{ childId: string } | null>(null);
  const [error, setError] = useState<{ message: string; billing: boolean } | null>(
    null,
  );

  useEffect(() => {
    let alive = true;
    api
      .get(`${WEBSITE_ROOM_PATH}/eligibility`, {
        params: { project_id: productId },
      })
      .then(({ data }) => {
        if (alive) setEligibility(asEligibility(data));
      })
      .catch(() => {
        // The router may not exist yet; nothing renders, nothing breaks.
      });
    return () => {
      alive = false;
    };
  }, [productId]);

  async function run() {
    setRunning(true);
    setError(null);
    try {
      const { data } = await api.post(`${WEBSITE_ROOM_PATH}/run`, {
        revision_id: revisionId,
      });
      setStarted({ childId: childRunId(data) ?? '' });
    } catch (err) {
      const status = err instanceof AxiosError ? err.response?.status : undefined;
      setError({
        message: getErrorMessage(
          err,
          'We could not put the new page in front of the room.',
        ),
        billing: status === 402,
      });
    } finally {
      setRunning(false);
    }
  }

  if (eligibility === null) return null;

  if (!eligibility.eligible) {
    return eligibility.reason ? (
      <p className="text-[12px] text-saibyl-muted leading-relaxed">
        {eligibility.reason}
      </p>
    ) : null;
  }

  return (
    <div className="rounded-xl border border-saibyl-gold/25 bg-saibyl-gold/[0.06] p-5">
      <p className="text-[14px] font-medium text-saibyl-platinum">
        Prove it with the room
      </p>
      <p className="text-[12.5px] text-saibyl-muted mt-1 leading-relaxed">
        The same buyers who read your current page can read the new one.
      </p>

      {error && (
        <div className="mt-3 rounded-xl border border-saibyl-negative/25 bg-saibyl-negative/[0.07] p-4">
          <p className="text-[13px] text-saibyl-negative leading-relaxed">
            {error.message}
          </p>
          {error.billing && (
            <Link
              to="/app/settings/billing"
              className="inline-flex items-center gap-1.5 mt-3 px-3.5 py-1.5 rounded-lg bg-saibyl-gold text-saibyl-void text-[12px] font-semibold hover:bg-saibyl-gold-hover transition-colors"
            >
              Add credits
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          )}
        </div>
      )}

      <div className="mt-4">
        {started ? (
          <Link
            to={
              started.childId
                ? `/app/simulations/${started.childId}/run`
                : `/app/products/${productId}/reactions`
            }
            className="inline-flex items-center gap-2 text-[13px] text-saibyl-gold hover:underline"
          >
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            The room is reading the new page &mdash; watch it in Reactions
          </Link>
        ) : (
          <Guarded
            label="Run the room against the new page"
            onClick={run}
            busy={running}
            busyLabel="Sending the new page into the room…"
          />
        )}
      </div>
    </div>
  );
}
