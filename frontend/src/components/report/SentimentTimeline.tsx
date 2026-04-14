interface SentimentTimelineProps {
  data?: { time: string; sentiment: number }[];
}

export default function SentimentTimeline({ data }: SentimentTimelineProps) {
  if (!data || data.length === 0) {
    return (
      <div className="bg-[#111820] border border-[#1B2433] rounded-2xl p-6 mb-6">
        <h3 className="text-[16px] font-bold text-[#E8ECF2] mb-3">Sentiment Over Time</h3>
        <div className="h-40 flex items-center justify-center text-[#5A6578] text-[13px]">
          Timeline data will appear once structured sentiment data is available.
        </div>
      </div>
    );
  }

  const max = Math.max(...data.map((d) => Math.abs(d.sentiment)), 1);

  return (
    <div className="bg-[#111820] border border-[#1B2433] rounded-2xl p-6 mb-6">
      <h3 className="text-[16px] font-bold text-[#E8ECF2] mb-4">Sentiment Over Time</h3>
      <div className="flex items-end gap-1 h-40">
        {data.map((d, i) => {
          const height = (Math.abs(d.sentiment) / max) * 100;
          const color = d.sentiment >= 0 ? 'bg-[#00D4FF]' : 'bg-[#FF6B6B]';
          return (
            <div key={i} className="flex-1 flex flex-col items-center justify-end h-full">
              <div
                className={`w-full rounded-t ${color} min-h-[2px]`}
                style={{ height: `${Math.max(height, 2)}%` }}
                title={`${d.time}: ${d.sentiment.toFixed(2)}`}
              />
              <span className="text-[9px] text-[#5A6578] mt-1 truncate w-full text-center">
                {d.time}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
