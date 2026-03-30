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

/** Terminal statuses — simulation is done and won't change */
export const TERMINAL_STATUSES = ['complete', 'completed', 'failed', 'stopped'];

/** Active statuses — simulation is in progress */
export const ACTIVE_STATUSES = ['preparing', 'running'];

/** Idle statuses — simulation can be (re)started */
export const IDLE_STATUSES = ['draft', 'ready', 'failed'];
