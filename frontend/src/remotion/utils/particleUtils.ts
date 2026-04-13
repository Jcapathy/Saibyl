// Particle generation and easing utilities

export interface Particle {
  id: number;
  x: number;
  y: number;
  targetX: number;
  targetY: number;
  radius: number;
  color: string;
  opacity: number;
  phaseOffset: number; // for pulsation desync
  driftVx: number;
  driftVy: number;
  letterIndex: number; // -1 = unassigned (will fade out)
  arcBend: number; // curve factor for convergence path
}

const COLORS = {
  gold: '#C9A227',
  blue: '#2563EB',
  violet: '#8B5CF6',
};

export function generateParticles(
  count: number,
  width: number,
  height: number,
  targets: { x: number; y: number; letterIdx: number }[]
): Particle[] {
  const particles: Particle[] = [];

  for (let i = 0; i < count; i++) {
    // Color distribution: 60% gold, 30% blue, 10% violet
    const rand = Math.random();
    let color: string;
    let opacity: number;
    if (rand < 0.6) {
      color = COLORS.gold;
      opacity = 0.4 + Math.random() * 0.4;
    } else if (rand < 0.9) {
      color = COLORS.blue;
      opacity = 0.3 + Math.random() * 0.4;
    } else {
      color = COLORS.violet;
      opacity = 0.3 + Math.random() * 0.3;
    }

    const target = i < targets.length ? targets[i] : null;

    particles.push({
      id: i,
      x: Math.random() * width,
      y: Math.random() * height,
      targetX: target?.x ?? Math.random() * width,
      targetY: target?.y ?? Math.random() * height,
      radius: 2 + Math.random() * 3,
      color,
      opacity,
      phaseOffset: Math.random() * Math.PI * 2,
      driftVx: (Math.random() - 0.5) * 0.6,
      driftVy: (Math.random() - 0.5) * 0.6,
      letterIndex: target?.letterIdx ?? -1,
      arcBend: (Math.random() - 0.5) * 120, // px bend for curved path
    });
  }

  return particles;
}

// Cubic bezier easing
export function easeInOutCubic(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

export function easeOutQuart(t: number): number {
  return 1 - Math.pow(1 - t, 4);
}

// Get particle position at a given animation progress
export function getParticlePosition(
  particle: Particle,
  convergenceProgress: number, // 0 = scattered, 1 = converged
): { x: number; y: number } {
  if (convergenceProgress <= 0) {
    return { x: particle.x, y: particle.y };
  }

  const t = easeInOutCubic(Math.min(1, convergenceProgress));

  // Arc trajectory: add perpendicular bend
  const dx = particle.targetX - particle.x;
  const dy = particle.targetY - particle.y;
  const perpX = -dy;
  const perpY = dx;
  const len = Math.sqrt(perpX * perpX + perpY * perpY) || 1;
  const arcX = (perpX / len) * particle.arcBend * Math.sin(t * Math.PI);
  const arcY = (perpY / len) * particle.arcBend * Math.sin(t * Math.PI);

  return {
    x: particle.x + dx * t + arcX * (1 - t),
    y: particle.y + dy * t + arcY * (1 - t),
  };
}

// Pulsation scale
export function getPulsationScale(frame: number, phaseOffset: number): number {
  const t = (frame * 0.05 + phaseOffset) % (Math.PI * 2);
  return 0.85 + 0.3 * Math.sin(t);
}
