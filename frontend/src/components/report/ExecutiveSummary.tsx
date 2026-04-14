import SectionRenderer from '@/components/report/SectionRenderer';
import { classifySentiment } from '@/lib/constants';
import { cleanContent } from '@/lib/utils';

interface Report {
  id: string;
  simulation_id: string;
  sections: { section_type?: string; title: string; content: string }[];
  full_markdown: string;
}

interface ExecutiveSummaryProps {
  report: Report;
  sentiment?: number;
  engagement?: number;
  controversy?: number;
  controversyLabel?: string;
  riskCount?: number;
  sentimentTrajectory?: string;
}

function sentimentLabel(v: number): string {
  return classifySentiment(v).label;
}

function sentimentColor(v: number | undefined): string {
  if (v == null) return 'text-[#8B97A8]';
  // Static Tailwind classes — must be complete strings for purge scanner
  if (v >= 0.2) return 'text-[#34D399]';   // CHART_COLORS.positive
  if (v >= -0.2) return 'text-[#D4A84B]';  // CHART_COLORS.neutral
  return 'text-[#F87171]';                  // CHART_COLORS.negative
}

export default function ExecutiveSummary({
  report,
  sentiment,
  engagement,
  controversy,
  controversyLabel,
  riskCount,
  sentimentTrajectory,
}: ExecutiveSummaryProps) {
  // Find the best section to display — try executive/summary/overview, fall back to first section
  const execSection =
    report.sections.find(
      (s) =>
        s.section_type === 'executive_summary' ||
        /executive|summary|overview|brief|conclusion/i.test(s.title),
    ) ?? (report.sections.length > 0 ? report.sections[0] : null);

  // If no sections but we have full_markdown, use the first ~2000 chars
  const fallbackContent =
    !execSection && report.full_markdown
      ? report.full_markdown.slice(0, 2000)
      : null;

  // Static Tailwind classes — must be complete strings for the purge scanner
  const stats = [
    {
      label: 'Sentiment',
      value: sentiment != null ? (sentiment >= 0 ? '+' : '') + sentiment.toFixed(2) : '—',
      sub: sentiment != null ? sentimentLabel(sentiment) : 'Pending',
      color: sentimentColor(sentiment),
      accent: 'bg-gradient-to-r from-[#6C63FF] to-[#00D4FF]',   // subjectA → subjectB
    },
    {
      label: 'Engagement',
      value: engagement != null ? `${(engagement * 10).toFixed(1)} / 10` : '—',
      sub: engagement != null ? (engagement >= 0.7 ? 'High virality potential' : 'Moderate reach') : 'Pending',
      color: 'text-[#00D4FF]',    // subjectB
      accent: 'bg-[#34D399]',     // positive
    },
    {
      label: 'Polarization Ratio',
      value: controversyLabel ?? (controversy != null ? controversy.toFixed(2) : '—'),
      sub: controversy != null
        ? controversy < 0.3 ? 'Low — Minimal polarization' : controversy < 0.6 ? 'Moderate — Notable division' : 'High — Significant polarization'
        : 'Pending',
      color: controversy != null
        ? (controversy < 0.3 ? 'text-[#34D399]' : controversy < 0.6 ? 'text-[#D4A84B]' : 'text-[#F87171]')
        : 'text-[#8B97A8]',
      accent: 'bg-[#D4A84B]',     // neutral
    },
    {
      label: 'Risks Found',
      value: riskCount != null ? String(riskCount) : '—',
      sub: riskCount != null ? (riskCount === 0 ? 'No risks detected' : `${riskCount} risk${riskCount > 1 ? 's' : ''} identified`) : 'Pending',
      color: riskCount != null && riskCount > 3 ? 'text-[#F87171]' : 'text-[#8B97A8]',
      accent: 'bg-[#F87171]',     // negative
    },
    {
      label: 'Sentiment Trajectory',
      value: sentimentTrajectory ?? '—',
      sub: sentimentTrajectory ? 'Net shift across simulation' : 'Pending',
      color: 'text-[#00D4FF]',
      accent: 'bg-gradient-to-r from-[#6C63FF] to-[#00D4FF]',
    },
  ];

  return (
    <div className="mb-6">
      {/* Key Metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
        {stats.map((s) => (
          <div key={s.label} className="bg-[#111820] border border-[#1B2433] rounded-2xl p-5 relative overflow-hidden">
            <div className={`absolute top-0 left-0 right-0 h-[2px] ${s.accent}`} />
            <p className="text-[10px] font-mono uppercase tracking-widest text-[#5A6578] mb-2">{s.label}</p>
            <p className={`${s.value.length > 15 ? 'text-[14px] leading-tight' : 'text-[28px] leading-none'} font-extrabold font-mono ${s.color}`}>{s.value}</p>
            <p className="text-[11px] text-[#5A6578] mt-1.5">{s.sub}</p>
          </div>
        ))}
      </div>

      {/* Executive Brief */}
      <div className="bg-[#111820] border border-[#1B2433] rounded-2xl p-6">
        <h2 className="text-[16px] font-bold text-[#E8ECF2] mb-4">Executive Brief</h2>
        {execSection ? (
          <SectionRenderer content={cleanContent(execSection.content)} className="text-[#8B97A8] leading-[1.75]" />
        ) : fallbackContent ? (
          <SectionRenderer content={cleanContent(fallbackContent)} className="text-[#8B97A8] leading-[1.75]" />
        ) : (
          <p className="text-[14px] text-[#5A6578]">
            Executive summary will appear once the report generation completes.
          </p>
        )}
      </div>
    </div>
  );
}
