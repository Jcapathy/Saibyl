import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Lightbulb } from 'lucide-react';
import api, { unwrapList } from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { listPacks } from '@/lib/packs';
import RunConfigurator, { type RunShape } from '@/components/RunConfigurator';
import FounderLensStep, { type FounderConfig } from '@/components/founder/FounderLensStep';
import type { OrgPersonaPack, PersonaPack, Project } from '@/types';

const PLATFORMS = [
  { id: 'twitter_x', name: 'Twitter / X', desc: 'Hot takes travel fastest' },
  { id: 'reddit', name: 'Reddit', desc: 'Threads, and depth gets rewarded' },
  { id: 'linkedin', name: 'LinkedIn', desc: 'Professional, and negativity sinks' },
  { id: 'instagram', name: 'Instagram', desc: 'Pictures first, then stories' },
  { id: 'tiktok', name: 'TikTok', desc: 'Short video, duets and stitches' },
  { id: 'youtube', name: 'YouTube', desc: 'Long video, comments underneath' },
  { id: 'facebook', name: 'Facebook', desc: 'Groups, reactions and shares' },
  { id: 'threads', name: 'Threads', desc: 'Text posts and reposts' },
  { id: 'hacker_news', name: 'Hacker News', desc: 'Technical crowd, front page fades fast' },
  { id: 'discord', name: 'Discord', desc: 'Channels and roles' },
  { id: 'news_comments', name: 'News Comments', desc: 'Comments under an article' },
  { id: 'custom', name: 'Custom', desc: 'Your own rules' },
];

/* Six steps. The heading counts them out of this array rather than restating
   the number — it read "in 5 steps" above six of them for as long as the sixth
   has existed, and a hand-written count is a second place for the truth to
   live. */
const STEPS = ['Setup', 'Where', 'Who reacts', 'Your buyers', 'Size', 'Review'];
const LAST_STEP = STEPS.length - 1;

const inputClass = 'w-full rounded-xl px-4 py-3 text-[14px] text-saibyl-platinum placeholder-saibyl-muted/50 focus:outline-none focus:ring-2 focus:ring-saibyl-gold/50 focus:border-transparent transition';
const inputBg = 'bg-[#0B1120] border border-white/[0.08]';

/**
 * `pre_launch_positioning` → `Pre launch positioning`.
 *
 * The review list used to lean on a `capitalize` class for these two values,
 * which also title-cased every full sentence beside them. Casing the two values
 * that need it here lets the sentences render as sentences.
 */
function sentenceCase(value: string): string {
  const words = value.replace(/_/g, ' ');
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function Hint({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2.5 px-4 py-3 rounded-xl bg-saibyl-gold/5 border border-saibyl-gold/15 mb-5">
      <Lightbulb className="w-3.5 h-3.5 text-saibyl-gold mt-0.5 shrink-0" />
      <p className="text-[12px] text-saibyl-muted leading-relaxed">{children}</p>
    </div>
  );
}

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
  /* Audiences this org has already worked out and kept. They go into the same
     `persona_pack_ids` list as the ready-made packs — the API has always taken
     a list and the engine blends whatever is in it, so there is one selection
     here, not two. */
  const [orgPacks, setOrgPacks] = useState<OrgPersonaPack[]>([]);
  const [orgPacksError, setOrgPacksError] = useState('');
  const [selectedPacks, setSelectedPacks] = useState<string[]>([]);
  const [showCustomModal, setShowCustomModal] = useState(false);
  const [customName, setCustomName] = useState('');
  const [customDesc, setCustomDesc] = useState('');
  const [creatingCustom, setCreatingCustom] = useState(false);

  // Step 4 — the priced run shape. `platforms` is derived from step 2 rather
  // than set here, so there is exactly one place a platform gets chosen.
  const [shape, setShape] = useState<RunShape>({
    agent_count: 25,
    rounds: 5,
    platforms: 1,
    variants: 1,
    depth: 'standard',
  });
  const [timezone, setTimezone] = useState('America/New_York');
  const [quoteError, setQuoteError] = useState('');

  // Step 4 — the Founder lens. A run with no stage and no ICP is an unlensed
  // run, which is what every simulation made before Phase 2 was: `lens` stays
  // null rather than being defaulted to 'founder', because a lens the user
  // never chose is an attribute nobody recorded.
  const [founder, setFounder] = useState<FounderConfig>({
    stage: null,
    icpProfileId: null,
    adversarialShare: 0,
  });

  useEffect(() => {
    api.get('/projects').then((r) => {
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
    if (step !== 2 || packs.length > 0) return;
    api
      .get('/persona-packs')
      .then((r) => setPacks(unwrapList<PersonaPack>(r.data).items))
      .catch(() => {});
    listPacks()
      .then((rows) => {
        setOrgPacks(rows);
        setOrgPacksError('');
      })
      // Kept distinct from "you have none saved". A failed lookup that rendered
      // as an empty library would tell a founder their saved audiences are gone.
      .catch((err) => setOrgPacksError(getErrorMessage(err, 'Your saved audiences could not be loaded.')));
  }, [step, packs.length]);

  const togglePlatform = (id: string) => setSelectedPlatforms((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);
  const togglePack = (id: string) => setSelectedPacks((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);

  const handleCreateCustomPack = async () => {
    if (!customName.trim() || !customDesc.trim()) return;
    setCreatingCustom(true);
    try {
      const { data } = await api.post('/persona-packs/custom', { name: customName, description: customDesc });
      setPacks((prev) => [...prev, data]);
      setSelectedPacks((prev) => [...prev, data.id]);
      setShowCustomModal(false);
      setCustomName('');
      setCustomDesc('');
    } catch (err) {
      setError(getErrorMessage(err, 'We could not build that group.'));
    } finally {
      setCreatingCustom(false);
    }
  };

  /* Fired whenever the configurator re-prices. An estimate is not a quote —
     it exists so the parent can invalidate anything stale, and so the Review
     step can refuse to launch a shape that could not be priced at all. */
  const handleQuote = useCallback((estimate: { credits: number } | null) => {
    setQuoteError(estimate ? '' : 'This run could not be priced.');
  }, []);

  const handleSubmit = async () => {
    setSubmitting(true);
    setError('');
    const platforms = selectedPlatforms.length > 0 ? selectedPlatforms : ['twitter_x'];

    try {
      // Issue the signed quote before creating anything. If the price cannot be
      // established the run does not start — the alternative is a run whose
      // cost the customer never agreed to.
      const { data: quote } = await api.post('/billing/quote', {
        ...shape,
        platforms: platforms.length,
      });

      const { data: sim } = await api.post('/simulations', {
        name,
        project_id: projectId,
        prediction_goal: predictionGoal,
        platforms,
        max_rounds: shape.rounds,
        persona_pack_ids: selectedPacks,
        agent_count: shape.agent_count,
        variants: shape.variants,
        depth: shape.depth,
        // A stage is only valid on a Founder-lens run, so the two travel
        // together or not at all — the API rejects a stage without the lens.
        lens: founder.stage ? 'founder' : null,
        founder_stage: founder.stage,
        icp_profile_id: founder.icpProfileId,
        // Only sent with an ICP. The share is expressed as archetype weight and
        // the built-in packs carry no adversarial archetypes, so sending it
        // without one is rejected rather than silently doing nothing.
        adversarial_share: founder.icpProfileId ? founder.adversarialShare : 0,
      });

      // The quote id travels to /start, where it is redeemed against the stored
      // shape. Prepare runs first; the credits are charged when the run starts.
      sessionStorage.setItem(`saibyl_quote_${sim.id}`, quote.id);
      api.post(`/simulations/${sim.id}/prepare`).catch(() => {});
      navigate(`/app/simulations/${sim.id}`);
    } catch (err) {
      setError(getErrorMessage(err, 'We could not start this run.'));
    } finally {
      setSubmitting(false);
    }
  };

  const canNext = () => {
    if (step === 0) return !!(name.trim() && projectId && predictionGoal.trim());
    // Steps 1-3: always allow next (selections are optional, defaults work)
    return true;
  };

  return (
    <div className="p-8 bg-saibyl-void min-h-full">
      <div className="max-w-3xl mx-auto">
        <h1 className="text-h1 text-saibyl-white mb-2">Start a new run</h1>
        <p className="text-small mb-8">
          {STEPS.length} steps to set it up. Then we put it in front of the room and
          tell you what they push back on.
        </p>

        {/* Step indicator */}
        <div className="flex items-center mb-8 gap-1">
          {STEPS.map((label, i) => (
            <div key={label} className="flex items-center">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-[12px] font-mono font-bold transition-colors ${
                i < step ? 'bg-saibyl-positive text-white' : i === step ? 'bg-saibyl-gold text-white' : 'bg-white/[0.04] text-saibyl-muted'
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
              <Hint>
                Ask one specific question. The narrower it is, the sharper the answer —
                instead of &ldquo;How will people react?&rdquo;, try &ldquo;Would solo
                founders pay $49 a month for this, or say they could build it themselves
                in a weekend?&rdquo;
              </Hint>
              <div>
                <label className="block text-[12px] font-medium text-saibyl-muted uppercase tracking-wide mb-2">Name this run</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. New pricing page, before launch"
                  className={`${inputClass} ${inputBg}`}
                />
              </div>
              <div>
                <label className="block text-[12px] font-medium text-saibyl-muted uppercase tracking-wide mb-2">Product</label>
                {projects.length === 0 ? (
                  <div className={`${inputClass} ${inputBg} text-saibyl-muted/50`}>
                    Nothing here yet — <button onClick={() => navigate('/app/projects')} className="text-saibyl-gold hover:underline">add your product first</button>
                  </div>
                ) : (
                  <div className="relative">
                    <select
                      value={projectId}
                      onChange={(e) => setProjectId(e.target.value)}
                      className={`${inputClass} ${inputBg} appearance-none cursor-pointer`}
                      style={{ colorScheme: 'dark' }}
                    >
                      <option value="" className="bg-[#0B1120] text-saibyl-muted">Choose a product…</option>
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
                <label className="block text-[12px] font-medium text-saibyl-muted uppercase tracking-wide mb-2">What do you want to know</label>
                <textarea
                  value={predictionGoal}
                  onChange={(e) => setPredictionGoal(e.target.value)}
                  rows={4}
                  placeholder="In your own words. e.g. 'If I launch this on Reddit and Hacker News at $49 a month, what will solo founders object to — the price, the fact that it needs my API key, or that they could wire this up themselves?'"
                  className={`${inputClass} ${inputBg} resize-none`}
                />
                <p className="text-[11px] text-saibyl-muted/50 mt-1.5">{predictionGoal.length} characters</p>
              </div>
            </div>
          )}

          {/* ── Step 2: Platforms ── */}
          {step === 1 && (
            <div>
              <Hint>
                Each place behaves differently — X amplifies hot takes, Reddit rewards
                depth, LinkedIn buries anything negative. Picking more of them tells you
                more, and takes longer to run.
              </Hint>
              <p className="text-[14px] text-saibyl-muted mb-5">Where will this be seen? Each one is modelled on how that place actually behaves.</p>
              <div className="grid grid-cols-2 gap-3">
                {PLATFORMS.map((p) => {
                  const selected = selectedPlatforms.includes(p.id);
                  return (
                    <button
                      key={p.id}
                      onClick={() => togglePlatform(p.id)}
                      className={`text-left p-4 rounded-xl border transition-all duration-200 ${
                        selected
                          ? 'border-saibyl-gold/50 bg-saibyl-gold/10'
                          : 'border-white/[0.06] bg-white/[0.02] hover:border-white/[0.12]'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className={`font-medium text-[14px] ${selected ? 'text-saibyl-white' : 'text-saibyl-platinum'}`}>{p.name}</span>
                        {selected && <div className="w-5 h-5 rounded-full bg-saibyl-gold flex items-center justify-center"><svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" /></svg></div>}
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
              <Hint>
                Mixing groups is where the useful arguments come from. Put tech workers and
                finance people in the same room and they will disagree with each other —
                that disagreement is usually the thing you needed to see. You can also
                describe a group of your own.
              </Hint>
              <p className="text-[14px] text-saibyl-muted mb-5">Who is in the room? Pick as many ready-made groups as you like, or describe your own.</p>
              {packs.length === 0 ? (
                <div className="text-center py-8 text-saibyl-muted">Loading…</div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {/* Create Custom card */}
                  <button
                    onClick={() => setShowCustomModal(true)}
                    className="text-left p-4 rounded-xl border border-dashed border-saibyl-gold/30 bg-saibyl-gold/5 hover:border-saibyl-gold/50 hover:bg-saibyl-gold/10 transition-all duration-200"
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <svg className="w-5 h-5 text-saibyl-gold" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
                      <span className="font-medium text-[14px] text-saibyl-gold">Describe your own group</span>
                    </div>
                    <p className="text-[11px] text-saibyl-muted leading-relaxed">Tell us who they are and we&rsquo;ll build out a room of them — ages, jobs, temperaments, and how they behave online.</p>
                  </button>

                  {packs.map((pack) => {
                    const selected = selectedPacks.includes(pack.id);
                    return (
                      <button
                        key={pack.id}
                        onClick={() => togglePack(pack.id)}
                        className={`text-left p-4 rounded-xl border transition-all duration-200 ${
                          selected
                            ? 'border-saibyl-gold/50 bg-saibyl-gold/10'
                            : 'border-white/[0.06] bg-white/[0.02] hover:border-white/[0.12]'
                        }`}
                      >
                        <div className="flex items-center justify-between mb-1">
                          <span className={`font-medium text-[14px] ${selected ? 'text-saibyl-white' : 'text-saibyl-platinum'}`}>{pack.name}</span>
                          {selected && <div className="w-5 h-5 rounded-full bg-saibyl-gold flex items-center justify-center"><svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" /></svg></div>}
                        </div>
                        <p className="text-[11px] text-saibyl-muted leading-relaxed">{pack.description}</p>
                        <div className="flex items-center gap-2 mt-2">
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-white/[0.04] text-saibyl-muted">{pack.category}</span>
                          <span className="text-[10px] text-saibyl-muted">
                            {pack.archetype_count === 1
                              ? '1 kind of person'
                              : `${pack.archetype_count} kinds of people`}
                          </span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
              {/* ── Audiences this org already worked out and kept ── */}
              <div className="mt-6 pt-6 border-t border-white/[0.04]">
                <div className="flex items-baseline justify-between mb-1">
                  <h3 className="text-[14px] font-medium text-saibyl-platinum">
                    Audiences you&rsquo;ve saved
                  </h3>
                  <button
                    type="button"
                    onClick={() => navigate('/app/audiences')}
                    className="text-[12px] text-saibyl-gold hover:underline"
                  >
                    Manage
                  </button>
                </div>
                <p className="text-[12px] text-saibyl-muted mb-3 leading-relaxed">
                  Buyers Saibyl worked out for one of your products and you kept. Pick as many
                  as you like — the run mixes them in with anything selected above.
                </p>

                {orgPacksError ? (
                  <p className="text-[12px] text-saibyl-muted">
                    {orgPacksError} Nothing is listed here because we don&rsquo;t know what you
                    have, not because you have none.
                  </p>
                ) : orgPacks.length === 0 ? (
                  <p className="text-[12px] text-saibyl-muted">
                    Nothing saved yet. Work out your buyers on the next step and you can keep
                    them for every other product you build.
                  </p>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {orgPacks.map((pack) => {
                      const selected = selectedPacks.includes(pack.id);
                      return (
                        <button
                          key={pack.id}
                          onClick={() => togglePack(pack.id)}
                          className={`text-left p-4 rounded-xl border transition-all duration-200 ${
                            selected
                              ? 'border-saibyl-gold/50 bg-saibyl-gold/10'
                              : 'border-white/[0.06] bg-white/[0.02] hover:border-white/[0.12]'
                          }`}
                        >
                          <div className="flex items-center justify-between gap-2 mb-1">
                            <span className={`font-medium text-[14px] ${selected ? 'text-saibyl-white' : 'text-saibyl-platinum'}`}>{pack.name}</span>
                            {selected && <div className="w-5 h-5 rounded-full bg-saibyl-gold flex items-center justify-center shrink-0"><svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" /></svg></div>}
                          </div>
                          {pack.description && (
                            <p className="text-[11px] text-saibyl-muted leading-relaxed line-clamp-2">{pack.description}</p>
                          )}
                          {/* Shown only when the server sent a count. A zero
                              here would read as an audience containing nobody. */}
                          {pack.archetype_count != null && (
                            <span className="block text-[10px] text-saibyl-muted mt-2">
                              {pack.archetype_count} group{pack.archetype_count === 1 ? '' : 's'} of people
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>

              <p className="text-[12px] text-saibyl-muted mt-4">{selectedPacks.length} group{selectedPacks.length !== 1 ? 's' : ''} selected</p>

              {/* Custom Persona Modal */}
              {showCustomModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
                  <motion.div
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    className="glass rounded-2xl p-8 w-full max-w-lg mx-4"
                  >
                    <h3 className="text-[18px] font-semibold text-saibyl-white mb-1">Describe your own group</h3>
                    <p className="text-[12px] text-saibyl-muted mb-6">Tell us who these people are and we&rsquo;ll build out a room of them — the different kinds of person in it, their ages, jobs and temperaments, and how they behave online.</p>

                    <div className="space-y-4">
                      <div>
                        <label className="block text-[12px] font-medium text-saibyl-muted uppercase tracking-wide mb-2">What would you call them?</label>
                        <input
                          type="text"
                          value={customName}
                          onChange={(e) => setCustomName(e.target.value)}
                          placeholder="e.g. Solo SaaS founders, Agency owners, Heads of RevOps"
                          className={`${inputClass} ${inputBg}`}
                        />
                      </div>
                      <div>
                        <label className="block text-[12px] font-medium text-saibyl-muted uppercase tracking-wide mb-2">Who are they?</label>
                        <textarea
                          value={customDesc}
                          onChange={(e) => setCustomDesc(e.target.value)}
                          rows={4}
                          placeholder="What they do, what drives them, how they behave online, what they already pay for. The more you write here, the more like real people they come out."
                          className={`${inputClass} ${inputBg} resize-none`}
                        />
                      </div>
                    </div>

                    <div className="flex justify-end gap-3 mt-6">
                      <button
                        onClick={() => { setShowCustomModal(false); setCustomName(''); setCustomDesc(''); }}
                        className="px-5 py-2.5 text-[14px] text-saibyl-muted hover:text-saibyl-platinum transition-colors"
                        disabled={creatingCustom}
                      >
                        Cancel
                      </button>
                      <button
                        onClick={handleCreateCustomPack}
                        disabled={creatingCustom || !customName.trim() || !customDesc.trim()}
                        className="px-6 py-2.5 rounded-xl bg-[#C9A227] text-[#0A0F1C] font-medium text-sm disabled:opacity-50 transition-all hover:bg-[#D4AF37] hover:-translate-y-0.5"
                      >
                        {creatingCustom ? 'Building…' : 'Build this group'}
                      </button>
                    </div>
                  </motion.div>
                </div>
              )}
            </div>
          )}

          {/* ── Step 4: Lens ── */}
          {step === 3 && (
            <div>
              {/* Written to the reader, not to the team. This said "a run with no
                  lens behaves exactly as it did before, which is what every run
                  made before this feature existed did" — a sentence about our
                  release history, addressed to somebody who has no before. */}
              <Hint>
                This step is optional, and it is the one that makes the answers about
                your product rather than about the topic. Tell us where you are with
                it and we&rsquo;ll read what you&rsquo;ve uploaded to work out who your
                buyers are and who will argue against you. Skip it and the run just
                uses the groups you picked on the last step.
              </Hint>
              <FounderLensStep
                projectId={projectId}
                platforms={selectedPlatforms}
                value={founder}
                onChange={setFounder}
              />
            </div>
          )}

          {/* ── Step 5: Configure ── */}
          {step === 4 && (
            <div className="space-y-6">
              <Hint>
                More people narrow the range on every finding; more rounds let
                objections spread between them. Both cost credits, and the exact
                cost is shown below before you commit to anything. The numbers you
                set here are the numbers that get built — type an exact figure into
                the box if the slider will not land on it.
              </Hint>

              <RunConfigurator
                shape={shape}
                platformCount={selectedPlatforms.length}
                onChange={setShape}
                onQuote={handleQuote}
              />

              <div>
                <label className="block text-[12px] font-medium text-saibyl-muted uppercase tracking-wide mb-2">Timezone</label>
                <select
                  value={timezone}
                  onChange={(e) => setTimezone(e.target.value)}
                  className={`${inputClass} ${inputBg} appearance-none`}
                  style={{ colorScheme: 'dark' }}
                >
                  {['America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles', 'UTC', 'Europe/London', 'Europe/Berlin', 'Asia/Tokyo', 'Asia/Shanghai'].map((tz) => (
                    <option key={tz} value={tz} className="bg-saibyl-deep text-saibyl-platinum">{tz}</option>
                  ))}
                </select>
              </div>
            </div>
          )}

          {/* ── Step 6: Review ── */}
          {step === LAST_STEP && (
            <div>
              <h2 className="text-[18px] font-semibold text-saibyl-platinum mb-5">One last look</h2>
              {/* Every row here is something the reader chose. A row with
                  nothing behind it is dropped rather than filled with an em
                  dash: five of these used to render "—", which reads as a
                  setting whose value is a dash instead of a setting that was
                  never reached.

                  `capitalize` also came off the value: it is on the shared span
                  and it title-cased whole sentences, so the product name and
                  "One — add more on the run's page before you start it" came
                  out with a capital on every word. The one value that wanted it
                  is capitalised where it is built. */}
              <div className="space-y-3">
                {(
                  [
                    ['Name', name.trim()],
                    ['Product', projects.find((p) => p.id === projectId)?.name ?? ''],
                    ['Your question', predictionGoal.trim()],
                    [
                      'Where',
                      selectedPlatforms
                        .map((id) => PLATFORMS.find((p) => p.id === id)?.name || id)
                        .join(', ') || 'Twitter / X',
                    ],
                    [
                      'Groups picked',
                      selectedPacks.length === 1 ? '1 group' : `${selectedPacks.length} groups`,
                    ],
                    ['Where you are', founder.stage ? sentenceCase(founder.stage) : ''],
                    [
                      'Your own buyers',
                      founder.icpProfileId ? 'Worked out from what you uploaded' : '',
                    ],
                    [
                      'Arguing against you',
                      founder.icpProfileId
                        ? `${(founder.adversarialShare * 100).toFixed(0)}% of the room`
                        : '',
                    ],
                    ['People in the room', String(shape.agent_count)],
                    ['Rounds', String(shape.rounds)],
                    [
                      'Messages tested',
                      'One — add more on the run’s page before you start it',
                    ],
                    ['Report depth', sentenceCase(shape.depth)],
                    ['Timezone', timezone],
                  ] as [string, string][]
                )
                  .filter(([, value]) => value !== '')
                  .map(([label, value]) => (
                    <div key={label} className="flex items-start gap-4 py-2 border-b border-white/[0.04] last:border-0">
                      <span className="text-[13px] text-saibyl-muted w-36 shrink-0">{label}</span>
                      <span className="text-[13px] text-saibyl-platinum flex-1">{value}</span>
                    </div>
                  ))}
              </div>

              {/* Re-priced here rather than echoing the figure from step 4: a
                  run is never started without its current cost on screen. */}
              <div className="mt-6">
                <RunConfigurator
                  shape={shape}
                  platformCount={selectedPlatforms.length}
                  onChange={setShape}
                  onQuote={handleQuote}
                  readOnly
                />
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
            {step < LAST_STEP ? (
              <button
                onClick={() => setStep((s) => s + 1)}
                disabled={!canNext()}
                className="bg-saibyl-gold text-white px-6 py-2.5 rounded-xl text-[14px] font-medium hover:bg-[#4B4FDE] disabled:opacity-30 transition-all"
              >
                Next →
              </button>
            ) : (
              /* The reason a run cannot start is written next to the button
                 rather than hidden in a `title`. A tooltip is no explanation on
                 a touch screen and invisible in a screenshot, and this is the
                 last screen before money is spent. */
              <div className="flex items-center gap-3">
                {quoteError && (
                  <span className="text-[12px] text-saibyl-warning">
                    {quoteError} Nothing can start until we can tell you what it costs.
                  </span>
                )}
                <button
                  onClick={handleSubmit}
                  disabled={submitting || !!quoteError}
                  className="px-8 py-2.5 rounded-xl bg-saibyl-gold text-saibyl-void font-semibold text-[14px] disabled:opacity-50 transition-all hover:bg-saibyl-gold-hover hover:-translate-y-0.5 hover:shadow-[0_0_20px_rgba(201,162,39,0.3)]"
                >
                  {submitting ? 'Starting…' : 'Start this run →'}
                </button>
              </div>
            )}
          </div>
        </motion.div>
      </div>
    </div>
  );
}
