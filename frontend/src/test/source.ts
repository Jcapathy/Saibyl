/**
 * Reading the source tree, so the acceptance tests check what ships.
 *
 * The five tests in `ia.test.ts` are static scans rather than renders, and that
 * is a deliberate trade. A render test asserts that a component behaves as its
 * props say; these assert something a render cannot reach — that **no screen
 * anywhere** breaks the rule. "Every empty state offers a way forward" is a
 * claim about the whole tree, and the only honest way to check it is to read
 * the whole tree.
 *
 * The cost is that a scan sees text, not semantics. Where that matters the
 * scanners below strip comments first, because a rule about what the founder
 * *reads* must not fire on a sentence explaining the rule.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

// `fileURLToPath`, not `URL.pathname` — the repo lives under "Saido Labs LLC"
// and `pathname` hands back `Saido%20Labs%20LLC`, which `readFileSync` then
// cannot open. The failure is a clean ENOENT rather than a silent empty scan,
// but only because `walk` reads the directory before it reads any file.
export const SRC = fileURLToPath(new URL('../', import.meta.url));

export interface SourceFile {
  /** Repo-relative, forward-slashed, e.g. `src/pages/product/AudienceStagePage.tsx`. */
  path: string;
  raw: string;
  /** `raw` with block and line comments blanked out, newlines preserved. */
  code: string;
}

const SKIP_DIRS = new Set(['node_modules', 'dist', 'test', 'remotion', 'assets']);

function walk(dir: string, out: string[]): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (!SKIP_DIRS.has(entry)) walk(full, out);
    } else if (/\.tsx?$/.test(entry) && !/\.test\.tsx?$/.test(entry)) {
      out.push(full);
    }
  }
  return out;
}

/**
 * Blank out comments, keeping every newline so line numbers survive.
 *
 * Not a parser. It does not understand a `//` inside a string literal, which
 * would blank the rest of that line. That produces false negatives (a jargon
 * word hidden after a slash-slash in a string), never false positives, and the
 * failure mode of a rule that under-fires is a rule somebody has to notice —
 * which is the safer direction for a scan that gates a build.
 */
function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, (match) => match.replace(/[^\n]/g, ' '))
    .replace(/\/\/[^\n]*/g, (match) => ' '.repeat(match.length));
}

let cache: SourceFile[] | null = null;

export function sourceFiles(): SourceFile[] {
  if (cache) return cache;
  const files = walk(SRC, []);
  cache = files.map((full) => {
    const raw = readFileSync(full, 'utf8');
    return {
      path: `src/${relative(SRC, full).split(sep).join('/')}`,
      raw,
      code: stripComments(raw),
    };
  });
  return cache;
}

/** The surfaces the staged rail is made of — the primary path a founder walks. */
export function railFiles(): SourceFile[] {
  return sourceFiles().filter(
    (f) =>
      f.path.startsWith('src/pages/product/') ||
      f.path.startsWith('src/components/stages/') ||
      f.path === 'src/lib/stages.ts' ||
      f.path === 'src/components/AppLayout.tsx',
  );
}

/* ------------------------------------------------------------------ */
/*  Extracting what renders                                            */
/* ------------------------------------------------------------------ */

/**
 * Strings a founder can actually read: JSX text nodes and the four attributes
 * that reach a screen reader or a tooltip.
 *
 * Type names, imports, CSS class names, `data-*` attributes and route paths are
 * excluded — the rule is about vocabulary the reader must understand, not about
 * identifiers. `className` in particular carries `variant` constantly and it is
 * a Tailwind token, not a word anybody reads.
 */
export function renderedStrings(file: SourceFile): string[] {
  const out: string[] = [];
  const code = file.code;

  // JSX text between tags. Requires a letter so `{'; '}` and punctuation-only
  // fragments do not count as copy.
  for (const match of code.matchAll(/>([^<>{}]*[A-Za-z][^<>{}]*)</g)) {
    const text = match[1].trim();
    if (text) out.push(text);
  }

  // The attributes that render or are announced.
  const spoken = /\b(aria-label|title|placeholder|alt)\s*=\s*(?:"([^"]*)"|'([^']*)'|\{`([^`]*)`\}|\{'([^']*)'\})/g;
  for (const match of code.matchAll(spoken)) {
    const value = match[2] ?? match[3] ?? match[4] ?? match[5];
    if (value?.trim()) out.push(value.trim());
  }

  // String and template literals assigned to something that reads like copy.
  const copyish =
    /\b(label|headline|body|blurb|ask|question|help|consequence|reason|busyLabel|text|summary|hint|verdict)\s*:\s*(?:'([^']{4,})'|"([^"]{4,})"|`([^`]{4,})`)/g;
  for (const match of code.matchAll(copyish)) {
    const value = match[2] ?? match[3] ?? match[4];
    if (value?.trim()) out.push(value.trim());
  }

  return out;
}

/**
 * Every route literal a file navigates to.
 *
 * `path:` is included because the sidebar declares its links as a data array
 * (`{ path: '/app/home', label: 'Home' }`) and renders them through one
 * `<Link to={item.path}>`. Without it the walk would report six surfaces as
 * unreachable when the sidebar reaches all of them from every page — a false
 * alarm, but one that would train a reader to ignore this test.
 */
export function routeTargets(file: SourceFile): string[] {
  const out = new Set<string>();
  const patterns = [
    /\bto=\{?["'`](\/[^"'`{}]*)["'`]/g,
    /\bto=\{`(\/[^`]*)`\}/g,
    /navigate\(\s*`(\/[^`]*)`/g,
    /navigate\(\s*['"](\/[^'"]*)['"]/g,
    /\bhref:\s*`(\/[^`]*)`/g,
    /\bhref:\s*['"](\/[^'"]*)['"]/g,
    /\bpath:\s*['"](\/app[^'"]*)['"]/g,
  ];
  for (const pattern of patterns) {
    for (const match of file.code.matchAll(pattern)) out.add(match[1]);
  }

  /*
    A link built by `stageHref(productId, id)` reaches whichever stage it is
    handed, and the rail hands it every entry in `STAGES`. The literal never
    appears in the calling file, so the scan would see the rail as linking
    nowhere. Resolved here by reading the segments out of `lib/stages.ts` —
    which is the single declaration of the rail, so this is following the app's
    own source rather than restating it.
  */
  if (/\bstageHref\(/.test(file.code)) {
    for (const segment of stageSegments()) {
      out.add(`/app/products/:p/${segment}`);
    }
  }

  return [...out];
}

let segmentCache: string[] | null = null;

/** The five `segment` values declared in `lib/stages.ts`. */
export function stageSegments(): string[] {
  if (segmentCache) return segmentCache;
  const stages = sourceFiles().find((f) => f.path === 'src/lib/stages.ts');
  if (!stages) throw new Error('src/lib/stages.ts is missing');
  segmentCache = [...stages.code.matchAll(/segment:\s*'([^']+)'/g)].map((m) => m[1]);
  if (segmentCache.length === 0) {
    // An empty list would make the reachability walk pass by finding nothing to
    // check, which is the vacuous-test failure this codebase keeps producing.
    throw new Error('No stage segments found in src/lib/stages.ts');
  }
  return segmentCache;
}

/**
 * Normalise a concrete link into its route pattern.
 *
 * `/app/products/${id}/audience` and `/app/products/abc/audience` both become
 * `/app/products/:p/audience`, so the walk compares routes rather than data.
 */
export function toPattern(href: string): string {
  return href
    .split('?')[0]
    .split('#')[0]
    .replace(/\$\{[^}]*\}/g, ':p')
    .replace(/\/[0-9a-f]{8}-[0-9a-f-]{27}/gi, '/:p')
    .replace(/\/+$/, '');
}
