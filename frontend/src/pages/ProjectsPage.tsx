import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { Folder, Loader2, Plus, Trash2 } from 'lucide-react';

import api from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { cn } from '@/lib/utils';
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
  Rise,
  cardSurface,
} from '@/components/design';
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
 *
 * ---
 *
 * **The restyle (2026-08-23).** This page had never been converted off the
 * dark theme. It rendered `saibyl-platinum`, `saibyl-white` and eleven
 * `saibyl-gold`s, all of which still *resolve* — the token file remapped them
 * to light values when the theme flipped — so it kept looking plausible and
 * nobody noticed it was never designed on the light system. It now composes
 * `components/design/` like every other converted surface: a washed ground, a
 * dotted eyebrow, one accent phrase, soft shadows only where a card carries a
 * claim, and the artboard's own deal-then-rise arrival instead of a second
 * motion vocabulary imported from framer-motion.
 *
 * ---
 *
 * **And the frame, later the same day: every page behind the login is a
 * landing page.** Hero, large type, then scroll — `GuidePage`'s shape, whose
 * values are `pages/landing.css`'s own. The founder read the app next to the
 * public site and called it "very sterile, mechanical, and looks
 * AI-generated"; a page that opens with a 32px heading and a grid of tiles is
 * what he was looking at.
 *
 * Two things that shape does *not* change here, and both are the point:
 *
 * - **Density.** The tiles are the same tiles at the same padding, dealt at the
 *   same 70ms. Only the frame around them grew.
 * - **The states.** Loading, failed, empty and full are a switch on the body of
 *   the first chapter and nothing else, so the hero renders identically in all
 *   four. A page whose opening vanishes while it fetches flickers between two
 *   different products.
 *
 * The list stays on `Deal` rather than `Reveal` for a mechanical reason:
 * `useReveal` queries its subtree once, when `Longform` mounts, so anything
 * that arrives after the fetch is never observed and would sit at `opacity: 0`
 * for good. `Reveal` is for the static chapters, which exist on mount.
 */

/**
 * What Saibyl does with a product once it has one, in the order it happens.
 *
 * Every line is checkable against a surface that already exists — the upload
 * step, the audience it derives, and the library that keeps it. This chapter
 * describes the product, not a nicer one.
 */
const WHAT_HAPPENS = [
  {
    title: 'It reads what you already wrote',
    body:
      'A deck, a landing page, a pricing page. Answer five questions instead and Saibyl is working from your description of your buyer rather than from your product — which is the one input you are least able to be objective about.',
  },
  {
    title: 'It works out who buys it',
    body:
      'What they do, what they already use, and what would make them doubt you. That set of buyers is what every reaction, objection and rewrite afterwards is measured against.',
  },
  {
    title: 'And you only do that once',
    body:
      'Keep the buyers it derived and you can point them at anything else you sell, instead of deriving the same room again for every page you want to test.',
  },
] as const;

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

  /*
    Where the one gradient goes.

    "Max one primary action per screen" is a rule about the eye, and a screen
    with four states cannot satisfy it by picking a favourite at authoring
    time — this page can show a create button, a retry, an empty state and a
    modal, and three of those pairs overlap. So the choice is derived once,
    here, from what the founder should actually press next. Everything else on
    screen is `quiet`, which is the artboard's white-on-hairline button and
    still a real control.

    The `new` case is the hero's button, which is where a page's one gradient
    lives under the longform frame.
  */
  const gradient: 'retry' | 'create' | 'first' | 'new' =
    !loading && !loaded
      ? 'retry'
      : showModal
        ? 'create'
        : loaded && projects.length === 0
          ? 'first'
          : 'new';

  return (
    <Ground className="min-h-full pb-24">
      <Longform>
        {/* Never wrapped in `Reveal` — this is the first screen, and it renders
            in every one of the four states below it. */}
        <Hero
          eyebrow="Everything you uploaded"
          title="Everything Saibyl"
          serif="has read."
          actions={
            <Action
              onClick={() => setShowModal(true)}
              kind={gradient === 'new' ? 'primary' : 'quiet'}
            >
              <Plus className="w-4 h-4" />
              New product
            </Action>
          }
        >
          <p>
            One product for each thing you are trying to sell. Every file you
            upload is filed under one of these, and so is everything Saibyl
            works out from it &mdash; who buys this, and what they argue with.{' '}
            <b className="text-saibyl-ink font-semibold">
              Everything Saibyl has read, filed under the thing it was written
              to sell.
            </b>
          </p>
        </Hero>

        {/* ── The list ──
            The four states switch here and nowhere else. */}
        <Chapter
          kicker="In your workspace"
          title={
            <>
              What you have <em>given it so far</em>
            </>
          }
          lead="Open one to see everything filed under it — the files you handed over, and what Saibyl worked out from them."
        >
          {deleteError && (
            <div
              role="alert"
              className="mb-4 rounded-xl border border-saibyl-negative/25 bg-saibyl-rose/[0.08] px-4 py-3 text-sm text-saibyl-negative"
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
               that this page cannot support.

               Said in the artboard's violet rather than in grey body text: this
               is a state, and the canvas is explicit that a state is told in
               colour with the control that resolves it sitting inside it. */
            <Notice
              tone="blocked"
              title="We could not load your products"
              action={
                <Action
                  onClick={() => {
                    setLoading(true);
                    fetchProjects();
                  }}
                  kind={gradient === 'retry' ? 'primary' : 'quiet'}
                >
                  Try again
                </Action>
              }
            >
              {listError} Nothing has been changed or lost &mdash; this is a
              failure to read, not to keep.
            </Notice>
          ) : projects.length === 0 ? (
            <Card carries="stage" className="p-10 text-center">
              <div className="w-14 h-14 rounded-2xl bg-saibyl-blue/10 flex items-center justify-center mb-4 mx-auto">
                <Folder className="w-7 h-7 text-saibyl-blue" strokeWidth={1.5} />
              </div>
              <p className="text-saibyl-ink font-medium mb-1">No products yet</p>
              <p className="text-saibyl-muted text-sm mb-6">One product for each thing you are trying to sell</p>
              <Action
                onClick={() => setShowModal(true)}
                kind={gradient === 'first' ? 'primary' : 'quiet'}
              >
                Create your first product
              </Action>
            </Card>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {/* Dealt at the artboard's 70ms, capped inside `dealDelayMs` — the
                  same arrival the rail has, rather than a framer-motion stagger
                  that ran to four seconds on a long list and did not collapse
                  under `prefers-reduced-motion`. */}
              {projects.map((p, i) => (
                <Deal key={p.id} index={i} className="relative group">
                  {/* `meaning`, and it lifts: a product card is a claim a founder
                      has to weigh, and it goes somewhere — which is the only
                      condition under which the hover rise is honest. */}
                  <Card carries="meaning" lift className="overflow-hidden">
                    <Link
                      to={`/app/projects/${p.id}`}
                      className="block p-5 hover:bg-saibyl-blue/[0.03] transition-colors"
                    >
                      <div className="w-9 h-9 rounded-xl bg-saibyl-blue/10 flex items-center justify-center mb-4 group-hover:bg-saibyl-blue/[0.15] transition-colors">
                        <Folder className="w-[18px] h-[18px] text-saibyl-blue" strokeWidth={1.5} />
                      </div>
                      {/* Was `text-saibyl-platinum` hovering to `text-saibyl-ink`
                          — two names for the identical value, so the hover did
                          nothing at all. Blue is the accent that means "this goes
                          somewhere". */}
                      <h3 className="font-semibold text-saibyl-ink mb-1 group-hover:text-saibyl-blue transition-colors">{p.name}</h3>
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
                  </Card>

                  {/* Delete, which is never a greyed-out rectangle while it runs:
                      the button is replaced by the spinner that says the click
                      landed, so there is nothing left to press twice.

                      Legible at rest, too. It used to be `opacity-0` until hover,
                      which is no affordance at all on a touch screen and none in
                      a screenshot — the same defect `ProjectDetailPage` records
                      an acceptance reader finding on its action cards. */}
                  {deletingId === p.id ? (
                    <span
                      aria-live="polite"
                      title="Deleting…"
                      className="absolute top-3 right-3 w-7 h-7 rounded-lg flex items-center justify-center text-saibyl-muted"
                    >
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    </span>
                  ) : (
                    <button
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        if (confirm(`Delete "${p.name}"? This cannot be undone.`)) {
                          handleDelete(p.id);
                        }
                      }}
                      className="absolute top-3 right-3 w-7 h-7 rounded-lg flex items-center justify-center opacity-60 group-hover:opacity-100 focus-visible:opacity-100 bg-[#14294a]/[0.04] hover:bg-saibyl-rose/15 text-saibyl-muted hover:text-saibyl-negative transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-saibyl-negative/50"
                      title="Delete this product"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  )}
                </Deal>
              ))}
            </div>
          )}
        </Chapter>

        {/* ── What happens to a file once it is here ──
            Static, so the scroll-reveal observer sees it on mount. */}
        <Chapter
          kicker="What it does with them"
          title={
            <>
              It reads what you <em>already wrote</em>
            </>
          }
          lead="Saibyl derives your buyers from your own material rather than from a form you filled in about them. That is the whole reason a file is worth uploading before you answer a single question."
        >
          <div className="space-y-3">
            {WHAT_HAPPENS.map((item, i) => (
              <Reveal key={item.title} step={i as 0 | 1 | 2}>
                {/* `density` — hairlines. These carry no claim to weigh; the
                    tiles above do, which is why only those have depth. */}
                <Card carries="density" className="p-5">
                  <div className="flex items-start gap-3">
                    <span className="w-6 h-6 rounded-lg bg-saibyl-blue/[0.09] flex items-center justify-center shrink-0 mt-0.5">
                      <span className="font-mono text-[11px] font-bold text-saibyl-blue tabular-nums">
                        {i + 1}
                      </span>
                    </span>
                    <div>
                      <h3 className="text-[13.5px] font-semibold text-saibyl-ink mb-1">
                        {item.title}
                      </h3>
                      <p className="text-[13px] text-saibyl-muted leading-relaxed">
                        {item.body}
                      </p>
                    </div>
                  </div>
                </Card>
              </Reveal>
            ))}
          </div>

          <Reveal className="mt-5">
            <Action as={Link} to="/app/audiences" kind="quiet">
              Audiences you can reuse
            </Action>
          </Reveal>
        </Chapter>

        {/* ── The way out ──
            `quiet`: the one gradient on this screen was spent in the hero, or
            wherever `gradient` decided it was needed more. */}
        <Chapter
          kicker="Adding another"
          title={
            <>
              Start with the thing <em>you can hand someone</em>
            </>
          }
          lead="A name is enough to create one. What makes it useful is the file you upload next — the deck you send, or the page you point people at."
        >
          <Reveal>
            <Action onClick={() => setShowModal(true)} kind="quiet">
              <Plus className="w-4 h-4" />
              New product
            </Action>
          </Reveal>
        </Chapter>
      </Longform>

      {/* Create Modal — fixed to the viewport, so it sits outside the measure
          `Longform` owns rather than inside it. */}
      {showModal && (
        <div
          className="fixed inset-0 bg-[#14294a]/30 backdrop-blur-sm flex items-center justify-center z-50 p-4"
          onClick={(e) => e.target === e.currentTarget && setShowModal(false)}
        >
          <Rise className="w-full max-w-md">
            {/*
              `cardSurface('stage')` rather than `<Card>`: the panel has to
              carry `role`, `aria-modal` and `aria-labelledby`, and `Card`
              takes no arbitrary props on purpose. The helper is exported for
              exactly this — the surface is still the system's, decided in one
              place, rather than a fifth hand-rolled glass rectangle.
            */}
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby="new-product-heading"
              className={cn(cardSurface('stage'), 'p-6')}
            >
              <h2
                id="new-product-heading"
                className="text-lg font-semibold text-saibyl-ink mb-5"
              >
                New product
              </h2>
              <form onSubmit={handleCreate} className="space-y-4">
                <div>
                  <label htmlFor="new-product-name" className="block text-[12px] font-medium text-saibyl-muted uppercase tracking-wide mb-1.5">What is it called?</label>
                  <input
                    id="new-product-name"
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Acme Invoicing"
                    className="w-full bg-white border border-saibyl-border-light rounded-xl px-4 py-2.5 text-saibyl-ink placeholder:text-saibyl-muted/70 focus:outline-none focus:border-saibyl-blue focus:ring-2 focus:ring-saibyl-blue/20 transition text-sm"
                  />
                </div>
                <div>
                  <label htmlFor="new-product-description" className="block text-[12px] font-medium text-saibyl-muted uppercase tracking-wide mb-1.5">
                    What does it do? <span className="normal-case text-saibyl-muted/50 ml-1 font-normal">(optional)</span>
                  </label>
                  <textarea
                    id="new-product-description"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    rows={3}
                    placeholder="What does it do, in one line?"
                    className="w-full bg-white border border-saibyl-border-light rounded-xl px-4 py-2.5 text-saibyl-ink placeholder:text-saibyl-muted/70 focus:outline-none focus:border-saibyl-blue focus:ring-2 focus:ring-saibyl-blue/20 transition text-sm resize-none"
                  />
                </div>
                {createError && (
                  <p
                    role="alert"
                    className="rounded-xl border border-saibyl-negative/25 bg-saibyl-rose/[0.08] px-4 py-3 text-sm text-saibyl-negative"
                  >
                    {createError}
                  </p>
                )}
                {/* The artboard's row: the gradient, and a white button on a
                    hairline beside it. */}
                <div className="flex justify-end gap-3 pt-1">
                  <Action as="button" onClick={() => setShowModal(false)} kind="quiet">
                    Cancel
                  </Action>
                  {creating ? (
                    /* Announced, not disabled. The click landed and the work
                       is running; a grey rectangle with no words is what this
                       replaces. */
                    <Action
                      as="span"
                      aria-live="polite"
                      kind={gradient === 'create' ? 'primary' : 'quiet'}
                      className="opacity-70 pointer-events-none"
                    >
                      Creating…
                    </Action>
                  ) : (
                    <Action
                      as="button"
                      type="submit"
                      kind={gradient === 'create' ? 'primary' : 'quiet'}
                    >
                      Create product
                    </Action>
                  )}
                </div>
              </form>
            </div>
          </Rise>
        </div>
      )}
    </Ground>
  );
}
