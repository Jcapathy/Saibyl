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
      {/* Value stays ink — the icon carries the accent, so color only ever
          encodes meaning, never decorates a numeral. */}
      <p className="text-[24px] font-extrabold leading-none text-saibyl-ink">
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
      ? '#0e7d55'
      : headline.trajectory === 'declining'
        ? '#d92d3c'
        : '#60718e';

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      <Stat
        label="How the room felt"
        value={valence.n > 0 ? formatSigned(valence.mean) : '—'}
        sub={
          valence.n === 0
            ? 'Nobody said anything we could measure.'
            : valence.n === 1
              ? 'Only one person said anything we could measure, so this is one voice rather than a reading of the room.'
              : `Somewhere between ${formatSigned(valence.lower)} and ${formatSigned(valence.upper)}, across ${valence.n} people. +1 is loved it, −1 is hated it.`
        }
        icon={<Users className="w-4 h-4" />}
        accent="#286cf0"
      />
      <Stat
        label="Which way it moved"
        value={
          headline.trajectory === 'flat'
            ? 'Held steady'
            : `${formatSigned(headline.trajectory_delta)}`
        }
        sub={`${TRAJECTORY_COPY[headline.trajectory]}, over ${quality.rounds} rounds.`}
        icon={trendIcon}
        accent={trendAccent}
      />
      <Stat
        label="For and against"
        value={`${headline.stance.oppose_pct.toFixed(0)}% against`}
        sub={`${headline.stance.support_pct.toFixed(0)}% for, ${headline.stance.undecided_pct.toFixed(0)}% undecided. ${headline.polarization_pct.toFixed(0)}% of what was said sat on the opposite side from the room's average.`}
        icon={<Split className="w-4 h-4" />}
        accent="#286cf0"
      />
      <Stat
        label="New ground"
        value={`${headline.novel_claim_pct.toFixed(0)}%`}
        sub="How much of what was said brought up something the conversation had not already covered. The rest is people repeating each other."
        icon={<Sparkles className="w-4 h-4" />}
        accent="#6a4fe0"
      />
    </div>
  );
}
