import { useCallback, useEffect, useState } from 'react';
import { Check, Loader2, Pencil, Trash2, X } from 'lucide-react';
import { getErrorMessage } from '@/lib/errors';
import { deletePack, listPacks, renamePack } from '@/lib/packs';
import { Action, Card, Deal, Ground, Notice, PageHeader, Rise } from '@/components/design';
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
 */

/** How many buyer names a row shows before it stops listing them. */
const NAMES_SHOWN = 4;

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

  return (
    <Ground className="p-8 min-h-full">
      <div className="max-w-4xl mx-auto">
        <Rise className="mb-8">
          <PageHeader
            eyebrow="Audiences you can reuse"
            title="Saved audiences"
            phrase="The expensive half, done once and kept."
            mark={packs.length > 0 ? `${packs.length} saved` : undefined}
          >
            <p>
              Working out who buys something is the slow part. Saibyl has to read
              everything you have written before it can tell you, and it charges
              you for that reading.
            </p>
            <p className="mt-2">
              So you only have to do it once. Keep a set of buyers here and you
              can point it at anything else you sell &mdash; pick one when you
              set up a run, or pick several and they all end up in the same room.
            </p>
          </PageHeader>
        </Rise>

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
            action={<Action onClick={() => void load()}>Try again</Action>}
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
      </div>
    </Ground>
  );
}
