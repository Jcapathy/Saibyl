interface Theme {
  label: string;
  weight: number;
  sentiment: 'positive' | 'negative' | 'neutral' | 'trending';
}

interface ThemeCloudProps {
  themes?: Theme[];
  headline?: string;
}

const sentimentColors: Record<Theme['sentiment'], string> = {
  positive: 'text-[#34D399]',
  negative: 'text-[#F87171]',
  neutral: 'text-[#D4A84B]',
  trending: 'text-[#00D4FF]',
};

export default function ThemeCloud({ themes, headline }: ThemeCloudProps) {
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
      {headline && (
        <p className="text-[14px] font-bold text-[#E8ECF2] mb-2 leading-snug">{headline}</p>
      )}
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
