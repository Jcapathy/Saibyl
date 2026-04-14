import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/* ── Report content cleanup ──────────────────────────────── */

const PREAMBLE_VERBS =
  'gather|start|begin|analyze|look|pull|search|investigate|examine|collect|retrieve|check|review|query|explore|write|assess|evaluate|compile|synthesize|research|identify|determine|provide';

/** Strip tool-use artifacts and ReACT traces from AI-generated content. */
export function cleanContent(raw: string): string {
  // 1a. Strip full preamble-through-ANSWER blocks
  let text = raw.replace(
    new RegExp(`(?:I'll|I will|Let me)\\s+(?:\\w+\\s+)*?(?:${PREAMBLE_VERBS})[\\s\\S]*?ANSWER:\\s*`, 'gi'),
    '',
  );
  // 1b. Strip preamble sentences with no ANSWER
  text = text.replace(
    new RegExp(`(?:I'll|I will|Let me)\\s+(?:\\w+\\s+)*?(?:${PREAMBLE_VERBS})\\b[^.]*\\.\\s*`, 'gi'),
    '',
  );
  // 1c. Broader self-referential preambles ("I have extensive evidence..., but ##")
  text = text.replace(
    /^(?:I have|I've|Based on|From the|Using the|After)(?:\s+\w+){0,5}?\s+(?:evidence|data|research|analysis|findings|information|results|rounds?)\b[\s\S]*?(?=\n##|\n\n)/gim,
    '',
  );
  // 2. Strip standalone ANSWER: markers
  text = text.replace(/^ANSWER:\s*/gm, '');

  return text
    .split('\n')
    .filter(line => {
      const trimmed = line.trim();
      if (/^(?:>\s*)?TOOL:\s/i.test(trimmed)) return false;
      if (/^(?:>\s*)?(?:Action:|Observation:|search_web|read_url|get_page)\b/i.test(trimmed)) return false;
      if (/^(?:Using tool|Calling tool|Tool call|Tool output|Tool result)\b/i.test(trimmed)) return false;
      if (/^(?:Thought|Reasoning):\s/i.test(trimmed)) return false;
      return true;
    })
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}
