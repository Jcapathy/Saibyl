/**
 * The route graph, read out of `App.tsx` rather than restated here.
 *
 * A hand-written copy of the routes would pass its own test forever while the
 * app drifted underneath it. Every node and every edge below comes from the
 * source: nodes from the `<Route>` tree, edges from the links each page
 * actually renders.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { SRC, sourceFiles, routeTargets, toPattern, type SourceFile } from './source';

export interface RouteNode {
  /** Full pattern, e.g. `/app/products/:p/audience`. */
  pattern: string;
  /** The component that renders it, e.g. `AudienceStagePage`. */
  component: string;
  /** Every ancestor layout component, outermost first. */
  layouts: string[];
  /** Where an index redirect points, if this is one. */
  redirectsTo: string | null;
}

const APP = join(SRC, 'App.tsx');

function importMap(source: string): Map<string, string> {
  const map = new Map<string, string>();
  for (const match of source.matchAll(/import\s+(\w+)\s+from\s+'([^']+)'/g)) {
    map.set(match[1], match[2]);
  }
  return map;
}

/** `@/pages/product/AudienceStagePage` -> `src/pages/product/AudienceStagePage.tsx` */
export function moduleToPath(specifier: string): string | null {
  if (!specifier.startsWith('@/')) return null;
  return `src/${specifier.slice(2)}.tsx`;
}

interface Tag {
  kind: 'open' | 'selfClosing' | 'close';
  text: string;
}

/**
 * Split the file into `<Route …>` / `<Route … />` / `</Route>` tokens.
 *
 * A line-based scan cannot do this. `<Route>` is written across several lines
 * here, and its `element={…}` attribute contains `>` characters of its own —
 * `element={<PageTransition><DashboardPage /></PageTransition>}`. So the scan
 * tracks brace depth and quoting, and only treats `>` at depth zero as the end
 * of the tag.
 *
 * The first version of this test was line-based, mis-parsed the multi-line
 * `<Route path="/app">` and reported every product route as unreachable. It was
 * wrong in the safe direction — a false alarm, not a false pass — which is the
 * direction a scan that gates a build should fail in.
 */
function routeTags(source: string): Tag[] {
  const tags: Tag[] = [];
  for (let i = 0; i < source.length; i += 1) {
    if (source.startsWith('</Route>', i)) {
      tags.push({ kind: 'close', text: '</Route>' });
      i += 7;
      continue;
    }
    if (!source.startsWith('<Route', i)) continue;

    let depth = 0;
    let quote: string | null = null;
    let j = i + 6;
    for (; j < source.length; j += 1) {
      const ch = source[j];
      if (quote) {
        if (ch === quote) quote = null;
        continue;
      }
      if (ch === '"' || ch === "'" || ch === '`') {
        quote = ch;
        continue;
      }
      if (ch === '{') depth += 1;
      else if (ch === '}') depth -= 1;
      else if (ch === '>' && depth === 0) break;
    }

    const text = source.slice(i, j + 1);
    tags.push({
      kind: /\/\s*>$/.test(text) ? 'selfClosing' : 'open',
      text,
    });
    i = j;
  }
  return tags;
}

/** Parse the `<Route>` tree into flat, fully-qualified patterns. */
export function routeNodes(): RouteNode[] {
  const source = readFileSync(APP, 'utf8');
  const nodes: RouteNode[] = [];
  const stack: { path: string; component: string }[] = [];

  for (const tag of routeTags(source)) {
    if (tag.kind === 'close') {
      stack.pop();
      continue;
    }

    const pathMatch = tag.text.match(/\bpath="([^"]*)"/);
    const indexRoute = /\bindex\b/.test(tag.text);
    const componentMatch = tag.text.match(/<(\w+Page|\w+Layout)\s*\/>/);
    const navigateMatch = tag.text.match(/<Navigate\s+to="([^"]+)"/);

    const segment = pathMatch ? pathMatch[1] : '';
    const parent = stack.length ? stack[stack.length - 1].path : '';
    const full = segment.startsWith('/')
      ? segment
      : `${parent}/${segment}`.replace(/\/+$/, '') || parent;

    const component = componentMatch ? componentMatch[1] : '';
    const layouts = stack.map((s) => s.component).filter(Boolean);

    if (indexRoute || pathMatch) {
      const base = indexRoute ? parent : full;
      nodes.push({
        pattern: normalise(base),
        component,
        layouts,
        redirectsTo: navigateMatch
          ? normalise(
              navigateMatch[1].startsWith('/')
                ? navigateMatch[1]
                : `${base}/${navigateMatch[1]}`,
            )
          : null,
      });
    }

    if (tag.kind === 'open') stack.push({ path: full, component });
  }

  return nodes;
}

function normalise(pattern: string): string {
  return (
    pattern
      .replace(/:\w+/g, ':p')
      // `settings/*` is a splat: a link to `/app/settings` lands on it, so the
      // two must compare equal or the walk reports a reachable page as lost.
      .replace(/\/\*$/, '')
      .replace(/\/+$/, '') || '/'
  );
}

/** Component name -> its source file. */
export function componentSources(): Map<string, SourceFile> {
  const source = readFileSync(APP, 'utf8');
  const imports = importMap(source);
  const byPath = new Map(sourceFiles().map((f) => [f.path, f]));
  const out = new Map<string, SourceFile>();
  for (const [name, specifier] of imports) {
    const path = moduleToPath(specifier);
    const file = path ? byPath.get(path) : undefined;
    if (file) out.set(name, file);
  }
  return out;
}

/**
 * How many clicks each route is from `/app`.
 *
 * An index redirect costs nothing — arriving at `/app` puts you on `/app/home`
 * without clicking. Links rendered by a layout are edges from every route that
 * layout wraps, which is what a persistent sidebar genuinely is.
 */
export function clickDepths(): Map<string, number> {
  const nodes = routeNodes();
  const sources = componentSources();

  const linksOf = (node: RouteNode): string[] => {
    const files = [node.component, ...node.layouts]
      .map((name) => sources.get(name))
      .filter((f): f is SourceFile => Boolean(f));
    return files.flatMap((f) => routeTargets(f).map(toPattern));
  };

  const byPattern = new Map(nodes.map((n) => [n.pattern, n]));
  const depths = new Map<string, number>();
  const queue: [string, number][] = [['/app', 0]];

  while (queue.length) {
    const [pattern, depth] = queue.shift()!;
    if (depths.has(pattern) && depths.get(pattern)! <= depth) continue;
    depths.set(pattern, depth);

    const node = byPattern.get(pattern);
    if (!node) continue;

    // A redirect is free — nobody clicks it.
    if (node.redirectsTo) queue.push([node.redirectsTo, depth]);

    for (const target of linksOf(node)) {
      if (byPattern.has(target)) queue.push([target, depth + 1]);
    }
  }

  return depths;
}
