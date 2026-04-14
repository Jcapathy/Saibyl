export const PLATFORM_NAMES: Record<string, string> = {
  twitter_x: 'Twitter / X',
  reddit: 'Reddit',
  linkedin: 'LinkedIn',
  instagram: 'Instagram',
  hacker_news: 'Hacker News',
  discord: 'Discord',
  news_comments: 'News Comments',
  custom: 'Custom',
};

export function formatPlatforms(platforms: string[]): string {
  return platforms.map((p) => PLATFORM_NAMES[p] || p).join(', ');
}

/* ── Chart color system ──────────────────────────────────────────── */

/** Semantic chart colors — used consistently across all report charts */
export const CHART_COLORS = {
  subjectA: '#6C63FF',   // Purple — Primary entity
  subjectB: '#00D4FF',   // Cyan — Secondary entity
  neutral:  '#D4A84B',   // Gold — Moderate / Undecided
  positive: '#34D399',   // Green — Positive movement
  negative: '#F87171',   // Red — Negative movement
} as const;

/** Ordered palette for bar/line charts with multiple series */
export const CHART_PALETTE = [
  CHART_COLORS.subjectA,
  CHART_COLORS.subjectB,
  CHART_COLORS.neutral,
  CHART_COLORS.positive,
  CHART_COLORS.negative,
  '#818CF8', // Light purple — overflow series
];

/** High-contrast print-safe palette (same order as CHART_PALETTE) */
export const PRINT_PALETTE = ['#4338ca', '#0891b2', '#b8860b', '#059669', '#dc2626', '#6d28d9'];

/** Pie chart colors: [positive, neutral, negative] */
export const PIE_COLORS = [CHART_COLORS.positive, CHART_COLORS.neutral, CHART_COLORS.negative] as const;
export const PRINT_PIE_COLORS = ['#059669', '#b8860b', '#dc2626'] as const;

/** Per-platform colors for bar charts and breakdowns */
export const PLATFORM_COLORS: Record<string, string> = {
  twitter_x:     CHART_COLORS.subjectA,  // Purple
  reddit:        CHART_COLORS.negative,  // Red
  linkedin:      CHART_COLORS.neutral,   // Gold
  instagram:     CHART_COLORS.subjectB,  // Cyan
  hacker_news:   '#818CF8',              // Light purple
  discord:       '#A78BFA',              // Violet
  news_comments: CHART_COLORS.positive,  // Green
  custom:        '#94A3B8',              // Slate
};

/** Resolve a platform color by platform key or display name */
export function platformColor(nameOrKey: string): string {
  // Direct key match
  if (PLATFORM_COLORS[nameOrKey]) return PLATFORM_COLORS[nameOrKey];
  // Match by display name (e.g., "Twitter / X" → twitter_x)
  const lower = nameOrKey.toLowerCase();
  for (const [key, color] of Object.entries(PLATFORM_COLORS)) {
    const displayName = (PLATFORM_NAMES[key] ?? '').toLowerCase();
    if (lower === displayName || displayName === lower) return color;
    // Partial matching for flexibility
    if (lower.includes(key.replace(/_/g, ' ')) || lower.includes(key.replace(/_/g, ''))) return color;
    if (displayName && (lower.includes(displayName) || displayName.includes(lower))) return color;
  }
  return CHART_PALETTE[0]; // fallback
}

/** Print-safe per-platform colors */
export const PRINT_PLATFORM_COLORS: Record<string, string> = {
  twitter_x:     '#4338ca',
  reddit:        '#dc2626',
  linkedin:      '#b8860b',
  instagram:     '#0891b2',
  hacker_news:   '#6d28d9',
  discord:       '#7c3aed',
  news_comments: '#059669',
  custom:        '#64748b',
};

/** Classify a sentiment value into a labelled bucket */
export function classifySentiment(v: number): { label: string; color: string } {
  if (v >= 0.5)  return { label: 'Strongly Positive', color: CHART_COLORS.positive };
  if (v >= 0.2)  return { label: 'Positive',          color: CHART_COLORS.positive };
  if (v >= -0.2) return { label: 'Moderate/Undecided', color: CHART_COLORS.neutral };
  if (v > -0.5)  return { label: 'Negative',          color: CHART_COLORS.negative };
  return { label: 'Strongly Negative', color: CHART_COLORS.negative };
}

/** Return a bar color for a single sentiment value */
export function sentimentBarColor(v: number): string {
  if (v >= 0.2) return CHART_COLORS.positive;
  if (v >= -0.2) return CHART_COLORS.neutral;
  return CHART_COLORS.negative;
}

/** Terminal statuses — simulation is done and won't change */
export const TERMINAL_STATUSES = ['complete', 'completed', 'failed', 'stopped'];

/** Active statuses — simulation is in progress */
export const ACTIVE_STATUSES = ['preparing', 'running'];

/** Idle statuses — simulation can be (re)started */
export const IDLE_STATUSES = ['draft', 'ready', 'failed'];
