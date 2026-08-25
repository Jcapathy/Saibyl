import { renderToString } from 'react-dom/server';
import { StaticRouter } from 'react-router-dom';

import LandingPage from '@/pages/LandingPage';
import PrivacyPage from '@/pages/PrivacyPage';
import TermsPage from '@/pages/TermsPage';

/**
 * Server-render the public pages, so an answer engine has something to read.
 *
 * **Why this exists.** No major AI crawler executes JavaScript — OAI-SearchBot,
 * ChatGPT-User, GPTBot, ClaudeBot and PerplexityBot were all measured as
 * non-rendering, Anthropic's own docs say its fetch tool cannot read
 * JS-rendered pages, and there is no contrary evidence. Saibyl is a
 * client-rendered SPA, so today every one of them fetches this site and
 * receives `<div id="root"></div>`. `docs/SEO_AEO.md` calls fixing that the
 * single biggest AEO unlock available, and it is the reason every word of
 * marketing copy on this site is currently invisible to the surfaces its
 * buyers actually use.
 *
 * **It renders the pages, not the app.** `App.tsx` carries the router for the
 * whole product: auth guards, a store that reads browser storage, providers,
 * and every screen behind the login. None of that is crawlable, none of it
 * belongs in a static file, and half of it would throw in Node. So this module
 * imports the three public pages directly and gives them the one piece of
 * context they actually need, which is a router for `<Link>`.
 *
 * **The reveal animation is left alone on purpose.** `useReveal` runs in an
 * effect, and effects do not run during `renderToString`, so this output ships
 * with `.reveal` elements in their pre-reveal state. That state is `opacity: 0`
 * — not `display: none` and not `visibility: hidden` — so the text is present
 * in the document and every text extractor reads it. Google renders the page
 * and the animation plays normally. Shipping the revealed state instead would
 * buy nothing and would cost the first-load motion, which is part of the
 * approved design rather than a garnish.
 */

/** The routes that are worth a static file: public, and fetching no data. */
export const PRERENDERED_ROUTES = ['/', '/privacy', '/terms'] as const;

const PAGES: Record<string, () => React.ReactElement> = {
  '/': LandingPage,
  '/privacy': PrivacyPage,
  '/terms': TermsPage,
};

export function render(url: string): string {
  const Page = PAGES[url];
  if (!Page) {
    throw new Error(
      `No page is registered for "${url}". Add it to PAGES, or drop it from ` +
        `PRERENDERED_ROUTES — a route in one and not the other writes an empty file.`,
    );
  }
  return renderToString(
    <StaticRouter location={url}>
      <Page />
    </StaticRouter>,
  );
}
