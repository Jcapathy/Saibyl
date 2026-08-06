import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Check, Loader2, Pencil, Trash2, X } from 'lucide-react';
import { getErrorMessage } from '@/lib/errors';
import { deletePack, listPacks, renamePack } from '@/lib/packs';
import type { OrgPersonaPack } from '@/types';

/**
 * Audiences saved across the whole organisation.
 *
 * Working out who buys a product is the expensive part and it is not
 * project-specific: a founder testing three landing pages against the same
 * buyers should not pay to derive those buyers three times. So an audience
 * derived once is promoted here and reused, and a run can blend several —
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
  const navigate = useNavigate();
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
    if (!name) return;
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
    <div className="p-8 bg-saibyl-void min-h-full">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-h1 text-saibyl-white mb-1">Saved audiences</h1>
        <p className="text-small mb-2 max-w-2xl">
          Working out who buys something is the slow part. Saibyl has to read everything you
          have written before it can tell you, and it charges you for that reading.
        </p>
        <p className="text-small mb-8 max-w-2xl">
          So you only have to do it once. Keep a set of buyers here and you can point it at
          anything else you sell — pick one when you set up a run, or pick several and they
          all end up in the same room.
        </p>

        {actionError && (
          <div className="mb-4 px-4 py-3 rounded-xl bg-saibyl-negative/10 border border-saibyl-negative/20 text-saibyl-negative text-sm">
            {actionError}
            <button onClick={() => setActionError('')} className="ml-3 underline">
              dismiss
            </button>
          </div>
        )}

        {loading && (
          <div className="glass rounded-2xl p-12 text-center">
            <Loader2 className="w-5 h-5 animate-spin text-saibyl-muted mx-auto" />
          </div>
        )}

        {!loading && loadError && (
          <div className="glass rounded-2xl p-8">
            <p className="text-[14px] text-saibyl-platinum font-medium mb-1">
              We couldn&rsquo;t load your saved audiences
            </p>
            <p className="text-[12px] text-saibyl-muted leading-relaxed mb-4">
              {loadError} This is not the same as having none saved — we simply
              don&rsquo;t know right now, so nothing is being shown.
            </p>
            <button
              onClick={() => void load()}
              className="px-4 py-2 rounded-lg bg-saibyl-gold text-saibyl-void text-[13px] font-medium hover:bg-saibyl-gold-hover transition-colors"
            >
              Try again
            </button>
          </div>
        )}

        {!loading && !loadError && packs.length === 0 && (
          <div className="glass rounded-2xl p-12 text-center">
            <p className="text-saibyl-platinum font-medium mb-2">Nothing saved yet</p>
            <p className="text-saibyl-muted text-sm max-w-md mx-auto leading-relaxed">
              When you set up a run, Saibyl reads what you have uploaded and works out who
              your buyers are. Keep that set of buyers and it shows up here, ready to use on
              anything else you sell.
            </p>
            <button
              onClick={() => navigate('/app/simulations/new')}
              className="mt-5 px-5 py-2.5 rounded-lg bg-saibyl-gold text-saibyl-void text-[13px] font-medium hover:bg-saibyl-gold-hover transition-colors"
            >
              Set up a run
            </button>
          </div>
        )}

        {!loading && !loadError && packs.length > 0 && (
          <div className="glass rounded-2xl overflow-hidden">
            {packs.map((pack, i) => {
              const names = buyerNames(pack);
              return (
              <div
                key={pack.id}
                className={`px-5 py-4 ${i > 0 ? 'border-t border-white/[0.04]' : ''}`}
              >
                <div className="flex items-center justify-between gap-4">
                  {editingId === pack.id ? (
                    <div className="flex items-center gap-2 flex-1 min-w-0">
                      <input
                        value={draftName}
                        autoFocus
                        maxLength={120}
                        onChange={(e) => setDraftName(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') void commitRename(pack.id);
                          if (e.key === 'Escape') setEditingId(null);
                        }}
                        className="flex-1 min-w-0 rounded-lg bg-[#0B1120] border border-white/[0.08] px-3 py-1.5 text-[14px] text-saibyl-platinum focus:outline-none focus:ring-1 focus:ring-saibyl-gold/50"
                      />
                      <button
                        onClick={() => void commitRename(pack.id)}
                        disabled={busyId === pack.id || !draftName.trim()}
                        className="text-saibyl-positive hover:opacity-80 disabled:opacity-30"
                        aria-label="Save name"
                      >
                        <Check className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => setEditingId(null)}
                        className="text-saibyl-muted hover:text-saibyl-platinum"
                        aria-label="Cancel rename"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  ) : (
                    <div className="min-w-0">
                      <p className="text-[14px] font-medium text-saibyl-platinum truncate">
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
                        className="text-saibyl-muted hover:text-saibyl-platinum transition-colors"
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

                {confirmingId === pack.id && (
                  <div className="mt-3 px-4 py-3 rounded-xl bg-saibyl-negative/[0.08] border border-saibyl-negative/20">
                    <p className="text-[12px] text-saibyl-silver leading-relaxed">
                      Delete &ldquo;{pack.name}&rdquo;? Runs that already used these buyers
                      keep their results — those people were created when the run started.
                      What you lose is the ability to pick this audience for a new run.
                    </p>
                    <div className="flex items-center gap-3 mt-3">
                      <button
                        onClick={() => void confirmDelete(pack.id)}
                        disabled={busyId === pack.id}
                        className="px-3 py-1.5 rounded-lg text-[12px] font-medium bg-saibyl-negative text-white hover:opacity-90 disabled:opacity-50 transition-opacity"
                      >
                        {busyId === pack.id ? 'Deleting…' : 'Delete it'}
                      </button>
                      <button
                        onClick={() => setConfirmingId(null)}
                        className="text-[12px] text-saibyl-muted hover:text-saibyl-platinum"
                      >
                        Keep it
                      </button>
                    </div>
                  </div>
                )}
              </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
