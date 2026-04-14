interface PlatformBreakdownProps {
  platforms?: { name: string; sentiment: number; agents: number }[];
}

export default function PlatformBreakdown({ platforms }: PlatformBreakdownProps) {
  if (!platforms || platforms.length === 0) {
    return (
      <div className="bg-[#111820] border border-[#1B2433] rounded-2xl p-6">
        <h3 className="text-[16px] font-bold text-[#E8ECF2] mb-3">Platform Breakdown</h3>
        <p className="text-[13px] text-[#5A6578]">
          Platform-specific analysis will be available with structured report data.
        </p>
      </div>
    );
  }

  return (
    <div className="bg-[#111820] border border-[#1B2433] rounded-2xl p-6">
      <h3 className="text-[16px] font-bold text-[#E8ECF2] mb-4">Platform Breakdown</h3>
      <div className="space-y-3">
        {platforms.map((p) => {
          const pct = ((p.sentiment + 1) / 2) * 100;
          const color = p.sentiment >= 0.3 ? '#00D4FF' : p.sentiment >= 0 ? '#C9A227' : '#FF6B6B';
          return (
            <div key={p.name}>
              <div className="flex justify-between text-[13px] mb-1">
                <span className="text-[#E8ECF2] font-medium">{p.name}</span>
                <span className="text-[#8B97A8]">
                  {p.agents} agents · {(p.sentiment * 100).toFixed(0)}% sentiment
                </span>
              </div>
              <div className="h-2 bg-[#0D1117] rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all"
                  style={{ width: `${pct}%`, backgroundColor: color }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
