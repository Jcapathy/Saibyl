// Particle target positions for "SAIBYL"
// Hardcoded bitmap grids for each letter — deterministic, no font/canvas dependency.
// Each letter is a grid of '#' (filled) and '.' (empty) characters.
// Modeled after Aktiv Grotesk 800 at display weight.

const LETTER_BITMAPS: Record<string, string[]> = {
  S: [
    '..#####.',
    '.##...##',
    '.##.....',
    '..####..',
    '.....##.',
    '##...##.',
    '.#####..',
  ],
  A: [
    '...##...',
    '..####..',
    '.##..##.',
    '.##..##.',
    '.######.',
    '.##..##.',
    '.##..##.',
  ],
  I: [
    '.######.',
    '...##...',
    '...##...',
    '...##...',
    '...##...',
    '...##...',
    '.######.',
  ],
  B: [
    '.#####..',
    '.##..##.',
    '.##..##.',
    '.#####..',
    '.##..##.',
    '.##..##.',
    '.#####..',
  ],
  Y: [
    '.##...##',
    '.##...##',
    '..##.##.',
    '...###..',
    '...##...',
    '...##...',
    '...##...',
  ],
  L: [
    '.##.....',
    '.##.....',
    '.##.....',
    '.##.....',
    '.##.....',
    '.##.....',
    '.######.',
  ],
};

function sampleFromBitmap(
  bitmap: string[],
  originX: number,
  originY: number,
  cellSize: number,
  targetCount: number,
  letterIdx: number,
): { x: number; y: number; letterIdx: number }[] {
  // Collect all filled cell centers
  const filled: { x: number; y: number }[] = [];
  const rows = bitmap.length;
  const cols = bitmap[0].length;

  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      if (bitmap[r][c] === '#') {
        filled.push({
          x: originX + c * cellSize + cellSize / 2,
          y: originY + r * cellSize + cellSize / 2,
        });
      }
    }
  }

  if (filled.length === 0) return [];

  // Distribute targetCount particles across filled cells with jitter
  const results: { x: number; y: number; letterIdx: number }[] = [];
  for (let i = 0; i < targetCount; i++) {
    const cell = filled[i % filled.length];
    results.push({
      x: cell.x + (Math.random() - 0.5) * cellSize * 0.8,
      y: cell.y + (Math.random() - 0.5) * cellSize * 0.8,
      letterIdx,
    });
  }

  return results;
}

/**
 * Generate particle target positions for "SAIBYL" wordmark.
 */
export function generateLetterTargets(
  centerX: number,
  centerY: number,
  scale: number = 1,
): { x: number; y: number; letterIdx: number }[] {
  const letters = ['S', 'A', 'I', 'B', 'Y', 'L'];
  const cellSize = 9 * scale;
  const letterGap = 8 * scale;

  // Calculate letter widths
  const letterWidths = letters.map((l) => LETTER_BITMAPS[l][0].length * cellSize);
  const totalWidth = letterWidths.reduce((a, b) => a + b, 0) + letterGap * (letters.length - 1);
  const totalHeight = LETTER_BITMAPS.S.length * cellSize;

  // Particles per letter (proportional to filled cells)
  const particlesPerLetter = [45, 42, 22, 44, 38, 30];

  let cursorX = centerX - totalWidth / 2;
  const originY = centerY - totalHeight / 2;

  const allTargets: { x: number; y: number; letterIdx: number }[] = [];

  letters.forEach((letter, idx) => {
    const bitmap = LETTER_BITMAPS[letter];
    const targets = sampleFromBitmap(
      bitmap,
      cursorX,
      originY,
      cellSize,
      particlesPerLetter[idx],
      idx,
    );
    allTargets.push(...targets);
    cursorX += letterWidths[idx] + letterGap;
  });

  return allTargets;
}

/**
 * Generate mark/icon node positions — simplified network graph.
 */
export function generateMarkNodes(
  cx: number,
  cy: number,
  scale: number = 1,
): { x: number; y: number }[] {
  const r = 30 * scale;
  const nodes: { x: number; y: number }[] = [];

  // Central node cluster
  for (let i = 0; i < 15; i++) {
    nodes.push({
      x: cx + (Math.random() - 0.5) * 8 * scale,
      y: cy + (Math.random() - 0.5) * 8 * scale,
    });
  }

  // 5 orbital nodes with connecting edge particles
  for (let n = 0; n < 5; n++) {
    const angle = (n / 5) * Math.PI * 2 - Math.PI / 2;
    const nx = cx + Math.cos(angle) * r;
    const ny = cy + Math.sin(angle) * r;

    for (let i = 0; i < 10; i++) {
      nodes.push({
        x: nx + (Math.random() - 0.5) * 8 * scale,
        y: ny + (Math.random() - 0.5) * 8 * scale,
      });
    }

    for (let i = 0; i < 6; i++) {
      const t = (i + 1) / 7;
      nodes.push({
        x: cx + (nx - cx) * t + (Math.random() - 0.5) * 3 * scale,
        y: cy + (ny - cy) * t + (Math.random() - 0.5) * 3 * scale,
      });
    }
  }

  return nodes;
}
