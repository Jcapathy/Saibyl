import { useEffect, useState, useRef } from 'react';
import { useParams } from 'react-router-dom';
import api from '@/lib/api';

interface Project {
  id: string;
  name: string;
  description: string;
}

interface Document {
  id: string;
  filename: string;
  status: string;
  created_at: string;
}

interface OntologyData {
  entities: { name: string; type: string }[];
  relationships: { source: string; target: string; label: string }[];
  status: string;
}

type Tab = 'documents' | 'ontology' | 'knowledge-graph';

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [tab, setTab] = useState<Tab>('documents');
  const [documents, setDocuments] = useState<Document[]>([]);
  const [ontology, setOntology] = useState<OntologyData | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.get(`/projects/${id}`).then((res) => setProject(res.data)).catch(() => {});
    api.get(`/projects/${id}/documents`).then((res) => setDocuments(res.data.items || res.data)).catch(() => {});
  }, [id]);

  useEffect(() => {
    if (tab === 'ontology' && !ontology) {
      api.get(`/projects/${id}/ontology`).then((res) => setOntology(res.data)).catch(() => {});
    }
  }, [tab, id, ontology]);

  const handleUpload = async () => {
    const files = fileInput.current?.files;
    if (!files?.length) return;
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        const form = new FormData();
        form.append('file', file);
        form.append('project_id', id!);
        await api.post('/documents/upload', form, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });
      }
      const res = await api.get(`/projects/${id}/documents`);
      setDocuments(res.data.items || res.data);
    } catch {
      // handle error
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = '';
    }
  };

  const approveOntology = async () => {
    try {
      await api.post(`/projects/${id}/ontology/approve`);
      setOntology((prev) => (prev ? { ...prev, status: 'approved' } : prev));
    } catch {
      // handle error
    }
  };

  const tabs: { key: Tab; label: string }[] = [
    { key: 'documents', label: 'Documents' },
    { key: 'ontology', label: 'Ontology' },
    { key: 'knowledge-graph', label: 'Knowledge Graph' },
  ];

  return (
    <div className="p-6 max-w-5xl mx-auto bg-saibyl-void">
      <h1 className="text-2xl font-bold text-saibyl-platinum mb-1">{project?.name || 'Project'}</h1>
      <p className="text-saibyl-muted mb-6">{project?.description}</p>

      {/* Tabs */}
      <div className="flex border-b border-saibyl-border mb-6">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 -mb-px text-sm font-medium transition ${
              tab === t.key
                ? 'border-b-2 border-saibyl-border-active text-saibyl-indigo'
                : 'text-saibyl-muted hover:text-saibyl-platinum'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Documents Tab */}
      {tab === 'documents' && (
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <input ref={fileInput} type="file" multiple className="text-sm" />
            <button
              onClick={handleUpload}
              disabled={uploading}
              className="bg-saibyl-indigo text-white px-4 py-2 rounded-lg text-sm hover:bg-[#4B4FDE] disabled:opacity-50"
            >
              {uploading ? 'Uploading...' : 'Upload'}
            </button>
          </div>
          {documents.length === 0 ? (
            <p className="text-saibyl-muted">No documents uploaded yet.</p>
          ) : (
            <ul className="bg-saibyl-deep rounded-2xl divide-y divide-saibyl-border border border-saibyl-border">
              {documents.map((doc) => (
                <li key={doc.id} className="px-4 py-3 flex items-center justify-between">
                  <span className="text-sm font-medium text-saibyl-platinum">{doc.filename}</span>
                  <span className="text-xs text-saibyl-muted">{doc.status}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Ontology Tab */}
      {tab === 'ontology' && (
        <div className="space-y-4">
          {!ontology ? (
            <p className="text-saibyl-muted">Loading ontology...</p>
          ) : (
            <>
              <div className="flex items-center justify-between">
                <span className="text-sm text-saibyl-muted">
                  Status: <span className="font-medium">{ontology.status}</span>
                </span>
                {ontology.status !== 'approved' && (
                  <button
                    onClick={approveOntology}
                    className="bg-green-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-green-700"
                  >
                    Approve Ontology
                  </button>
                )}
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="bg-saibyl-deep rounded-2xl p-4 border border-saibyl-border">
                  <h3 className="font-semibold text-saibyl-platinum mb-2">Entities ({ontology.entities.length})</h3>
                  <ul className="space-y-1 max-h-64 overflow-y-auto">
                    {ontology.entities.map((e, i) => (
                      <li key={i} className="text-sm">
                        <span className="font-medium text-saibyl-platinum">{e.name}</span>{' '}
                        <span className="text-saibyl-muted">({e.type})</span>
                      </li>
                    ))}
                  </ul>
                </div>
                <div className="bg-saibyl-deep rounded-2xl p-4 border border-saibyl-border">
                  <h3 className="font-semibold text-saibyl-platinum mb-2">Relationships ({ontology.relationships.length})</h3>
                  <ul className="space-y-1 max-h-64 overflow-y-auto">
                    {ontology.relationships.map((r, i) => (
                      <li key={i} className="text-sm text-saibyl-platinum">
                        {r.source} <span className="text-saibyl-indigo">--{r.label}--&gt;</span> {r.target}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* Knowledge Graph Tab */}
      {tab === 'knowledge-graph' && (
        <div className="bg-saibyl-deep rounded-2xl p-4 border border-saibyl-border">
          <div
            id="knowledge-graph-container"
            className="w-full h-[500px] flex items-center justify-center border-2 border-dashed border-saibyl-border rounded"
          >
            <p className="text-saibyl-muted">D3.js Knowledge Graph visualization will render here</p>
          </div>
        </div>
      )}
    </div>
  );
}
