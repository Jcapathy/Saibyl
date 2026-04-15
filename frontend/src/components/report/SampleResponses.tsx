interface SampleResponsesProps {
  responses?: { persona: string; platform: string; text: string; sentiment: number }[];
  headline?: string;
}

export default function SampleResponses({ responses, headline }: SampleResponsesProps) {
  if (!responses || responses.length === 0) {
    return (
      <div className="bg-[#111820] border border-[#1B2433] rounded-2xl p-6 mb-6">
        <h3 className="text-[16px] font-bold text-[#E8ECF2] mb-3">Sample Responses</h3>
        <p className="text-[13px] text-[#5A6578]">
          Sample agent responses will be available with structured report data.
        </p>
      </div>
    );
  }

  return (
    <div className="bg-[#111820] border border-[#1B2433] rounded-2xl p-6 mb-6">
      {headline && (
        <p className="text-[14px] font-bold text-[#E8ECF2] mb-2 leading-snug">{headline}</p>
      )}
      <h3 className="text-[16px] font-bold text-[#E8ECF2] mb-4">Sample Responses</h3>
      <div className="space-y-3">
        {responses.map((r, i) => {
          const sentColor = r.sentiment >= 0.3 ? 'border-[#34D399]/30' : r.sentiment >= 0 ? 'border-[#D4A84B]/30' : 'border-[#F87171]/30';
          return (
            <div key={i} className={`bg-[#0D1117] border ${sentColor} rounded-xl p-4`}>
              <div className="flex items-center gap-2 mb-2">
                <span className="text-[12px] font-semibold text-[#E8ECF2]">{r.persona}</span>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#1B2433] text-[#8B97A8]">{r.platform}</span>
                <span className="ml-auto text-[10px] text-[#5A6578]">Sentiment: {r.sentiment >= 0 ? '+' : ''}{r.sentiment.toFixed(2)}</span>
              </div>
              <p className="text-[13px] text-[#8B97A8] leading-relaxed">{r.text}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
