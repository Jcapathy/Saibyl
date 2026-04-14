import SectionRenderer from '@/components/report/SectionRenderer';

const PREAMBLE_VERBS =
  'gather|start|begin|analyze|look|pull|search|investigate|examine|collect|retrieve|check|review|query|explore|write|assess|evaluate|compile|synthesize|research|identify|determine|provide';

/** Strip tool-use artifacts and ReACT traces from AI-generated content. */
function cleanContent(raw: string): string {
  // 1a. Strip full preamble-through-ANSWER blocks
  let text = raw.replace(
    new RegExp(`(?:I'll|I will|Let me)\\s+(?:\\w+\\s+)*?(?:${PREAMBLE_VERBS})[\\s\\S]*?ANSWER:\\s*`, 'gi'),
    '',
  );
  // 1b. Strip preamble sentences with no ANSWER (e.g. "I'll systematically gather … section.")
  text = text.replace(
    new RegExp(`(?:I'll|I will|Let me)\\s+(?:\\w+\\s+)*?(?:${PREAMBLE_VERBS})\\b[^.]*\\.\\s*`, 'gi'),
    '',
  );
  // 2. Strip standalone ANSWER: markers
  text = text.replace(/^ANSWER:\s*/gm, '');

  return text
    .split('\n')
    .filter(line => {
      const trimmed = line.trim();
      // Remove TOOL: lines (ReACT tool calls)
      if (/^(?:>\s*)?TOOL:\s/i.test(trimmed)) return false;
      // Remove other tool-use artifact patterns
      if (/^(?:>\s*)?(?:Action:|Observation:|search_web|read_url|get_page)\b/i.test(trimmed)) return false;
      if (/^(?:Using tool|Calling tool|Tool call|Tool output|Tool result)\b/i.test(trimmed)) return false;
      if (/^(?:Thought|Reasoning):\s/i.test(trimmed)) return false;
      return true;
    })
    .join('\n')
    // Clean up multiple blank lines left behind
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

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
}

function sentimentLabel(v: number): string {
  if (v >= 0.5) return 'Strongly Positive';
  if (v >= 0.2) return 'Positive';
  if (v >= -0.2) return 'Mixed';
  if (v >= -0.5) return 'Negative';
  return 'Strongly Negative';
}

function sentimentColor(v: number | undefined): string {
  if (v == null) return 'text-[#8B97A8]';
  if (v >= 0.2) return 'text-[#22C55E]';
  if (v >= -0.2) return 'text-[#F59E0B]';
  return 'text-[#EF4444]';
}

export default function ExecutiveSummary({
  report,
  sentiment,
  engagement,
  controversy,
  controversyLabel,
  riskCount,
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

  const stats = [
    {
      label: 'Sentiment',
      value: sentiment != null ? (sentiment >= 0 ? '+' : '') + sentiment.toFixed(2) : '—',
      sub: sentiment != null ? sentimentLabel(sentiment) : 'Pending',
      color: sentimentColor(sentiment),
      accent: 'bg-gradient-to-r from-[#5B5FEE] to-[#00D4FF]',
    },
    {
      label: 'Engagement',
      value: engagement != null ? `${(engagement * 10).toFixed(1)} / 10` : '—',
      sub: engagement != null ? (engagement >= 0.7 ? 'High virality potential' : 'Moderate reach') : 'Pending',
      color: 'text-[#00D4FF]',
      accent: 'bg-[#22C55E]',
    },
    {
      label: 'Controversy',
      value: controversyLabel ?? (controversy != null ? controversy.toFixed(2) : '—'),
      sub: controversy != null
        ? controversy < 0.3 ? 'Low — Minimal polarization' : controversy < 0.6 ? 'Moderate' : 'High — Significant polarization'
        : 'Pending',
      color: controversy != null ? (controversy < 0.3 ? 'text-[#22C55E]' : controversy < 0.6 ? 'text-[#F59E0B]' : 'text-[#EF4444]') : 'text-[#8B97A8]',
      accent: 'bg-[#F59E0B]',
    },
    {
      label: 'Risks Found',
      value: riskCount != null ? String(riskCount) : '—',
      sub: riskCount != null ? (riskCount === 0 ? 'No risks detected' : `${riskCount} risk${riskCount > 1 ? 's' : ''} identified`) : 'Pending',
      color: riskCount != null && riskCount > 3 ? 'text-[#EF4444]' : 'text-[#8B97A8]',
      accent: 'bg-[#EF4444]',
    },
  ];

  return (
    <div className="mb-6">
      {/* Key Metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {stats.map((s) => (
          <div key={s.label} className="bg-[#111820] border border-[#1B2433] rounded-2xl p-5 relative overflow-hidden">
            <div className={`absolute top-0 left-0 right-0 h-[2px] ${s.accent}`} />
            <p className="text-[10px] font-mono uppercase tracking-widest text-[#5A6578] mb-2">{s.label}</p>
            <p className={`text-[28px] font-extrabold font-mono leading-none ${s.color}`}>{s.value}</p>
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
