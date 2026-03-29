import { useEffect, useState, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import api from '@/lib/api';
import StatusBadge from '@/components/StatusBadge';

interface Project {
  id: string;
  name: string;
  description: string;
}

interface Doc {
  id: string;
  filename: string;
  file_type: string;
  processing_status: string;
  file_size_bytes: number;
  created_at: string;
}

interface OntologyData {
  id: string;
  entity_types: { name: string; description: string; social_media_suitable: boolean }[];
  relationship_types: { name: string; source_entity_type: string; target_entity_type: string; description: string }[];
  refinement_round: number;
  human_approved: boolean;
}

type Tab = 'documents' | 'ontology' | 'knowledge-graph';

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [project, setProject] = useState<Project | null>(null);
  const [tab, setTab] = useState<Tab>('documents');
  const [documents, setDocuments] = useState<Doc[]>([]);
  const [ontology, setOntology] = useState<OntologyData | null>(null);
  const [ontologyLoading, setOntologyLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const [generating, setGenerating] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  // Load project + documents
  useEffect(() => {
    if (!id) return;
    api.get(`/projects/${id}`).then((r) => setProject(r.data)).catch(() => {});
    loadDocuments();
  }, [id]);

  // Poll documents while any are still processing
  useEffect(() => {
    const hasProcessing = documents.some((d) => d.processing_status === 'pending' || d.processing_status === 'processing');
    if (!hasProcessing || !id) return;
    const interval = setInterval(loadDocuments, 3000);
    return () => clearInterval(interval);
  }, [documents, id]);

  // Load ontology when tab switches to ontology OR knowledge-graph
  useEffect(() => {
    if (tab === 'ontology' || tab === 'knowledge-graph') loadOntology();
  }, [tab, id]);

  function loadDocuments() {
    api.get('/documents', { params: { project_id: id } })
      .then((r) => setDocuments(Array.isArray(r.data) ? r.data : []))
      .catch(() => setDocuments([]));
  }

  function loadOntology() {
    setOntologyLoading(true);
    api.get('/ontologies', { params: { project_id: id } })
      .then((r) => {
        const items = Array.isArray(r.data) ? r.data : [];
        setOntology(items.length > 0 ? items[0] : null);
      })
      .catch(() => setOntology(null))
      .finally(() => setOntologyLoading(false));
  }

  // Upload document
  async function handleUpload() {
    const files = fileInput.current?.files;
    if (!files?.length || !id) return;
    setUploading(true);
    setUploadError('');
    try {
      for (const file of Array.from(files)) {
        const form = new FormData();
        form.append('file', file);
        // Use the documents/upload endpoint — simpler, no media_type needed
        await api.post(`/documents/upload?project_id=${id}`, form, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });
      }
      loadDocuments();
    } catch (err: any) {
      setUploadError(err.response?.data?.detail || 'Upload failed');
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = '';
    }
  }

  // Generate ontology from documents
  async function handleGenerateOntology() {
    if (!id) return;
    setGenerating(true);
    setUploadError('');
    try {
      await api.post('/ontologies/generate', { project_id: id });
      // Poll until a new ontology appears (task runs async in Celery)
      let attempts = 0;
      const poll = setInterval(async () => {
        attempts++;
        try {
          const r = await api.get('/ontologies', { params: { project_id: id } });
          const items = Array.isArray(r.data) ? r.data : [];
          if (items.length > 0) {
            // Got an ontology — show it
            setOntology(items[0]);
            setGenerating(false);
            clearInterval(poll);
          }
        } catch { /* keep polling */ }
        if (attempts > 30) {
          // Timeout after ~90s
          setGenerating(false);
          setUploadError('Ontology generation timed out. Check your Anthropic API key and try again.');
          clearInterval(poll);
        }
      }, 3000);
    } catch (err: any) {
      setUploadError(err.response?.data?.detail || 'Ontology generation failed');
      setGenerating(false);
    }
  }

  // Approve ontology
  async function handleApprove() {
    if (!ontology?.id) return;
    try {
      await api.post(`/ontologies/${ontology.id}/approve`);
      setOntology((prev) => prev ? { ...prev, human_approved: true } : prev);
    } catch { /* ignore */ }
  }

  function formatBytes(bytes: number) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  }

  const tabs: { key: Tab; label: string; count?: number }[] = [
    { key: 'documents', label: 'Documents', count: documents.length },
    { key: 'ontology', label: 'Ontology' },
    { key: 'knowledge-graph', label: 'Knowledge Graph' },
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
                  ? 'bg-saibyl-indigo text-white'
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
                  className="text-sm text-saibyl-muted file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-saibyl-indigo/20 file:text-saibyl-indigo file:font-medium file:cursor-pointer hover:file:bg-saibyl-indigo/30"
                />
                <button
                  onClick={handleUpload}
                  disabled={uploading}
                  className="bg-saibyl-indigo text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-[#4B4FDE] disabled:opacity-50 transition-colors shrink-0"
                >
                  {uploading ? 'Uploading...' : 'Upload'}
                </button>
              </div>
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
                      <div className="w-8 h-8 rounded-lg bg-saibyl-indigo/10 flex items-center justify-center text-[11px] font-mono text-saibyl-indigo uppercase shrink-0">
                        {doc.file_type}
                      </div>
                      <div className="min-w-0">
                        <p className="text-[14px] font-medium text-saibyl-platinum truncate">{doc.filename}</p>
                        <p className="text-[11px] text-saibyl-muted">{formatBytes(doc.file_size_bytes || 0)}</p>
                      </div>
                    </div>
                    <StatusBadge status={doc.processing_status} />
                  </div>
                ))}
              </div>
            )}

            {/* Generate ontology CTA (show after docs uploaded) */}
            {documents.length > 0 && (
              <div className="glass rounded-2xl p-5 flex items-center justify-between">
                <div>
                  <p className="text-[14px] font-medium text-saibyl-platinum">Ready to extract entities?</p>
                  <p className="text-[12px] text-saibyl-muted mt-0.5">Generate an ontology from your uploaded documents.</p>
                </div>
                <button
                  onClick={() => { setTab('ontology'); handleGenerateOntology(); }}
                  disabled={generating}
                  className="bg-saibyl-indigo text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-[#4B4FDE] disabled:opacity-50 transition-colors shrink-0"
                >
                  {generating ? 'Generating...' : 'Generate Ontology →'}
                </button>
              </div>
            )}
          </div>
        )}

        {/* ═══ Ontology Tab ═══ */}
        {tab === 'ontology' && (
          <div className="space-y-5">
            {ontologyLoading ? (
              <div className="glass rounded-2xl p-12 text-center">
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-saibyl-indigo mx-auto mb-3" />
                <p className="text-saibyl-muted text-sm">Loading ontology...</p>
              </div>
            ) : !ontology ? (
              <div className="glass rounded-2xl p-12 text-center">
                {generating ? (
                  <>
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-saibyl-indigo mx-auto mb-4" />
                    <p className="text-saibyl-platinum font-medium mb-2">Generating ontology...</p>
                    <p className="text-saibyl-muted text-sm">Analyzing documents with Claude AI. This typically takes 20-30 seconds.</p>
                  </>
                ) : (
                  <>
                    <div className="text-3xl mb-3 opacity-30">🧬</div>
                    <p className="text-saibyl-platinum font-medium mb-2">No ontology generated yet</p>
                    <p className="text-saibyl-muted text-sm mb-5">Generate an ontology to extract entities and relationships from your documents.</p>
                    <button
                      onClick={handleGenerateOntology}
                      className="bg-saibyl-indigo text-white px-6 py-2.5 rounded-lg text-sm font-medium hover:bg-[#4B4FDE]"
                    >
                      Generate Ontology
                    </button>
                  </>
                )}
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <StatusBadge status={ontology.human_approved ? 'approved' : 'pending_review'} />
                    <span className="text-[12px] text-saibyl-muted">Round {ontology.refinement_round}</span>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={handleGenerateOntology} className="glass glass-hover px-4 py-2 rounded-lg text-sm text-saibyl-muted hover:text-saibyl-platinum">
                      Regenerate
                    </button>
                    {!ontology.human_approved && (
                      <button onClick={handleApprove} className="bg-saibyl-positive text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-saibyl-positive/80">
                        Approve Ontology
                      </button>
                    )}
                  </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="glass rounded-2xl p-5">
                    <h3 className="font-semibold text-saibyl-platinum mb-3">Entity Types ({ontology.entity_types?.length || 0})</h3>
                    <div className="space-y-2 max-h-72 overflow-y-auto">
                      {(ontology.entity_types || []).map((e, i) => (
                        <div key={i} className="p-3 rounded-lg bg-white/[0.02] border border-white/[0.04]">
                          <div className="flex items-center gap-2">
                            <span className="text-[13px] font-medium text-saibyl-platinum">{e.name}</span>
                            {e.social_media_suitable && <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-saibyl-positive/15 text-saibyl-positive">SIM-READY</span>}
                          </div>
                          <p className="text-[11px] text-saibyl-muted mt-1">{e.description}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="glass rounded-2xl p-5">
                    <h3 className="font-semibold text-saibyl-platinum mb-3">Relationship Types ({ontology.relationship_types?.length || 0})</h3>
                    <div className="space-y-2 max-h-72 overflow-y-auto">
                      {(ontology.relationship_types || []).map((r, i) => (
                        <div key={i} className="p-3 rounded-lg bg-white/[0.02] border border-white/[0.04]">
                          <p className="text-[13px] text-saibyl-platinum">
                            <span className="text-saibyl-indigo">{r.source_entity_type}</span>
                            {' → '}
                            <span className="font-medium">{r.name}</span>
                            {' → '}
                            <span className="text-saibyl-cyan">{r.target_entity_type}</span>
                          </p>
                          <p className="text-[11px] text-saibyl-muted mt-1">{r.description}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Next step CTA */}
                <div className="glass rounded-2xl p-6 flex items-center justify-between mt-5">
                  <div>
                    <p className="text-[14px] font-medium text-saibyl-platinum">
                      {ontology.human_approved ? 'Ontology approved — ready to simulate' : 'Approve the ontology, then run a simulation'}
                    </p>
                    <p className="text-[12px] text-saibyl-muted mt-0.5">
                      {ontology.entity_types?.length || 0} entity types and {ontology.relationship_types?.length || 0} relationships extracted
                    </p>
                  </div>
                  <div className="flex gap-2 shrink-0">
                    {!ontology.human_approved && (
                      <button onClick={handleApprove} className="bg-saibyl-positive text-white px-5 py-2.5 rounded-lg text-sm font-medium hover:bg-saibyl-positive/80">
                        Approve
                      </button>
                    )}
                    <button
                      onClick={() => navigate(`/app/simulations/new?project=${id}`)}
                      className="relative px-6 py-2.5 rounded-lg text-white font-medium text-sm overflow-hidden transition-all hover:scale-[1.02]"
                    >
                      <div className="absolute inset-0 bg-gradient-to-r from-[#5B5FEE] to-[#00D4FF]" />
                      <span className="relative">Run Simulation →</span>
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>
        )}

        {/* ═══ Knowledge Graph Tab ═══ */}
        {tab === 'knowledge-graph' && (
          <div className="glass rounded-2xl p-8">
            {!ontology?.human_approved ? (
              <div className="text-center py-12">
                <div className="text-3xl mb-3 opacity-30">🕸️</div>
                <p className="text-saibyl-platinum font-medium mb-2">Knowledge graph requires an approved ontology</p>
                <p className="text-saibyl-muted text-sm">Go to the Ontology tab, generate and approve an ontology first.</p>
              </div>
            ) : (
              <div>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-semibold text-saibyl-platinum">Knowledge Graph</h3>
                  <button className="bg-saibyl-indigo text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-[#4B4FDE]">
                    Build Graph
                  </button>
                </div>
                <div
                  id="knowledge-graph-container"
                  className="w-full h-[500px] flex items-center justify-center border border-white/[0.06] rounded-xl bg-saibyl-void"
                >
                  <p className="text-saibyl-muted text-sm">Knowledge graph visualization will render here after building.</p>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
