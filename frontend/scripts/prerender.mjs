/**
 * Write static HTML for the public routes, after `vite build`.
 *
 * Runs as the last step of `npm run build`, which is what Render runs. It reads
 * the freshly built `dist/index.html`, renders each public page to a string,
 * injects it into the app's mount point, and writes `dist/<route>/index.html`.
 * The client bundle is untouched: React hydrates over the markup exactly as it
 * would have mounted into an empty div, so behaviour for a real visitor does
 * not change.
 *
 * **Why bother:** no major AI crawler runs JavaScript, so without this every
 * answer engine fetches Saibyl and reads an empty div. See `SEO_AEO.md`.
 *
 * **It fails the build rather than warning.** A prerender that quietly skips is
 * worse than no prerender: the deploy goes green, the files are missing, and
 * nobody finds out until someone asks why the site is not cited anywhere. The
 * one exception is an environment with no `dist/index.html` at all, which means
 * this ran outside a build and should say so plainly.
 */
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { createServer } from 'vite';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const DIST = join(ROOT, 'dist');
const SHELL = join(DIST, 'index.html');

// The mount point Vite's built shell ships. If the app root's id ever changes,
// this must change with it — so it is asserted rather than assumed.
const MOUNT = '<div id="root"></div>';

async function main() {
  if (!existsSync(SHELL)) {
    throw new Error(
      `No dist/index.html. Run \`vite build\` before this script; it is meant ` +
        `to be the last step of \`npm run build\`, not a standalone command.`,
    );
  }

  const shell = await readFile(SHELL, 'utf8');
  if (!shell.includes(MOUNT)) {
    throw new Error(
      `dist/index.html does not contain ${MOUNT}. The mount point changed, and ` +
        `injecting into the wrong place would ship a page with the markup in ` +
        `the wrong element or duplicated. Update MOUNT in this script.`,
    );
  }

  // `ssrLoadModule` transpiles the TSX, resolves the `@/` alias from
  // vite.config, and stubs CSS imports. That is why this uses a Vite server
  // rather than a second SSR build: no parallel config to keep in step.
  const vite = await createServer({
    root: ROOT,
    logLevel: 'warn',
    server: { middlewareMode: true },
    appType: 'custom',
  });

  try {
    const { render, PRERENDERED_ROUTES } = await vite.ssrLoadModule(
      '/src/entry-server.tsx',
    );

    for (const route of PRERENDERED_ROUTES) {
      const html = render(route);
      if (!html || html.length < 500) {
        throw new Error(
          `${route} rendered ${html?.length ?? 0} characters, which is not a ` +
            `page. Something threw during render, or the route points at the ` +
            `wrong component.`,
        );
      }

      const page = shell.replace(MOUNT, `<div id="root">${html}</div>`);
      const outDir = route === '/' ? DIST : join(DIST, route);
      await mkdir(outDir, { recursive: true });
      await writeFile(join(outDir, 'index.html'), page, 'utf8');

      // **And a sibling `<route>.html`, which is what makes this work without
      // a rewrite rule.**
      //
      // `dist/privacy/index.html` alone serves `/privacy/` but not `/privacy`:
      // the extensionless form falls through to the SPA catch-all and receives
      // the homepage. A human never notices, because React boots and routes
      // client-side. An AI crawler does not run JavaScript, so it asks for
      // `/privacy` and is handed homepage markup — which is the whole thing
      // prerendering exists to prevent, quietly not working.
      //
      // The rewrite that fixes it lives in `render.yaml` and was committed
      // before the domain went live, and it did not apply: Render deploys code
      // on push but Blueprint config needs a separate sync. So the file is
      // written here instead, in the build, on the path that demonstrably runs.
      // Static hosts resolve `/privacy` to `privacy.html` by convention.
      if (route !== '/') {
        await writeFile(join(DIST, `${route.replace(/^\//, '')}.html`), page, 'utf8');
      }

      console.log(
        `prerendered ${route.padEnd(10)} ${String(html.length).padStart(7)} chars`,
      );
    }
  } finally {
    await vite.close();
  }
}

await main();
