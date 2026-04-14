import { useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import api from '@/lib/api';

interface Project {
  id: string;
  name: string;
  description: string;
  asset_count: number;
}

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [creating, setCreating] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

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

  const handleDelete = async (id: string) => {
    setDeletingId(id);
    try {
      await api.delete(`/projects/${id}`);
      setProjects((prev) => prev.filter((p) => p.id !== id));
    } catch {
      // handle error
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-saibyl-platinum">Projects</h1>
        <button
          onClick={() => setShowModal(true)}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-[#C9A227] text-white font-medium text-sm transition-all hover:bg-[#B08D1F] hover:scale-[1.02] hover:shadow-[0_0_20px_rgba(201,162,39,0.25)]"
        >
          + New Project
        </button>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-36 rounded-2xl bg-saibyl-deep animate-pulse" />
          ))}
        </div>
      ) : projects.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <div className="w-14 h-14 rounded-2xl bg-saibyl-gold/10 flex items-center justify-center mb-4">
            <svg className="w-7 h-7 text-saibyl-gold" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z" />
            </svg>
          </div>
          <p className="text-saibyl-platinum font-medium mb-1">No projects yet</p>
          <p className="text-saibyl-muted text-sm mb-6">Organize your simulations into projects</p>
          <button onClick={() => setShowModal(true)} className="bg-saibyl-gold text-white px-5 py-2.5 rounded-xl text-sm font-medium hover:bg-[#4B4FDE] transition">
            Create Project
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
                <p className="text-sm text-saibyl-muted mb-4 line-clamp-2">{p.description || 'No description'}</p>
                <span className="font-mono text-[11px] text-saibyl-muted/60">{p.asset_count ?? 0} documents</span>
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
                title="Delete project"
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
              className="glass rounded-2xl p-6 w-full max-w-md border border-white/[0.08] shadow-[0_0_60px_rgba(0,0,0,0.5)]"
            >
              <h2 className="text-lg font-semibold text-saibyl-platinum mb-5">Create Project</h2>
              <form onSubmit={handleCreate} className="space-y-4">
                <div>
                  <label className="block text-[12px] font-medium text-saibyl-muted uppercase tracking-wide mb-1.5">Name</label>
                  <input
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="My Research Project"
                    className="w-full bg-white/[0.04] border border-white/[0.07] rounded-xl px-4 py-2.5 text-saibyl-platinum placeholder-saibyl-muted/40 focus:outline-none focus:ring-2 focus:ring-saibyl-gold/50 transition text-sm"
                  />
                </div>
                <div>
                  <label className="block text-[12px] font-medium text-saibyl-muted uppercase tracking-wide mb-1.5">
                    Description <span className="normal-case text-saibyl-muted/50 ml-1 font-normal">(optional)</span>
                  </label>
                  <textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    rows={3}
                    placeholder="What is this project about?"
                    className="w-full bg-white/[0.04] border border-white/[0.07] rounded-xl px-4 py-2.5 text-saibyl-platinum placeholder-saibyl-muted/40 focus:outline-none focus:ring-2 focus:ring-saibyl-gold/50 transition text-sm resize-none"
                  />
                </div>
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
                    {creating ? 'Creating...' : 'Create Project'}
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
