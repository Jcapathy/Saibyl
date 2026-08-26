import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

/**
 * The prerender's two halves must agree, and nothing else makes them.
 *
 * `npm run build` writes a static HTML file per public route, so an answer
 * engine that does not execute JavaScript has something to read. Render then
 * has to actually serve those files: its `/*` rewrite hands every unmatched
 * path the empty SPA shell, which is the state that made every word of this
 * site invisible to ChatGPT, Claude and Perplexity to begin with.
 *
 * So a route can be broken in two directions, and neither one fails a build:
 *
 *   · prerendered but not routed, and the file is written and never served;
 *   · routed but not prerendered, and the rewrite points at a 404.
 *
 * Both are silent. This is the only thing that notices.
 */

const ROOT = resolve(__dirname, '../..');
const REPO = resolve(ROOT, '..');

const entryServer = readFileSync(resolve(ROOT, 'src/entry-server.tsx'), 'utf8');
const renderYaml = readFileSync(resolve(REPO, 'render.yaml'), 'utf8');

/** The routes the build actually writes files for. */
function prerenderedRoutes(): string[] {
  const block = entryServer.match(/PRERENDERED_ROUTES\s*=\s*\[([^\]]*)\]/);
  if (!block) throw new Error('PRERENDERED_ROUTES not found in entry-server.tsx');
  return [...block[1].matchAll(/'([^']+)'/g)].map((m) => m[1]);
}

/** Explicit rewrites in the frontend static service, in order. */
function rewrites(): { source: string; destination: string }[] {
  const out: { source: string; destination: string }[] = [];
  const pattern = /source:\s*(\S+)\s*\n\s*destination:\s*(\S+)/g;
  for (const match of renderYaml.matchAll(pattern)) {
    out.push({ source: match[1], destination: match[2] });
  }
  return out;
}

describe('prerendered routes and Render rewrites', () => {
  it('writes a sibling <route>.html so the extensionless URL needs no rewrite', () => {
    /*
      `dist/privacy/index.html` alone serves `/privacy/` but not `/privacy`. The
      extensionless form fell through to the SPA catch-all and was answered with
      the homepage, byte for byte, on the live site. A human never noticed
      because React boots and routes client-side; an AI crawler does not run
      JavaScript, so it asked for `/privacy` and received homepage markup, which
      is precisely what prerendering exists to prevent.

      The `render.yaml` rewrite that fixes it was committed before the domain
      went live and never applied, because Render deploys code on push while
      Blueprint config needs a separate sync. So the build writes the file
      instead, on the path that demonstrably runs.
    */
    const script = readFileSync(resolve(ROOT, 'scripts/prerender.mjs'), 'utf8');

    expect(
      script,
      'the prerender no longer writes a sibling .html, so /privacy will serve the homepage again',
    ).toMatch(/\$\{route\.replace\([^)]*\)\}\.html/);
  });

  it('finds the routes the build writes files for', () => {
    const routes = prerenderedRoutes();

    expect(routes.length).toBeGreaterThan(0);
    expect(routes).toContain('/');
  });

  it('serves every prerendered route from its own file', () => {
    const rules = rewrites();

    for (const route of prerenderedRoutes()) {
      // `/` is `dist/index.html`, which is what the catch-all already points
      // at, so it needs no rule of its own.
      if (route === '/') continue;

      const rule = rules.find((r) => r.source === route);
      expect(
        rule,
        `${route} is prerendered but render.yaml has no rewrite for it, so the ` +
          `/* catch-all will serve the empty shell and the file is never read`,
      ).toBeDefined();
      expect(rule?.destination).toBe(`${route}/index.html`);
    }
  });

  it('puts the specific rewrites before the catch-all', () => {
    const rules = rewrites();
    const catchAll = rules.findIndex((r) => r.source === '/*');

    expect(catchAll, 'the /* catch-all is missing; the SPA would 404').toBeGreaterThan(-1);

    for (const route of prerenderedRoutes()) {
      if (route === '/') continue;
      const index = rules.findIndex((r) => r.source === route);
      expect(
        index,
        `${route} is routed after the /* catch-all, which matches first and ` +
          `makes the specific rule dead`,
      ).toBeLessThan(catchAll);
    }
  });

  it('does not route a path the build never writes', () => {
    const routes = prerenderedRoutes();

    for (const rule of rewrites()) {
      if (rule.source === '/*') continue;
      expect(
        routes,
        `render.yaml rewrites ${rule.source} to a prerendered file, but nothing ` +
          `prerenders it, so that path serves a 404`,
      ).toContain(rule.source);
    }
  });
});
