import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import api from '@/lib/api';

interface Project {
  id: string;
  name: string;
  description: string;
}

interface PersonaPack {
  id: string;
  name: string;
  description: string;
  category: string;
  archetype_count: number;
  archetype_labels: string[];
}

const PLATFORMS = [
  { id: 'twitter_x', name: 'Twitter / X', desc: 'Engagement-weighted feeds' },
  { id: 'reddit', name: 'Reddit', desc: 'Hot ranking, nested threads' },
  { id: 'linkedin', name: 'LinkedIn', desc: 'Professional, connections' },
  { id: 'instagram', name: 'Instagram', desc: 'Visual-first, stories' },
  { id: 'hacker_news', name: 'Hacker News', desc: 'Technical, karma decay' },
  { id: 'discord', name: 'Discord', desc: 'Channel-based, roles' },
  { id: 'news_comments', name: 'News Comments', desc: 'Article reactions' },
  { id: 'custom', name: 'Custom', desc: 'Your own rules' },
];

const STEPS = ['Setup', 'Platforms', 'Personas', 'Settings', 'Review'];
const DEPTH_LABELS: Record<number, string> = { 1: 'Shallow', 2: 'Standard', 3: 'Standard', 4: 'Deep', 5: 'Exhaustive' };

const inputClass = 'w-full rounded-xl px-4 py-3 text-[14px] text-saibyl-platinum placeholder-saibyl-muted/50 focus:outline-none focus:ring-2 focus:ring-saibyl-indigo/50 focus:border-transparent transition';
const inputBg = 'bg-[#0B1120] border border-white/[0.08]';

export default function NewSimulationPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [step, setStep] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  // Step 1
  const [name, setName] = useState('');
  const [projectId, setProjectId] = useState('');
  const [predictionGoal, setPredictionGoal] = useState('');
  const [projects, setProjects] = useState<Project[]>([]);

  // Step 2
  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>([]);

  // Step 3
  const [packs, setPacks] = useState<PersonaPack[]>([]);
  const [selectedPacks, setSelectedPacks] = useState<string[]>([]);

  // Step 4
  const [rounds, setRounds] = useState(5);
  const [timezone, setTimezone] = useState('America/New_York');
  const [abEnabled, setAbEnabled] = useState(false);
  const [reactDepth, setReactDepth] = useState(2);

  useEffect(() => {
    api.get('/projects/').then((r) => {
      const items = Array.isArray(r.data) ? r.data : r.data.items || [];
      setProjects(items);
      // Pre-select project from URL query param
      const preselect = searchParams.get('project');
      if (preselect && items.some((p: Project) => p.id === preselect)) {
        setProjectId(preselect);
      }
    }).catch(() => {});
  }, [searchParams]);

  useEffect(() => {
    if (step === 2 && packs.length === 0) {
      api.get('/persona-packs/').then((r) => setPacks(Array.isArray(r.data) ? r.data : r.data.items || [])).catch(() => {});
    }
  }, [step, packs.length]);

  const togglePlatform = (id: string) => setSelectedPlatforms((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);
  const togglePack = (id: string) => setSelectedPacks((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);

  const handleSubmit = async () => {
    setSubmitting(true);
    setError('');
    try {
      const { data: sim } = await api.post('/simulations/', {
        name,
        project_id: projectId,
        prediction_goal: predictionGoal,
        platforms: selectedPlatforms,
        max_rounds: rounds,
        is_ab_test: abEnabled,
      });
      await api.post(`/simulations/${sim.id}/prepare`);
      await api.post(`/simulations/${sim.id}/start`);
      navigate(`/app/simulations/${sim.id}/run`);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to start simulation');
    } finally {
      setSubmitting(false);
    }
  };

  const canNext = () => {
    if (step === 0) return !!(name.trim() && projectId && predictionGoal.trim());
    if (step === 1) return selectedPlatforms.length > 0;
    if (step === 2) return selectedPacks.length > 0;
    return true;
  };

  return (
    <div className="p-8 bg-saibyl-void min-h-full">
      <div className="max-w-3xl mx-auto">
        <h1 className="text-h1 text-saibyl-white mb-2">New Simulation</h1>
        <p className="text-small mb-8">Configure your swarm simulation in 5 steps.</p>

        {/* Step indicator */}
        <div className="flex items-center mb-8 gap-1">
          {STEPS.map((label, i) => (
            <div key={label} className="flex items-center">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-[12px] font-mono font-bold transition-colors ${
                i < step ? 'bg-saibyl-positive text-white' : i === step ? 'bg-saibyl-indigo text-white' : 'bg-white/[0.04] text-saibyl-muted'
              }`}>
                {i < step ? '✓' : i + 1}
              </div>
              <span className={`ml-1.5 text-[13px] hidden sm:inline ${i <= step ? 'text-saibyl-platinum' : 'text-saibyl-muted/50'}`}>{label}</span>
              {i < STEPS.length - 1 && <div className={`w-8 h-px mx-2 ${i < step ? 'bg-saibyl-positive/40' : 'bg-white/[0.06]'}`} />}
            </div>
          ))}
        </div>

        {error && (
          <div className="mb-4 px-4 py-3 rounded-xl bg-saibyl-negative/10 border border-saibyl-negative/20 text-saibyl-negative text-sm">{error}</div>
        )}

        <motion.div
          key={step}
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.25 }}
          className="glass rounded-2xl p-8"
        >
          {/* ── Step 1: Setup ── */}
          {step === 0 && (
            <div className="space-y-5">
              <div>
                <label className="block text-[12px] font-medium text-saibyl-muted uppercase tracking-wide mb-2">Simulation Name</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Tesla Q1 Earnings Reaction"
                  className={`${inputClass} ${inputBg}`}
                />
              </div>
              <div>
                <label className="block text-[12px] font-medium text-saibyl-muted uppercase tracking-wide mb-2">Project</label>
                {projects.length === 0 ? (
                  <div className={`${inputClass} ${inputBg} text-saibyl-muted/50`}>
                    No projects yet — <button onClick={() => navigate('/app/projects')} className="text-saibyl-indigo hover:underline">create one first</button>
                  </div>
                ) : (
                  <div className="relative">
                    <select
                      value={projectId}
                      onChange={(e) => setProjectId(e.target.value)}
                      className={`${inputClass} ${inputBg} appearance-none cursor-pointer`}
                      style={{ colorScheme: 'dark' }}
                    >
                      <option value="" className="bg-[#0B1120] text-saibyl-muted">Select a project...</option>
                      {projects.map((p) => (
                        <option key={p.id} value={p.id} className="bg-[#0B1120] text-saibyl-platinum">{p.name}</option>
                      ))}
                    </select>
                    <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-saibyl-muted">
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
                    </div>
                  </div>
                )}
              </div>
              <div>
                <label className="block text-[12px] font-medium text-saibyl-muted uppercase tracking-wide mb-2">Prediction Goal</label>
                <textarea
                  value={predictionGoal}
                  onChange={(e) => setPredictionGoal(e.target.value)}
                  rows={4}
                  placeholder="Describe what you want to predict in plain language. e.g. 'How will retail investors react on Twitter and Reddit if Tesla Q1 earnings beat expectations by 15%?'"
                  className={`${inputClass} ${inputBg} resize-none`}
                />
                <p className="text-[11px] text-saibyl-muted/50 mt-1.5">{predictionGoal.length} characters</p>
              </div>
            </div>
          )}

          {/* ── Step 2: Platforms ── */}
          {step === 1 && (
            <div>
              <p className="text-[14px] text-saibyl-muted mb-5">Select the platforms to simulate. Each uses real algorithmic behavior.</p>
              <div className="grid grid-cols-2 gap-3">
                {PLATFORMS.map((p) => {
                  const selected = selectedPlatforms.includes(p.id);
                  return (
                    <button
                      key={p.id}
                      onClick={() => togglePlatform(p.id)}
                      className={`text-left p-4 rounded-xl border transition-all duration-200 ${
                        selected
                          ? 'border-saibyl-indigo/50 bg-saibyl-indigo/10'
                          : 'border-white/[0.06] bg-white/[0.02] hover:border-white/[0.12]'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className={`font-medium text-[14px] ${selected ? 'text-saibyl-white' : 'text-saibyl-platinum'}`}>{p.name}</span>
                        {selected && <div className="w-5 h-5 rounded-full bg-saibyl-indigo flex items-center justify-center"><svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" /></svg></div>}
                      </div>
                      <p className="text-[11px] text-saibyl-muted mt-1">{p.desc}</p>
                    </button>
                  );
                })}
              </div>
              <p className="text-[12px] text-saibyl-muted mt-4">{selectedPlatforms.length} platform{selectedPlatforms.length !== 1 ? 's' : ''} selected</p>
            </div>
          )}

          {/* ── Step 3: Persona Packs ── */}
          {step === 2 && (
            <div>
              <p className="text-[14px] text-saibyl-muted mb-5">Choose persona packs to populate your simulation agents.</p>
              {packs.length === 0 ? (
                <div className="text-center py-8 text-saibyl-muted">Loading persona packs...</div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {packs.map((pack) => {
                    const selected = selectedPacks.includes(pack.id);
                    return (
                      <button
                        key={pack.id}
                        onClick={() => togglePack(pack.id)}
                        className={`text-left p-4 rounded-xl border transition-all duration-200 ${
                          selected
                            ? 'border-saibyl-indigo/50 bg-saibyl-indigo/10'
                            : 'border-white/[0.06] bg-white/[0.02] hover:border-white/[0.12]'
                        }`}
                      >
                        <div className="flex items-center justify-between mb-1">
                          <span className={`font-medium text-[14px] ${selected ? 'text-saibyl-white' : 'text-saibyl-platinum'}`}>{pack.name}</span>
                          {selected && <div className="w-5 h-5 rounded-full bg-saibyl-indigo flex items-center justify-center"><svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" /></svg></div>}
                        </div>
                        <p className="text-[11px] text-saibyl-muted leading-relaxed">{pack.description}</p>
                        <div className="flex items-center gap-2 mt-2">
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-white/[0.04] text-saibyl-muted">{pack.category}</span>
                          <span className="text-[10px] text-saibyl-muted">{pack.archetype_count} archetypes</span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
              <p className="text-[12px] text-saibyl-muted mt-4">{selectedPacks.length} pack{selectedPacks.length !== 1 ? 's' : ''} selected</p>
            </div>
          )}

          {/* ── Step 4: Settings ── */}
          {step === 3 && (
            <div className="space-y-6">
              <div>
                <label className="block text-[12px] font-medium text-saibyl-muted uppercase tracking-wide mb-3">
                  Simulation Rounds: <span className="text-saibyl-indigo font-bold">{rounds}</span>
                </label>
                <input type="range" min={1} max={20} value={rounds} onChange={(e) => setRounds(Number(e.target.value))} className="w-full accent-saibyl-indigo" />
                <div className="flex justify-between text-[10px] text-saibyl-muted/50 mt-1"><span>1</span><span>10</span><span>20</span></div>
              </div>
              <div>
                <label className="block text-[12px] font-medium text-saibyl-muted uppercase tracking-wide mb-2">Timezone</label>
                <select
                  value={timezone}
                  onChange={(e) => setTimezone(e.target.value)}
                  className={`${inputClass} ${inputBg} appearance-none`}
                  style={{ colorScheme: 'dark' }}
                >
                  {['America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles', 'UTC', 'Europe/London', 'Europe/Berlin', 'Asia/Tokyo', 'Asia/Shanghai'].map((tz) => (
                    <option key={tz} value={tz} className="bg-[#0B1120] text-saibyl-platinum">{tz}</option>
                  ))}
                </select>
              </div>
              <div className="flex items-center gap-3 p-4 rounded-xl bg-white/[0.02] border border-white/[0.06]">
                <input type="checkbox" id="ab-toggle" checked={abEnabled} onChange={(e) => setAbEnabled(e.target.checked)} className="accent-saibyl-indigo w-4 h-4" />
                <div>
                  <label htmlFor="ab-toggle" className="text-[14px] text-saibyl-platinum font-medium cursor-pointer">Enable A/B Testing</label>
                  <p className="text-[11px] text-saibyl-muted mt-0.5">Run two variants simultaneously and compare results</p>
                </div>
              </div>
              <div>
                <label className="block text-[12px] font-medium text-saibyl-muted uppercase tracking-wide mb-3">
                  ReACT Report Depth: <span className="text-saibyl-indigo font-bold">{DEPTH_LABELS[reactDepth] || reactDepth}</span>
                </label>
                <input type="range" min={1} max={5} value={reactDepth} onChange={(e) => setReactDepth(Number(e.target.value))} className="w-full accent-saibyl-indigo" />
                <div className="flex justify-between text-[10px] text-saibyl-muted/50 mt-1"><span>Shallow</span><span>Standard</span><span>Exhaustive</span></div>
              </div>
            </div>
          )}

          {/* ── Step 5: Review ── */}
          {step === 4 && (
            <div>
              <h2 className="text-[18px] font-semibold text-saibyl-white mb-5">Review &amp; Launch</h2>
              <div className="space-y-3">
                {[
                  ['Name', name],
                  ['Project', projects.find((p) => p.id === projectId)?.name || '—'],
                  ['Prediction Goal', predictionGoal || '—'],
                  ['Platforms', selectedPlatforms.map((id) => PLATFORMS.find((p) => p.id === id)?.name || id).join(', ')],
                  ['Persona Packs', `${selectedPacks.length} selected`],
                  ['Rounds', String(rounds)],
                  ['Timezone', timezone],
                  ['A/B Testing', abEnabled ? 'Enabled' : 'Disabled'],
                  ['Report Depth', DEPTH_LABELS[reactDepth] || String(reactDepth)],
                ].map(([label, value]) => (
                  <div key={label} className="flex items-start gap-4 py-2 border-b border-white/[0.04] last:border-0">
                    <span className="text-[13px] text-saibyl-muted w-36 shrink-0">{label}</span>
                    <span className="text-[13px] text-saibyl-platinum flex-1">{value}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── Navigation ── */}
          <div className="flex justify-between mt-8 pt-5 border-t border-white/[0.04]">
            <button
              onClick={() => setStep((s) => s - 1)}
              disabled={step === 0}
              className="px-5 py-2.5 text-[14px] text-saibyl-muted hover:text-saibyl-platinum disabled:opacity-30 transition-colors"
            >
              ← Back
            </button>
            {step < 4 ? (
              <button
                onClick={() => setStep((s) => s + 1)}
                disabled={!canNext()}
                className="bg-saibyl-indigo text-white px-6 py-2.5 rounded-xl text-[14px] font-medium hover:bg-[#4B4FDE] disabled:opacity-30 transition-all"
              >
                Next →
              </button>
            ) : (
              <button
                onClick={handleSubmit}
                disabled={submitting}
                className="relative px-8 py-2.5 rounded-xl text-white font-semibold text-[14px] overflow-hidden disabled:opacity-50 transition-all hover:scale-[1.02]"
              >
                <div className="absolute inset-0 bg-gradient-to-r from-[#5B5FEE] to-[#00D4FF]" />
                <div className="absolute inset-0 animate-glow-pulse rounded-xl" />
                <span className="relative">{submitting ? 'Launching...' : 'Start Simulation →'}</span>
              </button>
            )}
          </div>
        </motion.div>
      </div>
    </div>
  );
}
