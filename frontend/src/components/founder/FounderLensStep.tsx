import { useEffect, useState } from 'react';
import { AlertTriangle, Loader2, Sparkles } from 'lucide-react';
import api, { unwrapList } from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import AudienceReview from './AudienceReview';
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
 * 2. **That the audience is a proposal.** Synthesis reads the founder's material
 *    and is often wrong about who signs the cheque, so `AudienceReview` puts it
 *    in front of them to agree with or correct. The gaps it reports are the
 *    honest part. Nothing on this screen requires the reader to know the phrase
 *    "ideal customer profile" — DECISIONS_V2 §3 is that synthesis proposes and
 *    the founder disposes, and a founder who cannot read the proposal cannot
 *    dispose of anything.
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
  const [reviewingId, setReviewingId] = useState<string | null>(null);

  useEffect(() => {
    api.get('/simulations/founder-stages').then((r) => setStages(r.data)).catch(() => {});
    api.get('/icp/estimate').then((r) => setSynthCost(r.data)).catch(() => {});
  }, []);

  useEffect(() => {
    if (!projectId) return;
    api
      .get('/icp', { params: { project_id: projectId } })
      .then((r) => setProfiles(unwrapList<ICPProfile>(r.data).items))
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
      // Opened straight away rather than behind a second click: this is a
      // proposal, and a proposal nobody was shown is indistinguishable from a
      // generated blob.
      setReviewingId(data.id);
    } catch (err) {
      setError(getErrorMessage(err, 'We could not work out your buyers from this project.'));
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

      {/* ── Who will react ────────────────────────────────────────── */}
      <div>
        <label className="block text-[12px] font-medium text-saibyl-muted uppercase tracking-wide mb-2">
          Who will react to this
        </label>
        <p className="text-[12px] text-saibyl-muted mb-3 leading-relaxed">
          Saibyl reads the documents on this project — your pitch, landing page, deck, pricing
          — and works out who your buyers are and what they care about. You get to check it
          before anything runs.
        </p>

        {profiles.length > 0 && (
          <div className="space-y-2 mb-3">
            {profiles.map((p) => {
              const selected = p.id === value.icpProfileId;
              return (
                <div key={p.id} className="space-y-2">
                  <button
                    type="button"
                    onClick={() => {
                      const next = selected ? null : p.id;
                      // Reviewing an audience that is no longer selected would
                      // let a founder correct a profile the run will not use.
                      setReviewingId(next);
                      onChange({ ...value, icpProfileId: next });
                    }}
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
                        {p.profile.archetypes.length} buyer
                        {p.profile.archetypes.length === 1 ? '' : 's'}
                        {p.profile.adversarial.length > 0
                          ? ` · ${p.profile.adversarial.length} who'll push back`
                          : ''}
                      </span>
                    </div>
                    <p className="text-[11px] text-saibyl-muted mt-1 leading-relaxed line-clamp-2">
                      {p.product_summary}
                    </p>
                    <div className="flex items-center gap-3 mt-2">
                      {p.profile.gaps.length > 0 && (
                        <span className="text-[10px] text-saibyl-gold/80">
                          {p.profile.gaps.length} thing
                          {p.profile.gaps.length === 1 ? '' : 's'} your documents never say
                        </span>
                      )}
                      {p.edited_by_user && (
                        <span className="text-[10px] text-saibyl-muted">You edited this</span>
                      )}
                    </div>
                  </button>

                  {selected && reviewingId !== p.id && (
                    <button
                      type="button"
                      onClick={() => setReviewingId(p.id)}
                      className="text-[12px] text-saibyl-gold hover:underline"
                    >
                      Check who we think will buy this →
                    </button>
                  )}

                  {selected && reviewingId === p.id && (
                    <AudienceReview
                      profile={p}
                      platforms={platforms}
                      adversarialShare={value.adversarialShare}
                      onSaved={(updated) =>
                        setProfiles((prev) =>
                          prev.map((row) => (row.id === updated.id ? updated : row)),
                        )
                      }
                      onClose={() => setReviewingId(null)}
                    />
                  )}
                </div>
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
          {synthesizing ? 'Reading your documents…' : 'Work out who my buyers are'}
        </button>
        {synthCost && (
          <p className="text-[11px] text-saibyl-muted mt-2">
            {synthCost.credits_required.toLocaleString()} credits, charged once — not per run.
            Every simulation in this project reuses the same buyers.
          </p>
        )}
      </div>

      {/* ── Adversarial share ─────────────────────────────────────── */}
      <div>
        <div className="flex items-baseline justify-between mb-2">
          <label className="text-[12px] font-medium text-saibyl-muted uppercase tracking-wide">
            How many will push back
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
              Work out your buyers first. The people who argue against you are built from the
              documents you uploaded — the ready-made persona packs have nobody like that in
              them, so there is no share to set.
            </>
          ) : (
            <>
              These are people happy with whatever they use today, so they talk your score down
              on purpose. The report always keeps them separate from your buyers and says where
              they came from. 50% is the ceiling: past half the room, the score is measuring the
              number you picked here rather than the market.
            </>
          )}
        </p>
        {profile && profile.profile.competitors.some((c) => c.mentioned_in.length > 0) && (
          <p className="text-[11px] text-saibyl-muted mt-2">
            Rivals we can name:{' '}
            {profile.profile.competitors
              .filter((c) => c.mentioned_in.length > 0)
              .map((c) => c.name)
              .join(', ')}
            . They appear by name only because something you uploaded named them.
          </p>
        )}
      </div>
    </div>
  );
}
