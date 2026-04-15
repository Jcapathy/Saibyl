interface PersonaAnalysisProps {
  personas?: { name: string; sentiment: number; engagement: number; topTheme: string; quote: string }[];
  headline?: string;
}

export default function PersonaAnalysis({ personas, headline }: PersonaAnalysisProps) {
  if (!personas || personas.length === 0) {
    return (
      <div className="bg-[#111820] border border-[#1B2433] rounded-2xl p-6">
        <h3 className="text-[16px] font-bold text-[#E8ECF2] mb-3">Persona Analysis</h3>
        <p className="text-[13px] text-[#5A6578]">
          Persona-level analysis will be available with structured report data.
        </p>
      </div>
    );
  }

  return (
    <div className="bg-[#111820] border border-[#1B2433] rounded-2xl p-6">
      {headline && (
        <p className="text-[14px] font-bold text-[#E8ECF2] mb-2 leading-snug">{headline}</p>
      )}
      <h3 className="text-[16px] font-bold text-[#E8ECF2] mb-4">Persona Analysis</h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {personas.map((p) => (
          <div key={p.name} className="bg-[#0D1117] border border-[#1B2433] rounded-xl p-4">
            <p className="text-[13px] font-semibold text-[#E8ECF2] mb-2">{p.name}</p>
            <div className="space-y-1.5">
              <div className="flex justify-between text-[11px]">
                <span className="text-[#5A6578]">Sentiment</span>
                <span className="text-[#00D4FF]">{p.sentiment >= 0 ? '+' : ''}{p.sentiment.toFixed(2)}</span>
              </div>
              <div className="h-1.5 bg-[#111820] rounded-full overflow-hidden">
                <div className="h-full bg-[#00D4FF] rounded-full" style={{ width: `${((p.sentiment + 1) / 2) * 100}%` }} />
              </div>
              <div className="flex justify-between text-[11px]">
                <span className="text-[#5A6578]">Engagement</span>
                <span className="text-[#C9A227]">{(p.engagement * 100).toFixed(0)}%</span>
              </div>
              <div className="h-1.5 bg-[#111820] rounded-full overflow-hidden">
                <div className="h-full bg-[#C9A227] rounded-full" style={{ width: `${p.engagement * 100}%` }} />
              </div>
              <p className="text-[10px] text-[#5A6578] mt-1">Theme: {p.topTheme}</p>
              <p className="text-[11px] text-[#8B97A8] italic mt-1 line-clamp-2">&ldquo;{p.quote}&rdquo;</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
