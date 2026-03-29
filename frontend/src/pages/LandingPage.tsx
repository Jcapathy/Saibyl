import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import HeroAnimation from '@/components/HeroAnimation';

/* ══════════════════════════════════════════════════════════
   SAIBYL LANDING PAGE — Vercel-tier dark SaaS
   ══════════════════════════════════════════════════════════ */

/* ── Intersection Observer fade-in ── */
function useFadeIn() {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(([e]) => { if (e.isIntersecting) setVisible(true); }, { threshold: 0.15 });
    obs.observe(el);
    return () => obs.disconnect();
  }, []);
  return { ref, className: `transition-all duration-700 ${visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'}` };
}

function Section({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  const fade = useFadeIn();
  return <div ref={fade.ref} className={`${fade.className} ${className}`}>{children}</div>;
}

/* ── Data ── */
const features = [
  { icon: '◉', tag: 'SIMULATE', title: 'Deploy swarms at scale', body: 'Up to 1 million synthetic personas across 8 social platforms. Each agent has unique personality, behavior, and platform-native posting patterns.', color: '#5B5FEE' },
  { icon: '◈', tag: 'ANALYZE', title: 'ReACT intelligence engine', body: 'Multi-pass reasoning with 5 retrieval tools and 4 depth levels. Full evidence chains, source citations, and interactive Q&A with your reports.', color: '#00D4FF' },
  { icon: '◇', tag: 'PREDICT', title: 'Prediction market edge', body: 'Import from Kalshi and Polymarket. Get probability estimates, edge analysis, and recommended positions backed by swarm consensus.', color: '#A78BFA' },
];

const platforms = [
  { name: 'Twitter / X', agents: '280 char', algo: 'Engagement' },
  { name: 'Reddit', agents: '40K char', algo: 'Hot rank' },
  { name: 'LinkedIn', agents: '3K char', algo: 'Connections' },
  { name: 'Instagram', agents: '2.2K cap', algo: 'Explore' },
  { name: 'Hacker News', agents: '10K char', algo: 'Karma decay' },
  { name: 'Discord', agents: '2K char', algo: 'Channels' },
  { name: 'News', agents: '2K char', algo: 'Moderation' },
  { name: 'Custom', agents: 'Config', algo: 'Your rules' },
];

const metrics = [
  { value: '1M', label: 'Max agents', sub: 'per simulation' },
  { value: '8', label: 'Platforms', sub: 'built-in adapters' },
  { value: '42', label: 'Archetypes', sub: 'across 13 packs' },
  { value: '<3s', label: 'Per round', sub: 'execution speed' },
];

const plans = [
  { name: 'Starter', price: '99', desc: 'For individuals and small teams exploring predictive intelligence.', items: ['10 simulations / mo', '5,000 agents per sim', '5 GB storage', '3 team members'] },
  { name: 'Pro', price: '299', desc: 'For teams that need deeper analysis and higher volume.', items: ['50 simulations / mo', '50,000 agents per sim', '25 GB storage', '10 team members', 'All platforms', 'Prediction markets'], pop: true },
  { name: 'Enterprise', price: '999', desc: 'For organizations running prediction at scale.', items: ['Unlimited simulations', '500,000 agents per sim', '100 GB storage', 'Unlimited team', 'Custom adapters', 'Dedicated support'] },
];

/* ══════════════════════════════════════════════════════════ */

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-saibyl-void text-saibyl-platinum overflow-x-hidden selection:bg-saibyl-indigo/30">

      {/* ── BG layers (fixed) ── */}
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute inset-0 bg-grid" />
        <div className="absolute top-[-40%] left-[-20%] w-[80%] h-[80%] rounded-full bg-[radial-gradient(ellipse,rgba(91,95,238,0.12)_0%,transparent_60%)] animate-breathe" />
        <div className="absolute bottom-[-30%] right-[-15%] w-[70%] h-[70%] rounded-full bg-[radial-gradient(ellipse,rgba(0,212,255,0.08)_0%,transparent_60%)] animate-breathe" style={{ animationDelay: '-4s' }} />
        <div className="absolute top-[20%] right-[10%] w-[40%] h-[40%] rounded-full bg-[radial-gradient(ellipse,rgba(167,139,250,0.06)_0%,transparent_60%)] animate-breathe" style={{ animationDelay: '-6s' }} />
      </div>

      {/* ── NAV ── */}
      <nav className="fixed top-0 left-0 right-0 z-50">
        <div className="mx-4 mt-4 rounded-2xl glass">
          <div className="max-w-6xl mx-auto flex items-center justify-between px-6 h-14">
            <img src="/logo-primary.svg" alt="Saibyl" className="h-7" />
            <div className="flex items-center gap-5">
              <a href="#features" className="text-[13px] text-saibyl-muted hover:text-saibyl-platinum transition-colors hidden md:block">Features</a>
              <a href="#platforms" className="text-[13px] text-saibyl-muted hover:text-saibyl-platinum transition-colors hidden md:block">Platforms</a>
              <a href="#pricing" className="text-[13px] text-saibyl-muted hover:text-saibyl-platinum transition-colors hidden md:block">Pricing</a>
              <div className="w-px h-5 bg-white/[0.08] hidden md:block" />
              <Link to="/login" className="text-[13px] text-saibyl-muted hover:text-saibyl-platinum transition-colors">Sign in</Link>
              <Link to="/signup" className="text-[13px] font-medium px-4 py-1.5 rounded-lg bg-saibyl-indigo text-white hover:bg-[#4B4FDE] transition-all hover:shadow-[0_0_20px_rgba(91,95,238,0.25)]">
                Get started
              </Link>
            </div>
          </div>
        </div>
      </nav>

      {/* ════════════════════════════════════════════════════ */}
      {/* HERO                                                */}
      {/* ════════════════════════════════════════════════════ */}
      <section className="relative min-h-[100dvh] flex flex-col items-center justify-center text-center px-6 overflow-hidden">
        <div className="absolute inset-0 opacity-60"><HeroAnimation /></div>

        {/* Radial gradient behind logo */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] rounded-full bg-[radial-gradient(circle,rgba(91,95,238,0.15)_0%,transparent_70%)] pointer-events-none" />

        <div className="relative z-10 max-w-3xl">
          {/* Badge */}
          <div className="inline-flex items-center gap-2.5 px-4 py-1.5 rounded-full glass mb-12">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-saibyl-positive opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-saibyl-positive" />
            </span>
            <span className="font-mono text-[11px] tracking-[0.2em] uppercase text-saibyl-muted">Now in private beta</span>
          </div>

          {/* Logo lockup */}
          <div className="flex items-center justify-center gap-5 mb-14">
            <img src="/logo-mark.svg" alt="" className="w-[72px] h-[72px] sm:w-[88px] sm:h-[88px] animate-float drop-shadow-[0_0_40px_rgba(91,95,238,0.5)]" />
            <span className="font-display font-extrabold text-[56px] sm:text-[68px] md:text-[80px] text-gradient select-none" style={{ lineHeight: 1, letterSpacing: '-0.03em' }}>
              SAIBYL
            </span>
          </div>

          {/* Tagline — BIG */}
          <h1 className="font-display font-extrabold text-[40px] sm:text-[52px] md:text-[64px] leading-[1.05] tracking-tight text-white mb-6">
            Know the conversation{' '}
            <span className="text-gradient">before it happens</span>
          </h1>

          <p className="text-[16px] sm:text-[17px] text-saibyl-muted max-w-xl mx-auto leading-[1.75] mb-12">
            Deploy swarms of AI personas to simulate how real communities react.
            Get predictive intelligence reports before the world catches up.
          </p>

          {/* CTAs */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link
              to="/signup"
              className="group relative w-full sm:w-auto inline-flex items-center justify-center px-8 py-4 rounded-xl text-white font-semibold text-[15px] overflow-hidden transition-all hover:scale-[1.03]"
            >
              <div className="absolute inset-0 bg-gradient-to-r from-[#5B5FEE] to-[#00D4FF] transition-all" />
              <div className="absolute inset-0 bg-gradient-to-r from-[#4B4FDE] to-[#00B8D9] opacity-0 group-hover:opacity-100 transition-opacity" />
              <div className="absolute inset-0 animate-glow-pulse rounded-xl" />
              <span className="relative flex items-center gap-2">
                Request early access
                <svg className="w-4 h-4 group-hover:translate-x-1 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" /></svg>
              </span>
            </Link>
            <Link to="/login" className="w-full sm:w-auto inline-flex items-center justify-center px-8 py-4 rounded-xl text-saibyl-platinum font-medium text-[15px] glass glass-hover transition-all">
              Watch demo
            </Link>
          </div>
        </div>

        {/* Scroll indicator */}
        <div className="absolute bottom-10 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 text-saibyl-muted/50">
          <span className="text-[10px] font-mono tracking-[0.15em] uppercase">Scroll</span>
          <div className="w-px h-8 bg-gradient-to-b from-saibyl-muted/30 to-transparent" />
        </div>
      </section>

      {/* ── Shimmer divider ── */}
      <div className="h-px shimmer-border" />

      {/* ════════════════════════════════════════════════════ */}
      {/* METRICS BAR                                         */}
      {/* ════════════════════════════════════════════════════ */}
      <section className="relative py-20 px-6">
        <Section>
          <div className="max-w-5xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-8">
            {metrics.map((m) => (
              <div key={m.label} className="text-center">
                <div className="text-[48px] font-display font-extrabold text-gradient leading-none">{m.value}</div>
                <div className="text-[14px] font-medium text-saibyl-platinum mt-2">{m.label}</div>
                <div className="text-[12px] text-saibyl-muted mt-0.5">{m.sub}</div>
              </div>
            ))}
          </div>
        </Section>
      </section>

      <div className="h-px shimmer-border" />

      {/* ════════════════════════════════════════════════════ */}
      {/* FEATURES                                            */}
      {/* ════════════════════════════════════════════════════ */}
      <section id="features" className="relative py-32 px-6">
        <div className="max-w-5xl mx-auto">
          <Section className="text-center mb-20">
            <span className="font-mono text-[11px] tracking-[0.22em] uppercase text-saibyl-indigo">Capabilities</span>
            <h2 className="font-display font-extrabold text-[36px] sm:text-[44px] text-white mt-4 leading-[1.08]" style={{ letterSpacing: '-0.025em' }}>
              Everything you need to<br /><span className="text-gradient">predict the future</span>
            </h2>
          </Section>

          <div className="space-y-5">
            {features.map((f) => (
              <Section key={f.tag}>
                <div className="group glass glass-hover rounded-2xl p-8 md:p-10 transition-all duration-300 relative overflow-hidden">
                  {/* Color accent line */}
                  <div className="absolute left-0 top-0 bottom-0 w-[3px] rounded-full transition-all duration-300 opacity-0 group-hover:opacity-100" style={{ background: f.color }} />

                  <div className="flex flex-col md:flex-row md:items-center gap-6">
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-3">
                        <span className="text-2xl" style={{ color: f.color }}>{f.icon}</span>
                        <span className="font-mono text-[11px] tracking-[0.22em] uppercase" style={{ color: f.color }}>{f.tag}</span>
                      </div>
                      <h3 className="font-display font-bold text-[24px] text-white mb-2" style={{ letterSpacing: '-0.02em' }}>{f.title}</h3>
                      <p className="text-[15px] text-saibyl-muted leading-[1.75] max-w-lg">{f.body}</p>
                    </div>

                    {/* Visual element */}
                    <div className="w-48 h-32 rounded-xl border border-white/[0.06] overflow-hidden relative shrink-0 hidden md:block" style={{ background: `linear-gradient(135deg, ${f.color}08, ${f.color}03)` }}>
                      <div className="absolute inset-0 bg-grid opacity-50" />
                      <div className="absolute bottom-3 right-3 w-8 h-8 rounded-lg" style={{ background: `${f.color}20`, boxShadow: `0 0 20px ${f.color}15` }} />
                      <div className="absolute top-3 left-3 w-5 h-5 rounded" style={{ background: `${f.color}15` }} />
                      <div className="absolute top-4 right-6 w-3 h-3 rounded-full" style={{ background: `${f.color}30` }} />
                    </div>
                  </div>
                </div>
              </Section>
            ))}
          </div>
        </div>
      </section>

      <div className="h-px shimmer-border" />

      {/* ════════════════════════════════════════════════════ */}
      {/* PLATFORMS                                           */}
      {/* ════════════════════════════════════════════════════ */}
      <section id="platforms" className="relative py-32 px-6">
        <div className="max-w-5xl mx-auto">
          <Section className="text-center mb-16">
            <span className="font-mono text-[11px] tracking-[0.22em] uppercase text-saibyl-cyan">Platforms</span>
            <h2 className="font-display font-extrabold text-[36px] sm:text-[44px] text-white mt-4 leading-[1.08]" style={{ letterSpacing: '-0.025em' }}>
              Simulate <span className="text-gradient">every platform</span>
            </h2>
            <p className="text-[15px] text-saibyl-muted max-w-md mx-auto mt-4 leading-[1.7]">
              Each adapter replicates real algorithmic behavior, feed ranking, and community dynamics.
            </p>
          </Section>

          <Section>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              {platforms.map((p) => (
                <div key={p.name} className="glass glass-hover rounded-xl p-5 transition-all duration-300 group cursor-default">
                  <h4 className="font-sans font-semibold text-[15px] text-saibyl-platinum group-hover:text-white transition-colors">{p.name}</h4>
                  <div className="flex items-center gap-3 mt-3">
                    <div className="text-[11px] text-saibyl-muted">
                      <span className="text-saibyl-indigo font-mono">{p.agents}</span>
                    </div>
                    <div className="w-px h-3 bg-white/[0.08]" />
                    <div className="text-[11px] text-saibyl-muted">
                      <span className="text-saibyl-cyan font-mono">{p.algo}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </Section>
        </div>
      </section>

      <div className="h-px shimmer-border" />

      {/* ════════════════════════════════════════════════════ */}
      {/* PRICING                                             */}
      {/* ════════════════════════════════════════════════════ */}
      <section id="pricing" className="relative py-32 px-6">
        <div className="max-w-5xl mx-auto">
          <Section className="text-center mb-16">
            <span className="font-mono text-[11px] tracking-[0.22em] uppercase text-saibyl-violet">Pricing</span>
            <h2 className="font-display font-extrabold text-[36px] sm:text-[44px] text-white mt-4 leading-[1.08]" style={{ letterSpacing: '-0.025em' }}>
              Simple, transparent pricing
            </h2>
          </Section>

          <Section>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
              {plans.map((p) => (
                <div
                  key={p.name}
                  className={`relative rounded-2xl p-8 transition-all duration-300 ${
                    p.pop
                      ? 'glass border-saibyl-indigo/30 shadow-[0_0_60px_rgba(91,95,238,0.08)] scale-[1.02]'
                      : 'glass glass-hover'
                  }`}
                >
                  {p.pop && (
                    <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                      <span className="font-mono text-[9px] tracking-[0.2em] uppercase px-3 py-1 rounded-full text-white" style={{ background: 'var(--grad-arc)' }}>Recommended</span>
                    </div>
                  )}
                  <div className="mb-6">
                    <h3 className="font-sans font-semibold text-[20px] text-white">{p.name}</h3>
                    <p className="text-[13px] text-saibyl-muted mt-1 leading-relaxed">{p.desc}</p>
                  </div>
                  <div className="mb-8">
                    <span className="text-[48px] font-display font-extrabold text-white leading-none">${p.price}</span>
                    <span className="text-saibyl-muted text-[14px] ml-1">/mo</span>
                  </div>
                  <ul className="space-y-3 mb-8">
                    {p.items.map((item) => (
                      <li key={item} className="flex items-center gap-2.5 text-[14px] text-saibyl-muted">
                        <svg className="w-4 h-4 text-saibyl-positive shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
                        {item}
                      </li>
                    ))}
                  </ul>
                  <Link
                    to="/signup"
                    className={`block text-center py-3 rounded-xl font-medium text-[14px] transition-all ${
                      p.pop
                        ? 'text-white hover:scale-[1.02] hover:shadow-[0_0_30px_rgba(91,95,238,0.3)]'
                        : 'glass glass-hover text-saibyl-platinum'
                    }`}
                    style={p.pop ? { background: 'var(--grad-arc)' } : undefined}
                  >
                    Get started
                  </Link>
                </div>
              ))}
            </div>
          </Section>
        </div>
      </section>

      <div className="h-px shimmer-border" />

      {/* ════════════════════════════════════════════════════ */}
      {/* FINAL CTA                                           */}
      {/* ════════════════════════════════════════════════════ */}
      <section className="relative py-40 px-6 overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(91,95,238,0.08)_0%,transparent_60%)]" />
        <Section className="relative z-10 max-w-2xl mx-auto text-center">
          <img src="/logo-mark.svg" alt="" className="w-20 h-20 mx-auto mb-10 animate-float drop-shadow-[0_0_40px_rgba(91,95,238,0.5)]" />
          <h2 className="font-display font-extrabold text-[36px] sm:text-[48px] text-white leading-[1.08]" style={{ letterSpacing: '-0.025em' }}>
            The oracle who saw everything.
            <br />
            <span className="text-gradient">Now as software.</span>
          </h2>
          <p className="text-[15px] text-saibyl-muted mt-6 leading-[1.7] max-w-md mx-auto">
            Join the private beta. Start predicting before the world reacts.
          </p>
          <Link
            to="/signup"
            className="group relative inline-flex items-center mt-10 px-10 py-4 rounded-xl text-white font-semibold text-[15px] overflow-hidden transition-all hover:scale-[1.03]"
          >
            <div className="absolute inset-0 bg-gradient-to-r from-[#5B5FEE] to-[#00D4FF]" />
            <div className="absolute inset-0 animate-glow-pulse rounded-xl" />
            <span className="relative flex items-center gap-2">
              Request early access
              <svg className="w-4 h-4 group-hover:translate-x-1 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" /></svg>
            </span>
          </Link>
        </Section>
      </section>

      {/* ── Footer ── */}
      <footer className="border-t border-white/[0.04] py-10 px-6">
        <div className="max-w-5xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <img src="/logo-primary.svg" alt="Saibyl" className="h-5 opacity-50" />
          <p className="text-[12px] text-saibyl-muted/60">&copy; 2024–2026 Saido Labs LLC</p>
          <div className="flex gap-5">
            <Link to="/login" className="text-[12px] text-saibyl-muted/60 hover:text-saibyl-platinum transition-colors">Sign in</Link>
            <Link to="/signup" className="text-[12px] text-saibyl-muted/60 hover:text-saibyl-platinum transition-colors">Get access</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
