import { ShieldAlert } from 'lucide-react';
import type { AdversarialDisclosure } from '@/lib/analysis';

const ACCENT = '#286cf0'; // Signal Blue — fills, borders, icons
const ACCENT_TEXT = '#1e5ad9'; // darker blue — text on the tinted ground

const ROLE_LABELS: Record<string, string> = {
  incumbent_employee: 'Works for what they already use',
  incumbent_power_user: 'Gets a lot out of what they already use',
  sunk_cost_consultant: 'Has built a living on the old way',
  category_skeptic: 'Doubts anyone needs this kind of thing',
  free_alternative_advocate: 'Says a free tool already does this',
};

/**
 * The people in the room who were built to argue against you, disclosed
 * wherever the run is shown.
 *
 * PRD §4 requires incumbent-aligned agents to be labelled synthetic in every
 * report and export. The sentence itself is composed on the server and rendered
 * here verbatim, so this page, the print page, the PDF and the JSON export say
 * the same words — a disclosure re-worded per surface is a disclosure that
 * eventually says something different on one of them. That is also why the
 * server's sentence is the one place on this card that may still carry the
 * vocabulary: it is a compliance string, not copy this file gets to rewrite.
 *
 * Renders nothing when the run had nobody arguing against you, which is every
 * run made before Phase 2.
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
          <p className="text-[13px] font-semibold" style={{ color: ACCENT_TEXT }}>
            People who&rsquo;ll argue against you — {adversarial.agents_total} of them
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
                  style={{ backgroundColor: 'rgba(20,41,74,.05)', color: '#44587a' }}
                >
                  {ROLE_LABELS[role] ?? role.replace(/_/g, ' ')} · {count}
                </span>
              ))}
            </div>
          )}

          {/* What was asked for versus what was built. Places are handed out by
              how big each group of buyers is and then rounded to whole people,
              so the two differ in a small room — and a founder who asked for
              30% and got 22% should be able to see that rather than reason
              about a share the run never had. */}
          {adversarial.share_configured > 0 &&
            Math.abs(adversarial.share_realised - adversarial.share_configured) >= 0.02 && (
              <p className="text-[11px] text-saibyl-muted mt-2">
                You asked for {(adversarial.share_configured * 100).toFixed(0)}% of the
                room to push back; it came out at{' '}
                {(adversarial.share_realised * 100).toFixed(0)}% once we rounded to whole
                people.
              </p>
            )}

          {adversarial.agents_active < adversarial.agents_total && (
            <p className="text-[11px] text-saibyl-muted mt-1">
              {adversarial.agents_active} of the {adversarial.agents_total} said something
              we could read.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
