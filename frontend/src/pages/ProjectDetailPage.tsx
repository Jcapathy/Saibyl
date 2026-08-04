import { useEffect, useState, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import api, { unwrapList } from '@/lib/api';
import { formatPlatforms } from '@/lib/constants';
import StatusBadge from '@/components/StatusBadge';
import { getErrorMessage } from '../lib/errors';
import type { MaterialKind, Project, ProjectDocument, Simulation } from '@/types';

type Tab = 'documents' | 'simulations';

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
    help: 'Something a rival published. Lets Saibyl name them in a simulation.',
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
  const [tab, setTab] = useState<Tab>('documents');
  const [documents, setDocuments] = useState<ProjectDocument[]>([]);
  const [simulations, setSimulations] = useState<Simulation[]>([]);
  const [pending, setPending] = useState<PendingUpload[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const fileInput = useRef<HTMLInputElement>(null);

  // Load project + documents + simulations
  useEffect(() => {
    if (!id) return;
    api.get(`/projects/${id}`).then((r) => setProject(r.data)).catch(() => {});
    loadDocuments();
    api.get('/simulations', { params: { project_id: id, limit: 50 } }).then((r) => {
      setSimulations(unwrapList<Simulation>(r.data).items);
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
      .then((r) => setDocuments(unwrapList<ProjectDocument>(r.data).items))
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

  const tabs: { key: Tab; label: string; count?: number }[] = [
    { key: 'documents', label: 'Documents', count: documents.length },
    { key: 'simulations', label: 'Simulations', count: simulations.length },
  ];

  return (
    <div className="p-8 bg-saibyl-void min-h-full">
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <h1 className="text-h1 text-saibyl-white mb-1">{project?.name || 'Project'}</h1>
        <p className="text-small mb-8">{project?.description}</p>

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
              <h3 className="text-[14px] font-medium text-saibyl-platinum mb-3">Upload Documents</h3>
              <p className="text-[12px] text-saibyl-muted mb-4">Supported: PDF, DOCX, TXT, MD (max 50MB each)</p>
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
                    Whose is this? We ask so we know what the simulation is allowed to say.
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
                        That lets simulated skeptics name that company out loud, and quote it,
                        using only what this document actually says. Without a document like
                        this, Saibyl refuses to name anyone — a model asked about a rival will
                        confidently make things up, and you would have no way of telling which
                        parts. Only mark material a rival genuinely published.
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Document list */}
            {documents.length === 0 ? (
              <div className="glass rounded-2xl p-12 text-center">
                <div className="text-3xl mb-3 opacity-30">📄</div>
                <p className="text-saibyl-muted text-sm">No documents yet. Upload files to get started.</p>
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

            {/* CTA to create simulation after docs uploaded */}
            {documents.length > 0 && (
              <div className="glass rounded-2xl p-5 flex items-center justify-between">
                <div>
                  <p className="text-[14px] font-medium text-saibyl-platinum">Documents ready</p>
                  <p className="text-[12px] text-saibyl-muted mt-0.5">Create a simulation to predict reactions to your content.</p>
                </div>
                <button
                  onClick={handleRunSimulation}
                  className="px-5 py-2 rounded-lg bg-[#C9A227] text-[#0A0F1C] font-medium text-sm transition-all hover:bg-[#D4AF37] hover:-translate-y-0.5 shrink-0"
                >
                  New Simulation →
                </button>
              </div>
            )}
          </div>
        )}

        {/* ═══ Simulations Tab ═══ */}
        {tab === 'simulations' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <p className="text-[14px] text-saibyl-muted">{simulations.length} simulation{simulations.length !== 1 ? 's' : ''} for this project</p>
              <button
                onClick={() => navigate(`/app/simulations/new?project=${id}`)}
                className="bg-saibyl-gold text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-[#4B4FDE]"
              >
                + New Simulation
              </button>
            </div>
            {simulations.length === 0 ? (
              <div className="glass rounded-2xl p-12 text-center">
                <p className="text-saibyl-platinum font-medium mb-2">No simulations yet</p>
                <p className="text-saibyl-muted text-sm mb-5">Create a simulation to predict how people will react to your content.</p>
                <button
                  onClick={() => navigate(`/app/simulations/new?project=${id}`)}
                  className="bg-saibyl-gold text-white px-6 py-2.5 rounded-lg text-sm font-medium hover:bg-[#4B4FDE]"
                >
                  Create Simulation
                </button>
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
