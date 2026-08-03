import { ShieldAlert } from 'lucide-react';
import type { AdversarialDisclosure } from '@/lib/analysis';

const ACCENT = '#C9A227'; // Sovereign Gold

const ROLE_LABELS: Record<string, string> = {
  incumbent_employee: 'Incumbent employee',
  incumbent_power_user: 'Incumbent power user',
  sunk_cost_consultant: 'Sunk-cost consultant',
  category_skeptic: 'Category skeptic',
  free_alternative_advocate: 'Free-alternative advocate',
};

/**
 * The adversarial cohort, disclosed wherever the run is shown.
 *
 * PRD §4 requires incumbent-aligned agents to be labelled synthetic in every
 * report and export. The sentence itself is composed on the server and rendered
 * here verbatim, so this page, the print page, the PDF and the JSON export say
 * the same words — a disclosure re-worded per surface is a disclosure that
 * eventually says something different on one of them.
 *
 * Renders nothing when the run had no adversarial cohort, which is every run
 * made before Phase 2.
 */
export default function AdversarialNotice({
  adversarial,
}: {
  adversarial: AdversarialDisclosure | undefined;
}) {
  if (!adversarial?.enabled) return null;

  const roles = Object.entries(adversarial.roles ?? {}).sort(([a], [b]) =>
    a.localeCompare(b),
  );

  return (
    <div
      className="rounded-2xl border p-5 mb-6"
      style={{ borderColor: `${ACCENT}33`, backgroundColor: `${ACCENT}0D` }}
    >
      <div className="flex items-start gap-3">
        <ShieldAlert className="w-4 h-4 mt-0.5 shrink-0" style={{ color: ACCENT }} />
        <div className="min-w-0">
          <p className="text-[13px] font-semibold" style={{ color: ACCENT }}>
            Adversarial cohort — {adversarial.agents_total} synthetic agents
          </p>

          <p className="text-[12px] text-saibyl-silver mt-1 leading-relaxed">
            {adversarial.disclosure}
          </p>

          {roles.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-2.5">
              {roles.map(([role, count]) => (
                <span
                  key={role}
                  className="px-2 py-0.5 rounded text-[10px]"
                  style={{ backgroundColor: `${ACCENT}1A`, color: ACCENT }}
                >
                  {ROLE_LABELS[role] ?? role.replace(/_/g, ' ')} · {count}
                </span>
              ))}
            </div>
          )}

          {/* Configured versus realised. Allocation is by archetype weight and
              rounds to whole agents, so the two differ on small swarms — and a
              founder who asked for 30% and got 22% should be able to see that
              rather than reason about a share the run never had. */}
          {adversarial.share_configured > 0 &&
            Math.abs(adversarial.share_realised - adversarial.share_configured) >= 0.02 && (
              <p className="text-[11px] text-saibyl-muted mt-2">
                Configured at {(adversarial.share_configured * 100).toFixed(0)}%; the
                swarm allocated {(adversarial.share_realised * 100).toFixed(0)}% after
                rounding to whole agents.
              </p>
            )}

          {adversarial.agents_active < adversarial.agents_total && (
            <p className="text-[11px] text-saibyl-muted mt-1">
              {adversarial.agents_active} of {adversarial.agents_total} produced a
              measured event.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
