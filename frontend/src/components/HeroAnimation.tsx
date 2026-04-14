import { useEffect, useRef } from 'react';

/**
 * Constellation network — nodes connected by glowing edges, reacting to mouse.
 */
export default function HeroAnimation() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number>(0);
  const mouseRef = useRef({ x: -9999, y: -9999 });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const parent = canvas.parentElement;
    if (!parent) return;

    const dpr = Math.min(window.devicePixelRatio, 2);

    interface Node {
      x: number; y: number;
      vx: number; vy: number;
      r: number; color: string;
      alpha: number; phase: number;
    }

    const COLORS = ['#5B5FEE', '#00D4FF'];
    const CONNECT_DIST = 160;
    const MOUSE_PUSH = 100;
    const MOUSE_FORCE = 0.6;

    let nodes: Node[] = [];
    let w = 0;
    let h = 0;

    function resize() {
      const rect = parent!.getBoundingClientRect();
      w = rect.width;
      h = rect.height;
      canvas!.width = w * dpr;
      canvas!.height = h * dpr;
      canvas!.style.width = w + 'px';
      canvas!.style.height = h + 'px';

      const count = Math.min(90, Math.max(40, Math.floor((w * h) / 12000)));
      nodes = Array.from({ length: count }, () => ({
        x: Math.random() * w,
        y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.3,
        vy: (Math.random() - 0.5) * 0.25,
        r: 1.5 + Math.random() * 1.5,
        color: COLORS[Math.floor(Math.random() * COLORS.length)],
        alpha: 0.4 + Math.random() * 0.5,
        phase: Math.random() * Math.PI * 2,
      }));
    }

    resize();
    window.addEventListener('resize', resize);

    const onMouseMove = (e: MouseEvent) => {
      const rect = canvas!.getBoundingClientRect();
      mouseRef.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    };
    const onMouseLeave = () => { mouseRef.current = { x: -9999, y: -9999 }; };
    canvas.parentElement!.addEventListener('mousemove', onMouseMove);
    canvas.parentElement!.addEventListener('mouseleave', onMouseLeave);

    function hexAlpha(hex: string, a: number) {
      const r = parseInt(hex.slice(1, 3), 16);
      const g = parseInt(hex.slice(3, 5), 16);
      const b = parseInt(hex.slice(5, 7), 16);
      return `rgba(${r},${g},${b},${a.toFixed(3)})`;
    }

    function draw(t: number) {
      const ctx = canvas!.getContext('2d');
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      const mx = mouseRef.current.x;
      const my = mouseRef.current.y;

      // Update positions
      for (const n of nodes) {
        // Mouse repulsion
        const dx = n.x - mx;
        const dy = n.y - my;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < MOUSE_PUSH && dist > 0) {
          const force = (MOUSE_PUSH - dist) / MOUSE_PUSH * MOUSE_FORCE;
          n.vx += (dx / dist) * force;
          n.vy += (dy / dist) * force;
        }

        // Damping
        n.vx *= 0.98;
        n.vy *= 0.98;

        // Clamp speed
        const speed = Math.sqrt(n.vx * n.vx + n.vy * n.vy);
        if (speed > 1.2) { n.vx = (n.vx / speed) * 1.2; n.vy = (n.vy / speed) * 1.2; }

        n.x += n.vx;
        n.y += n.vy;

        // Wrap
        if (n.x < -20) n.x = w + 20;
        if (n.x > w + 20) n.x = -20;
        if (n.y < -20) n.y = h + 20;
        if (n.y > h + 20) n.y = -20;
      }

      // Draw edges
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i];
          const b = nodes[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < CONNECT_DIST) {
            const opacity = (1 - dist / CONNECT_DIST) * 0.18;
            const midColor = a.color;
            const grad = ctx.createLinearGradient(a.x, a.y, b.x, b.y);
            grad.addColorStop(0, hexAlpha(a.color, opacity));
            grad.addColorStop(1, hexAlpha(b.color, opacity));
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.strokeStyle = grad;
            ctx.lineWidth = 0.8;
            ctx.stroke();
            void midColor;
          }
        }
      }

      // Draw nodes
      for (const n of nodes) {
        const pulse = 0.7 + 0.3 * Math.sin(t * 0.0008 + n.phase);

        // Outer glow
        const grd = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, n.r * 5);
        grd.addColorStop(0, hexAlpha(n.color, n.alpha * pulse * 0.35));
        grd.addColorStop(1, hexAlpha(n.color, 0));
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.r * 5, 0, Math.PI * 2);
        ctx.fillStyle = grd;
        ctx.fill();

        // Core dot
        ctx.globalAlpha = n.alpha * pulse;
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
        ctx.fillStyle = n.color;
        ctx.fill();
        ctx.globalAlpha = 1;
      }

      // Mouse proximity highlight ring
      if (mx > 0 && my > 0) {
        const ringGrad = ctx.createRadialGradient(mx, my, MOUSE_PUSH * 0.3, mx, my, MOUSE_PUSH);
        ringGrad.addColorStop(0, 'rgba(91,95,238,0)');
        ringGrad.addColorStop(0.85, 'rgba(91,95,238,0.04)');
        ringGrad.addColorStop(1, 'rgba(91,95,238,0)');
        ctx.beginPath();
        ctx.arc(mx, my, MOUSE_PUSH, 0, Math.PI * 2);
        ctx.fillStyle = ringGrad;
        ctx.fill();
      }

      animRef.current = requestAnimationFrame(draw);
    }

    animRef.current = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(animRef.current);
      window.removeEventListener('resize', resize);
      canvas.parentElement?.removeEventListener('mousemove', onMouseMove);
      canvas.parentElement?.removeEventListener('mouseleave', onMouseLeave);
    };
  }, []);

  return <canvas ref={canvasRef} className="absolute inset-0 pointer-events-none" />;
}
