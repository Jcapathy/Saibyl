import { useEffect, useState, useRef } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import { ArrowRight, Building2, FileText, MessageSquare, Plus, Users } from 'lucide-react';
import { AxiosError } from 'axios';

import api, { unwrapList } from '@/lib/api';
import { formatPlatforms } from '@/lib/constants';
import StatusBadge from '@/components/StatusBadge';
import { describeRun } from '@/lib/gtm';
import { isRead } from '@/lib/status';
import { getErrorMessage } from '../lib/errors';
import { EmptyState } from '@/components/stages/StagePrimitives';
import {
  Action,
  Card,
  Deal,
  Ground,
  Notice,
  PageHeader,
  Rise,
  dealDelayMs,
} from '@/components/design';
import type { DiscoveryRun, MaterialKind, Project, ProjectDocument, Simulation } from '@/types';

/**
 * One product: everything it has been given, and everything that has been done
 * with it.
 *
 * **The restyle (2026-08-23).** This was the densest pocket of unconverted
 * dark-theme code left in the app — thirty-three `saibyl-gold`, `saibyl-white`,
 * `saibyl-platinum` and `saibyl-void` classes, all of which still *resolve*
 * because the token file remapped those names to light values when the theme
 * flipped. That is precisely why nobody noticed: the page rendered, it looked
 * plausible, and it had never once been designed on the light system.
 *
 * It now composes `components/design/`. Three things changed beyond the
 * colours, and each is a canvas rule rather than a preference:
 *
 *   - Every state the page reports — a product that will not open, a step that
 *     cannot be offered yet, a file still being read, a file that has been —
 *     is a tinted block with a coloured heading and the control that resolves
 *     it, instead of another paragraph of grey body text. Nothing on the old
 *     screen claimed to matter more than anything else on it.
 *   - Depth means meaning. The four things you can do are `meaning` cards; the
 *     document, search and run lists are `density` — hairlines, no shadow per
 *     row, because a shadow under every row turns the page to soup.
 *   - One orchestrated arrival: the four cards deal at the artboard's 70ms and
 *     the tabbed stage rises once the deal is done, which is the canvas's own
 *     motion note applied to the surface it was drawn for.
 *
 * Density is untouched. Same 13px body, same row rhythm, same type sizes.
 */

type Tab = 'documents' | 'companies' | 'simulations';

/**
 * One of the things this page offers to do next.
 *
 * Named `ProductAction` rather than `Action`, which is now the design system's
 * gradient control — two different things called the same word in one file is
 * how the next reader learns the wrong map.
 */
interface ProductAction {
  key: string;
  label: string;
  blurb: string;
  to: string;
  Icon: React.ComponentType<{ className?: string }>;
}

/**
 * What a discovery run asked for, delivered and actually cost.
 *
 * Attached to every run row by `GET /gtm/runs` (`_with_delivery`). Declared
 * locally rather than on the shared `DiscoveryRun` type because it is computed
 * on read and only this screen and the prospect screens consume it — and
 * because `sentence` is written by the server, which is the only place that
 * knows both halves of the arithmetic. A client that composed its own sentence
 * would be a second implementation of the refund rule.
 */
interface RunDelivery {
  queries_requested: number;
  queries_delivered: number;
  credits_charged: number;
  credits_refunded: number;
  credits_net: number;
  credits_refundable: number;
  reconciled: boolean;
  sentence: string;
}

type DiscoveryRunWithDelivery = DiscoveryRun & { delivery?: RunDelivery };

/**
 * Whose material this is, asked as a question rather than as an enum.
 *
 * This is not a tag. `competitor` is the only thing that ever lets a simulated
 * skeptic say a rival's name out loud, so the answer is a permission the person
 * uploading grants — which is why it is asked once, per file, at the moment
 * they are looking at the file, and why nothing here ever pre-selects
 * `competitor` on their behalf.
 */
const MATERIAL_KINDS: { value: MaterialKind; label: string; help: string }[] = [
  {
    value: 'own',
    label: 'Mine',
    help: 'Something you wrote or published — your site, deck, pricing, docs.',
  },
  {
    value: 'competitor',
    label: "A competitor's",
    help: 'Something a rival published. Lets Saibyl name them out loud.',
  },
  {
    value: 'market',
    label: 'Market research',
    help: 'Industry reports, analyst notes, survey results — nobody in particular.',
  },
];

interface PendingUpload {
  file: File;
  kind: MaterialKind;
}

/** How a stored document's `material_kind` reads back. NULL means nobody said. */
const MATERIAL_KIND_BADGES: Record<MaterialKind, string> = {
  own: 'Yours',
  competitor: "Competitor's",
  market: 'Market research',
};

/** The one id the file picker answers to. Two labels point at it — the button
 *  in the upload panel, and the one inside the empty state below it. */
const FILE_INPUT_ID = 'material-files';

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [project, setProject] = useState<Project | null>(null);
  /* Why the product is not on screen, when it is not.

     `catch(() => {})` left this page rendering the heading "Product" with an
     empty description, forever, on a 404 — which is what a founder sees after
     following a link to something they deleted, or after mistyping a URL. It
     looked like a product that was still loading, and it never stopped. */
  const [projectError, setProjectError] = useState('');
  const [tab, setTab] = useState<Tab>('documents');
  const [documents, setDocuments] = useState<ProjectDocument[]>([]);
  const [simulations, setSimulations] = useState<Simulation[]>([]);
  const [runs, setRuns] = useState<DiscoveryRunWithDelivery[]>([]);
  const [pending, setPending] = useState<PendingUpload[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const fileInput = useRef<HTMLInputElement>(null);

  /*
    Did each list actually come back?

    Set only on success, never in a `catch`. Everything on this page that counts
    something reads one of these first: a tab that says "(0)" and an empty state
    that says "nothing here yet" are both claims about the account, and a
    request that failed supports neither. Until the answer is in, the count is
    simply not rendered.
  */
  const [documentsLoaded, setDocumentsLoaded] = useState(false);
  /* Why the file list could not be re-read, when it could not. Distinct from
     `documents.length === 0`, which is a claim about the account rather than
     about the request — see `loadDocuments`. */
  const [documentsError, setDocumentsError] = useState('');
  const [simulationsLoaded, setSimulationsLoaded] = useState(false);
  const [runsLoaded, setRunsLoaded] = useState(false);

  // Load project + documents + runs
  useEffect(() => {
    if (!id) return;
    api
      .get(`/projects/${id}`)
      .then((r) => {
        setProject(r.data);
        setProjectError('');
      })
      .catch((err) =>
        setProjectError(
          err instanceof AxiosError && err.response?.status === 404
            ? 'This product does not exist, or it is not in your account.'
            : getErrorMessage(err, 'We could not load this product.'),
        ),
      );
    loadDocuments();
    api.get('/simulations', { params: { project_id: id, limit: 50 } }).then((r) => {
      setSimulations(unwrapList<Simulation>(r.data).items);
      setSimulationsLoaded(true);
    }).catch(() => {});
    /* Company searches run against this product. Fetched here so the product is
       a real route into that work rather than a dead end that only offers
       another run — and so the money each search actually cost is visible on
       the same screen that spent it. */
    api.get('/gtm/runs', { params: { project_id: id, limit: 20 } }).then((r) => {
      setRuns(unwrapList<DiscoveryRunWithDelivery>(r.data).items);
      setRunsLoaded(true);
    }).catch(() => {});
  }, [id]);

  // Poll documents while any are still processing
  useEffect(() => {
    const hasProcessing = documents.some((d) => d.processing_status === 'pending' || d.processing_status === 'processing');
    if (!hasProcessing || !id) return;
    const interval = setInterval(loadDocuments, 3000);
    return () => clearInterval(interval);
  }, [documents, id]);

  function loadDocuments() {
    api.get('/documents', { params: { project_id: id } })
      .then((r) => {
        setDocuments(unwrapList<ProjectDocument>(r.data).items);
        setDocumentsLoaded(true);
        setDocumentsError('');
      })
      /* **A failed read must not empty the list.**
         This was `.catch(() => setDocuments([]))`, under a comment arguing that
         `documentsLoaded` stays false so nothing claims there are no files.
         That is true on the *first* load and false ever after: once one read
         has succeeded the flag is permanently true, and this page polls every
         three seconds while anything is still processing. So one dropped poll
         — a sleeping laptop, a redeploy, a flaky network — replaced a real list
         of files with "Nothing uploaded yet", over files that exist. That is
         the same class of confident false claim this file's own header says it
         was written to end.
         Keeping the last good list is the correct answer to a transient
         failure: it is the most recent thing known to be true. The failure is
         reported rather than swallowed, so a founder who is genuinely offline
         is told so instead of being shown a stale list with no explanation. */
      .catch((err) =>
        setDocumentsError(getErrorMessage(err, 'We could not re-read your files just now.')),
      );
  }

  /* Files are staged rather than uploaded on selection, because each one has to
     be answered for individually — a batch of five can easily be four of yours
     and one of a rival's, and a single answer for the batch would either
     under-claim (losing the grounding) or over-claim (granting a permission
     nobody meant to give). */
  function stageFiles(files: FileList | null) {
    if (!files) return;
    setPending(
      Array.from(files).map((file) => ({
        file,
        // Never `competitor`. That value is a permission, and a permission that
        // arrives pre-selected is a permission nobody granted.
        kind: 'own' as MaterialKind,
      })),
    );
  }

  function setPendingKind(index: number, kind: MaterialKind) {
    setPending((prev) => prev.map((item, i) => (i === index ? { ...item, kind } : item)));
  }

  // Upload document
  async function handleUpload() {
    if (!pending.length || !id) return;
    setUploading(true);
    setUploadError('');
    try {
      for (const item of pending) {
        const form = new FormData();
        form.append('file', item.file);
        // `material_kind` is a query parameter, not a form field — the route
        // declares it as `Query(...)` alongside `project_id`.
        await api.post('/documents/upload', form, {
          params: { project_id: id, material_kind: item.kind },
          headers: { 'Content-Type': 'multipart/form-data' },
        });
      }
      setPending([]);
      loadDocuments();
    } catch (err) {
      setUploadError(getErrorMessage(err, 'Upload failed'));
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = '';
    }
  }

  // Delete document
  async function handleDeleteDoc(docId: string) {
    try {
      await api.delete(`/documents/${docId}`);
      setDocuments((prev) => prev.filter((d) => d.id !== docId));
    } catch { /* ignore */ }
  }

  // Run simulation — navigate to wizard with project pre-selected
  function handleRunSimulation() {
    navigate(`/app/simulations/new?project=${id}`);
  }

  function formatBytes(bytes: number) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  }

  /* Counts are a claim about the account, so a tab whose list has not come back
     shows a name and no number rather than "(0)". `undefined` is already how the
     renderer below spells "no number". */
  const tabs: { key: Tab; label: string; count?: number }[] = [
    { key: 'documents', label: 'Your material', count: documentsLoaded ? documents.length : undefined },
    { key: 'companies', label: 'Companies', count: runsLoaded ? runs.length : undefined },
    { key: 'simulations', label: 'Runs', count: simulationsLoaded ? simulations.length : undefined },
  ];

  /* A file whose text reached the product. Everything that reads your material
     needs this rather than "a file exists" — an upload that is still queued, or
     that failed to parse, has given Saibyl nothing to work from. */
  const readable = documents.filter((d) => isRead(d.processing_status));
  const stillReading = documentsLoaded && documents.length > 0 && readable.length === 0;

  /*
    Where the one gradient goes on the material tab.

    "Max one primary action per screen" is a rule about the eye, and this tab
    has three controls that each want to be it. So the choice is derived once,
    from what the founder should actually press next: finish the upload they
    started, or start the run their read files have earned, or pick a file
    because there is nothing here at all. Everything else renders `quiet` —
    the artboard's white button on a hairline, which is still a real control.
  */
  const materialAct: 'upload' | 'run' | 'choose' =
    pending.length > 0 ? 'upload' : readable.length > 0 ? 'run' : 'choose';

  /* ── What you can do with this product ──
     Until this existed, opening a product offered exactly one thing to do: start
     another run. Audiences, company discovery and message testing were all
     built, deployed and reachable only by typing a URL — which is the same as
     not having shipped them.

     Named for what the founder gets, not for the discipline. Nobody arriving
     here has heard the phrase "ideal customer profile", and nothing on this page
     requires them to learn it.

     The list is built from what this product actually has. Every product used to
     show all four regardless of state, so a product with nothing uploaded
     offered "Find real companies" exactly as a finished one did — and that one
     cannot work: finding companies searches for the buyers, the buyers are
     derived by reading your files, and with no readable file
     `POST /icp/synthesize` refuses with the server's own words, "No processed
     documents in this project". Offering a button that is guaranteed to
     dead-end is worse than not
     offering it, so it is not built, and the notice under the grid says why. */
  const actions: ProductAction[] = [
    {
      key: 'audiences',
      label: 'Who buys this',
      blurb:
        'The buyers Saibyl worked out for you, kept and ready to use on anything else you sell.',
      to: '/app/audiences',
      Icon: Users,
    },
    ...(readable.length > 0
      ? [
          {
            key: 'companies',
            label: 'Find real companies',
            blurb:
              'Search the web for companies that look like your buyers. Every one comes back with the page that says so.',
            to: `/app/prospects/discover?project_id=${id}`,
            Icon: Building2,
          },
        ]
      : []),
    {
      key: 'messages',
      label: 'Test more than one message',
      blurb:
        'Put two or more versions of your pitch in front of the same room and see which one lands.',
      to: `/app/launch?product=${id}`,
      Icon: MessageSquare,
    },
    {
      key: 'run',
      label: 'Start a run',
      blurb:
        'Show what you have written to a room of simulated buyers and read what they say back.',
      to: `/app/simulations/new?project=${id}`,
      Icon: FileText,
    },
  ];

  return (
    <Ground className="p-8 min-h-full">
      <div className="max-w-5xl mx-auto">
        <Rise className="mb-6">
          <PageHeader
            eyebrow="Your products"
            /* Not "Product" as a stand-in. A placeholder name is a claim that
               there is a product here whose name has not arrived yet, and on a
               404 there is no product at all. */
            title={project?.name || (projectError ? 'Product not found' : 'Loading…')}
            /* The artboard's line beside the title, and a real number rather
               than an invented one: rendered only once the list has actually
               come back, because a count is a claim about the account. */
            mark={
              documentsLoaded && documents.length > 0
                ? `${readable.length} of ${documents.length} ${documents.length === 1 ? 'file' : 'files'} read`
                : undefined
            }
            phrase="What you have written, who has read it, and what came back."
          >
            {project?.description && <p>{project.description}</p>}
          </PageHeader>
        </Rise>

        {projectError && (
          /* `role` stays on a wrapper: the notice is the state, and a screen
             reader still has to be told it arrived. */
          <div role="alert" className="mb-6">
            <Notice
              tone="blocked"
              title="We could not open this product"
              action={
                <Action as={Link} to="/app/projects" kind="quiet">
                  Back to your products
                </Action>
              }
            >
              {projectError}
            </Notice>
          </div>
        )}

        {/*
          What you can do with this product.

          These are buttons and they now look like it. They shipped as
          `glass glass-hover` with no arrow, no visible border at rest and no
          focus ring, and an acceptance reader took them for explanatory text —
          they only found out by guessing. A control whose only affordance
          appears on hover is invisible to anyone on a touch screen and to
          anyone reading a screenshot, so the border, the arrow and the press
          feedback are all rendered at rest.

          `meaning` and `lift`: each card carries a claim about what this
          product could do next, and each one goes somewhere — which is the only
          condition under which the artboard's hover rise is honest.
        */}
        <div className="mb-8">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {actions.map(({ key, label, blurb, to, Icon }, i) => (
              <Deal key={key} index={i}>
                <Card carries="meaning" lift className="h-full overflow-hidden">
                  <button
                    type="button"
                    onClick={() => navigate(to)}
                    className="group h-full w-full text-left p-5 rounded-2xl transition-colors hover:bg-saibyl-blue/[0.04] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-saibyl-blue/70 focus-visible:ring-offset-2 focus-visible:ring-offset-saibyl-paper"
                  >
                    <div className="flex items-center gap-2.5 mb-1.5">
                      <Icon className="w-4 h-4 text-saibyl-blue shrink-0" />
                      <span className="text-[14px] font-medium text-saibyl-ink">{label}</span>
                      <ArrowRight
                        aria-hidden="true"
                        className="w-4 h-4 text-saibyl-blue shrink-0 ml-auto transition-transform group-hover:translate-x-1"
                      />
                    </div>
                    <p className="text-[12px] text-saibyl-muted leading-relaxed">{blurb}</p>
                  </button>
                </Card>
              </Deal>
            ))}
          </div>

          {/* Why there is no "Find real companies" card. Said once, under the
              grid, rather than as a fifth card the reader would try to press —
              and said in the artboard's colours, because a step that cannot run
              yet and a document still being read are two different states and
              the old page rendered both as the same grey paragraph. */}
          {documentsLoaded && readable.length === 0 && (
            <div className="mt-4 max-w-2xl">
              {stillReading ? (
                <Notice tone="live" title="We are still reading what you uploaded">
                  Once that finishes, Saibyl can work out who buys this and go
                  looking for real companies that match.
                </Notice>
              ) : (
                <Notice
                  tone="blocked"
                  title="Finding real companies is not offered yet"
                  action={
                    <Action onClick={() => setTab('documents')} kind="quiet">
                      Add a file
                    </Action>
                  }
                >
                  It searches for the people who buy this, and Saibyl only knows
                  who they are once it has read something you wrote.
                </Notice>
              )}
            </div>
          )}
        </div>

        {/* The stage arrives after the cards are dealt — the canvas's own
            motion note, on the surface it was drawn for. */}
        <Rise delayMs={dealDelayMs(actions.length)}>
          {/* Tabs. The selected one wears the artboard's own treatment for a
              selected thing — a blue tint under ink, the same as the active
              item in the sidebar — rather than a solid blue chip, so the
              gradient stays spent on the thing to press. */}
          <Card carries="density" className="flex gap-1 p-1 rounded-xl w-fit mb-8">
            {tabs.map((t) => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                aria-pressed={tab === t.key}
                className={`px-5 py-2 rounded-lg text-sm transition-colors ${
                  tab === t.key
                    ? 'bg-saibyl-blue/10 text-saibyl-ink font-semibold'
                    : 'text-saibyl-muted hover:text-saibyl-ink font-medium'
                }`}
              >
                {t.label}{t.count !== undefined ? ` (${t.count})` : ''}
              </button>
            ))}
          </Card>

          {uploadError && (
            <div
              role="alert"
              className="mb-4 px-4 py-3 rounded-xl bg-saibyl-negative/10 border border-saibyl-negative/20 text-saibyl-negative text-sm"
            >
              {uploadError}
              <button onClick={() => setUploadError('')} className="ml-3 underline">dismiss</button>
            </div>
          )}

          {/* ═══ Documents Tab ═══ */}
          {tab === 'documents' && (
            <div className="space-y-5">
              {/* The one panel this tab is about. */}
              <Card carries="stage" className="p-6">
                <h3 className="text-[14px] font-medium text-saibyl-ink mb-1.5">
                  What you have written
                </h3>
                <p className="text-[12px] text-saibyl-muted mb-1.5 leading-relaxed max-w-2xl">
                  A deck, a landing page, a pricing page, a spec. Saibyl reads these to work out
                  who buys this — nothing else is used.
                </p>
                <p className="text-[12px] text-saibyl-muted mb-4">
                  PDF, Word, plain text or Markdown. Up to 50MB each.
                </p>

                {/* The artboard's row, with the native picker behind it. The
                    input is the control — same ref, same `onChange`, same
                    reset — and the label in front of it is what the artboard
                    draws. `peer` carries the input's focus ring out to the
                    label, so it is still reachable and visible by keyboard. */}
                <div className="flex flex-wrap items-center gap-2.5">
                  <input
                    ref={fileInput}
                    id={FILE_INPUT_ID}
                    type="file"
                    multiple
                    accept=".pdf,.docx,.txt,.md"
                    onChange={(e) => stageFiles(e.target.files)}
                    className="peer sr-only"
                  />
                  <Action
                    as="label"
                    htmlFor={FILE_INPUT_ID}
                    kind={materialAct === 'choose' ? 'primary' : 'quiet'}
                    className="cursor-pointer peer-focus-visible:ring-2 peer-focus-visible:ring-saibyl-blue/70 peer-focus-visible:ring-offset-2"
                  >
                    Choose a file
                  </Action>

                  {pending.length > 0 &&
                    (uploading ? (
                      /* Announced, not disabled. The click landed and the work
                         is running; a grey rectangle with no words is what this
                         replaces. */
                      <Action
                        as="span"
                        aria-live="polite"
                        className="opacity-70 pointer-events-none"
                      >
                        Uploading…
                      </Action>
                    ) : (
                      <Action
                        onClick={handleUpload}
                        kind={materialAct === 'upload' ? 'primary' : 'quiet'}
                      >
                        Upload {pending.length} file{pending.length === 1 ? '' : 's'}
                      </Action>
                    ))}
                </div>

                {pending.length > 0 && (
                  <div className="mt-5 space-y-3">
                    <p className="text-[13px] text-saibyl-ink">
                      Whose is this? We ask so we know what the simulated buyers are allowed
                      to say.
                    </p>
                    {pending.map((item, i) => (
                      <Card
                        key={`${item.file.name}-${i}`}
                        carries="density"
                        className="p-4 rounded-xl"
                      >
                        <p className="text-[13px] text-saibyl-ink truncate mb-2.5">
                          {item.file.name}
                        </p>
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                          {MATERIAL_KINDS.map((option) => {
                            const selected = item.kind === option.value;
                            return (
                              <button
                                key={option.value}
                                type="button"
                                onClick={() => setPendingKind(i, option.value)}
                                aria-pressed={selected}
                                className={`text-left p-3 rounded-lg border transition-colors ${
                                  selected
                                    ? 'border-saibyl-blue/40 bg-saibyl-blue/[0.07]'
                                    : 'border-saibyl-border bg-white hover:border-saibyl-border-light'
                                }`}
                              >
                                <span
                                  className={`block text-[13px] font-medium ${
                                    selected ? 'text-saibyl-blue' : 'text-saibyl-ink'
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
                      </Card>
                    ))}

                    {/* What marking something as a competitor's actually does. Shown
                        only once the person has chosen it, because it is a
                        consequence of their choice and not a warning about the
                        upload. Amber: it will run, and here is what it costs. */}
                    {pending.some((item) => item.kind === 'competitor') && (
                      <Notice
                        tone="thin"
                        title={
                          <>
                            You&rsquo;ve marked{' '}
                            {pending.filter((item) => item.kind === 'competitor').length} file
                            {pending.filter((item) => item.kind === 'competitor').length === 1
                              ? ''
                              : 's'}{' '}
                            as a competitor&rsquo;s
                          </>
                        }
                      >
                        That lets doubters in the room name that company out loud, and quote
                        it, using only what this document actually says. Without a document
                        like this, Saibyl refuses to name anyone — a model asked about a rival
                        will confidently make things up, and you would have no way of telling
                        which parts. Only mark material a rival genuinely published.
                      </Notice>
                    )}
                  </div>
                )}
              </Card>

              {/* A read that failed, reported without throwing away what is on
                  screen. It sits above the list rather than replacing it: the
                  list is the last state known to be true, and a founder who is
                  briefly offline should keep seeing his files with a note that
                  they are not being refreshed — not an empty page. */}
              {documentsError && (
                <Notice
                  tone="thin"
                  title="We could not re-read your files just now"
                  className="mb-4"
                  action={
                    <Action kind="quiet" onClick={loadDocuments}>
                      Try again
                    </Action>
                  }
                >
                  {documentsError} What is listed below is what we last read
                  successfully, so it may be out of date.
                </Notice>
              )}

              {/* Document list. "Nothing here yet" is only said once the list has
                  actually come back — a failed read has no idea whether there are
                  files, and telling the founder there are none is the same defect
                  as printing a zero we never counted. */}
              {documents.length === 0 ? (
                documentsLoaded ? (
                  <Notice
                    tone="blocked"
                    title="Nothing uploaded yet"
                    action={
                      <Action
                        as="label"
                        htmlFor={FILE_INPUT_ID}
                        kind="quiet"
                        className="cursor-pointer"
                      >
                        Choose a file
                      </Action>
                    }
                  >
                    The deck is usually the best one to start with.
                  </Notice>
                ) : (
                  <Notice
                    tone="blocked"
                    title="We could not read your files"
                    action={
                      <Action onClick={loadDocuments} kind="quiet">
                        Try again
                      </Action>
                    }
                  >
                    None are listed because we do not know what is there &mdash;
                    which is a different fact from there being nothing, and only
                    one of the two should worry you.
                  </Notice>
                )
              ) : (
                /* `density`: a list of rows, so hairlines and no shadow. */
                <Card carries="density" className="overflow-hidden">
                  {documents.map((doc, i) => (
                    <div key={doc.id} className={`flex items-center justify-between px-5 py-3 ${i > 0 ? 'border-t border-saibyl-border' : ''}`}>
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="w-8 h-8 rounded-lg bg-saibyl-blue/10 flex items-center justify-center text-[11px] font-mono text-saibyl-blue uppercase shrink-0">
                          {doc.file_type}
                        </div>
                        <div className="min-w-0">
                          <p className="text-[14px] font-medium text-saibyl-ink truncate">{doc.filename}</p>
                          <div className="flex items-center gap-2">
                            <p className="text-[11px] text-saibyl-muted">{formatBytes(doc.file_size_bytes || 0)}</p>
                            {/* Rendered only when the column actually holds a value.
                                Rows uploaded before this question was asked carry
                                NULL, and labelling those "Yours" would put words in
                                the mouth of someone who was never asked.

                                A competitor's file wears the amber that means "this
                                one changes what the room is allowed to say" — the
                                same amber the staging notice uses, rather than the
                                accent blue, which on this system means "press me". */}
                            {doc.material_kind && (
                              <span
                                className={`text-[10px] px-1.5 py-0.5 rounded ${
                                  doc.material_kind === 'competitor'
                                    ? 'bg-[#b45309]/[0.10] text-[#b45309]'
                                    : 'bg-[#14294a]/[0.04] text-saibyl-muted'
                                }`}
                              >
                                {MATERIAL_KIND_BADGES[doc.material_kind]}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <StatusBadge status={doc.processing_status} />
                        <button
                          onClick={(e) => { e.stopPropagation(); handleDeleteDoc(doc.id); }}
                          className="text-saibyl-muted hover:text-saibyl-negative transition-colors"
                          title="Delete document"
                          aria-label={`Delete ${doc.filename}`}
                        >
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                        </button>
                      </div>
                    </div>
                  ))}
                </Card>
              )}

              {/* The way on, once there is something to work from. Gated on a file
                  Saibyl has actually read rather than on a file existing — an
                  upload still in the queue has given it nothing yet. Cyan,
                  because this is the one state on the page that is genuinely
                  good news. */}
              {readable.length > 0 && (
                <Notice
                  tone="live"
                  title={
                    readable.length === 1
                      ? 'Your file has been read'
                      : `All ${readable.length} of your files have been read`
                  }
                  action={
                    <Action
                      onClick={handleRunSimulation}
                      kind={materialAct === 'run' ? 'primary' : 'quiet'}
                    >
                      Start a run
                      <ArrowRight className="w-3.5 h-3.5" />
                    </Action>
                  }
                >
                  Put this in front of a room of buyers and find out what they argue with.
                </Notice>
              )}
            </div>
          )}

          {/* ═══ Companies Tab ═══ */}
          {tab === 'companies' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between gap-4">
                <p className="text-[14px] text-saibyl-muted">
                  {runsLoaded
                    ? `${runs.length} company search${runs.length !== 1 ? 'es' : ''} for this product`
                    : 'Company searches for this product'}
                </p>
                <Action
                  as={Link}
                  to={`/app/prospects/discover?project_id=${id}`}
                  className="shrink-0"
                >
                  <Plus className="w-4 h-4" />
                  New search
                </Action>
              </div>

              {runs.length === 0 ? (
                runsLoaded ? (
                  <EmptyState
                    headline="No company searches yet"
                    body="Once Saibyl has worked out who buys this, it can go and find real companies that look like them — with the page that says so attached to every one."
                    action={{
                      label: 'Find companies',
                      href: `/app/prospects/discover?project_id=${id}`,
                    }}
                  />
                ) : (
                  <Notice tone="blocked" title="We could not read your company searches">
                    None are listed because we do not know what is there. Reload
                    the page to try again.
                  </Notice>
                )
              ) : (
                <div className="space-y-3">
                  {runs.map((run) => {
                    const summary = describeRun(run);
                    return (
                      <Card key={run.id} carries="density" className="p-5 rounded-xl">
                        <div className="flex items-center justify-between gap-4 mb-1.5">
                          <span className="text-[15px] font-medium text-saibyl-ink">
                            {summary.headline}
                          </span>
                          <span className="text-[11px] text-saibyl-muted shrink-0">
                            {new Date(run.created_at).toLocaleDateString()}
                          </span>
                        </div>
                        <p className="text-[12px] text-saibyl-muted leading-relaxed">
                          {summary.detail}
                        </p>

                        {/* What it cost, stated rather than left to be worked out
                            from two numbers on a billing page. The sentence comes
                            from the server, which is the only place that knows
                            what was charged and what was given back. */}
                        {run.delivery && (
                          <p
                            className={`text-[12px] mt-2.5 leading-relaxed ${
                              run.delivery.credits_refunded > 0
                                ? 'text-saibyl-blue'
                                : 'text-saibyl-silver'
                            }`}
                          >
                            {run.delivery.sentence}
                          </p>
                        )}

                        {run.candidates_found > 0 && (
                          <Link
                            to={`/app/prospects?discovery_run_id=${run.id}`}
                            className="inline-flex items-center gap-1 mt-3 text-[12px] text-saibyl-blue hover:underline"
                          >
                            See the {run.candidates_found} compan
                            {run.candidates_found === 1 ? 'y' : 'ies'} this found
                            <ArrowRight className="w-3 h-3" />
                          </Link>
                        )}
                      </Card>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* ═══ Runs Tab ═══ */}
          {tab === 'simulations' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <p className="text-[14px] text-saibyl-muted">
                  {simulationsLoaded
                    ? `${simulations.length} run${simulations.length !== 1 ? 's' : ''} on this product`
                    : 'Runs on this product'}
                </p>
                <Action
                  as={Link}
                  to={`/app/simulations/new?project=${id}`}
                  className="shrink-0"
                >
                  <Plus className="w-4 h-4" />
                  New run
                </Action>
              </div>
              {simulations.length === 0 ? (
                simulationsLoaded ? (
                  <EmptyState
                    headline="No runs yet"
                    body="Start one and find out how people react to what you have written."
                    action={{
                      label: 'Start a run',
                      href: `/app/simulations/new?project=${id}`,
                    }}
                  />
                ) : (
                  <Notice tone="blocked" title="We could not read your runs">
                    None are listed because we do not know what is there. Reload
                    the page to try again.
                  </Notice>
                )
              ) : (
                <div className="space-y-3">
                  {simulations.map((sim) => (
                    <Card key={sim.id} carries="density" lift className="overflow-hidden rounded-xl">
                      <button
                        onClick={() => navigate(`/app/simulations/${sim.id}`)}
                        className="w-full text-left p-5 rounded-xl transition-colors hover:bg-saibyl-blue/[0.04] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-saibyl-blue/70 focus-visible:ring-offset-2 focus-visible:ring-offset-saibyl-paper"
                      >
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-[15px] font-medium text-saibyl-ink">{sim.name}</span>
                          <StatusBadge status={sim.status} />
                        </div>
                        <p className="text-[12px] text-saibyl-muted line-clamp-1">{sim.prediction_goal}</p>
                        <div className="flex items-center gap-4 mt-2 text-[11px] text-saibyl-muted">
                          <span>{formatPlatforms(sim.platforms || [])}</span>
                          <span>{sim.max_rounds} rounds</span>
                          <span>{new Date(sim.created_at).toLocaleDateString()}</span>
                        </div>
                      </button>
                    </Card>
                  ))}
                </div>
              )}
            </div>
          )}
        </Rise>
      </div>
    </Ground>
  );
}
