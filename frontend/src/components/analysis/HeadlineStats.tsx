import { TrendingDown, TrendingUp, Minus, Users, Split, Sparkles } from 'lucide-react';
import {
  TRAJECTORY_COPY,
  formatSigned,
  type Headline,
  type QualityBlock,
} from '@/lib/analysis';

function Stat({
  label,
  value,
  sub,
  icon,
  accent,
}: {
  label: string;
  value: string;
  sub: string;
  icon: React.ReactNode;
  accent: string;
}) {
  return (
    <div className="bg-saibyl-surface border border-saibyl-border rounded-2xl p-5">
      <div className="flex items-center gap-2 mb-2">
        <span style={{ color: accent }}>{icon}</span>
        <span className="text-[10px] uppercase tracking-wider text-saibyl-muted">
          {label}
        </span>
      </div>
      <p className="text-[24px] font-extrabold leading-none" style={{ color: accent }}>
        {value}
      </p>
      <p className="text-[11px] text-saibyl-muted mt-2 leading-relaxed">{sub}</p>
    </div>
  );
}

/**
 * The four numbers a reader sees first.
 *
 * Each carries what it rests on in its own subtitle rather than in a footnote —
 * a stat card is exactly where a number gets screenshotted and quoted without
 * its context, so the context travels with it.
 */
export default function HeadlineStats({
  headline,
  quality,
}: {
  headline: Headline;
  quality: QualityBlock;
}) {
  const { valence } = headline;
  const trendIcon =
    headline.trajectory === 'improving' ? (
      <TrendingUp className="w-4 h-4" />
    ) : headline.trajectory === 'declining' ? (
      <TrendingDown className="w-4 h-4" />
    ) : (
      <Minus className="w-4 h-4" />
    );
  const trendAccent =
    headline.trajectory === 'improving'
      ? '#22C55E'
      : headline.trajectory === 'declining'
        ? '#EF4444'
        : '#8B97A8';

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      <Stat
        label="Overall sentiment"
        value={valence.n > 0 ? formatSigned(valence.mean) : '—'}
        sub={
          valence.n < 2
            ? `${valence.n} agent produced a measurable opinion — not resolvable.`
            : `95% CI ${formatSigned(valence.lower)} to ${formatSigned(valence.upper)}, across ${valence.n} agents.`
        }
        icon={<Users className="w-4 h-4" />}
        accent="#C9A227"
      />
      <Stat
        label="Trajectory"
        value={
          headline.trajectory === 'flat'
            ? 'Flat'
            : `${formatSigned(headline.trajectory_delta)}`
        }
        sub={`${TRAJECTORY_COPY[headline.trajectory]}, over ${quality.rounds} measured rounds.`}
        icon={trendIcon}
        accent={trendAccent}
      />
      <Stat
        label="Split"
        value={`${headline.stance.oppose_pct.toFixed(0)}% oppose`}
        sub={`${headline.stance.support_pct.toFixed(0)}% support, ${headline.stance.undecided_pct.toFixed(0)}% undecided. ${headline.polarization_pct.toFixed(0)}% of events sat opposite the run's own mean.`}
        icon={<Split className="w-4 h-4" />}
        accent="#2563EB"
      />
      <Stat
        label="New ground"
        value={`${headline.novel_claim_pct.toFixed(0)}%`}
        sub="Share of events introducing a claim not already in the conversation. The rest is the audience repeating itself."
        icon={<Sparkles className="w-4 h-4" />}
        accent="#8B5CF6"
      />
    </div>
  );
}
