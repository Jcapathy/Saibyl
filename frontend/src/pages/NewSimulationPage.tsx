import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '@/lib/api';

interface Project {
  id: string;
  name: string;
}

interface PersonaPack {
  id: string;
  name: string;
  description: string;
  persona_count: number;
}

const PLATFORMS = ['Twitter', 'Reddit', 'TikTok', 'Instagram', 'Facebook', 'LinkedIn', 'YouTube'];
const STEPS = ['Basics', 'Platforms', 'Personas', 'Settings', 'Review'];

export default function NewSimulationPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [submitting, setSubmitting] = useState(false);

  // Step 1 - Basics
  const [name, setName] = useState('');
  const [projectId, setProjectId] = useState('');
  const [predictionGoal, setPredictionGoal] = useState('');
  const [projects, setProjects] = useState<Project[]>([]);

  // Step 2 - Platforms
  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>([]);

  // Step 3 - Personas
  const [packs, setPacks] = useState<PersonaPack[]>([]);
  const [selectedPacks, setSelectedPacks] = useState<string[]>([]);

  // Step 4 - Settings
  const [rounds, setRounds] = useState(5);
  const [timezone, setTimezone] = useState('UTC');
  const [abEnabled, setAbEnabled] = useState(false);
  const [reactDepth, setReactDepth] = useState(2);

  useEffect(() => {
    api.get('/projects').then((res) => setProjects(res.data.items || res.data)).catch(() => {});
  }, []);

  useEffect(() => {
    if (step === 2 && packs.length === 0) {
      api.get('/persona-packs').then((res) => setPacks(res.data.items || res.data)).catch(() => {});
    }
  }, [step, packs.length]);

  const togglePlatform = (p: string) => {
    setSelectedPlatforms((prev) =>
      prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]
    );
  };

  const togglePack = (id: string) => {
    setSelectedPacks((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      const { data: sim } = await api.post('/simulations', {
        name,
        project_id: projectId,
        prediction_goal: predictionGoal,
        platforms: selectedPlatforms,
        persona_pack_ids: selectedPacks,
        rounds,
        timezone,
        ab_enabled: abEnabled,
        react_depth: reactDepth,
      });
      await api.post(`/simulations/${sim.id}/prepare`);
      await api.post(`/simulations/${sim.id}/start`);
      navigate(`/app/simulations/${sim.id}/run`);
    } catch {
      // handle error
    } finally {
      setSubmitting(false);
    }
  };

  const canNext = () => {
    if (step === 0) return name && projectId;
    if (step === 1) return selectedPlatforms.length > 0;
    if (step === 2) return selectedPacks.length > 0;
    return true;
  };

  return (
    <div className="p-6 max-w-3xl mx-auto bg-saibyl-void">
      <h1 className="text-2xl font-bold text-saibyl-platinum mb-6">New Simulation</h1>

      {/* Step indicator */}
      <div className="flex items-center mb-8">
        {STEPS.map((label, i) => (
          <div key={label} className="flex items-center">
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
                i <= step ? 'bg-saibyl-indigo text-white' : 'bg-saibyl-surface text-saibyl-muted'
              }`}
            >
              {i + 1}
            </div>
            <span className={`ml-2 text-sm ${i <= step ? 'text-saibyl-platinum' : 'text-saibyl-muted'}`}>{label}</span>
            {i < STEPS.length - 1 && <div className="w-8 h-px bg-saibyl-border mx-3" />}
          </div>
        ))}
      </div>

      <div className="bg-saibyl-deep rounded-2xl p-6 border border-saibyl-border">
        {/* Step 1: Basics */}
        {step === 0 && (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-saibyl-platinum mb-1">Simulation Name</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full bg-saibyl-surface border border-saibyl-border rounded-lg px-3 py-2 text-saibyl-platinum placeholder-saibyl-muted focus:outline-none focus:ring-2 focus:ring-saibyl-indigo"
                placeholder="e.g. Q1 Launch Campaign Test"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-saibyl-platinum mb-1">Project</label>
              <select
                value={projectId}
                onChange={(e) => setProjectId(e.target.value)}
                className="w-full bg-saibyl-surface border border-saibyl-border rounded-lg px-3 py-2 text-saibyl-platinum placeholder-saibyl-muted focus:outline-none focus:ring-2 focus:ring-saibyl-indigo"
              >
                <option value="">Select a project</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-saibyl-platinum mb-1">Prediction Goal</label>
              <textarea
                value={predictionGoal}
                onChange={(e) => setPredictionGoal(e.target.value)}
                rows={3}
                className="w-full bg-saibyl-surface border border-saibyl-border rounded-lg px-3 py-2 text-saibyl-platinum placeholder-saibyl-muted focus:outline-none focus:ring-2 focus:ring-saibyl-indigo"
                placeholder="What do you want to predict or test?"
              />
            </div>
          </div>
        )}

        {/* Step 2: Platforms */}
        {step === 1 && (
          <div>
            <p className="text-sm text-saibyl-muted mb-4">Select platforms to simulate:</p>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {PLATFORMS.map((p) => (
                <button
                  key={p}
                  onClick={() => togglePlatform(p)}
                  className={`px-4 py-3 rounded-lg border-2 text-sm font-medium transition ${
                    selectedPlatforms.includes(p)
                      ? 'border-saibyl-border-active bg-saibyl-surface text-saibyl-indigo'
                      : 'border-saibyl-border text-saibyl-muted hover:border-saibyl-border'
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Step 3: Persona Packs */}
        {step === 2 && (
          <div>
            <p className="text-sm text-saibyl-muted mb-4">Choose persona packs for the simulation:</p>
            {packs.length === 0 ? (
              <p className="text-saibyl-muted">Loading persona packs...</p>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {packs.map((pack) => (
                  <button
                    key={pack.id}
                    onClick={() => togglePack(pack.id)}
                    className={`text-left px-4 py-3 rounded-lg border-2 transition ${
                      selectedPacks.includes(pack.id)
                        ? 'border-saibyl-border-active bg-saibyl-surface'
                        : 'border-saibyl-border hover:border-saibyl-border'
                    }`}
                  >
                    <div className="font-medium text-sm text-saibyl-platinum">{pack.name}</div>
                    <div className="text-xs text-saibyl-muted mt-1">{pack.description}</div>
                    <div className="text-xs text-saibyl-muted mt-1">{pack.persona_count} personas</div>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Step 4: Settings */}
        {step === 3 && (
          <div className="space-y-5">
            <div>
              <label className="block text-sm font-medium text-saibyl-platinum mb-1">
                Rounds: {rounds}
              </label>
              <input
                type="range"
                min={1}
                max={20}
                value={rounds}
                onChange={(e) => setRounds(Number(e.target.value))}
                className="w-full"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-saibyl-platinum mb-1">Timezone</label>
              <input
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                className="w-full bg-saibyl-surface border border-saibyl-border rounded-lg px-3 py-2 text-saibyl-platinum placeholder-saibyl-muted focus:outline-none focus:ring-2 focus:ring-saibyl-indigo"
              />
            </div>
            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                id="ab-toggle"
                checked={abEnabled}
                onChange={(e) => setAbEnabled(e.target.checked)}
                className="rounded"
              />
              <label htmlFor="ab-toggle" className="text-sm text-saibyl-platinum">Enable A/B Testing</label>
            </div>
            <div>
              <label className="block text-sm font-medium text-saibyl-platinum mb-1">
                ReACT Depth: {reactDepth}
              </label>
              <input
                type="range"
                min={1}
                max={5}
                value={reactDepth}
                onChange={(e) => setReactDepth(Number(e.target.value))}
                className="w-full"
              />
            </div>
          </div>
        )}

        {/* Step 5: Review */}
        {step === 4 && (
          <div className="space-y-3">
            <h2 className="text-lg font-semibold text-saibyl-platinum">Review &amp; Launch</h2>
            <dl className="text-sm space-y-2">
              <div className="flex"><dt className="w-32 text-saibyl-muted">Name:</dt><dd className="text-saibyl-platinum">{name}</dd></div>
              <div className="flex"><dt className="w-32 text-saibyl-muted">Project:</dt><dd className="text-saibyl-platinum">{projects.find((p) => p.id === projectId)?.name || projectId}</dd></div>
              <div className="flex"><dt className="w-32 text-saibyl-muted">Goal:</dt><dd className="text-saibyl-platinum line-clamp-2">{predictionGoal || '(none)'}</dd></div>
              <div className="flex"><dt className="w-32 text-saibyl-muted">Platforms:</dt><dd className="text-saibyl-platinum">{selectedPlatforms.join(', ')}</dd></div>
              <div className="flex"><dt className="w-32 text-saibyl-muted">Persona Packs:</dt><dd className="text-saibyl-platinum">{selectedPacks.length} selected</dd></div>
              <div className="flex"><dt className="w-32 text-saibyl-muted">Rounds:</dt><dd className="text-saibyl-platinum">{rounds}</dd></div>
              <div className="flex"><dt className="w-32 text-saibyl-muted">Timezone:</dt><dd className="text-saibyl-platinum">{timezone}</dd></div>
              <div className="flex"><dt className="w-32 text-saibyl-muted">A/B Testing:</dt><dd className="text-saibyl-platinum">{abEnabled ? 'Yes' : 'No'}</dd></div>
              <div className="flex"><dt className="w-32 text-saibyl-muted">ReACT Depth:</dt><dd className="text-saibyl-platinum">{reactDepth}</dd></div>
            </dl>
          </div>
        )}

        {/* Navigation */}
        <div className="flex justify-between mt-8 pt-4 border-t border-saibyl-border">
          <button
            onClick={() => setStep((s) => s - 1)}
            disabled={step === 0}
            className="px-4 py-2 text-saibyl-muted hover:text-saibyl-platinum disabled:opacity-40"
          >
            Back
          </button>
          {step < 4 ? (
            <button
              onClick={() => setStep((s) => s + 1)}
              disabled={!canNext()}
              className="bg-saibyl-indigo text-white px-6 py-2 rounded-lg hover:bg-[#4B4FDE] disabled:opacity-50 transition"
            >
              Next
            </button>
          ) : (
            <button
              onClick={handleSubmit}
              disabled={submitting}
              className="bg-green-600 text-white px-6 py-2 rounded-lg hover:bg-green-700 disabled:opacity-50 transition"
            >
              {submitting ? 'Launching...' : 'Start Simulation'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
