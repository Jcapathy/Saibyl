import { useEffect, useState, useRef } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import { ArrowRight, Building2, FileText, MessageSquare, Users } from 'lucide-react';
import { AxiosError } from 'axios';

import api, { unwrapList } from '@/lib/api';
import { formatPlatforms } from '@/lib/constants';
import StatusBadge from '@/components/StatusBadge';
import { describeRun } from '@/lib/gtm';
import { isRead } from '@/lib/status';
import { getErrorMessage } from '../lib/errors';
import type { DiscoveryRun, MaterialKind, Project, ProjectDocument, Simulation } from '@/types';

type Tab = 'documents' | 'companies' | 'simulations';

/** One of the things this page offers to do next. */
interface Action {
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
      })
      // Left as it was found — a failed read shows no files, and
      // `documentsLoaded` stays false so nothing on the page claims there are
      // none. Deliberately not `setDocumentsLoaded(true)` here.
      .catch(() => setDocuments([]));
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
     `POST /icp/synthesize` refuses with "No processed documents in this
     project". Offering a button that is guaranteed to dead-end is worse than not
     offering it, so it is not built, and the sentence under the grid says why. */
  const actions: Action[] = [
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
      to: `/app/marketing?project=${id}`,
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
    <div className="p-8 bg-saibyl-void min-h-full">
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <h1 className="text-h1 text-saibyl-white mb-1">
          {/* Not "Product" as a stand-in. A placeholder name is a claim that
              there is a product here whose name has not arrived yet, and on a
              404 there is no product at all. */}
          {project?.name || (projectError ? 'Product not found' : 'Loading…')}
        </h1>
        <p className="text-small mb-6">{project?.description}</p>

        {projectError && (
          <div
            role="alert"
            className="mb-6 rounded-xl border border-red-500/25 bg-red-500/[0.07] p-4"
          >
            <p className="text-sm text-red-300">{projectError}</p>
            <Link
              to="/app/projects"
              className="inline-flex items-center gap-1.5 mt-3 px-3.5 py-1.5 rounded-lg bg-saibyl-gold text-saibyl-void text-[12px] font-semibold hover:bg-saibyl-gold-hover transition-colors"
            >
              Back to your products
            </Link>
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
        */}
        <div className="mb-8">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {actions.map(({ key, label, blurb, to, Icon }) => (
              <button
                key={key}
                type="button"
                onClick={() => navigate(to)}
                className="group text-left rounded-2xl border border-white/[0.12] bg-white/[0.03] p-5 transition-all hover:border-saibyl-gold/45 hover:bg-white/[0.06] hover:-translate-y-0.5 active:translate-y-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-saibyl-gold/70 focus-visible:ring-offset-2 focus-visible:ring-offset-saibyl-void"
              >
                <div className="flex items-center gap-2.5 mb-1.5">
                  <Icon className="w-4 h-4 text-saibyl-gold shrink-0" />
                  <span className="text-[14px] font-medium text-saibyl-platinum">{label}</span>
                  <ArrowRight
                    aria-hidden="true"
                    className="w-4 h-4 text-saibyl-gold shrink-0 ml-auto transition-transform group-hover:translate-x-1"
                  />
                </div>
                <p className="text-[12px] text-saibyl-muted leading-relaxed">{blurb}</p>
              </button>
            ))}
          </div>

          {/* Why there is no "Find real companies" card. Said once, under the
              grid, rather than as a fifth card the reader would try to press. */}
          {documentsLoaded && readable.length === 0 && (
            <p className="text-[12px] text-saibyl-muted leading-relaxed mt-4 max-w-2xl">
              {stillReading
                ? 'We are still reading what you uploaded. Once that finishes, Saibyl can work out who buys this and go looking for real companies that match.'
                : 'Finding real companies is not offered yet. It searches for the people who buy this, and Saibyl only knows who they are once it has read something you wrote — add a file on the Your material tab below and the option appears here.'}
            </p>
          )}
        </div>

        {/* Tabs */}
        <div className="flex gap-1 p-1 glass rounded-xl w-fit mb-8">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-5 py-2 rounded-lg text-sm font-medium transition-all ${
                tab === t.key
                  ? 'bg-saibyl-gold text-white'
                  : 'text-saibyl-muted hover:text-saibyl-platinum'
              }`}
            >
              {t.label}{t.count !== undefined ? ` (${t.count})` : ''}
            </button>
          ))}
        </div>

        {uploadError && (
          <div className="mb-4 px-4 py-3 rounded-xl bg-saibyl-negative/10 border border-saibyl-negative/20 text-saibyl-negative text-sm">
            {uploadError}
            <button onClick={() => setUploadError('')} className="ml-3 underline">dismiss</button>
          </div>
        )}

        {/* ═══ Documents Tab ═══ */}
        {tab === 'documents' && (
          <div className="space-y-5">
            {/* Upload area */}
            <div className="glass rounded-2xl p-6">
              <h3 className="text-[14px] font-medium text-saibyl-platinum mb-1.5">
                What you have written
              </h3>
              <p className="text-[12px] text-saibyl-muted mb-1.5 leading-relaxed max-w-2xl">
                A deck, a landing page, a pricing page, a spec. Saibyl reads these to work out
                who buys this — nothing else is used.
              </p>
              <p className="text-[12px] text-saibyl-muted mb-4">
                PDF, Word, plain text or Markdown. Up to 50MB each.
              </p>
              <div className="flex items-center gap-3">
                <input
                  ref={fileInput}
                  type="file"
                  multiple
                  accept=".pdf,.docx,.txt,.md"
                  onChange={(e) => stageFiles(e.target.files)}
                  className="text-sm text-saibyl-muted file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-saibyl-gold/20 file:text-saibyl-gold file:font-medium file:cursor-pointer hover:file:bg-saibyl-gold/30"
                />
                <button
                  onClick={handleUpload}
                  disabled={uploading || pending.length === 0}
                  className="bg-saibyl-gold text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-[#4B4FDE] disabled:opacity-50 transition-colors shrink-0"
                >
                  {uploading ? 'Uploading...' : 'Upload'}
                </button>
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
                              onClick={() => setPendingKind(i, option.value)}
                              aria-pressed={selected}
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

                  {/* What marking something as a competitor's actually does. Shown
                      only once the person has chosen it, because it is a
                      consequence of their choice and not a warning about the
                      upload. */}
                  {pending.some((item) => item.kind === 'competitor') && (
                    <div className="px-4 py-3 rounded-xl border border-saibyl-gold/25 bg-saibyl-gold/[0.06]">
                      <p className="text-[12px] text-saibyl-gold font-medium mb-1">
                        You&rsquo;ve marked{' '}
                        {pending.filter((item) => item.kind === 'competitor').length} file
                        {pending.filter((item) => item.kind === 'competitor').length === 1
                          ? ''
                          : 's'}{' '}
                        as a competitor&rsquo;s
                      </p>
                      <p className="text-[11px] text-saibyl-muted leading-relaxed">
                        That lets doubters in the room name that company out loud, and quote
                        it, using only what this document actually says. Without a document
                        like this, Saibyl refuses to name anyone — a model asked about a rival
                        will confidently make things up, and you would have no way of telling
                        which parts. Only mark material a rival genuinely published.
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Document list. "Nothing here yet" is only said once the list has
                actually come back — a failed read has no idea whether there are
                files, and telling the founder there are none is the same defect
                as printing a zero we never counted. */}
            {documents.length === 0 ? (
              <div className="glass rounded-2xl p-12 text-center">
                <div className="text-3xl mb-3 opacity-30">📄</div>
                <p className="text-saibyl-muted text-sm">
                  {documentsLoaded
                    ? 'Nothing uploaded yet — the deck is usually the best one to start with.'
                    : 'We could not read your files just now, so none are listed. Reload the page to try again.'}
                </p>
              </div>
            ) : (
              <div className="glass rounded-2xl overflow-hidden">
                {documents.map((doc, i) => (
                  <div key={doc.id} className={`flex items-center justify-between px-5 py-3 ${i > 0 ? 'border-t border-white/[0.04]' : ''}`}>
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="w-8 h-8 rounded-lg bg-saibyl-gold/10 flex items-center justify-center text-[11px] font-mono text-saibyl-gold uppercase shrink-0">
                        {doc.file_type}
                      </div>
                      <div className="min-w-0">
                        <p className="text-[14px] font-medium text-saibyl-platinum truncate">{doc.filename}</p>
                        <div className="flex items-center gap-2">
                          <p className="text-[11px] text-saibyl-muted">{formatBytes(doc.file_size_bytes || 0)}</p>
                          {/* Rendered only when the column actually holds a value.
                              Rows uploaded before this question was asked carry
                              NULL, and labelling those "Yours" would put words in
                              the mouth of someone who was never asked. */}
                          {doc.material_kind && (
                            <span
                              className={`text-[10px] px-1.5 py-0.5 rounded ${
                                doc.material_kind === 'competitor'
                                  ? 'bg-saibyl-gold/15 text-saibyl-gold'
                                  : 'bg-white/[0.05] text-saibyl-muted'
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
                      >
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* The way on, once there is something to work from. Gated on a file
                Saibyl has actually read rather than on a file existing — an
                upload still in the queue has given it nothing yet. */}
            {readable.length > 0 && (
              <div className="glass rounded-2xl p-5 flex items-center justify-between gap-4">
                <div>
                  <p className="text-[14px] font-medium text-saibyl-platinum">
                    {readable.length === 1
                      ? 'Your file has been read'
                      : `All ${readable.length} of your files have been read`}
                  </p>
                  <p className="text-[12px] text-saibyl-muted mt-0.5">
                    Put this in front of a room of buyers and find out what they argue with.
                  </p>
                </div>
                <button
                  onClick={handleRunSimulation}
                  className="px-5 py-2 rounded-lg bg-[#C9A227] text-[#0A0F1C] font-medium text-sm transition-all hover:bg-[#D4AF37] hover:-translate-y-0.5 shrink-0"
                >
                  Start a run →
                </button>
              </div>
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
              <button
                onClick={() => navigate(`/app/prospects/discover?project_id=${id}`)}
                className="bg-saibyl-gold text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-[#4B4FDE] shrink-0"
              >
                + New search
              </button>
            </div>

            {runs.length === 0 ? (
              <div className="glass rounded-2xl p-12 text-center">
                {runsLoaded ? (
                  <>
                    <p className="text-saibyl-platinum font-medium mb-2">
                      No company searches yet
                    </p>
                    <p className="text-saibyl-muted text-sm mb-5 max-w-md mx-auto leading-relaxed">
                      Once Saibyl has worked out who buys this, it can go and find real
                      companies that look like them — with the page that says so attached
                      to every one.
                    </p>
                    <button
                      onClick={() => navigate(`/app/prospects/discover?project_id=${id}`)}
                      className="bg-saibyl-gold text-white px-6 py-2.5 rounded-lg text-sm font-medium hover:bg-[#4B4FDE]"
                    >
                      Find companies
                    </button>
                  </>
                ) : (
                  <p className="text-saibyl-muted text-sm max-w-md mx-auto leading-relaxed">
                    We could not read your company searches just now, so none are listed.
                    Reload the page to try again.
                  </p>
                )}
              </div>
            ) : (
              <div className="space-y-3">
                {runs.map((run) => {
                  const summary = describeRun(run);
                  return (
                    <div key={run.id} className="glass rounded-xl p-5">
                      <div className="flex items-center justify-between gap-4 mb-1.5">
                        <span className="text-[15px] font-medium text-saibyl-platinum">
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
                              ? 'text-saibyl-gold'
                              : 'text-saibyl-silver'
                          }`}
                        >
                          {run.delivery.sentence}
                        </p>
                      )}

                      {run.candidates_found > 0 && (
                        <button
                          onClick={() =>
                            navigate(`/app/prospects?discovery_run_id=${run.id}`)
                          }
                          className="mt-3 text-[12px] text-saibyl-gold hover:underline"
                        >
                          See the {run.candidates_found} compan
                          {run.candidates_found === 1 ? 'y' : 'ies'} this found →
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* ═══ Simulations Tab ═══ */}
        {tab === 'simulations' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <p className="text-[14px] text-saibyl-muted">
                {simulationsLoaded
                  ? `${simulations.length} run${simulations.length !== 1 ? 's' : ''} on this product`
                  : 'Runs on this product'}
              </p>
              <button
                onClick={() => navigate(`/app/simulations/new?project=${id}`)}
                className="bg-saibyl-gold text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-[#4B4FDE]"
              >
                + New run
              </button>
            </div>
            {simulations.length === 0 ? (
              <div className="glass rounded-2xl p-12 text-center">
                {simulationsLoaded ? (
                  <>
                    <p className="text-saibyl-platinum font-medium mb-2">No runs yet</p>
                    <p className="text-saibyl-muted text-sm mb-5">
                      Start one and find out how people react to what you have written.
                    </p>
                    <button
                      onClick={() => navigate(`/app/simulations/new?project=${id}`)}
                      className="bg-saibyl-gold text-white px-6 py-2.5 rounded-lg text-sm font-medium hover:bg-[#4B4FDE]"
                    >
                      Start a run
                    </button>
                  </>
                ) : (
                  <p className="text-saibyl-muted text-sm max-w-md mx-auto leading-relaxed">
                    We could not read your runs just now, so none are listed. Reload the page
                    to try again.
                  </p>
                )}
              </div>
            ) : (
              <div className="space-y-3">
                {simulations.map((sim) => (
                  <button
                    key={sim.id}
                    onClick={() => navigate(`/app/simulations/${sim.id}`)}
                    className="w-full text-left glass glass-hover rounded-xl p-5 transition-all"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-[15px] font-medium text-saibyl-platinum">{sim.name}</span>
                      <StatusBadge status={sim.status} />
                    </div>
                    <p className="text-[12px] text-saibyl-muted line-clamp-1">{sim.prediction_goal}</p>
                    <div className="flex items-center gap-4 mt-2 text-[11px] text-saibyl-muted">
                      <span>{formatPlatforms(sim.platforms || [])}</span>
                      <span>{sim.max_rounds} rounds</span>
                      <span>{new Date(sim.created_at).toLocaleDateString()}</span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

      </div>
    </div>
  );
}
