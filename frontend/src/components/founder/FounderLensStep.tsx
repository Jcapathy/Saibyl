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
  /**
   * True once the founder has moved the share slider themselves. Client-side
   * only — the submit payload picks its fields by name and never sends this.
   * While false, picking a stage adopts that stage's default share; once true,
   * a hand-set value is kept and the notice by the slider says so.
   */
  shareSetByUser: boolean;
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
  /**
   * Takes an updater as well as a value, for the same reason `RunConfigurator`
   * does: React treats `input` on a range as a continuous event and batches
   * several into one commit, and a handler that spreads the `value` of the
   * render that created it silently reverts whatever the earlier handlers in
   * that batch set. Every writer here passes a function.
   */
  onChange: (update: FounderConfig | ((prev: FounderConfig) => FounderConfig)) => void;
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
    // Adopt the stage's audience default — concept validation is 0% and growth
    // is 40%, and that difference is the substance of stage-awareness — but
    // only while the founder has not set the share by hand. A hand-set value
    // used to be silently reset here; now it is kept, and the notice by the
    // slider says the stage default was not applied and offers it back.
    onChange((prev) =>
      prev.shareSetByUser
        ? { ...prev, stage: spec.id }
        : { ...prev, stage: spec.id, adversarialShare: spec.default_adversarial_share },
    );
  };

  /* A stage can arrive already set instead of through `selectStage` — the
     product rail links here with the moment in the URL — and adopting the
     stage default lives in `selectStage`. This adopts it for the pre-set case
     once the stage list has loaded, and only while the share is untouched, so
     it can never overwrite a hand-set value. Idempotent: after adopting, the
     shares match and it returns early. */
  useEffect(() => {
    if (value.shareSetByUser || !value.stage) return;
    const spec = stages.find((s) => s.id === value.stage);
    if (
      !spec ||
      Math.round(spec.default_adversarial_share * 100) ===
        Math.round(value.adversarialShare * 100)
    ) {
      return;
    }
    onChange((prev) =>
      prev.shareSetByUser || prev.stage !== spec.id
        ? prev
        : { ...prev, adversarialShare: spec.default_adversarial_share },
    );
  }, [stages, value.stage, value.shareSetByUser, value.adversarialShare, onChange]);

  /* The one-tap way back after `selectStage` kept a hand-set share. Taking the
     default is also a statement that the default should follow the stage
     again, so the hand-set flag comes off with it. */
  const adoptStageDefault = () => {
    const spec = stage;
    if (!spec) return;
    onChange((prev) => ({
      ...prev,
      adversarialShare: spec.default_adversarial_share,
      shareSetByUser: false,
    }));
  };

  /* True when a hand-set share survived a stage pick and differs from that
     stage's default — the state the notice above the slider exists for. */
  const keptShare =
    value.shareSetByUser &&
    stage !== null &&
    Math.round(stage.default_adversarial_share * 100) !==
      Math.round(value.adversarialShare * 100);

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
      onChange((prev) => ({ ...prev, icpProfileId: data.id }));
      // Opened straight away rather than behind a second click: this is a
      // proposal, and a proposal nobody was shown is indistinguishable from a
      // generated blob.
      setReviewingId(data.id);
    } catch (err) {
      setError(getErrorMessage(err, 'We could not work out your buyers from this product.'));
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
          Where are you with this
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
          Saibyl reads what you have uploaded for this product — your pitch, landing page,
          deck, pricing — and works out who your buyers are and what they care about. You get
          to check it before anything runs.
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
                      onChange((prev) => ({ ...prev, icpProfileId: next }));
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
            {synthCost.credits_required.toLocaleString()} credits, charged once — not every
            time. Every run on this product reuses the same buyers.
          </p>
        )}
      </div>

      {/* ── How much of the room argues back ──────────────────────────
          The percentage and the slider render once there is anything for the
          number to act on — a stage picked, or buyers already worked out.

          The share is an input to the *build*, not only to the run:
          `synthesize` sends `adversarial_share` to shape how much of the
          proposed room argues back, and picking a stage seeds it from that
          stage's default. An earlier version hid the control until a profile
          existed, on the reasoning that the run submits a share of 0 without
          one — true of run submit, and false of synthesis, so the invisible
          stage default was sent at the one moment the number built anything.

          With no stage picked and no buyers worked out there really is
          nothing for it to act on — run submit sends 0 without a profile,
          the API rejects a share without one outright, and the ready-made
          packs carry nobody who argues back — so that state keeps the
          sentence instead of a number nothing would act on. */}
      <div>
        {!value.stage && !value.icpProfileId ? (
          <>
            <label className="block text-[12px] font-medium text-saibyl-muted uppercase tracking-wide mb-2">
              How many will push back
            </label>
            <p className="text-[11px] text-saibyl-muted leading-relaxed">
              Nobody, on this run. The people who argue against you are built out of the
              documents you uploaded, and the ready-made groups above have nobody like that in
              them. Say where you are with this, or work out your buyers, and you can set the
              share here.
            </p>
          </>
        ) : (
          <>
            {stage && keptShare && (
              /* Modelled on the configurator's value-changed notice: the
                 stage pick kept a hand-set share, and this says so instead of
                 the picker silently deciding either way. */
              <div className="rounded-xl border border-saibyl-warning/25 bg-saibyl-warning/[0.06] px-4 py-3 mb-3">
                <p className="text-[12px] text-saibyl-silver leading-relaxed">
                  You set this to {(value.adversarialShare * 100).toFixed(0)}% yourself, so
                  picking a stage did not change it. Runs at this stage usually start at{' '}
                  {(stage.default_adversarial_share * 100).toFixed(0)}%.{' '}
                  <button
                    type="button"
                    onClick={adoptStageDefault}
                    className="text-saibyl-gold hover:underline"
                  >
                    Use {(stage.default_adversarial_share * 100).toFixed(0)}% instead
                  </button>
                </p>
              </div>
            )}
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
              onChange={(e) => {
                const adversarialShare = Number(e.target.value) / 100;
                onChange((prev) => ({ ...prev, adversarialShare, shareSetByUser: true }));
              }}
              className="w-full accent-saibyl-gold"
            />
            {value.icpProfileId ? (
              <p className="text-[11px] text-saibyl-muted mt-2 leading-relaxed">
                These are people happy with whatever they use today, so they talk your score down
                on purpose. The report always keeps them separate from your buyers and says where
                they came from. Half the room is the ceiling: past that, the score is measuring
                the number you picked here rather than the market.
              </p>
            ) : (
              <p className="text-[11px] text-saibyl-muted mt-2 leading-relaxed">
                This shapes the group we are about to work out of your documents: the share of
                that room who are happy with what they use today and will talk your score down
                on purpose. Half the room is the ceiling: past that, the score is measuring
                the number you picked here rather than the market.
              </p>
            )}
          </>
        )}
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
