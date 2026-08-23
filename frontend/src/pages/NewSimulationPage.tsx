import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Lightbulb } from 'lucide-react';
import api, { unwrapList } from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { listPacks } from '@/lib/packs';
import RunConfigurator, { type RunShape } from '@/components/RunConfigurator';
import FounderLensStep, { type FounderConfig } from '@/components/founder/FounderLensStep';
import {
  Action,
  Card,
  Eyebrow,
  Ground,
  Notice,
  PageHeader,
  Rise,
  dealDelayMs,
} from '@/components/design';
import type { FounderStage } from '@/lib/founder';
import type { OrgPersonaPack, PersonaPack, Project } from '@/types';

/**
 * Setting a run up, in six steps.
 *
 * Two things were wrong here beyond the colours, and both were founder rules
 * rather than taste:
 *
 * 1. **Six `disabled` attributes.** Back on step 1, Next on an incomplete step,
 *    Cancel and Build inside the custom-audience modal, and Start on the review
 *    step. Every one of them was a grey rectangle with no sentence beside it —
 *    the exact rendering the standing rule forbids: "a control either runs and
 *    states what its answer will be missing, or it is blocked with the reason
 *    and the button that unblocks it." There is no third rendering, so all six
 *    are gone. Where a step genuinely cannot be left, the control is replaced
 *    by a violet `Notice tone="blocked"` that says what is missing.
 * 2. **Twenty-eight legacy dark-theme aliases** — `saibyl-void`, `saibyl-white`,
 *    `saibyl-platinum`, `saibyl-gold`. They still resolve, because the token
 *    file remapped them to light values when the theme flipped, which is
 *    precisely why nobody noticed this page had never been converted.
 */

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

/* The five stage ids, mirroring `FounderStage` in lib/founder.ts. The specs
   themselves are fetched, not copied — this list exists only to validate the
   `founder_stage` query parameter the product rail passes along, so an
   unrecognised value is dropped rather than sent to the API. */
const FOUNDER_STAGES: readonly FounderStage[] = [
  'concept_validation',
  'pre_launch_positioning',
  'launch_gtm',
  'growth',
  'fundraise',
];

/* Six steps. The heading counts them out of this array rather than restating
   the number — it read "in 5 steps" above six of them for as long as the sixth
   has existed, and a hand-written count is a second place for the truth to
   live. */
const STEPS = ['Setup', 'Where', 'Who reacts', 'Your buyers', 'Size', 'Review'];
const LAST_STEP = STEPS.length - 1;

const inputClass = 'w-full rounded-xl px-4 py-3 text-[14px] text-saibyl-ink placeholder:text-saibyl-muted/70 focus:outline-none focus:border-saibyl-blue focus:ring-2 focus:ring-saibyl-blue/20 transition';
const inputBg = 'bg-white border border-saibyl-border-light';

/** The uppercase caption above a field. Not an `Eyebrow`: the dot marks where a
    *block* begins, and dotting nine form labels in a row turns a dense form
    into a constellation — which the canvas's density constraint rules out. */
const fieldLabel = 'block text-[12px] font-medium text-saibyl-muted uppercase tracking-wide mb-2';

/** A selectable tile — a platform, a ready-made group, a saved audience. */
function tileClass(selected: boolean): string {
  return `text-left p-4 rounded-xl border transition-all duration-200 ${
    selected
      ? 'border-saibyl-blue/45 bg-saibyl-blue/[0.07]'
      : 'border-saibyl-border bg-white hover:border-saibyl-border-light'
  }`;
}

/** The tick on a chosen tile. Blue, because blue is what "chosen" means here. */
function Tick() {
  return (
    <div className="w-5 h-5 rounded-full bg-saibyl-blue flex items-center justify-center shrink-0">
      <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
      </svg>
    </div>
  );
}

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

/**
 * Advice, and deliberately not a `Notice`.
 *
 * The three notice tones each report a *state* — blocked, thinner, live — and a
 * hint reports none of them. It was amber (`saibyl-gold`, the legacy alias for
 * blue), which read as the artboard's "this will run, but thinner" warning on
 * every step of a wizard where nothing was wrong.
 */
function Hint({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2.5 px-4 py-3 rounded-xl bg-saibyl-blue/[0.05] border border-saibyl-blue/15 mb-5">
      <Lightbulb className="w-3.5 h-3.5 text-saibyl-blue mt-0.5 shrink-0" />
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
  const [quoteError, setQuoteError] = useState('');

  // Step 4 — the Founder lens. A run with no stage and no ICP is an unlensed
  // run, which is what every simulation made before Phase 2 was: `lens` stays
  // null rather than being defaulted to 'founder', because a lens the user
  // never chose is an attribute nobody recorded.
  const [founder, setFounder] = useState<FounderConfig>({
    stage: null,
    icpProfileId: null,
    adversarialShare: 0,
    // False until the founder moves the share slider themselves. Never sent to
    // the API — the submit payload below picks its fields by name.
    shareSetByUser: false,
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
    /* The product rail's "start a run" link carries the moment the founder
       just picked (`?founder_stage=…`) so they are not asked to pick it twice.
       Adopted only when it names a real stage. The stage-default share is then
       applied by the buyers step exactly as if the stage had been clicked
       there — its untouched-share effect adopts the default, and a hand-set
       share is never overwritten. */
    const stageParam = searchParams.get('founder_stage');
    if (stageParam && (FOUNDER_STAGES as readonly string[]).includes(stageParam)) {
      setFounder((prev) => (prev.stage === stageParam ? prev : { ...prev, stage: stageParam }));
    }
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

  /*
    Why this step cannot be left, when it cannot — and the control that fixes
    it, when one exists on another screen.

    This is the whole of the no-grey-button rule in one value. Either `blocked`
    is null and the forward control renders, or it is set and the violet block
    renders in the control's place. There is no state in which a founder sees a
    dead rectangle and has to guess.
  */
  const blocked: { title: string; body: string; action?: React.ReactNode } | null =
    step === 0 && !canNext()
      ? {
          title: 'Three things before we can go on',
          body: 'Name this run, say which product it is about, and write down what you want to know. All three go into the room with your message — without them we would be guessing at the question as well as the answer.',
          action:
            projects.length === 0 ? (
              <Action kind="quiet" onClick={() => navigate('/app/projects')}>
                Add your product first
              </Action>
            ) : undefined,
        }
      : step === LAST_STEP && quoteError
        ? {
            title: 'This run can’t start yet',
            body: `${quoteError} Nothing starts until we can tell you what it will cost you.`,
          }
        : null;

  return (
    <Ground className="p-6 lg:p-8 min-h-full">
      <div className="max-w-3xl mx-auto">
        <Rise>
          <PageHeader
            eyebrow="New run"
            title="Start a new run"
            mark={`${STEPS.length} steps`}
            phrase="Set the room, then find out what it says back."
          >
            <p>
              A run puts one message in front of one room of buyers and reports
              what they push back on. These {STEPS.length} steps decide who is in
              the room, where they see it and how long they argue &mdash; and the
              last one shows you the exact cost before anything starts.
            </p>
          </PageHeader>
        </Rise>

        {/* Step indicator */}
        <div className="flex items-center mt-7 mb-6 gap-1">
          {STEPS.map((label, i) => (
            <div key={label} className="flex items-center">
              <div className={`w-7 h-7 sm:w-8 sm:h-8 rounded-full flex items-center justify-center text-[12px] font-mono font-bold transition-colors ${
                i < step
                  ? 'bg-saibyl-positive text-white'
                  : i === step
                    ? 'bg-saibyl-blue text-white shadow-[0_6px_14px_rgba(40,108,240,0.24)]'
                    : 'bg-[#14294a]/[0.04] text-saibyl-muted'
              }`}>
                {i < step ? '✓' : i + 1}
              </div>
              <span className={`ml-1.5 text-[13px] hidden sm:inline whitespace-nowrap ${i <= step ? 'text-saibyl-ink' : 'text-saibyl-muted'}`}>{label}</span>
              {i < STEPS.length - 1 && <div className={`w-3 sm:w-8 h-px mx-1 sm:mx-2 ${i < step ? 'bg-saibyl-positive/40' : 'bg-saibyl-border'}`} />}
            </div>
          ))}
        </div>

        {error && (
          <div className="mb-4 px-4 py-3 rounded-xl bg-saibyl-negative/10 border border-saibyl-negative/20 text-saibyl-negative text-sm">{error}</div>
        )}

        {/* The one panel this screen is about — `carries="stage"`, once, and it
            re-rises whenever the step changes. Keyed on `step` exactly as the
            framer-motion wrapper it replaces was, so the subtree remounts the
            same way; what changed is that the movement is now the artboard's
            own keyframe and collapses under `prefers-reduced-motion`. */}
        <Rise key={step} delayMs={dealDelayMs(1)}>
          <Card carries="stage" className="p-8">
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
                  <label className={fieldLabel}>Name this run</label>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. New pricing page, before launch"
                    className={`${inputClass} ${inputBg}`}
                  />
                </div>
                <div>
                  <label className={fieldLabel}>Product</label>
                  {projects.length === 0 ? (
                    <div className={`${inputClass} ${inputBg} text-saibyl-muted`}>
                      Nothing here yet — <button onClick={() => navigate('/app/projects')} className="text-saibyl-blue hover:underline">add your product first</button>
                    </div>
                  ) : (
                    <div className="relative">
                      <select
                        value={projectId}
                        onChange={(e) => setProjectId(e.target.value)}
                        className={`${inputClass} ${inputBg} appearance-none cursor-pointer`}
                        style={{ colorScheme: 'light' }}
                      >
                        <option value="" className="bg-white text-saibyl-muted">Choose a product…</option>
                        {projects.map((p) => (
                          <option key={p.id} value={p.id} className="bg-white text-saibyl-ink">{p.name}</option>
                        ))}
                      </select>
                      <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-saibyl-muted">
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
                      </div>
                    </div>
                  )}
                </div>
                <div>
                  <label className={fieldLabel}>What do you want to know</label>
                  <textarea
                    value={predictionGoal}
                    onChange={(e) => setPredictionGoal(e.target.value)}
                    rows={4}
                    placeholder="In your own words. e.g. 'If I launch this on Reddit and Hacker News at $49 a month, what will solo founders object to — the price, the fact that it needs my API key, or that they could wire this up themselves?'"
                    className={`${inputClass} ${inputBg} resize-none`}
                  />
                  <p className="text-[11px] text-saibyl-muted mt-1.5">{predictionGoal.length} characters</p>
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
                      <button key={p.id} onClick={() => togglePlatform(p.id)} className={tileClass(selected)}>
                        <div className="flex items-center justify-between">
                          <span className="font-medium text-[14px] text-saibyl-ink">{p.name}</span>
                          {selected && <Tick />}
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
                      className="text-left p-4 rounded-xl border border-dashed border-saibyl-blue/35 bg-saibyl-blue/[0.05] hover:border-saibyl-blue/55 hover:bg-saibyl-blue/[0.09] transition-all duration-200"
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <svg className="w-5 h-5 text-saibyl-blue" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
                        <span className="font-medium text-[14px] text-saibyl-blue">Describe your own group</span>
                      </div>
                      <p className="text-[11px] text-saibyl-muted leading-relaxed">Tell us who they are and we&rsquo;ll build out a room of them — ages, jobs, temperaments, and how they behave online.</p>
                    </button>

                    {packs.map((pack) => {
                      const selected = selectedPacks.includes(pack.id);
                      return (
                        <button key={pack.id} onClick={() => togglePack(pack.id)} className={tileClass(selected)}>
                          <div className="flex items-center justify-between mb-1">
                            <span className="font-medium text-[14px] text-saibyl-ink">{pack.name}</span>
                            {selected && <Tick />}
                          </div>
                          <p className="text-[11px] text-saibyl-muted leading-relaxed">{pack.description}</p>
                          <div className="flex items-center gap-2 mt-2">
                            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#14294a]/[0.04] text-saibyl-muted">{pack.category}</span>
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
                <div className="mt-6 pt-6 border-t border-saibyl-border">
                  <div className="flex items-baseline justify-between mb-1">
                    <h3 className="text-[14px] font-medium text-saibyl-ink">
                      Audiences you&rsquo;ve saved
                    </h3>
                    <button
                      type="button"
                      onClick={() => navigate('/app/audiences')}
                      className="text-[12px] text-saibyl-blue hover:underline"
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
                      Nothing saved so far. Work out your buyers on the next step and you can keep
                      them for every other product you build.
                    </p>
                  ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      {orgPacks.map((pack) => {
                        const selected = selectedPacks.includes(pack.id);
                        return (
                          <button key={pack.id} onClick={() => togglePack(pack.id)} className={tileClass(selected)}>
                            <div className="flex items-center justify-between gap-2 mb-1">
                              <span className="font-medium text-[14px] text-saibyl-ink">{pack.name}</span>
                              {selected && <Tick />}
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
                  <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#14294a]/40 backdrop-blur-sm">
                    <Rise className="w-full max-w-lg mx-4">
                      {/* `meaning`, not `stage`: while this is open it sits over
                          the step panel, and two stages on screen at once means
                          neither of them is the subject. */}
                      <Card carries="meaning" className="p-8">
                        <h3 className="text-[18px] font-semibold text-saibyl-ink mb-1">Describe your own group</h3>
                        <p className="text-[12px] text-saibyl-muted mb-6">Tell us who these people are and we&rsquo;ll build out a room of them — the different kinds of person in it, their ages, jobs and temperaments, and how they behave online.</p>

                        <div className="space-y-4">
                          <div>
                            <label className={fieldLabel}>What would you call them?</label>
                            <input
                              type="text"
                              value={customName}
                              onChange={(e) => setCustomName(e.target.value)}
                              placeholder="e.g. Solo SaaS founders, Agency owners, Heads of RevOps"
                              className={`${inputClass} ${inputBg}`}
                            />
                          </div>
                          <div>
                            <label className={fieldLabel}>Who are they?</label>
                            <textarea
                              value={customDesc}
                              onChange={(e) => setCustomDesc(e.target.value)}
                              rows={4}
                              placeholder="What they do, what drives them, how they behave online, what they already pay for. The more you write here, the more like real people they come out."
                              className={`${inputClass} ${inputBg} resize-none`}
                            />
                          </div>
                        </div>

                        <div className="flex justify-end items-center gap-3 mt-6">
                          <button
                            onClick={() => { setShowCustomModal(false); setCustomName(''); setCustomDesc(''); }}
                            className="px-5 py-2.5 text-[14px] text-saibyl-muted hover:text-saibyl-ink transition-colors"
                          >
                            Cancel
                          </button>
                          {creatingCustom ? (
                            /* Announced, not disabled. A `<span>` cannot be
                               clicked twice into two rooms, and it says what is
                               happening instead of going grey. */
                            <Action as="span" aria-live="polite" className="opacity-70">
                              Building…
                            </Action>
                          ) : customName.trim() && customDesc.trim() ? (
                            <Action onClick={handleCreateCustomPack}>Build this group</Action>
                          ) : (
                            <span className="text-[12px] text-saibyl-violet max-w-[16rem] leading-relaxed">
                              Both boxes need something in them before we can build anybody.
                            </span>
                          )}
                        </div>
                      </Card>
                    </Rise>
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

                {/* A timezone picker stood here, and the Review step listed the
                    answer back to the founder among the settings he was about to
                    pay for.

                    **It changed nothing, anywhere.** `POST /simulations` never
                    sent it — `CreateSimulationBody` has no such field — so it
                    was not stored, and the only thing in the backend that reads
                    a run's timezone is `json_exporter`, which therefore always
                    emitted the column default. Nothing in the swarm has a
                    concept of time of day at all.

                    Wiring it through would have made the export truthful and
                    left the control just as false, because the review screen's
                    real claim is "your run happens in this timezone" and no
                    code makes that true. So it is gone rather than plumbed.
                    The `simulations.timezone` column and the exporter line stay
                    — a timezone-aware run is a feature to build, and this comes
                    back with it. */}
              </div>
            )}

            {/* ── Step 6: Review ── */}
            {step === LAST_STEP && (
              <div>
                <Eyebrow>Review</Eyebrow>
                <h2 className="text-[18px] font-semibold text-saibyl-ink mt-2 mb-5">One last look</h2>
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
                      // No 'Timezone' row. The review step's job is to list what
                      // the founder is paying for, and a setting that reaches
                      // neither the request nor the run is the one line here
                      // that was not true.
                    ] as [string, string][]
                  )
                    .filter(([, value]) => value !== '')
                    .map(([label, value]) => (
                      <div key={label} className="flex items-start gap-4 py-2 border-b border-saibyl-border last:border-0">
                        <span className="text-[13px] text-saibyl-muted w-36 shrink-0">{label}</span>
                        <span className="text-[13px] text-saibyl-ink flex-1">{value}</span>
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

            {/* ── Navigation ──
                The reason a step cannot be left is written where the control
                would have been, rather than hidden in a `title` or spelled as a
                grey rectangle. A tooltip is no explanation on a touch screen and
                invisible in a screenshot, and the last of these is the screen
                before money is spent. */}
            <div className="mt-8 pt-5 border-t border-saibyl-border">
              {blocked && (
                <Notice
                  tone="blocked"
                  title={blocked.title}
                  action={blocked.action}
                  className="mb-4"
                >
                  {blocked.body}
                </Notice>
              )}
              <div className="flex justify-between items-center gap-4">
                {step > 0 ? (
                  <button
                    onClick={() => setStep((s) => s - 1)}
                    className="px-5 py-2.5 text-[14px] text-saibyl-muted hover:text-saibyl-ink transition-colors"
                  >
                    ← Back
                  </button>
                ) : (
                  /* Nothing to go back to on step 1, so there is nothing here.
                     The spacer keeps the forward control on the right. */
                  <span />
                )}

                {/* Exactly one gradient action is ever on screen: Next while
                    there are steps left, Start on the last one. They are
                    mutually exclusive, so the screen never carries two. */}
                {blocked ? null : step < LAST_STEP ? (
                  <Action onClick={() => setStep((s) => s + 1)}>Next →</Action>
                ) : submitting ? (
                  <Action as="span" aria-live="polite" className="opacity-70">
                    Starting…
                  </Action>
                ) : (
                  <Action onClick={handleSubmit}>Start this run →</Action>
                )}
              </div>
            </div>
          </Card>
        </Rise>
      </div>
    </Ground>
  );
}
