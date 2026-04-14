import ReactMarkdown from 'react-markdown';

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
  riskCount?: number;
}

export default function ExecutiveSummary({
  report,
  sentiment,
  engagement,
  controversy,
  riskCount,
}: ExecutiveSummaryProps) {
  const execSection = report.sections.find(
    (s) =>
      s.section_type === 'executive_summary' ||
      s.title.toLowerCase().includes('executive') ||
      s.title.toLowerCase().includes('summary'),
  );

  const stats = [
    { label: 'Sentiment', value: sentiment != null ? `${(sentiment * 100).toFixed(0)}%` : '--', color: 'text-[#00D4FF]' },
    { label: 'Engagement', value: engagement != null ? `${(engagement * 100).toFixed(0)}%` : '--', color: 'text-[#C9A227]' },
    { label: 'Controversy', value: controversy != null ? `${(controversy * 100).toFixed(0)}%` : '--', color: 'text-[#FF6B6B]' },
    { label: 'Risks Found', value: riskCount != null ? String(riskCount) : '--', color: 'text-[#8B97A8]' },
  ];

  return (
    <div className="bg-[#111820] border border-[#1B2433] rounded-2xl p-6 mb-6">
      <h2 className="text-[18px] font-bold text-[#E8ECF2] mb-4">Executive Summary</h2>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {stats.map((s) => (
          <div key={s.label} className="bg-[#0D1117] border border-[#1B2433] rounded-xl p-4 text-center">
            <p className="text-[11px] uppercase tracking-wider text-[#5A6578] mb-1">{s.label}</p>
            <p className={`text-[24px] font-extrabold ${s.color}`}>{s.value}</p>
          </div>
        ))}
      </div>

      {execSection ? (
        <div className="prose prose-sm prose-invert max-w-none">
          <ReactMarkdown>{execSection.content}</ReactMarkdown>
        </div>
      ) : (
        <p className="text-[14px] text-[#5A6578]">
          Executive summary data will populate once the simulation completes with structured output.
        </p>
      )}
    </div>
  );
}
