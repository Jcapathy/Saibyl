import { useEffect, useState, FormEvent } from 'react';
import { Link } from 'react-router-dom';
import api from '@/lib/api';

interface Project {
  id: string;
  name: string;
  description: string;
  document_count: number;
}

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [creating, setCreating] = useState(false);

  const fetchProjects = () => {
    api.get('/projects')
      .then((res) => setProjects(res.data.items || res.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchProjects(); }, []);

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault();
    setCreating(true);
    try {
      await api.post('/projects', { name, description });
      setShowModal(false);
      setName('');
      setDescription('');
      fetchProjects();
    } catch {
      // handle error
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="p-6 max-w-5xl mx-auto bg-saibyl-void">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-saibyl-platinum">Projects</h1>
        <button
          onClick={() => setShowModal(true)}
          className="bg-saibyl-indigo text-white px-4 py-2 rounded-lg hover:bg-[#4B4FDE] transition"
        >
          + New Project
        </button>
      </div>

      {loading ? (
        <p className="text-saibyl-muted">Loading projects...</p>
      ) : projects.length === 0 ? (
        <p className="text-saibyl-muted">No projects yet. Create one to get started.</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map((p) => (
            <Link
              key={p.id}
              to={`/app/projects/${p.id}`}
              className="bg-saibyl-deep rounded-2xl p-5 border border-saibyl-border hover:bg-saibyl-elevated transition"
            >
              <h3 className="font-semibold text-saibyl-platinum mb-1">{p.name}</h3>
              <p className="text-sm text-saibyl-muted mb-3 line-clamp-2">{p.description || 'No description'}</p>
              <span className="text-xs text-saibyl-muted">{p.document_count ?? 0} documents</span>
            </Link>
          ))}
        </div>
      )}

      {/* Create Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-saibyl-deep rounded-2xl p-6 w-full max-w-md border border-saibyl-border">
            <h2 className="text-lg font-semibold text-saibyl-platinum mb-4">Create Project</h2>
            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-saibyl-platinum mb-1">Name</label>
                <input
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full bg-saibyl-surface border border-saibyl-border rounded-lg px-3 py-2 text-saibyl-platinum placeholder-saibyl-muted focus:outline-none focus:ring-2 focus:ring-saibyl-indigo"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-saibyl-platinum mb-1">Description</label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={3}
                  className="w-full bg-saibyl-surface border border-saibyl-border rounded-lg px-3 py-2 text-saibyl-platinum placeholder-saibyl-muted focus:outline-none focus:ring-2 focus:ring-saibyl-indigo"
                />
              </div>
              <div className="flex justify-end gap-3">
                <button type="button" onClick={() => setShowModal(false)} className="px-4 py-2 text-saibyl-muted hover:text-saibyl-platinum">
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="bg-saibyl-indigo text-white px-4 py-2 rounded-lg hover:bg-[#4B4FDE] disabled:opacity-50"
                >
                  {creating ? 'Creating...' : 'Create'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
