import { useMemo, useState } from 'react';
import { AlertTriangle, Check, Loader2, Trash2 } from 'lucide-react';
import { AxiosError } from 'axios';
import api from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import {
  BUDGET_AUTHORITY_LABELS,
  SENIORITY_LABELS,
  SUPPORTED_ICP_SCHEMA_VERSION,
  SWITCHING_COST_LABELS,
  isSupportedICPSchema,
  type BudgetAuthority,
  type ICPArchetype,
  type ICPProfile,
  type ICPProfileBody,
  type Seniority,
  type SwitchingCost,
} from '@/lib/founder';

/**
 * "Here's who we think will buy this — does that look right?"
 *
 * This is a **review-and-confirm** surface, not a form. DECISIONS_V2 §3 settled
 * that: the founder is the wrong person to ask which of forty persona packs
 * matches their buyer, because that judgement is the thing they are paying for.
 * So synthesis proposes and the founder corrects only what looks wrong — and a
 * founder who has never heard the phrase "ideal customer profile" must be able
 * to read this, agree with it, and carry on without touching a single field.
 * Accepting is the obvious path; editing is the exception.
 *
 * Until this existed `PATCH /api/icp/{id}` had no caller, so the "founder
 * corrects" half of that decision was unreachable from the product.
 *
 * Three things it has to get right underneath the plain English:
 *
 * 1. **The profile is replaced whole, not diffed.** The server re-validates the
 *    entire body and recompiles the audience from it. So an unrecognised
 *    `schema_version` renders *nothing* rather than the fields it happens to
 *    know: rendering a recognised subset and saving the result would delete
 *    every field this build had never heard of.
 *
 * 2. **`platforms` and `adversarial_share` go on every save.** They are inputs
 *    to the recompile rather than stored properties, so a save with no
 *    platforms selected would rebuild the audience against an empty platform
 *    list. Refused here instead.
 *
 * 3. **A rejection is shown verbatim and then explained.** The server writes
 *    that sentence for a founder to read, and the most common one — a rival
 *    named with no uploaded document behind it — is an integrity guardrail
 *    (DECISIONS §7), not a validation failure. It is presented as the product
 *    declining to make something up, with the remedy spelled out.
 */

const inputBase =
  'w-full rounded-xl bg-white border border-saibyl-border-light px-3 py-2 text-[13px] text-saibyl-ink placeholder:text-saibyl-muted/70 focus:outline-none focus:border-saibyl-blue focus:ring-2 focus:ring-saibyl-blue/20';

/** One value per line. Blank lines are dropped rather than stored as empties. */
function parseLines(value: string): string[] {
  return value
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
}

/**
 * Does this rejection concern the competitor-naming rule?
 *
 * A substring test on a message the server authored, used only to decide
 * whether to add an explanation underneath it. The verbatim text is shown
 * either way, so the worst a miss can do is withhold the extra paragraph.
 */
function isGroundingRejection(message: string): boolean {
  const lower = message.toLowerCase();
  return lower.includes('competitor') || lower.includes('ground');
}

function Labelled({
  question,
  hint,
  children,
}: {
  question: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="block text-[12px] text-saibyl-silver mb-1.5">{question}</label>
      {children}
      {hint && <p className="text-[10px] text-saibyl-muted mt-1">{hint}</p>}
    </div>
  );
}

function ListInput({
  question,
  hint,
  values,
  onChange,
}: {
  question: string;
  hint: string;
  values: string[];
  onChange: (next: string[]) => void;
}) {
  return (
    <Labelled question={question} hint={hint}>
      <textarea
        rows={Math.min(6, Math.max(2, values.length + 1))}
        value={values.join('\n')}
        onChange={(e) => onChange(parseLines(e.target.value))}
        className={`${inputBase} resize-y`}
      />
    </Labelled>
  );
}

/** A read-only line of the summary. Renders nothing when there is nothing to say. */
function Detail({ label, value }: { label: string; value: string }) {
  if (!value.trim()) return null;
  return (
    <p className="text-[12px] text-saibyl-muted leading-relaxed">
      <span className="text-saibyl-muted">{label} </span>
      <span className="text-saibyl-silver">{value}</span>
    </p>
  );
}

function BuyerCard({
  archetype,
  sharePct,
  canRemove,
  onChange,
  onRemove,
}: {
  archetype: ICPArchetype;
  /** Share of the buyers, from the weights already on the profile. */
  sharePct: number | null;
  canRemove: boolean;
  onChange: (next: ICPArchetype) => void;
  onRemove: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const patch = (fields: Partial<ICPArchetype>) => onChange({ ...archetype, ...fields });

  return (
    <div className="rounded-xl border border-saibyl-border bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[14px] font-medium text-saibyl-platinum">
            {archetype.label || 'Unnamed buyer'}
          </p>
          {archetype.role && (
            <p className="text-[11px] text-saibyl-muted mt-0.5">{archetype.role}</p>
          )}
        </div>
        {/* Absent only if every weight is missing — then nothing is shown, rather
            than a 0% that would read as a real measurement of nobody. */}
        {sharePct !== null && (
          <span className="text-[10px] text-saibyl-muted whitespace-nowrap shrink-0 mt-0.5">
            about {sharePct}% of your buyers
          </span>
        )}
      </div>

      {/*
        Why we think this is one of your buyers. The reader may never have
        heard the term "ICP" and cannot judge an archetype from a role and a
        switching-cost enum — this sentence is what makes the confirm-or-correct
        decision possible at all.

        Rendered only when the backend supplies one. It drops any rationale
        that merely paraphrases the archetype's own fields, so an empty value
        means "we could not point at anything in your material", and the honest
        rendering of that is nothing. No placeholder, no "n/a": inventing a
        reason here is the product asserting evidence it does not have, which
        is the defect class this whole build exists to remove.
      */}
      {archetype.rationale?.trim() ? (
        <p className="mt-2.5 text-[12px] leading-relaxed text-saibyl-muted">
          {archetype.rationale.trim()}
        </p>
      ) : null}

      {!editing ? (
        <>
          <div className="mt-3 space-y-1.5">
            <Detail label="Seniority:" value={SENIORITY_LABELS[archetype.seniority] ?? ''} />
            <Detail
              label="Spending:"
              value={BUDGET_AUTHORITY_LABELS[archetype.budget_authority] ?? ''}
            />
            <Detail label="Uses today:" value={archetype.incumbent_tooling.join(', ')} />
            <Detail
              label="Moving off it:"
              value={SWITCHING_COST_LABELS[archetype.switching_cost] ?? ''}
            />
            <Detail label="Judges you on:" value={archetype.evaluation_criteria.join(', ')} />
            <Detail label="Would doubt:" value={archetype.skepticism_triggers.join(', ')} />
            <Detail label="Trying to:" value={archetype.goals.join(', ')} />
            <Detail label="Struggles with:" value={archetype.pains.join(', ')} />
          </div>
          <div className="flex items-center gap-4 mt-3">
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="text-[12px] text-saibyl-gold hover:underline"
            >
              This isn&rsquo;t quite right
            </button>
            {/* Never a grey button. This was `disabled={!canRemove}` with its
                only explanation in a `title` attribute — which is no
                explanation at all on a touch screen, and invisible in any
                screenshot. The last remaining buyer now says why it cannot be
                removed, in a sentence, in the layout. */}
            {canRemove ? (
              <button
                type="button"
                onClick={onRemove}
                className="flex items-center gap-1.5 text-[12px] text-saibyl-muted hover:text-saibyl-negative"
              >
                <Trash2 className="w-3 h-3" />
                Not my buyer
              </button>
            ) : (
              <span className="text-[12px] text-saibyl-muted">
                This is your last buyer &mdash; a run needs at least one
              </span>
            )}
          </div>
        </>
      ) : (
        <div className="mt-4 space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Labelled question="What would you call them?">
              <input
                value={archetype.label}
                onChange={(e) => patch({ label: e.target.value })}
                placeholder="e.g. Small agency owners"
                className={inputBase}
              />
            </Labelled>
            <Labelled question="What's their job?">
              <input
                value={archetype.role}
                onChange={(e) => patch({ role: e.target.value })}
                placeholder="e.g. Runs a 5-person design studio"
                className={inputBase}
              />
            </Labelled>
            <Labelled question="How senior are they?">
              <select
                value={archetype.seniority}
                onChange={(e) => patch({ seniority: e.target.value as Seniority })}
                className={inputBase}
                style={{ colorScheme: 'light' }}
              >
                {(Object.keys(SENIORITY_LABELS) as Seniority[]).map((key) => (
                  <option key={key} value={key}>
                    {SENIORITY_LABELS[key]}
                  </option>
                ))}
              </select>
            </Labelled>
            <Labelled question="Can they sign off on this themselves?">
              <select
                value={archetype.budget_authority}
                onChange={(e) =>
                  patch({ budget_authority: e.target.value as BudgetAuthority })
                }
                className={inputBase}
                style={{ colorScheme: 'light' }}
              >
                {(Object.keys(BUDGET_AUTHORITY_LABELS) as BudgetAuthority[]).map((key) => (
                  <option key={key} value={key}>
                    {BUDGET_AUTHORITY_LABELS[key]}
                  </option>
                ))}
              </select>
            </Labelled>
            <Labelled question="How hard is it for them to move off what they use today?">
              <select
                value={archetype.switching_cost}
                onChange={(e) => patch({ switching_cost: e.target.value as SwitchingCost })}
                className={inputBase}
                style={{ colorScheme: 'light' }}
              >
                {(Object.keys(SWITCHING_COST_LABELS) as SwitchingCost[]).map((key) => (
                  <option key={key} value={key}>
                    {SWITCHING_COST_LABELS[key]}
                  </option>
                ))}
              </select>
            </Labelled>
            <Labelled
              question="How many of your buyers are people like this?"
              hint="A rough weight, not a percentage. Give the biggest group the biggest number."
            >
              <input
                type="number"
                min={0.05}
                step={0.05}
                value={archetype.weight}
                onChange={(e) => patch({ weight: Number(e.target.value) })}
                className={inputBase}
              />
            </Labelled>
          </div>

          <ListInput
            question="What they use today"
            hint="One per line. This matters more than anything else here — people judge you against whatever they'd have to give up."
            values={archetype.incumbent_tooling}
            onChange={(incumbent_tooling) => patch({ incumbent_tooling })}
          />
          <ListInput
            question="What they'll judge this on"
            hint="One per line, most important first."
            values={archetype.evaluation_criteria}
            onChange={(evaluation_criteria) => patch({ evaluation_criteria })}
          />
          <ListInput
            question="What would make them doubt this?"
            hint="One per line. These are what the simulated buyers will push back with."
            values={archetype.skepticism_triggers}
            onChange={(skepticism_triggers) => patch({ skepticism_triggers })}
          />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <ListInput
              question="What are they trying to get done?"
              hint="One per line."
              values={archetype.goals}
              onChange={(goals) => patch({ goals })}
            />
            <ListInput
              question="What's frustrating them right now?"
              hint="One per line."
              values={archetype.pains}
              onChange={(pains) => patch({ pains })}
            />
          </div>

          <button
            type="button"
            onClick={() => setEditing(false)}
            className="text-[12px] text-saibyl-gold hover:underline"
          >
            Done with this one
          </button>
        </div>
      )}
    </div>
  );
}

export default function AudienceReview({
  profile,
  platforms,
  adversarialShare,
  onSaved,
  onClose,
}: {
  profile: ICPProfile;
  /** The run's selected platforms. Re-sent on every save — the audience recompiles. */
  platforms: string[];
  /** Re-sent on every save for the same reason. */
  adversarialShare: number;
  onSaved: (updated: ICPProfile) => void;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState<ICPProfileBody>(() => profile.profile);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [gone, setGone] = useState(false);

  const supported = isSupportedICPSchema(draft?.schema_version);

  const dirty = useMemo(
    () => JSON.stringify(draft) !== JSON.stringify(profile.profile),
    [draft, profile],
  );

  const weightTotal = useMemo(
    () => (draft?.archetypes ?? []).reduce((sum, a) => sum + (a.weight || 0), 0),
    [draft],
  );

  const noPlatforms = platforms.length === 0;

  // An unrecognised schema shows nothing it might half-understand. This screen
  // sends the whole profile back on save, so a partial render is a partial
  // delete.
  if (!supported) {
    return (
      <div className="rounded-xl border border-saibyl-warning/25 bg-saibyl-warning/[0.06] p-4">
        <p className="flex items-center gap-2 text-[12px] font-medium text-saibyl-warning">
          <AlertTriangle className="w-3.5 h-3.5" />
          This app can&rsquo;t show this audience
        </p>
        <p className="text-[11px] text-saibyl-muted mt-1.5 leading-relaxed">
          It was written by a newer version of Saibyl (format {String(draft?.schema_version)};
          this app reads up to {SUPPORTED_ICP_SCHEMA_VERSION}). We&rsquo;re showing nothing
          rather than the parts we recognise — saving a half-read version would throw away
          the rest. Reload the page to pick up the current version.
        </p>
        <button
          type="button"
          onClick={onClose}
          className="mt-3 text-[12px] text-saibyl-gold hover:underline"
        >
          Close
        </button>
      </div>
    );
  }

  if (gone) {
    return (
      <div className="rounded-xl border border-saibyl-negative/25 bg-saibyl-negative/[0.06] p-4">
        <p className="text-[12px] font-medium text-saibyl-negative">
          This audience has been deleted
        </p>
        <p className="text-[11px] text-saibyl-muted mt-1.5 leading-relaxed">
          It was removed while you were looking at it, so there is nowhere for your changes
          to go. Work out the buyers again to start over.
        </p>
        <button
          type="button"
          onClick={onClose}
          className="mt-3 text-[12px] text-saibyl-gold hover:underline"
        >
          Close
        </button>
      </div>
    );
  }

  const setArchetype = (index: number, next: ICPArchetype) =>
    setDraft((prev) => ({
      ...prev,
      archetypes: prev.archetypes.map((a, i) => (i === index ? next : a)),
    }));

  const removeArchetype = (index: number) =>
    setDraft((prev) => ({
      ...prev,
      archetypes: prev.archetypes.filter((_, i) => i !== index),
    }));

  const save = async () => {
    setSaving(true);
    setError('');
    try {
      const { data } = await api.patch<ICPProfile>(`/icp/${profile.id}`, {
        // The whole body. The server replaces rather than merges, so a diff
        // would be validated against a profile nobody assembled.
        profile: draft,
        // Both re-sent every time: the audience is rebuilt on save and these
        // are inputs to that rebuild, not properties of the profile.
        platforms,
        adversarial_share: adversarialShare,
      });
      // Adopt what came back rather than keeping what was sent. The server
      // re-validates and re-serialises the profile, so the round-tripped body
      // is not byte-identical to the draft — and the "you have unsaved changes"
      // test is a comparison against it, which would otherwise stay true
      // forever after the first successful save.
      setDraft(data.profile);
      onSaved(data);
    } catch (err) {
      if (err instanceof AxiosError && err.response?.status === 404) {
        setGone(true);
        return;
      }
      setError(getErrorMessage(err, 'Your changes could not be saved.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-xl border border-saibyl-gold/20 bg-white p-5 space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-[15px] font-medium text-saibyl-platinum">
            Here&rsquo;s who we think will buy this
          </h3>
          <p className="text-[12px] text-saibyl-muted mt-1 leading-relaxed max-w-xl">
            We read what you uploaded and worked out who your buyers are and
            what they care about. Have a read. If something&rsquo;s wrong, change it —
            otherwise carry on, and every run uses exactly what you see here.
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="text-[12px] text-saibyl-muted hover:text-saibyl-platinum shrink-0"
        >
          Close
        </button>
      </div>

      {/* The accept path, stated before anything asks to be edited. */}
      <div className="flex items-start gap-2.5 px-4 py-3 rounded-xl border border-saibyl-positive/25 bg-saibyl-positive/[0.06]">
        <Check className="w-3.5 h-3.5 text-saibyl-positive mt-0.5 shrink-0" />
        <p className="text-[12px] text-saibyl-silver leading-relaxed">
          {dirty
            ? 'You’ve changed something. Save it below, and your version is what gets used.'
            : 'Looks right? Then there’s nothing to do — carry on to the next step and we’ll use this.'}
        </p>
      </div>

      {draft.gaps.length > 0 && (
        <div className="rounded-xl border border-saibyl-gold/20 bg-saibyl-gold/[0.06] p-4">
          <p className="text-[11px] font-medium text-saibyl-gold mb-1.5">
            Things your documents never said
          </p>
          <ul className="space-y-1">
            {draft.gaps.map((gap) => (
              <li key={gap} className="text-[11px] text-saibyl-muted leading-relaxed">
                — {gap}
              </li>
            ))}
          </ul>
          <p className="text-[10px] text-saibyl-muted mt-2 leading-relaxed">
            We left these blank instead of guessing. Filling them in below makes the
            answers sharper, but it works without them.
          </p>
        </div>
      )}

      <div>
        <p className="text-[11px] font-medium text-saibyl-muted uppercase tracking-wide mb-2">
          Your buyers · {draft.archetypes.length}
        </p>
        <div className="space-y-2">
          {draft.archetypes.map((archetype, i) => (
            <BuyerCard
              key={archetype.id}
              archetype={archetype}
              sharePct={
                weightTotal > 0 ? Math.round(((archetype.weight || 0) / weightTotal) * 100) : null
              }
              canRemove={draft.archetypes.length > 1}
              onChange={(next) => setArchetype(i, next)}
              onRemove={() => removeArchetype(i)}
            />
          ))}
        </div>
      </div>

      {draft.adversarial.length > 0 && (
        <div>
          <p className="text-[11px] font-medium text-saibyl-muted uppercase tracking-wide mb-2">
            People who&rsquo;ll argue against you · {draft.adversarial.length}
          </p>
          <div className="space-y-2">
            {draft.adversarial.map((adv) => (
              <div
                key={adv.id}
                className="rounded-xl border border-saibyl-border bg-white px-4 py-3"
              >
                <p className="text-[13px] text-saibyl-platinum">{adv.label}</p>
                {adv.core_argument && (
                  <p className="text-[11px] text-saibyl-muted mt-1 leading-relaxed">
                    {adv.core_argument}
                  </p>
                )}
                {adv.competitor_name && (
                  <p className="text-[10px] text-saibyl-muted mt-1.5">
                    Mentions {adv.competitor_name}, because {adv.grounded_in.length} document
                    {adv.grounded_in.length === 1 ? '' : 's'} you uploaded named them.
                  </p>
                )}
              </div>
            ))}
          </div>
          <p className="text-[10px] text-saibyl-muted mt-2 leading-relaxed">
            These are people happy with what they already use. They&rsquo;re shown here but
            can&rsquo;t be edited — a rival is only ever named because one of your own
            uploads named them, and that link isn&rsquo;t something to retype.
          </p>
        </div>
      )}

      {error && (
        <div className="px-4 py-3 rounded-xl bg-saibyl-negative/10 border border-saibyl-negative/20 space-y-2">
          <p className="text-[12px] text-saibyl-negative leading-relaxed whitespace-pre-wrap">
            {error}
          </p>
          {isGroundingRejection(error) && (
            <p className="text-[11px] text-saibyl-muted leading-relaxed">
              In plain English: Saibyl will only put a rival&rsquo;s name in front of
              your buyers when you have uploaded something that rival actually published.
              Otherwise the
              model is making up what they say — and you&rsquo;d have no way of telling.
              To name them, upload their landing page, pricing page or docs and
              mark the file as a competitor&rsquo;s when you do. Then come back here.
            </p>
          )}
        </div>
      )}

      {noPlatforms && (
        <div className="px-4 py-3 rounded-xl bg-saibyl-warning/[0.08] border border-saibyl-warning/25">
          <p className="flex items-center gap-2 text-[12px] text-saibyl-warning">
            <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
            Pick at least one platform before saving
          </p>
          <p className="text-[11px] text-saibyl-muted mt-1 leading-relaxed">
            Saving rebuilds this audience for the places your run will simulate. With none
            selected, we&rsquo;d rebuild it for nowhere.
          </p>
        </div>
      )}

      {dirty && (
        <div className="flex items-center gap-3 pt-1">
          {/* Saving is announced rather than greyed, and the one thing that
              genuinely blocks a save — no platform picked — already says so in
              full above. A grey rectangle repeating it silently is what this
              replaces. */}
          {saving ? (
            <span
              aria-live="polite"
              className="flex items-center gap-2 px-5 py-2 rounded-xl bg-saibyl-gold text-saibyl-void font-semibold text-[13px]"
            >
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              Saving&hellip;
            </span>
          ) : noPlatforms ? (
            <span className="text-[12px] text-saibyl-warning">
              Pick a platform above and this saves
            </span>
          ) : (
            <button
              type="button"
              onClick={save}
              className="flex items-center gap-2 px-5 py-2 rounded-xl bg-saibyl-gold text-saibyl-void font-semibold text-[13px] transition-colors hover:bg-saibyl-gold-hover"
            >
              Save my changes
            </button>
          )}
          {!saving && (
            <button
              type="button"
              onClick={() => {
                setDraft(profile.profile);
                setError('');
              }}
              className="text-[12px] text-saibyl-muted hover:text-saibyl-platinum"
            >
              Undo my changes
            </button>
          )}
        </div>
      )}
    </div>
  );
}
