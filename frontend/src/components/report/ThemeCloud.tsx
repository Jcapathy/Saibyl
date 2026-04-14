interface Theme {
  label: string;
  weight: number;
  sentiment: 'positive' | 'negative' | 'neutral' | 'trending';
}

interface ThemeCloudProps {
  themes?: Theme[];
}

const sentimentColors: Record<Theme['sentiment'], string> = {
  positive: 'text-[#00D4FF]',
  negative: 'text-[#FF6B6B]',
  neutral: 'text-[#8B97A8]',
  trending: 'text-[#C9A227]',
};

export default function ThemeCloud({ themes }: ThemeCloudProps) {
  if (!themes || themes.length === 0) {
    return (
      <div className="bg-[#111820] border border-[#1B2433] rounded-2xl p-6 mb-6">
        <h3 className="text-[16px] font-bold text-[#E8ECF2] mb-3">Theme Cloud</h3>
        <p className="text-[13px] text-[#5A6578]">
          Theme analysis will be available with structured report data.
        </p>
      </div>
    );
  }

  const maxWeight = Math.max(...themes.map((t) => t.weight));

  return (
    <div className="bg-[#111820] border border-[#1B2433] rounded-2xl p-6 mb-6">
      <h3 className="text-[16px] font-bold text-[#E8ECF2] mb-4">Theme Cloud</h3>
      <div className="flex flex-wrap gap-2">
        {themes.map((t) => {
          const scale = 0.75 + (t.weight / maxWeight) * 0.75;
          return (
            <span
              key={t.label}
              className={`inline-block px-3 py-1.5 rounded-full bg-[#0D1117] border border-[#1B2433] font-medium ${sentimentColors[t.sentiment]}`}
              style={{ fontSize: `${scale}rem` }}
            >
              {t.label}
            </span>
          );
        })}
      </div>
    </div>
  );
}
