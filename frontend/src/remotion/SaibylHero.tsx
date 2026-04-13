import { useCallback, useMemo, useRef } from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion';
import { generateLetterTargets, generateMarkNodes } from './utils/letterPaths';
import {
  generateParticles,
  getParticlePosition,
  getPulsationScale,
  easeOutQuart,
} from './utils/particleUtils';

// Timing (in frames at 30fps)
const ACT1_END = 75; // 2.5s
const ACT2_END = 150; // 5.0s
const ACT3_END = 225; // 7.5s
const TOTAL_PARTICLES = 380;
const MARK_PARTICLES = 80;

export const SaibylHero: React.FC = () => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const centerX = width / 2;
  const centerY = height / 2 - 40;
  const scale = width / 1920;

  // Pre-compute all particle data once
  const { wordParticles, markParticles } = useMemo(() => {
    const letterTargets = generateLetterTargets(centerX, centerY, scale);
    const wordP = generateParticles(TOTAL_PARTICLES, width, height, letterTargets);

    const markCenter = { x: centerX - 220 * scale, y: centerY - 90 * scale };
    const markTargetPositions = generateMarkNodes(markCenter.x, markCenter.y, scale);
    const markTargetsWithIdx = markTargetPositions.map((p) => ({
      ...p,
      letterIdx: 99, // special index for mark
    }));
    const markP = generateParticles(MARK_PARTICLES, width, height, markTargetsWithIdx);

    return { wordParticles: wordP, markParticles: markP };
  }, [width, height, centerX, centerY, scale]);

  // Render via canvas for performance
  const renderCanvas = useCallback(
    (canvas: HTMLCanvasElement | null) => {
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      ctx.clearRect(0, 0, width, height);

      // Act 1-2: Word particles
      const convergenceProgress =
        frame <= ACT1_END
          ? 0
          : frame <= ACT2_END
            ? (frame - ACT1_END) / (ACT2_END - ACT1_END)
            : 1;

      wordParticles.forEach((p) => {
        const pos = getParticlePosition(p, convergenceProgress);

        // Drift during scatter phase
        let x = pos.x;
        let y = pos.y;
        if (convergenceProgress < 0.1) {
          x += p.driftVx * frame;
          y += p.driftVy * frame;
          // Bounce within bounds
          x = ((x % width) + width) % width;
          y = ((y % height) + height) % height;
        }

        // Pulsation
        const pulseScale = convergenceProgress >= 1 ? 1 : getPulsationScale(frame, p.phaseOffset);

        // Fade out unassigned particles after convergence
        let alpha = p.opacity;
        if (p.letterIndex === -1 && convergenceProgress > 0.8) {
          alpha *= Math.max(0, 1 - (convergenceProgress - 0.8) * 5);
        }

        // Glow flash on lock-in
        let glowRadius = 0;
        if (convergenceProgress >= 0.95 && convergenceProgress <= 1 && p.letterIndex >= 0) {
          glowRadius = 8 * (1 - Math.abs(convergenceProgress - 0.975) / 0.025);
        }

        if (alpha <= 0) return;

        // Draw glow
        if (glowRadius > 0) {
          ctx.beginPath();
          ctx.arc(x, y, p.radius * pulseScale + glowRadius, 0, Math.PI * 2);
          ctx.fillStyle = p.color + '30';
          ctx.fill();
        }

        // Draw particle
        ctx.beginPath();
        ctx.arc(x, y, p.radius * pulseScale, 0, Math.PI * 2);
        ctx.fillStyle = p.color;
        ctx.globalAlpha = alpha;
        ctx.fill();
        ctx.globalAlpha = 1;
      });

      // Act 2 complete: gradient glow on wordmark
      if (convergenceProgress >= 1 && frame <= ACT2_END + 15) {
        const glowAlpha = Math.max(0, 1 - (frame - ACT2_END) / 15);
        const gradient = ctx.createLinearGradient(
          centerX - 200 * scale,
          centerY,
          centerX + 200 * scale,
          centerY
        );
        gradient.addColorStop(0, `rgba(201,162,39,${glowAlpha * 0.3})`);
        gradient.addColorStop(1, `rgba(37,99,235,${glowAlpha * 0.3})`);
        ctx.fillStyle = gradient;
        ctx.fillRect(centerX - 210 * scale, centerY - 40 * scale, 420 * scale, 80 * scale);
      }

      // Act 3: Mark formation
      if (frame >= ACT2_END) {
        const markProgress =
          frame <= ACT3_END
            ? (frame - ACT2_END) / (ACT3_END - ACT2_END)
            : 1;
        const markT = easeOutQuart(Math.min(1, markProgress));

        markParticles.forEach((p) => {
          const pos = getParticlePosition(p, markT);
          const alpha = Math.min(1, markProgress * 2) * p.opacity;

          if (alpha <= 0) return;

          ctx.beginPath();
          ctx.arc(pos.x, pos.y, p.radius * 0.8, 0, Math.PI * 2);
          ctx.fillStyle = p.color;
          ctx.globalAlpha = alpha;
          ctx.fill();
          ctx.globalAlpha = 1;
        });

        // Center node glow pulse when assembled
        if (markProgress >= 1) {
          const pulse = 0.5 + 0.5 * Math.sin(frame * 0.08);
          const markCx = centerX - 220 * scale;
          const markCy = centerY - 90 * scale;
          const grad = ctx.createRadialGradient(markCx, markCy, 0, markCx, markCy, 20 * scale);
          grad.addColorStop(0, `rgba(201,162,39,${pulse * 0.4})`);
          grad.addColorStop(1, 'rgba(201,162,39,0)');
          ctx.fillStyle = grad;
          ctx.beginPath();
          ctx.arc(markCx, markCy, 20 * scale, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      // Act 4: Orbital motion
      if (frame > ACT3_END) {
        const orbitFrame = frame - ACT3_END;
        const orbitPeriod = 240; // 8s at 30fps
        const angle = (orbitFrame / orbitPeriod) * Math.PI * 2;
        const orbitRx = 60 * scale;
        const orbitRy = 30 * scale; // perspective-flattened ellipse
        const markCx = centerX - 220 * scale;
        const markCy = centerY - 90 * scale;

        const orbX = markCx + Math.cos(angle) * orbitRx;
        const orbY = markCy + Math.sin(angle) * orbitRy - 20 * scale;

        // Trailing particles
        for (let t = 1; t <= 4; t++) {
          const trailAngle = angle - t * 0.12;
          const tx = markCx + Math.cos(trailAngle) * orbitRx;
          const ty = markCy + Math.sin(trailAngle) * orbitRy - 20 * scale;
          ctx.beginPath();
          ctx.arc(tx, ty, 2 * scale, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(201,162,39,${0.3 - t * 0.06})`;
          ctx.fill();
        }

        // Orbiting node
        ctx.beginPath();
        ctx.arc(orbX, orbY, 4 * scale, 0, Math.PI * 2);
        ctx.fillStyle = '#C9A227';
        ctx.fill();

        // Glow
        const grad = ctx.createRadialGradient(orbX, orbY, 0, orbX, orbY, 12 * scale);
        grad.addColorStop(0, 'rgba(201,162,39,0.3)');
        grad.addColorStop(1, 'rgba(201,162,39,0)');
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(orbX, orbY, 12 * scale, 0, Math.PI * 2);
        ctx.fill();
      }
    },
    [frame, width, height, wordParticles, markParticles, centerX, centerY, scale]
  );

  // Remotion re-renders this component on every frame, so the ref callback fires
  // each render. We also call renderCanvas directly here to ensure the canvas
  // is painted before Remotion captures the frame for video export.
  return (
    <AbsoluteFill style={{ backgroundColor: '#070B14' }}>
      <canvas
        ref={(el) => {
          canvasRef.current = el;
          renderCanvas(el);
        }}
        width={width}
        height={height}
        style={{ width: '100%', height: '100%', display: 'block' }}
      />
    </AbsoluteFill>
  );
};
