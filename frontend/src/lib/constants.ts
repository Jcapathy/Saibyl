export const PLATFORM_NAMES: Record<string, string> = {
  twitter_x: 'Twitter / X',
  reddit: 'Reddit',
  linkedin: 'LinkedIn',
  instagram: 'Instagram',
  tiktok: 'TikTok',
  youtube: 'YouTube',
  facebook: 'Facebook',
  threads: 'Threads',
  hacker_news: 'Hacker News',
  discord: 'Discord',
  news_comments: 'News Comments',
  custom: 'Custom',
};

export function formatPlatforms(platforms: string[]): string {
  return platforms.map((p) => PLATFORM_NAMES[p] || p).join(', ');
}

/* ── Chart color system ──────────────────────────────────────────── */

/** Semantic chart colors — used consistently across all report charts.
    Light-ground palette: each value doubles as a bar fill on white and as
    occasional small text (sentimentBarColor feeds an 11px readout), so every
    value holds ≥4.5:1 on white. */
export const CHART_COLORS = {
  subjectA: '#6a4fe0',   // Violet — Primary entity
  subjectB: '#286cf0',   // Blue — Secondary entity
  neutral:  '#b45309',   // Amber — Moderate / Undecided
  positive: '#0e7d55',   // Green — Positive movement
  negative: '#d92d3c',   // Red — Negative movement
} as const;

/** Ordered palette for bar/line charts with multiple series */
export const CHART_PALETTE = [
  CHART_COLORS.subjectA,
  CHART_COLORS.subjectB,
  CHART_COLORS.neutral,
  CHART_COLORS.positive,
  CHART_COLORS.negative,
  '#8b73ee', // Light violet — overflow series
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
  tiktok:        '#EE1D52',              // TikTok pink
  youtube:       '#FF0000',              // YouTube red
  facebook:      '#1877F2',              // Facebook blue
  threads:       '#14294a',              // Threads — ink, not pure black
  hacker_news:   '#8b73ee',              // Light violet
  discord:       '#6a4fe0',              // Violet
  news_comments: CHART_COLORS.positive,  // Green
  custom:        '#60718e',              // Slate
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
  tiktok:        '#EE1D52',
  youtube:       '#c00',
  facebook:      '#1877F2',
  threads:       '#333',
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

/* ── Simulation status ───────────────────────────────────────────── */

/**
 * Every value the backend writes to `simulations.status`, in lifecycle order.
 *
 * Written by `app/api/simulations.py` and `app/workers/simulation_tasks.py`.
 * The column has no CHECK constraint, so nothing but this list stands between
 * a new backend status and a page that silently stops polling — `analyzing`
 * was missing here and froze the detail page for the whole measurement pass.
 * Add to this list before adding to any of the sets below.
 */
export const SIMULATION_STATUSES = [
  'draft',
  'preparing',
  'ready',
  'running',
  'analyzing',
  'complete',
  'stopped',
  'failed',
] as const;

export type SimulationStatus = (typeof SIMULATION_STATUSES)[number];

/**
 * Terminal — the run is over and the status will not change again.
 *
 * `completed` is not written by the backend; it is accepted here because the
 * scoring route still reads it and older rows may carry it.
 */
export const TERMINAL_STATUSES: string[] = ['complete', 'completed', 'failed', 'stopped'];

/**
 * In flight — keep polling.
 *
 * `analyzing` is the post-run measurement pass. It is not visible progress,
 * but it is the window in which the report becomes available, so a page that
 * stops polling here never shows the link to it.
 */
export const ACTIVE_STATUSES: string[] = ['preparing', 'running', 'analyzing'];

/** Idle — the run can be started or restarted. */
export const IDLE_STATUSES: string[] = ['draft', 'ready', 'failed'];

/* ── Report status ───────────────────────────────────────────────── */

/** Every value the backend writes to `reports.status`. */
export const REPORT_STATUSES = ['pending', 'generating', 'complete', 'failed'] as const;

export type ReportStatus = (typeof REPORT_STATUSES)[number];

/**
 * Report generation is over — stop polling.
 *
 * `failed` belongs here: a failed report has no markdown and no section
 * content, so a poll that only tests for emptiness never terminates.
 */
export const REPORT_TERMINAL_STATUSES: string[] = ['complete', 'completed', 'failed'];
