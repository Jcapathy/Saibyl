export default function SentimentBar({ value }: { value: number }) {
  // value: -1.0 to 1.0
  const pct = ((value + 1) / 2) * 100;
  const color =
    value > 0.2 ? 'bg-saibyl-positive' : value < -0.2 ? 'bg-saibyl-negative' : 'bg-saibyl-neutral';

  return (
    <div className="w-full h-2 bg-saibyl-elevated rounded-full overflow-hidden">
      <div className={`h-full ${color} transition-all`} style={{ width: `${pct}%` }} />
    </div>
  );
}
