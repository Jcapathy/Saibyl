interface Risk {
  id: string;
  category: string;
  description: string;
  likelihood: number;
  impact: number;
  severity: number;
  action: string;
}

interface RiskMatrixProps {
  risks?: Risk[];
}

function severityColor(severity: number): string {
  if (severity >= 0.7) return 'bg-[#FF6B6B]/20 text-[#FF6B6B] border-[#FF6B6B]/30';
  if (severity >= 0.4) return 'bg-[#C9A227]/20 text-[#C9A227] border-[#C9A227]/30';
  return 'bg-[#00D4FF]/20 text-[#00D4FF] border-[#00D4FF]/30';
}

export default function RiskMatrix({ risks }: RiskMatrixProps) {
  if (!risks || risks.length === 0) {
    return (
      <div className="bg-[#111820] border border-[#1B2433] rounded-2xl p-6 mb-6">
        <h3 className="text-[16px] font-bold text-[#E8ECF2] mb-3">Risk Assessment Matrix</h3>
        <p className="text-[13px] text-[#5A6578]">
          Risk analysis will be available with structured report data.
        </p>
      </div>
    );
  }

  const sorted = [...risks].sort((a, b) => b.severity - a.severity);

  return (
    <div className="bg-[#111820] border border-[#1B2433] rounded-2xl p-6 mb-6">
      <h3 className="text-[16px] font-bold text-[#E8ECF2] mb-4">Risk Assessment Matrix</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="border-b border-[#1B2433]">
              <th className="text-left py-2 px-3 text-[#5A6578] font-medium">Category</th>
              <th className="text-left py-2 px-3 text-[#5A6578] font-medium">Description</th>
              <th className="text-center py-2 px-3 text-[#5A6578] font-medium">Likelihood</th>
              <th className="text-center py-2 px-3 text-[#5A6578] font-medium">Impact</th>
              <th className="text-center py-2 px-3 text-[#5A6578] font-medium">Severity</th>
              <th className="text-left py-2 px-3 text-[#5A6578] font-medium">Action</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr key={r.id} className="border-b border-[#1B2433]/50 hover:bg-[#0D1117]/50">
                <td className="py-2.5 px-3 text-[#E8ECF2] font-medium">{r.category}</td>
                <td className="py-2.5 px-3 text-[#8B97A8] max-w-[240px]">{r.description}</td>
                <td className="py-2.5 px-3 text-center text-[#8B97A8]">{(r.likelihood * 100).toFixed(0)}%</td>
                <td className="py-2.5 px-3 text-center text-[#8B97A8]">{(r.impact * 100).toFixed(0)}%</td>
                <td className="py-2.5 px-3 text-center">
                  <span className={`inline-block px-2 py-0.5 rounded-full text-[11px] font-semibold border ${severityColor(r.severity)}`}>
                    {(r.severity * 100).toFixed(0)}%
                  </span>
                </td>
                <td className="py-2.5 px-3 text-[#8B97A8]">{r.action}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
