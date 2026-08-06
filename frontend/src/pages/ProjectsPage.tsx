import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import api from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import type { Project } from '@/types';

/**
 * Every product in the account.
 *
 * ── THREE SWALLOWED FAILURES, AND WHAT EACH ONE TOLD THE FOUNDER ───────────
 * All three were `catch {}` with a comment in it. None of them logged, none
 * rendered, and the page carried on as though the request had succeeded.
 *
 * **The list.** A failed `GET /projects` left `projects` at `[]` and `loading`
 * at false, so the page rendered "No products yet" over an account full of
 * them. That is not a missing error message — it is the page stating, as a
 * fact, that the founder's work is gone.
 *
 * **Create.** The modal closed, the fields cleared and the list refetched
 * without the product in it. Indistinguishable from a product that was created
 * and then failed to appear.
 *
 * **Delete.** The card stayed. A founder who pressed delete and watched nothing
 * happen presses it again.
 *
 * The rule this file now follows is the one `ProjectDetailPage` already uses:
 * a count or an empty state is a claim about the account, and a request that
 * failed supports neither. `loaded` is set only on success.
 */

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  // Set only on success. "No products yet" is rendered from this and not from
  // `projects.length`, which is also 0 when the request failed.
  const [loaded, setLoaded] = useState(false);
  const [listError, setListError] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState('');
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState('');

  const fetchProjects = useCallback(() => {
    api.get('/projects')
      .then((res) => {
        setProjects(res.data.items || res.data);
        setLoaded(true);
        setListError('');
      })
      .catch((err) =>
        setListError(getErrorMessage(err, 'We could not load your products.')),
      )
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { fetchProjects(); }, [fetchProjects]);

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault();
    setCreating(true);
    setCreateError('');
    try {
      await api.post('/projects', { name, description });
      setShowModal(false);
      setName('');
      setDescription('');
      fetchProjects();
    } catch (err) {
      // The modal stays open with what they typed still in it. Closing it and
      // clearing the fields — which is what the success path does — was how a
      // failed create read as a successful one.
      setCreateError(getErrorMessage(err, 'We could not create that product.'));
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (id: string) => {
    setDeletingId(id);
    setDeleteError('');
    try {
      await api.delete(`/projects/${id}`);
      setProjects((prev) => prev.filter((p) => p.id !== id));
    } catch (err) {
      setDeleteError(getErrorMessage(err, 'We could not delete that product.'));
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-saibyl-platinum">Your products</h1>
        <button
          onClick={() => setShowModal(true)}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-[#C9A227] text-white font-medium text-sm transition-all hover:bg-[#B08D1F] hover:scale-[1.02] hover:shadow-[0_0_20px_rgba(201,162,39,0.25)]"
        >
          + New product
        </button>
      </div>

      {deleteError && (
        <div
          role="alert"
          className="mb-4 rounded-xl border border-red-500/25 bg-red-500/[0.07] px-4 py-3 text-sm text-red-300"
        >
          {deleteError}
        </div>
      )}

      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-36 rounded-2xl bg-saibyl-deep animate-pulse" />
          ))}
        </div>
      ) : !loaded ? (
        /* The list did not come back. Anything else here — an empty state, a
           count, a "create your first product" — is a claim about the account
           that this page cannot support. */
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <p className="text-saibyl-platinum font-medium mb-1">
            We could not load your products
          </p>
          <p className="text-saibyl-muted text-sm mb-6 max-w-sm">
            {listError} Nothing has been changed or lost — this is a failure to
            read, not to keep.
          </p>
          <button
            onClick={() => {
              setLoading(true);
              fetchProjects();
            }}
            className="bg-saibyl-gold text-white px-5 py-2.5 rounded-xl text-sm font-medium hover:bg-[#B08D1F] transition"
          >
            Try again
          </button>
        </div>
      ) : projects.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <div className="w-14 h-14 rounded-2xl bg-saibyl-gold/10 flex items-center justify-center mb-4">
            <svg className="w-7 h-7 text-saibyl-gold" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z" />
            </svg>
          </div>
          <p className="text-saibyl-platinum font-medium mb-1">No products yet</p>
          <p className="text-saibyl-muted text-sm mb-6">One product for each thing you are trying to sell</p>
          <button onClick={() => setShowModal(true)} className="bg-saibyl-gold text-white px-5 py-2.5 rounded-xl text-sm font-medium hover:bg-[#4B4FDE] transition">
            Create your first product
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map((p, i) => (
            <motion.div
              key={p.id}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: i * 0.05 }}
              className="relative group"
            >
              <Link
                to={`/app/projects/${p.id}`}
                className="block bg-saibyl-deep rounded-2xl p-5 border border-white/[0.05] hover:border-saibyl-gold/20 hover:bg-saibyl-elevated transition-all"
              >
                <div className="w-9 h-9 rounded-xl bg-saibyl-gold/10 flex items-center justify-center mb-4 group-hover:bg-saibyl-gold/15 transition-colors">
                  <svg className="w-[18px] h-[18px] text-saibyl-gold" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z" />
                  </svg>
                </div>
                <h3 className="font-semibold text-saibyl-platinum mb-1 group-hover:text-white transition-colors">{p.name}</h3>
                {/* Only when there is one. "No description" is filler standing in
                    for something nobody wrote, and it reads as a fact about the
                    product rather than an absence of one. */}
                {p.description && (
                  <p className="text-sm text-saibyl-muted line-clamp-2">{p.description}</p>
                )}
                {/*
                  `document_count`, counted from `documents` by the server on
                  every request. **Not `asset_count`**, which is what this line
                  used to render and which read "0 documents" on products that
                  demonstrably had files in them: migration 010 added that
                  column with `DEFAULT 0` and never backfilled it, migration 025
                  records that the RPC the upload route calls existed in
                  production only because someone added it by hand, the media
                  ingestion path built the same request without `.execute()`, and
                  the upload route logs and carries on when the RPC fails. A zero
                  there meant "this counter never incremented", which is a
                  different claim from "this product has no files".

                  Rendered only when the field is present, so a client talking to
                  an older server shows nothing rather than a zero it inferred
                  from an absence. That is the same distinction the counter got
                  wrong, one layer out.
                */}
                {typeof p.document_count === 'number' && (
                  <p className="text-xs text-saibyl-muted/70 mt-2">
                    {p.document_count === 0
                      ? 'No files yet'
                      : `${p.document_count} file${p.document_count === 1 ? '' : 's'}`}
                  </p>
                )}
              </Link>
              <button
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  if (confirm(`Delete "${p.name}"? This cannot be undone.`)) {
                    handleDelete(p.id);
                  }
                }}
                disabled={deletingId === p.id}
                className="absolute top-3 right-3 w-7 h-7 rounded-lg flex items-center justify-center opacity-0 group-hover:opacity-100 bg-white/[0.04] hover:bg-red-500/20 text-saibyl-muted hover:text-red-400 transition-all"
                title="Delete this product"
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </motion.div>
          ))}
        </div>
      )}

      {/* Create Modal */}
      <AnimatePresence>
        {showModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4"
            onClick={(e) => e.target === e.currentTarget && setShowModal(false)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 12 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 12 }}
              transition={{ duration: 0.2 }}
              role="dialog"
              aria-modal="true"
              aria-labelledby="new-product-heading"
              className="glass rounded-2xl p-6 w-full max-w-md border border-white/[0.08] shadow-[0_0_60px_rgba(0,0,0,0.5)]"
            >
              <h2
                id="new-product-heading"
                className="text-lg font-semibold text-saibyl-platinum mb-5"
              >
                New product
              </h2>
              <form onSubmit={handleCreate} className="space-y-4">
                <div>
                  <label className="block text-[12px] font-medium text-saibyl-muted uppercase tracking-wide mb-1.5">What is it called?</label>
                  <input
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Acme Invoicing"
                    className="w-full bg-white/[0.04] border border-white/[0.07] rounded-xl px-4 py-2.5 text-saibyl-platinum placeholder-saibyl-muted/40 focus:outline-none focus:ring-2 focus:ring-saibyl-gold/50 transition text-sm"
                  />
                </div>
                <div>
                  <label className="block text-[12px] font-medium text-saibyl-muted uppercase tracking-wide mb-1.5">
                    What does it do? <span className="normal-case text-saibyl-muted/50 ml-1 font-normal">(optional)</span>
                  </label>
                  <textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    rows={3}
                    placeholder="What does it do, in one line?"
                    className="w-full bg-white/[0.04] border border-white/[0.07] rounded-xl px-4 py-2.5 text-saibyl-platinum placeholder-saibyl-muted/40 focus:outline-none focus:ring-2 focus:ring-saibyl-gold/50 transition text-sm resize-none"
                  />
                </div>
                {createError && (
                  <p
                    role="alert"
                    className="rounded-xl border border-red-500/25 bg-red-500/[0.07] px-4 py-3 text-sm text-red-300"
                  >
                    {createError}
                  </p>
                )}
                <div className="flex justify-end gap-3 pt-1">
                  <button
                    type="button"
                    onClick={() => setShowModal(false)}
                    className="px-4 py-2 text-saibyl-muted hover:text-saibyl-platinum transition-colors text-sm"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={creating}
                    className="bg-saibyl-gold text-white px-5 py-2 rounded-xl text-sm font-medium hover:bg-[#4B4FDE] disabled:opacity-50 transition"
                  >
                    {creating ? 'Creating…' : 'Create product'}
                  </button>
                </div>
              </form>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
