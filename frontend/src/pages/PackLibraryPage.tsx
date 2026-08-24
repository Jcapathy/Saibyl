import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Check, Loader2, Pencil, Trash2, X } from 'lucide-react';
import { getErrorMessage } from '@/lib/errors';
import { deletePack, listPacks, renamePack } from '@/lib/packs';
import {
  Action,
  Card,
  Chapter,
  Deal,
  Ground,
  Hero,
  Longform,
  Notice,
  Reveal,
} from '@/components/design';
import { EmptyState } from '@/components/stages/StagePrimitives';
import type { OrgPersonaPack } from '@/types';

/**
 * Audiences saved across the whole organisation.
 *
 * Working out who buys a product is the expensive part and it is not tied to
 * one product: a founder testing three landing pages against the same buyers
 * should not pay to derive those buyers three times. So an audience derived
 * once is promoted here and reused, and a run can blend several —
 * `simulations.persona_pack_ids` has always been a list.
 *
 * Everything below `name` is rendered only when the server sends it. A missing
 * archetype count shows nothing rather than a zero: "we were not told" and
 * "this audience contains nobody" are different facts, and only one of them
 * should worry the reader.
 *
 * What each row *shows* changed after an acceptance reader asked what this page
 * was for. It rendered `description` — a machine-written one-liner that came out
 * as `bi-directional AI security for regulated enterprise decision-makers, low
 * switching cost`, which is a database column printed at a person. The names of
 * the buyers inside (`archetype_labels`, computed by the server from the pack
 * body) are the thing a human can actually recognise, so those are what the row
 * leads with now. `description` is no longer rendered anywhere: it is derived
 * from the same pack body the labels come from, so nothing is lost that the
 * labels do not say more plainly.
 *
 * ---
 *
 * **The restyle (2026-08-23).** The page painted `bg-saibyl-void` over the
 * ground `<body>` carries and said every state — loading, failed, empty — in
 * the same grey body text, which is the mechanical reason a screen full of
 * real information read as sterile. It now composes `components/design/`: the
 * washed ground, a dotted eyebrow, one accent phrase, and the artboard's
 * tinted blocks for the two states that are not a list. The list itself is a
 * `density` card — hairlines, no shadow per row, exactly as the canvas says.
 *
 * ---
 *
 * **And the frame, later the same day: every page behind the login is a
 * landing page.** Hero, large type, then scroll — `GuidePage`'s shape, whose
 * values are `pages/landing.css`'s own.
 *
 * Three notes on how that was applied here, because each one is a thing the
 * next page to be converted will get wrong:
 *
 * - **The hero renders in every state.** Loading, failed, empty and full are a
 *   switch on the body of the first chapter and nothing else.
 * - **The second half of the old explainer moved rather than went.** It was two
 *   paragraphs stacked under one heading; the first is the hero's lead and the
 *   second is the lead of "Using one", which is the section it was already
 *   describing.
 * - **The rows stay on `Deal`, not `Reveal`.** `useReveal` queries its subtree
 *   once, when `Longform` mounts, so a row that arrives after the fetch is
 *   never observed and would sit at `opacity: 0` for good. `Reveal` is for the
 *   static chapters, which exist on mount.
 *
 * Density is untouched: the same 14px name, the same 12px buyer line, the same
 * `px-5 py-4` row.
 */

/** How many buyer names a row shows before it stops listing them. */
const NAMES_SHOWN = 4;

/**
 * What a row is actually telling you, for the founder reading their first one.
 *
 * Both lines describe the render below rather than a nicer one: the names come
 * from `buyerNames`, and the two facts under them are the pair that is dropped
 * entirely when the server did not send them.
 */
const WHAT_A_ROW_SHOWS = [
  {
    title: 'The names, first',
    body:
      'Computed from the audience itself, so they are the words those buyers were actually given — not a label you typed when you saved it. Four of them, and then a count of the rest.',
  },
  {
    title: 'And nothing that was not measured',
    body:
      'How many kinds of buyer, and the day it was kept, shown only when Saibyl was told. A missing number renders as nothing rather than as a zero, because “we were not told” and “this audience contains nobody” are different facts and only one of them should worry you.',
  },
] as const;

/**
 * The buyers inside a saved audience, named.
 *
 * `archetype_labels` is computed by the server off the pack body and defaults a
 * missing label to an empty string, so blanks are dropped here rather than
 * rendered as an unnamed buyer. Returns an empty list when the field is absent
 * entirely — the caller renders nothing in that case, because "we were not told
 * who is in here" is not something to paper over with a placeholder.
 */
function buyerNames(pack: OrgPersonaPack): string[] {
  const labels = (pack.archetype_labels ?? []).map((l) => l.trim()).filter(Boolean);
  if (labels.length <= NAMES_SHOWN) return labels;
  return [
    ...labels.slice(0, NAMES_SHOWN),
    `and ${labels.length - NAMES_SHOWN} more`,
  ];
}

export default function PackLibraryPage() {
  const [packs, setPacks] = useState<OrgPersonaPack[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [actionError, setActionError] = useState('');

  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftName, setDraftName] = useState('');
  const [busyId, setBusyId] = useState<string | null>(null);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError('');
    try {
      setPacks(await listPacks());
    } catch (err) {
      // Distinguished from an empty library on purpose. Rendering "no saved
      // audiences" when the request failed would tell the user their work is
      // gone.
      setLoadError(getErrorMessage(err, 'Your saved audiences could not be loaded.'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const startRename = (pack: OrgPersonaPack) => {
    setEditingId(pack.id);
    setDraftName(pack.name);
    setActionError('');
  };

  const commitRename = async (id: string) => {
    const name = draftName.trim();
    if (!name) {
      // Said, not enforced by a greyed-out tick. The save control used to carry
      // `disabled={!draftName.trim()}`, which is the one rendering the founder's
      // standing rule refuses: a control either runs and states what is wrong,
      // or it is blocked with the reason beside it.
      setActionError('Give it a name — an audience with no name is one you cannot find again.');
      return;
    }
    setBusyId(id);
    setActionError('');
    try {
      const updated = await renamePack(id, name);
      setPacks((prev) =>
        prev.map((pack) => (pack.id === id ? { ...pack, ...updated } : pack)),
      );
      setEditingId(null);
    } catch (err) {
      setActionError(getErrorMessage(err, 'That name could not be saved.'));
    } finally {
      setBusyId(null);
    }
  };

  const confirmDelete = async (id: string) => {
    setBusyId(id);
    setActionError('');
    try {
      await deletePack(id);
      setPacks((prev) => prev.filter((pack) => pack.id !== id));
      setConfirmingId(null);
    } catch (err) {
      setActionError(getErrorMessage(err, 'That audience could not be deleted.'));
    } finally {
      setBusyId(null);
    }
  };

  /*
    Where the one gradient goes.

    Under the longform frame a page's one primary action lives in the hero, and
    on this page that is "Set up a run" — the only thing here that is not
    "open, rename or delete something that already exists". The exception is the
    state where the library could not be read at all: nothing on the page can be
    trusted until the retry succeeds, so the gradient moves to it and the hero's
    button steps back to `quiet`. Derived once, here, rather than decided twice
    at two render sites that would eventually disagree.
  */
  const gradient: 'retry' | 'run' = !loading && loadError ? 'retry' : 'run';

  return (
    <Ground className="min-h-full pb-24">
      <Longform>
        {/* Never wrapped in `Reveal`, and outside every branch below. */}
        <Hero
          eyebrow="Audiences you can reuse"
          title="The expensive half,"
          serif="done once."
          actions={
            <Action
              as={Link}
              to="/app/simulations/new"
              kind={gradient === 'run' ? 'primary' : 'quiet'}
            >
              Set up a run
            </Action>
          }
        >
          <p>
            Working out who buys something is the slow part. Saibyl has to read
            everything you have written before it can tell you, and it charges
            you for that reading.{' '}
            <b className="text-saibyl-ink font-semibold">
              The expensive half, done once and kept.
            </b>
          </p>
        </Hero>

        {/* ── The library ──
            Loading, failed, empty and full switch here and nowhere else. */}
        <Chapter
          kicker="Saved audiences"
          title={
            <>
              The rooms you can <em>use again</em>
            </>
          }
          lead={
            <>
              Rename one so you can find it later, and delete it when it stops
              matching what you sell.
              {packs.length > 0 && <> You have {packs.length} kept so far.</>}
            </>
          }
        >
          {actionError && (
            <div
              role="alert"
              className="mb-4 px-4 py-3 rounded-xl bg-saibyl-negative/10 border border-saibyl-negative/20 text-saibyl-negative text-sm"
            >
              {actionError}
              <button onClick={() => setActionError('')} className="ml-3 underline">
                dismiss
              </button>
            </div>
          )}

          {loading && (
            <Card carries="stage" className="p-12 text-center">
              <Loader2 className="w-5 h-5 animate-spin text-saibyl-muted mx-auto" />
            </Card>
          )}

          {/* A failed read is a state, and the canvas says a state is told in
              colour with the control that resolves it inside it — not in the
              same grey body text as everything else on the screen. */}
          {!loading && loadError && (
            <Notice
              tone="blocked"
              title="We couldn’t load your saved audiences"
              action={
                <Action
                  onClick={() => void load()}
                  kind={gradient === 'retry' ? 'primary' : 'quiet'}
                >
                  Try again
                </Action>
              }
            >
              {loadError} This is not the same as having none saved &mdash; we
              simply don&rsquo;t know right now, so nothing is being shown.
            </Notice>
          )}

          {!loading && !loadError && packs.length === 0 && (
            <EmptyState
              headline="Nothing saved yet"
              body="When you set up a run, Saibyl reads what you have uploaded and works out who your buyers are. Keep that set of buyers and it shows up here, ready to use on anything else you sell."
              action={{ label: 'Set up a run', href: '/app/simulations/new' }}
            />
          )}

          {!loading && !loadError && packs.length > 0 && (
            /* `density`. This is a list of rows, and the canvas is explicit that
               hairlines stay on dense lists — a soft shadow under every row and
               the page turns to soup. */
            <Card carries="density" className="overflow-hidden">
              {packs.map((pack, i) => {
                const names = buyerNames(pack);
                const busy = busyId === pack.id;
                return (
                <Deal
                  key={pack.id}
                  index={i}
                  className={`px-5 py-4 ${i > 0 ? 'border-t border-saibyl-border' : ''}`}
                >
                  <div className="flex items-center justify-between gap-4">
                    {editingId === pack.id ? (
                      <div className="flex items-center gap-2 flex-1 min-w-0">
                        <input
                          value={draftName}
                          autoFocus
                          maxLength={120}
                          aria-label={`Name for ${pack.name}`}
                          onChange={(e) => setDraftName(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') void commitRename(pack.id);
                            if (e.key === 'Escape') setEditingId(null);
                          }}
                          className="flex-1 min-w-0 rounded-lg bg-white border border-saibyl-border-light px-3 py-1.5 text-[14px] text-saibyl-ink placeholder:text-saibyl-muted/70 focus:outline-none focus:border-saibyl-blue focus:ring-2 focus:ring-saibyl-blue/20"
                        />
                        {busy ? (
                          <span aria-live="polite" title="Saving…" className="text-saibyl-muted">
                            <Loader2 className="w-4 h-4 animate-spin" />
                          </span>
                        ) : (
                          <button
                            onClick={() => void commitRename(pack.id)}
                            className="text-saibyl-positive hover:opacity-80"
                            aria-label="Save name"
                          >
                            <Check className="w-4 h-4" />
                          </button>
                        )}
                        <button
                          onClick={() => setEditingId(null)}
                          className="text-saibyl-muted hover:text-saibyl-ink"
                          aria-label="Cancel rename"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      </div>
                    ) : (
                      <div className="min-w-0">
                        <p className="text-[14px] font-medium text-saibyl-ink truncate">
                          {pack.name}
                        </p>
                        {/* Who is actually in it, in the words the buyers were
                            given. This is the line that makes the row mean
                            something: a name alone tells you what you called it,
                            not who you would be selling to. Empty labels are
                            dropped rather than rendered as gaps — the server
                            defaults a missing one to "" and a bare separator
                            would read as a buyer with no name. */}
                        {names.length > 0 && (
                          <p className="text-[12px] text-saibyl-silver mt-1 leading-relaxed">
                            {names.join(' · ')}
                          </p>
                        )}
                        <div className="flex items-center gap-3 mt-1">
                          {pack.archetype_count != null && (
                            <span className="text-[11px] text-saibyl-muted">
                              {pack.archetype_count} kind
                              {pack.archetype_count === 1 ? '' : 's'} of buyer
                            </span>
                          )}
                          {pack.created_at && (
                            <span className="text-[11px] text-saibyl-muted">
                              saved {new Date(pack.created_at).toLocaleDateString()}
                            </span>
                          )}
                        </div>
                      </div>
                    )}

                    {editingId !== pack.id && (
                      <div className="flex items-center gap-3 shrink-0">
                        <button
                          onClick={() => startRename(pack)}
                          className="text-saibyl-muted hover:text-saibyl-ink transition-colors"
                          title="Rename"
                          aria-label={`Rename ${pack.name}`}
                        >
                          <Pencil className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => setConfirmingId(pack.id)}
                          className="text-saibyl-muted hover:text-saibyl-negative transition-colors"
                          title="Delete"
                          aria-label={`Delete ${pack.name}`}
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    )}
                  </div>

                  {/* Red rather than the artboard's violet, and deliberately: a
                      `blocked` notice means "supply something and this proceeds",
                      and this one means "press it and the thing is gone". */}
                  {confirmingId === pack.id && (
                    <div className="mt-3 px-4 py-3 rounded-xl bg-saibyl-negative/[0.08] border border-saibyl-negative/20">
                      <p className="text-[12px] text-saibyl-silver leading-relaxed">
                        Delete &ldquo;{pack.name}&rdquo;? Runs that already used these buyers
                        keep their results — those people were created when the run started.
                        What you lose is the ability to pick this audience for a new run.
                      </p>
                      <div className="flex items-center gap-3 mt-3">
                        {busy ? (
                          <span
                            aria-live="polite"
                            className="px-3 py-1.5 rounded-lg text-[12px] font-medium bg-saibyl-negative text-white opacity-70"
                          >
                            Deleting…
                          </span>
                        ) : (
                          <button
                            onClick={() => void confirmDelete(pack.id)}
                            className="px-3 py-1.5 rounded-lg text-[12px] font-medium bg-saibyl-negative text-white hover:opacity-90 transition-opacity"
                          >
                            Delete it
                          </button>
                        )}
                        <button
                          onClick={() => setConfirmingId(null)}
                          className="text-[12px] text-saibyl-muted hover:text-saibyl-ink"
                        >
                          Keep it
                        </button>
                      </div>
                    </div>
                  )}
                </Deal>
                );
              })}
            </Card>
          )}
        </Chapter>

        {/* ── Reading a row ──
            Static, so the scroll-reveal observer picks it up on mount. */}
        <Chapter
          kicker="What a row shows"
          title={
            <>
              Who is in it, not just <em>what you called it</em>
            </>
          }
          lead="A name tells you what you called an audience. The line under it tells you who you would be selling to, which is the thing you are actually choosing between."
        >
          <div className="space-y-3">
            {WHAT_A_ROW_SHOWS.map((item, i) => (
              <Reveal key={item.title} step={i as 0 | 1}>
                {/* `density` — hairlines, no shadow per row. */}
                <Card carries="density" className="p-5">
                  <h3 className="text-[13.5px] font-semibold text-saibyl-ink mb-1">
                    {item.title}
                  </h3>
                  <p className="text-[13px] text-saibyl-muted leading-relaxed">
                    {item.body}
                  </p>
                </Card>
              </Reveal>
            ))}
          </div>
        </Chapter>

        {/* ── The way out ──
            The second half of the old page explainer, now sitting under the
            heading it was already describing. `quiet`, because the gradient on
            this screen was spent in the hero. */}
        <Chapter
          kicker="Using one"
          title={
            <>
              Point it at anything <em>else you sell</em>
            </>
          }
          lead="So you only have to do it once. Keep a set of buyers here and you can point it at anything else you sell — pick one when you set up a run, or pick several and they all end up in the same room."
        >
          <Reveal>
            <Action as={Link} to="/app/simulations/new" kind="quiet">
              Set up a run
            </Action>
          </Reveal>
        </Chapter>
      </Longform>
    </Ground>
  );
}
