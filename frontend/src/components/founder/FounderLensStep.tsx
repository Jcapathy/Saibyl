import { useEffect, useState } from 'react';
import { AlertTriangle, Loader2, Sparkles } from 'lucide-react';
import api from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import type { ICPProfile, StageSpec } from '@/lib/founder';

export interface FounderConfig {
  stage: string | null;
  icpProfileId: string | null;
  adversarialShare: number;
}

/**
 * Stage, synthesized ICP, and the adversarial share — the Founder-lens intake.
 *
 * Three things this screen is responsible for saying out loud, because they are
 * the three ways a founder can get a confidently wrong answer:
 *
 * 1. **What the stage cannot conclude.** Shown before the run, not buried in the
 *    report afterwards. A concept-validation run has no product to adopt.
 * 2. **That the ICP is a proposal.** Synthesis reads the founder's material and
 *    is often wrong about who signs the cheque. The gaps it reports are the
 *    honest part.
 * 3. **What the adversarial share does to the headline.** Past a certain point
 *    the run measures the share, not the market.
 */
export default function FounderLensStep({
  projectId,
  platforms,
  value,
  onChange,
}: {
  projectId: string;
  platforms: string[];
  value: FounderConfig;
  onChange: (next: FounderConfig) => void;
}) {
  const [stages, setStages] = useState<StageSpec[]>([]);
  const [profiles, setProfiles] = useState<ICPProfile[]>([]);
  const [synthesizing, setSynthesizing] = useState(false);
  const [synthCost, setSynthCost] = useState<{ credits_required: number; message: string } | null>(
    null,
  );
  const [error, setError] = useState('');

  useEffect(() => {
    api.get('/simulations/founder-stages').then((r) => setStages(r.data)).catch(() => {});
    api.get('/icp/estimate').then((r) => setSynthCost(r.data)).catch(() => {});
  }, []);

  useEffect(() => {
    if (!projectId) return;
    api
      .get('/icp', { params: { project_id: projectId } })
      .then((r) => setProfiles(r.data))
      .catch(() => {});
  }, [projectId]);

  const stage = stages.find((s) => s.id === value.stage) ?? null;
  const profile = profiles.find((p) => p.id === value.icpProfileId) ?? null;

  const selectStage = (spec: StageSpec) => {
    // Adopt the stage's audience default. Concept validation is 0% and growth
    // is 40%, and that difference is the substance of stage-awareness — a
    // picker that changed the label and nothing else would be decoration.
    onChange({ ...value, stage: spec.id, adversarialShare: spec.default_adversarial_share });
  };

  const synthesize = async () => {
    if (!projectId) return;
    setSynthesizing(true);
    setError('');
    try {
      const { data } = await api.post('/icp/synthesize', {
        project_id: projectId,
        platforms,
        adversarial: true,
        adversarial_share: value.adversarialShare,
      });
      setProfiles((prev) => [data, ...prev]);
      onChange({ ...value, icpProfileId: data.id });
    } catch (err) {
      setError(getErrorMessage(err, 'ICP synthesis failed'));
    } finally {
      setSynthesizing(false);
    }
  };

  return (
    <div className="space-y-7">
      {error && (
        <div className="px-4 py-3 rounded-xl bg-saibyl-negative/10 border border-saibyl-negative/20 text-saibyl-negative text-[13px]">
          {error}
        </div>
      )}

      {/* ── Stage ─────────────────────────────────────────────────── */}
      <div>
        <label className="block text-[12px] font-medium text-saibyl-muted uppercase tracking-wide mb-3">
          Stage
        </label>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {stages.map((spec) => {
            const selected = spec.id === value.stage;
            return (
              <button
                key={spec.id}
                type="button"
                onClick={() => selectStage(spec)}
                className={`text-left p-4 rounded-xl border transition-all duration-200 ${
                  selected
                    ? 'border-saibyl-gold/50 bg-saibyl-gold/10'
                    : 'border-white/[0.06] bg-white/[0.02] hover:border-white/[0.12]'
                }`}
              >
                <span
                  className={`font-medium text-[14px] ${selected ? 'text-saibyl-white' : 'text-saibyl-platinum'}`}
                >
                  {spec.label}
                </span>
                <p className="text-[11px] text-saibyl-muted mt-1 leading-relaxed">{spec.question}</p>
              </button>
            );
          })}
        </div>
      </div>

      {stage && (
        <>
          <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
            <p className="text-[11px] font-medium text-saibyl-muted uppercase tracking-wide mb-2">
              Bring
            </p>
            <ul className="space-y-1">
              {stage.expected_inputs.map((input) => (
                <li key={input} className="text-[12px] text-saibyl-platinum">
                  — {input}
                </li>
              ))}
            </ul>
          </div>

          {/* The honesty block. Shown before the run rather than as a footnote
              in the report, because the point of stating a limit is to stop
              somebody asking a question the run cannot answer. */}
          <div className="rounded-xl border border-saibyl-gold/20 bg-saibyl-gold/[0.06] p-4">
            <div className="flex items-start gap-2.5">
              <AlertTriangle className="w-3.5 h-3.5 text-saibyl-gold mt-0.5 shrink-0" />
              <div>
                <p className="text-[12px] font-medium text-saibyl-gold mb-1.5">
                  What this run will not be able to tell you
                </p>
                <ul className="space-y-1">
                  {stage.cannot_conclude.map((limit) => (
                    <li key={limit} className="text-[11px] text-saibyl-muted leading-relaxed">
                      — {limit}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </>
      )}

      {/* ── ICP ───────────────────────────────────────────────────── */}
      <div>
        <label className="block text-[12px] font-medium text-saibyl-muted uppercase tracking-wide mb-2">
          Audience
        </label>
        <p className="text-[12px] text-saibyl-muted mb-3 leading-relaxed">
          Synthesis reads the documents on this project — PRD, landing page, deck, pricing — and
          proposes the buyers. It is a proposal: correct it before you run against it.
        </p>

        {profiles.length > 0 && (
          <div className="space-y-2 mb-3">
            {profiles.map((p) => {
              const selected = p.id === value.icpProfileId;
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => onChange({ ...value, icpProfileId: selected ? null : p.id })}
                  className={`w-full text-left p-4 rounded-xl border transition-all ${
                    selected
                      ? 'border-saibyl-gold/50 bg-saibyl-gold/10'
                      : 'border-white/[0.06] bg-white/[0.02] hover:border-white/[0.12]'
                  }`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-medium text-[14px] text-saibyl-platinum truncate">
                      {p.name}
                    </span>
                    <span className="text-[10px] text-saibyl-muted whitespace-nowrap">
                      {p.profile.archetypes.length} buyers ·{' '}
                      {p.profile.adversarial.length} incumbent-aligned
                    </span>
                  </div>
                  <p className="text-[11px] text-saibyl-muted mt-1 leading-relaxed line-clamp-2">
                    {p.product_summary}
                  </p>
                  {p.profile.gaps.length > 0 && (
                    <p className="text-[10px] text-saibyl-gold/80 mt-2">
                      {p.profile.gaps.length} thing
                      {p.profile.gaps.length === 1 ? '' : 's'} your material never says
                    </p>
                  )}
                </button>
              );
            })}
          </div>
        )}

        <button
          type="button"
          onClick={synthesize}
          disabled={!projectId || synthesizing}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-dashed border-saibyl-gold/30 bg-saibyl-gold/5 hover:border-saibyl-gold/50 hover:bg-saibyl-gold/10 disabled:opacity-40 transition-all text-[13px] text-saibyl-gold"
        >
          {synthesizing ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Sparkles className="w-4 h-4" />
          )}
          {synthesizing ? 'Reading your documents…' : 'Synthesize an ICP from this project'}
        </button>
        {synthCost && (
          <p className="text-[11px] text-saibyl-muted mt-2">
            {synthCost.credits_required.toLocaleString()} credits. Charged once per synthesis, not
            per run — the ICP is reused across every run in this project.
          </p>
        )}
      </div>

      {/* ── Adversarial share ─────────────────────────────────────── */}
      <div>
        <div className="flex items-baseline justify-between mb-2">
          <label className="text-[12px] font-medium text-saibyl-muted uppercase tracking-wide">
            Incumbent-aligned share
          </label>
          <span className="text-[13px] font-mono text-saibyl-platinum">
            {(value.adversarialShare * 100).toFixed(0)}%
          </span>
        </div>
        <input
          type="range"
          min={0}
          max={50}
          step={5}
          value={Math.round(value.adversarialShare * 100)}
          onChange={(e) =>
            onChange({ ...value, adversarialShare: Number(e.target.value) / 100 })
          }
          disabled={!value.icpProfileId}
          className="w-full accent-saibyl-gold disabled:opacity-40"
        />
        <p className="text-[11px] text-saibyl-muted mt-2 leading-relaxed">
          {!value.icpProfileId ? (
            <>
              Needs a synthesized ICP. The incumbent-aligned cohort is built from your uploaded
              material; the built-in persona packs have no adversarial archetypes for a share to
              apply to.
            </>
          ) : (
            <>
              These agents argue against adopting by construction, so they pull the headline
              negative on purpose. The report separates them from buyers and labels them synthetic
              everywhere it appears. The ceiling is 50%: past half the swarm, the headline measures
              the share you chose rather than the market.
            </>
          )}
        </p>
        {profile && profile.profile.competitors.some((c) => c.mentioned_in.length > 0) && (
          <p className="text-[11px] text-saibyl-muted mt-2">
            Grounded competitors:{' '}
            {profile.profile.competitors
              .filter((c) => c.mentioned_in.length > 0)
              .map((c) => c.name)
              .join(', ')}
            . Names appear only because your uploaded material named them.
          </p>
        )}
      </div>
    </div>
  );
}
