import { useCallback, useEffect, useRef, useState } from 'react';
import { Check, FileText, Loader2 } from 'lucide-react';

import api, { unwrapList } from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { documentStateWord, isBeingRead, isRead } from '@/lib/status';
import type { ICPProfile } from '@/lib/founder';
import type { ProjectDocument, MaterialKind } from '@/types';
import AudienceReview from '@/components/founder/AudienceReview';
import StageHeader from '@/components/stages/StageHeader';
import {
  EmptyState,
  Guarded,
  StageError,
} from '@/components/stages/StagePrimitives';
import { useProduct, useStage } from '@/components/stages/useProduct';

/**
 * Step 1 — who is going to react to this?
 *
 * Upload the deck, the landing page, the pricing page. One pass reads it and
 * proposes the buyers. The founder confirms, or corrects what looks wrong.
 *
 * The confirm control is the interesting part and it is not decoration.
 * `POST /icp/{id}/confirm` writes `confirmed_at`, and stage 4 reads it to decide
 * whether it is searching from a confirmed audience or from a guess. Agreement
 * and silence were sharing one column until migration 030; they are different
 * answers and the founder deserves to be told which one the search used.
 */

/** Whose material this is. The answer is a permission, so nothing pre-selects
 *  `competitor` — that value is what lets a simulated skeptic say a rival's
 *  name out loud, and a permission that arrives pre-ticked is one nobody gave. */
const MATERIAL_KINDS: { value: MaterialKind; label: string; help: string }[] = [
  {
    value: 'own',
    label: 'Mine',
    help: 'Something you wrote or published — your site, deck, pricing, docs.',
  },
  {
    value: 'competitor',
    label: "A competitor's",
    help: 'Something a rival published. Lets Saibyl name them by name.',
  },
  {
    value: 'market',
    label: 'Market research',
    help: 'Industry reports, analyst notes, survey results — nobody in particular.',
  },
];

export default function AudienceStagePage() {
  const { product, refresh } = useProduct();
  const stage = useStage('audience');

  const [documents, setDocuments] = useState<ProjectDocument[]>([]);
  const [profile, setProfile] = useState<ICPProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [pending, setPending] = useState<{ file: File; kind: MaterialKind }[]>([]);
  const [uploading, setUploading] = useState(false);
  const [working, setWorking] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [editing, setEditing] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    Promise.all([
      api.get('/documents', { params: { project_id: product.id } }),
      api.get('/icp', { params: { project_id: product.id } }),
    ])
      .then(([docs, profiles]) => {
        setDocuments(unwrapList<ProjectDocument>(docs.data).items);
        const list = unwrapList<ICPProfile>(profiles.data).items;
        setProfile(list.length > 0 ? list[0] : null);
        setError('');
      })
      .catch((err) => setError(getErrorMessage(err, 'We could not read this step.')))
      .finally(() => setLoading(false));
  }, [product.id]);

  useEffect(() => {
    load();
  }, [load]);

  /* Retrying is a click, so it says so. `load` itself never sets this: an
     effect that sets state synchronously on mount is a cascading render, and
     `loading` already starts true. */
  const retry = useCallback(() => {
    setLoading(true);
    load();
  }, [load]);


  // Poll while anything is still being read, so "Being read" does not sit there
  // forever after the worker has finished.
  useEffect(() => {
    const busy = documents.some((d) => isBeingRead(d.processing_status));
    if (!busy) return;
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, [documents, load]);

  async function upload() {
    if (pending.length === 0) return;
    setUploading(true);
    setError('');
    try {
      for (const item of pending) {
        const form = new FormData();
        form.append('file', item.file);
        await api.post('/documents/upload', form, {
          params: { project_id: product.id, material_kind: item.kind },
          headers: { 'Content-Type': 'multipart/form-data' },
        });
      }
      setPending([]);
      if (fileInput.current) fileInput.current.value = '';
      load();
      refresh();
    } catch (err) {
      setError(getErrorMessage(err, 'That upload did not go through.'));
    } finally {
      setUploading(false);
    }
  }

  async function workOutBuyers() {
    setWorking(true);
    setError('');
    try {
      const { data } = await api.post<ICPProfile>('/icp/synthesize', {
        project_id: product.id,
        adversarial: true,
        platforms: ['reddit', 'x'],
        adversarial_share: 0.3,
      });
      setProfile(data);
      refresh();
    } catch (err) {
      setError(getErrorMessage(err, 'We could not work out your buyers.'));
    } finally {
      setWorking(false);
    }
  }

  async function confirm() {
    if (!profile) return;
    setConfirming(true);
    setError('');
    try {
      const { data } = await api.post<ICPProfile>(`/icp/${profile.id}/confirm`);
      setProfile(data);
      refresh();
    } catch (err) {
      setError(getErrorMessage(err, 'We could not save that.'));
    } finally {
      setConfirming(false);
    }
  }

  const readable = documents.filter((d) => isRead(d.processing_status));
  const confirmed = Boolean(profile?.confirmed_at);

  return (
    <div className="space-y-6">
      <StageHeader stage={stage} />

      {error && <StageError message={error} retry={retry} />}

      {/* ── Your material ── */}
      <section id="material" className="glass rounded-2xl p-6 scroll-mt-6">
        <h2 className="text-[15px] font-medium text-saibyl-platinum">
          What you have written
        </h2>
        <p className="text-[12.5px] text-saibyl-muted mt-1 leading-relaxed">
          A deck, a landing page, a PRD, a pricing page. We read these to work out
          who buys this — nothing else is used.
        </p>

        <div id="upload" className="mt-4 scroll-mt-6">
          <input
            ref={fileInput}
            type="file"
            multiple
            accept=".pdf,.docx,.txt,.md"
            onChange={(e) =>
              setPending(
                Array.from(e.target.files ?? []).map((file) => ({
                  file,
                  kind: 'own' as MaterialKind,
                })),
              )
            }
            className="text-[13px] text-saibyl-muted file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-saibyl-gold/20 file:text-saibyl-gold file:font-medium file:cursor-pointer hover:file:bg-saibyl-gold/30"
          />
          <p className="text-[11px] text-saibyl-muted/70 mt-2">
            PDF, Word, plain text or Markdown. Up to 50MB each.
          </p>
        </div>

        {pending.length > 0 && (
          <div className="mt-5 space-y-3">
            <p className="text-[13px] text-saibyl-platinum">
              Whose is this? We ask so we know what the simulated buyers are allowed
              to say.
            </p>
            {pending.map((item, i) => (
              <div
                key={`${item.file.name}-${i}`}
                className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4"
              >
                <p className="text-[13px] text-saibyl-platinum truncate mb-2.5">
                  {item.file.name}
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                  {MATERIAL_KINDS.map((option) => {
                    const selected = item.kind === option.value;
                    return (
                      <button
                        key={option.value}
                        type="button"
                        aria-pressed={selected}
                        onClick={() =>
                          setPending((prev) =>
                            prev.map((p, j) =>
                              j === i ? { ...p, kind: option.value } : p,
                            ),
                          )
                        }
                        className={`text-left p-3 rounded-lg border transition-all ${
                          selected
                            ? 'border-saibyl-gold/50 bg-saibyl-gold/10'
                            : 'border-white/[0.06] bg-white/[0.02] hover:border-white/[0.12]'
                        }`}
                      >
                        <span
                          className={`block text-[13px] font-medium ${
                            selected ? 'text-saibyl-white' : 'text-saibyl-platinum'
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
            ))}

            {pending.some((p) => p.kind === 'competitor') && (
              <div className="px-4 py-3 rounded-xl border border-saibyl-gold/25 bg-saibyl-gold/[0.06]">
                <p className="text-[11px] text-saibyl-muted leading-relaxed">
                  Marking something as a rival&rsquo;s lets simulated skeptics name
                  that company and quote it, using only what the document actually
                  says. Without one, Saibyl refuses to name anyone — a model asked
                  about a rival will confidently make things up and you would have
                  no way of telling which parts.
                </p>
              </div>
            )}

            <Guarded
              label={`Upload ${pending.length === 1 ? 'this file' : `these ${pending.length} files`}`}
              onClick={upload}
              busy={uploading}
              busyLabel="Uploading…"
            />
          </div>
        )}

        <div className="mt-5">
          {loading && documents.length === 0 ? (
            <p className="flex items-center gap-2 text-[12.5px] text-saibyl-muted">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              Loading…
            </p>
          ) : documents.length === 0 ? (
            /* "Pick a file above" pointed at a control the reader had to go and
               find. The button opens it, which is the difference between naming
               a way forward and being one. */
            <p className="text-[12.5px] text-saibyl-muted">
              Nothing uploaded yet — the deck is usually the best first one.{' '}
              <button
                type="button"
                onClick={() => fileInput.current?.click()}
                className="text-saibyl-gold hover:underline"
              >
                Choose a file
              </button>
            </p>
          ) : (
            <ul className="space-y-1.5">
              {documents.map((doc) => (
                <li key={doc.id} className="flex items-center gap-2.5 text-[12.5px]">
                  <FileText className="w-3.5 h-3.5 text-saibyl-muted shrink-0" />
                  <span className="text-saibyl-platinum truncate">{doc.filename}</span>
                  <span
                    className={
                      doc.processing_status === 'failed'
                        ? 'text-saibyl-negative'
                        : 'text-saibyl-muted'
                    }
                  >
                    {documentStateWord(doc.processing_status)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      {/* ── Who buys this ── */}
      <section className="space-y-4">
        {profile === null ? (
          readable.length === 0 ? (
            <EmptyState
              headline="Nothing to read yet"
              body="We work out who buys this by reading what you have written. Upload the deck, the landing page or the pricing page and this step can run."
              action={{ label: 'Upload something', href: '#upload' }}
            />
          ) : (
            <div className="glass rounded-2xl p-6">
              <h2 className="text-[15px] font-medium text-saibyl-platinum">
                Ready to work out who buys this
              </h2>
              <p className="text-[12.5px] text-saibyl-muted mt-1.5 mb-4 leading-relaxed">
                We will read {readable.length === 1 ? 'your file' : `all ${readable.length} files`} and
                propose the groups of people likely to buy this — what they do, what
                they already use, and what would make them doubt you. You get to
                correct anything that looks wrong.
              </p>
              <Guarded
                label="Work out who buys this"
                onClick={workOutBuyers}
                busy={working}
                busyLabel="Reading your material…"
              />
            </div>
          )
        ) : editing ? (
          <AudienceReview
            profile={profile}
            platforms={['reddit', 'x']}
            adversarialShare={0.3}
            onSaved={(updated) => {
              setProfile(updated);
              setEditing(false);
              refresh();
            }}
            onClose={() => setEditing(false)}
          />
        ) : (
          <div className="glass rounded-2xl p-6">
            <h2 className="text-[15px] font-medium text-saibyl-platinum">
              Here&rsquo;s who we think will buy this
            </h2>
            <p className="text-[12.5px] text-saibyl-muted mt-1.5 leading-relaxed">
              {profile.profile.archetypes.length === 1
                ? 'One group of buyers'
                : `${profile.profile.archetypes.length} groups of buyers`}
              , worked out from your material.
            </p>

            <ul className="mt-4 space-y-2">
              {profile.profile.archetypes.map((archetype) => (
                <li
                  key={archetype.id}
                  className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-4 py-3"
                >
                  <p className="text-[13.5px] text-saibyl-platinum">
                    {archetype.label || 'Unnamed buyer'}
                  </p>
                  {archetype.role && (
                    <p className="text-[11.5px] text-saibyl-muted mt-0.5">
                      {archetype.role}
                    </p>
                  )}
                </li>
              ))}
            </ul>

            <div className="flex flex-wrap items-center gap-3 mt-5">
              {confirmed ? (
                <p className="flex items-center gap-2 text-[12.5px] text-saibyl-positive">
                  <Check className="w-3.5 h-3.5" />
                  You confirmed this. Every later step uses it.
                </p>
              ) : (
                <Guarded
                  label="This looks right"
                  onClick={confirm}
                  busy={confirming}
                  busyLabel="Saving…"
                />
              )}
              <button
                type="button"
                onClick={() => setEditing(true)}
                className="text-[12.5px] text-saibyl-gold hover:underline"
              >
                Something&rsquo;s wrong with this
              </button>
              <Guarded
                label="Find out what they object to"
                to={`/app/products/${product.id}/reactions`}
                tone="quiet"
              />
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
