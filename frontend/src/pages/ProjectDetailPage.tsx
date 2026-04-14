import { useEffect, useState, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import api from '@/lib/api';
import { formatPlatforms } from '@/lib/constants';
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

interface Sim {
  id: string;
  name: string;
  status: string;
  platforms: string[];
  max_rounds: number;
  created_at: string;
  project_id: string;
  prediction_goal: string;
}

type Tab = 'documents' | 'simulations';

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [project, setProject] = useState<Project | null>(null);
  const [tab, setTab] = useState<Tab>('documents');
  const [documents, setDocuments] = useState<Doc[]>([]);
  const [simulations, setSimulations] = useState<Sim[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const fileInput = useRef<HTMLInputElement>(null);

  // Load project + documents + simulations
  useEffect(() => {
    if (!id) return;
    api.get(`/projects/${id}`).then((r) => setProject(r.data)).catch(() => {});
    loadDocuments();
    api.get('/simulations', { params: { project_id: id, limit: 50 } }).then((r) => {
      setSimulations(Array.isArray(r.data) ? r.data : []);
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
      .then((r) => setDocuments(Array.isArray(r.data) ? r.data : []))
      .catch(() => setDocuments([]));
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
                  className="text-sm text-saibyl-muted file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-saibyl-gold/20 file:text-saibyl-gold file:font-medium file:cursor-pointer hover:file:bg-saibyl-gold/30"
                />
                <button
                  onClick={handleUpload}
                  disabled={uploading}
                  className="bg-saibyl-gold text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-[#4B4FDE] disabled:opacity-50 transition-colors shrink-0"
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
                      <div className="w-8 h-8 rounded-lg bg-saibyl-gold/10 flex items-center justify-center text-[11px] font-mono text-saibyl-gold uppercase shrink-0">
                        {doc.file_type}
                      </div>
                      <div className="min-w-0">
                        <p className="text-[14px] font-medium text-saibyl-platinum truncate">{doc.filename}</p>
                        <p className="text-[11px] text-saibyl-muted">{formatBytes(doc.file_size_bytes || 0)}</p>
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
                  className="px-5 py-2 rounded-lg bg-[#C9A227] text-[#070B14] font-medium text-sm transition-all hover:bg-[#D4AF37] hover:-translate-y-0.5 shrink-0"
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
