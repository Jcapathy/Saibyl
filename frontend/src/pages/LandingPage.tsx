import { useRef } from 'react';
import { Link } from 'react-router-dom';
import { motion, useScroll, useTransform } from 'framer-motion';
import HeroAnimation from '@/components/HeroAnimation';

/* ── Animation helpers ──────────────────────────────────── */
const fadeUp = { initial: { opacity: 0, y: 32 }, whileInView: { opacity: 1, y: 0 }, viewport: { once: true, amount: 0.2 as const }, transition: { duration: 0.7 } };
const stagger = (i: number) => ({ ...fadeUp, transition: { duration: 0.6, delay: i * 0.1 } });
const hoverLift = { whileHover: { y: -5, transition: { duration: 0.25 } } };

/* ── Data ───────────────────────────────────────────────── */
const proofNames = ['Meridian Capital', 'Apex Strategies', 'NovaBridge AI', 'Polaris Research', 'Elysium Labs'];

const steps = [
  { n: '01', t: 'Upload source material', d: 'PDFs, videos, images, news articles — any content about the topic you want to predict.' },
  { n: '02', t: 'Configure the swarm', d: 'Choose platforms, persona packs, and agent count. Describe your prediction goal in plain language.' },
  { n: '03', t: 'Get predictive intelligence', d: 'Watch agents simulate in real time. Receive a full ReACT-powered report with evidence chains.' },
];

const features = [
  { tag: 'SIMULATE', title: 'Swarm intelligence at scale', body: 'Up to 1,000,000 synthetic personas across 8 social platforms. Each agent has a unique personality, backstory, and behavioral fingerprint.', color: '#5B5FEE', stats: [{ v: '1M', l: 'max agents' }, { v: '8', l: 'platforms' }, { v: '42', l: 'archetypes' }] },
  { tag: 'ANALYZE', title: 'ReACT intelligence engine', body: 'Multi-pass reasoning with 5 retrieval tools. Tunable depth from quick pulse checks to exhaustive research. Full evidence chains and interactive Q&A.', color: '#00D4FF', stats: [{ v: '5', l: 'tools' }, { v: '4', l: 'depth levels' }, { v: '∞', l: 'follow-ups' }] },
  { tag: 'PREDICT', title: 'Prediction market edge', body: 'Import from Kalshi and Polymarket. Get probability estimates, edge-vs-market analysis, and recommended positions backed by swarm consensus.', color: '#A78BFA', stats: [{ v: '2', l: 'exchanges' }, { v: '<3pp', l: 'pass threshold' }, { v: '80%', l: 'CI bands' }] },
];

const platforms = [
  { n: 'Twitter / X', a: 'Engagement-weighted', c: '#5B5FEE' }, { n: 'Reddit', a: 'Hot ranking', c: '#00D4FF' },
  { n: 'LinkedIn', a: 'Connection graph', c: '#5B5FEE' }, { n: 'Instagram', a: 'Explore algo', c: '#A78BFA' },
  { n: 'Hacker News', a: 'Karma decay', c: '#00D4FF' }, { n: 'Discord', a: 'Channel-based', c: '#5B5FEE' },
  { n: 'News Comments', a: 'Moderation sim', c: '#A78BFA' }, { n: 'Custom', a: 'Your rules', c: '#00D4FF' },
];

const plans = [
  { name: 'Starter', price: '99', items: ['10 simulations / mo', '5,000 agents per sim', '5 GB storage', '3 team members', '3 platforms'] },
  { name: 'Pro', price: '299', items: ['50 simulations / mo', '50,000 agents per sim', '25 GB storage', '10 team members', 'All platforms', 'Prediction markets'], pop: true },
  { name: 'Enterprise', price: '999', items: ['Unlimited simulations', '500,000 agents per sim', '100 GB storage', 'Unlimited team', 'Custom adapters', 'Dedicated support'] },
];

/* ── Simulated dashboard (product showcase) ─────────────── */
function FakeDashboard() {
  const agents = [
    { name: 'Sarah Chen', type: 'CTO', platform: 'Twitter / X', content: '"This merger changes everything for cloud infrastructure..."', sentiment: 0.7, color: '#5B5FEE' },
    { name: 'Mike Torres', type: 'Reddit Trader', platform: 'Reddit', content: '"Bullish on this — $ACME to $180 by Q3..."', sentiment: 0.4, color: '#00D4FF' },
    { name: 'Dr. Priya Nair', type: 'Academic', platform: 'LinkedIn', content: '"The regulatory implications here are significant..."', sentiment: -0.2, color: '#A78BFA' },
  ];
  return (
    <div className="glass rounded-2xl overflow-hidden border border-white/[0.08]">
      {/* macOS chrome */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-white/[0.06] bg-saibyl-deep/80">
        <div className="flex gap-1.5"><span className="w-3 h-3 rounded-full bg-[#FF5F57]" /><span className="w-3 h-3 rounded-full bg-[#FEBC2E]" /><span className="w-3 h-3 rounded-full bg-[#28C840]" /></div>
        <span className="text-[11px] text-saibyl-muted ml-2 font-mono">saibyl.app — Live Simulation</span>
      </div>
      <div className="flex">
        {/* Mini sidebar */}
        <div className="w-40 border-r border-white/[0.04] p-3 hidden md:block bg-saibyl-deep/50">
          {['Dashboard', 'Simulations', 'Markets', 'Reports', 'Settings'].map((item, i) => (
            <div key={item} className={`text-[11px] px-2.5 py-1.5 rounded-md mb-0.5 ${i === 1 ? 'bg-saibyl-elevated text-saibyl-platinum' : 'text-saibyl-muted'}`}>{item}</div>
          ))}
        </div>
        {/* Main area */}
        <div className="flex-1 p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <span className="text-[10px] font-mono text-saibyl-indigo tracking-wider uppercase">Live simulation</span>
              <h4 className="text-[14px] font-medium text-white mt-0.5">ACME Corp Merger Analysis</h4>
            </div>
            <div className="flex items-center gap-3 text-[11px] text-saibyl-muted">
              <span>Round <span className="text-saibyl-platinum font-mono">4</span>/10</span>
              <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-saibyl-positive animate-pulse" />Running</span>
            </div>
          </div>
          {/* Agent cards */}
          <div className="space-y-2">
            {agents.map((a) => (
              <div key={a.name} className="flex items-start gap-3 p-3 rounded-lg bg-white/[0.02] border border-white/[0.04]">
                <div className="w-7 h-7 rounded-full shrink-0 flex items-center justify-center text-[10px] font-bold text-white" style={{ background: a.color + '40' }}>{a.name[0]}</div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-[12px] font-medium text-saibyl-platinum">{a.name}</span>
                    <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-white/[0.04] text-saibyl-muted">{a.type}</span>
                    <span className="text-[9px] font-mono text-saibyl-muted ml-auto">{a.platform}</span>
                  </div>
                  <p className="text-[11px] text-saibyl-muted leading-relaxed truncate">{a.content}</p>
                  {/* Sentiment bar */}
                  <div className="mt-1.5 w-full h-1 bg-saibyl-elevated rounded-full overflow-hidden">
                    <div className="h-full rounded-full" style={{ width: `${(a.sentiment + 1) * 50}%`, background: a.sentiment > 0.2 ? '#10B981' : a.sentiment < -0.2 ? '#EF4444' : '#64748B' }} />
                  </div>
                </div>
              </div>
            ))}
          </div>
          {/* Fake chart */}
          <div className="mt-4 flex items-end gap-1 h-12">
            {[35, 42, 38, 55, 48, 62, 58, 70, 65, 72, 68, 75].map((h, i) => (
              <div key={i} className="flex-1 rounded-sm" style={{ height: `${h}%`, background: `linear-gradient(to top, #5B5FEE${i > 8 ? '' : '80'}, #00D4FF${i > 8 ? '' : '60'})` }} />
            ))}
          </div>
          <div className="flex justify-between text-[9px] text-saibyl-muted mt-1 font-mono">
            <span>R1</span><span>R4</span><span>R8</span><span>R12</span>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════ */
/* PAGE                                                       */
/* ══════════════════════════════════════════════════════════ */

export default function LandingPage() {
  const containerRef = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: containerRef });
  const navShadow = useTransform(scrollYProgress, [0, 0.02], [0, 1]);

  return (
    <div ref={containerRef} className="min-h-screen bg-saibyl-void text-saibyl-platinum overflow-x-hidden selection:bg-saibyl-indigo/30">

      {/* BG layers */}
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute inset-0 bg-grid" />
        <div className="absolute top-[-40%] left-[-20%] w-[80%] h-[80%] rounded-full bg-[radial-gradient(ellipse,rgba(91,95,238,0.12)_0%,transparent_60%)] animate-breathe" />
        <div className="absolute bottom-[-30%] right-[-15%] w-[70%] h-[70%] rounded-full bg-[radial-gradient(ellipse,rgba(0,212,255,0.07)_0%,transparent_60%)] animate-breathe" style={{ animationDelay: '-4s' }} />
        <div className="absolute top-[20%] right-[5%] w-[50%] h-[50%] rounded-full bg-[radial-gradient(ellipse,rgba(167,139,250,0.05)_0%,transparent_60%)] animate-breathe" style={{ animationDelay: '-7s' }} />
      </div>

      {/* NAV */}
      <motion.nav className="fixed top-0 left-0 right-0 z-50" style={{ boxShadow: useTransform(navShadow, (v: number) => `0 1px 20px rgba(0,0,0,${v * 0.3})`) }}>
        <div className="mx-3 sm:mx-4 mt-3 rounded-2xl glass">
          <div className="max-w-6xl mx-auto flex items-center justify-between px-5 h-14">
            <img src="/logo-primary.svg" alt="Saibyl" className="h-7" />
            <div className="flex items-center gap-5">
              <a href="#how" className="text-[13px] text-saibyl-muted hover:text-saibyl-platinum transition-colors hidden md:block">How It Works</a>
              <a href="#features" className="text-[13px] text-saibyl-muted hover:text-saibyl-platinum transition-colors hidden md:block">Features</a>
              <a href="#pricing" className="text-[13px] text-saibyl-muted hover:text-saibyl-platinum transition-colors hidden md:block">Pricing</a>
              <div className="w-px h-5 bg-white/[0.08] hidden md:block" />
              <Link to="/login" className="text-[13px] text-saibyl-muted hover:text-saibyl-platinum transition-colors">Sign in</Link>
              <Link to="/signup" className="text-[13px] font-medium px-4 py-1.5 rounded-lg bg-saibyl-indigo text-white hover:bg-[#4B4FDE] transition-all hover:shadow-[0_0_20px_rgba(91,95,238,0.25)]">
                Get started
              </Link>
            </div>
          </div>
        </div>
      </motion.nav>

      {/* ═══ HERO ═══ */}
      <section className="relative min-h-[100dvh] flex flex-col items-center justify-center text-center px-6 overflow-hidden">
        <div className="absolute inset-0 opacity-50"><HeroAnimation /></div>
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[700px] rounded-full bg-[radial-gradient(circle,rgba(91,95,238,0.12)_0%,transparent_65%)] pointer-events-none" />

        <div className="relative z-10 max-w-3xl">
          <motion.div {...stagger(0)} className="inline-flex items-center gap-2.5 px-4 py-1.5 rounded-full glass mb-10">
            <span className="relative flex h-2 w-2"><span className="animate-ping absolute h-full w-full rounded-full bg-saibyl-positive opacity-75" /><span className="relative rounded-full h-2 w-2 bg-saibyl-positive" /></span>
            <span className="font-mono text-[11px] tracking-[0.2em] uppercase text-saibyl-muted">Now in private beta</span>
          </motion.div>

          <motion.div {...stagger(1)} className="flex items-center justify-center gap-5 mb-10">
            <img src="/logo-mark.svg" alt="" className="w-[72px] h-[72px] sm:w-[88px] sm:h-[88px] animate-float drop-shadow-[0_0_40px_rgba(91,95,238,0.5)]" />
            <span className="font-display font-extrabold text-[56px] sm:text-[68px] md:text-[80px] text-gradient select-none" style={{ lineHeight: 1, letterSpacing: '-0.03em' }}>SAIBYL</span>
          </motion.div>

          <motion.h1 {...stagger(2)} className="font-display font-extrabold text-[36px] sm:text-[48px] md:text-[60px] leading-[1.06] tracking-tight text-white mb-6">
            Know the conversation{' '}<span className="text-gradient">before it happens</span>
          </motion.h1>

          <motion.p {...stagger(3)} className="text-[16px] sm:text-[17px] text-saibyl-muted max-w-xl mx-auto leading-[1.75] mb-12">
            Deploy swarms of AI personas to simulate social media reactions and predict outcomes — before the world catches up.
          </motion.p>

          <motion.div {...stagger(4)} className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link to="/signup" className="group relative w-full sm:w-auto inline-flex items-center justify-center px-8 py-4 rounded-xl text-white font-semibold text-[15px] overflow-hidden transition-all hover:scale-[1.03]">
              <div className="absolute inset-0 bg-gradient-to-r from-[#5B5FEE] to-[#00D4FF]" />
              <div className="absolute inset-0 bg-gradient-to-r from-[#4B4FDE] to-[#00B8D9] opacity-0 group-hover:opacity-100 transition-opacity" />
              <div className="absolute inset-0 animate-glow-pulse rounded-xl" />
              <span className="relative flex items-center gap-2">Request early access<svg className="w-4 h-4 group-hover:translate-x-1 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" /></svg></span>
            </Link>
            <Link to="/login" className="w-full sm:w-auto inline-flex items-center justify-center px-8 py-4 rounded-xl text-saibyl-platinum font-medium text-[15px] glass glass-hover transition-all">Watch demo</Link>
          </motion.div>
        </div>

        <div className="absolute bottom-10 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 text-saibyl-muted/40">
          <span className="text-[10px] font-mono tracking-[0.15em] uppercase">Scroll</span>
          <div className="w-px h-8 bg-gradient-to-b from-saibyl-muted/30 to-transparent" />
        </div>
      </section>

      <div className="h-px shimmer-border" />

      {/* ═══ SOCIAL PROOF ═══ */}
      <section className="py-14 px-6">
        <motion.div {...fadeUp} className="max-w-4xl mx-auto flex flex-col sm:flex-row items-center justify-center gap-6 sm:gap-10">
          <span className="text-[11px] font-mono tracking-[0.15em] uppercase text-saibyl-muted/50 shrink-0">Trusted by teams building the future</span>
          <div className="flex flex-wrap items-center justify-center gap-8">
            {proofNames.map((n) => (<span key={n} className="text-[14px] font-medium text-saibyl-muted/30 tracking-wide">{n}</span>))}
          </div>
        </motion.div>
      </section>

      <div className="h-px shimmer-border" />

      {/* ═══ PRODUCT SHOWCASE ═══ */}
      <section className="py-32 px-6">
        <div className="max-w-4xl mx-auto">
          <motion.div initial={{ opacity: 0, y: 40, scale: 0.96 }} whileInView={{ opacity: 1, y: 0, scale: 1 }} viewport={{ once: true, amount: 0.15 }} transition={{ duration: 0.8 }}>
            <FakeDashboard />
          </motion.div>
          <motion.div {...fadeUp} className="text-center mt-14">
            <h2 className="font-display font-extrabold text-[32px] sm:text-[40px] text-white leading-[1.1]" style={{ letterSpacing: '-0.025em' }}>
              See your predictions <span className="text-gradient">come alive</span>
            </h2>
            <p className="text-[15px] text-saibyl-muted mt-4 max-w-lg mx-auto leading-[1.7]">
              Watch thousands of AI agents debate, react, and form consensus in real time. Every interaction streamed live to your dashboard.
            </p>
          </motion.div>
        </div>
      </section>

      <div className="h-px shimmer-border" />

      {/* ═══ HOW IT WORKS ═══ */}
      <section id="how" className="py-32 px-6">
        <div className="max-w-5xl mx-auto">
          <motion.div {...fadeUp} className="text-center mb-20">
            <span className="font-mono text-[11px] tracking-[0.22em] uppercase text-saibyl-cyan">How It Works</span>
            <h2 className="font-display font-extrabold text-[36px] sm:text-[44px] text-white mt-4 leading-[1.08]" style={{ letterSpacing: '-0.025em' }}>Three steps to prediction</h2>
          </motion.div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 relative">
            {/* Connecting lines */}
            <div className="hidden md:block absolute top-14 left-[33%] right-[33%] h-px bg-gradient-to-r from-saibyl-indigo/30 via-saibyl-cyan/30 to-saibyl-violet/30" />
            {steps.map((s, i) => (
              <motion.div key={s.n} {...stagger(i)} {...hoverLift} className="glass glass-hover rounded-2xl p-8 transition-all duration-300 relative">
                <span className="font-mono text-[42px] font-bold text-gradient opacity-25">{s.n}</span>
                <h3 className="font-sans font-semibold text-[17px] text-white mt-2 mb-2">{s.t}</h3>
                <p className="text-[14px] text-saibyl-muted leading-[1.7]">{s.d}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      <div className="h-px shimmer-border" />

      {/* ═══ FEATURES ═══ */}
      <section id="features" className="py-32 px-6">
        <div className="max-w-5xl mx-auto">
          <motion.div {...fadeUp} className="text-center mb-20">
            <span className="font-mono text-[11px] tracking-[0.22em] uppercase text-saibyl-indigo">Capabilities</span>
            <h2 className="font-display font-extrabold text-[36px] sm:text-[44px] text-white mt-4 leading-[1.08]" style={{ letterSpacing: '-0.025em' }}>
              Everything you need to <span className="text-gradient">predict the future</span>
            </h2>
          </motion.div>
          <div className="space-y-5">
            {features.map((f, i) => (
              <motion.div key={f.tag} {...stagger(i)} className="group glass glass-hover rounded-2xl p-8 md:p-10 transition-all duration-300 relative overflow-hidden">
                <div className="absolute left-0 top-0 bottom-0 w-[3px] rounded-full opacity-0 group-hover:opacity-100 transition-all duration-300" style={{ background: f.color }} />
                <div className="flex flex-col md:flex-row md:items-start gap-6">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-3">
                      <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: f.color + '18' }}><div className="w-3 h-3 rounded-sm" style={{ background: f.color }} /></div>
                      <span className="font-mono text-[11px] tracking-[0.22em] uppercase" style={{ color: f.color }}>{f.tag}</span>
                    </div>
                    <h3 className="font-display font-bold text-[22px] text-white mb-2" style={{ letterSpacing: '-0.015em' }}>{f.title}</h3>
                    <p className="text-[15px] text-saibyl-muted leading-[1.75] max-w-lg">{f.body}</p>
                  </div>
                  <div className="flex gap-7 md:pt-8 shrink-0">
                    {f.stats.map((s) => (<div key={s.l} className="text-center"><div className="text-[28px] font-display font-bold text-gradient leading-none">{s.v}</div><div className="text-[11px] text-saibyl-muted mt-1 whitespace-nowrap">{s.l}</div></div>))}
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      <div className="h-px shimmer-border" />

      {/* ═══ PLATFORMS ═══ */}
      <section className="py-32 px-6">
        <div className="max-w-5xl mx-auto">
          <motion.div {...fadeUp} className="text-center mb-16">
            <span className="font-mono text-[11px] tracking-[0.22em] uppercase text-saibyl-cyan">Platforms</span>
            <h2 className="font-display font-extrabold text-[36px] sm:text-[44px] text-white mt-4 leading-[1.08]" style={{ letterSpacing: '-0.025em' }}>
              Simulate <span className="text-gradient">every platform</span>
            </h2>
          </motion.div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {platforms.map((p, i) => (
              <motion.div key={p.n} {...stagger(i)} {...hoverLift} className="glass glass-hover rounded-xl p-5 transition-all duration-300 cursor-default">
                <div className="flex items-center gap-2 mb-2">
                  <div className="w-2 h-2 rounded-full" style={{ background: p.c }} />
                  <span className="text-[14px] font-medium text-saibyl-platinum">{p.n}</span>
                </div>
                <span className="text-[12px] text-saibyl-muted font-mono">{p.a}</span>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      <div className="h-px shimmer-border" />

      {/* ═══ PRICING ═══ */}
      <section id="pricing" className="py-32 px-6">
        <div className="max-w-5xl mx-auto">
          <motion.div {...fadeUp} className="text-center mb-16">
            <span className="font-mono text-[11px] tracking-[0.22em] uppercase text-saibyl-violet">Pricing</span>
            <h2 className="font-display font-extrabold text-[36px] sm:text-[44px] text-white mt-4 leading-[1.08]" style={{ letterSpacing: '-0.025em' }}>Simple, transparent pricing</h2>
          </motion.div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            {plans.map((p, i) => (
              <motion.div key={p.name} {...stagger(i)} {...hoverLift}
                className={`relative rounded-2xl p-8 transition-all duration-300 ${p.pop ? 'glass border-saibyl-indigo/30 shadow-[0_0_60px_rgba(91,95,238,0.08)] scale-[1.03]' : 'glass glass-hover'}`}
              >
                {p.pop && <div className="absolute -top-3 left-1/2 -translate-x-1/2"><span className="font-mono text-[9px] tracking-[0.2em] uppercase px-3 py-1 rounded-full text-white" style={{ background: 'var(--grad-arc)' }}>Recommended</span></div>}
                <h3 className="font-sans font-semibold text-[20px] text-white">{p.name}</h3>
                <div className="mt-4 mb-6"><span className="text-[48px] font-display font-extrabold text-white leading-none">${p.price}</span><span className="text-saibyl-muted text-[14px] ml-1">/mo</span></div>
                <ul className="space-y-3 mb-8">
                  {p.items.map((item) => (
                    <li key={item} className="flex items-center gap-2.5 text-[14px] text-saibyl-muted">
                      <svg className="w-4 h-4 text-saibyl-positive shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>{item}
                    </li>
                  ))}
                </ul>
                <Link to="/signup" className={`block text-center py-3 rounded-xl font-medium text-[14px] transition-all ${p.pop ? 'text-white hover:shadow-[0_0_30px_rgba(91,95,238,0.3)] hover:scale-[1.02]' : 'glass glass-hover text-saibyl-platinum'}`} style={p.pop ? { background: 'var(--grad-arc)' } : undefined}>
                  Get started
                </Link>
              </motion.div>
            ))}
          </div>
          <motion.p {...fadeUp} className="text-center text-[13px] text-saibyl-muted/60 mt-8">All plans include a 14-day free trial. No credit card required.</motion.p>
        </div>
      </section>

      <div className="h-px shimmer-border" />

      {/* ═══ FINAL CTA ═══ */}
      <section className="py-40 px-6 relative overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(91,95,238,0.08)_0%,transparent_60%)]" />
        <motion.div {...fadeUp} className="relative z-10 max-w-2xl mx-auto text-center">
          <img src="/logo-mark.svg" alt="" className="w-20 h-20 mx-auto mb-10 animate-float drop-shadow-[0_0_40px_rgba(91,95,238,0.5)]" />
          <h2 className="font-display font-extrabold text-[36px] sm:text-[48px] text-white leading-[1.08]" style={{ letterSpacing: '-0.025em' }}>
            The oracle who saw everything.<br /><span className="text-gradient">Now as software.</span>
          </h2>
          <p className="text-[15px] text-saibyl-muted mt-6 leading-[1.7] max-w-md mx-auto">Join the private beta. Start predicting before the world reacts.</p>
          <Link to="/signup" className="group relative inline-flex items-center mt-10 px-10 py-4 rounded-xl text-white font-semibold text-[15px] overflow-hidden transition-all hover:scale-[1.03]">
            <div className="absolute inset-0 bg-gradient-to-r from-[#5B5FEE] to-[#00D4FF]" /><div className="absolute inset-0 animate-glow-pulse rounded-xl" />
            <span className="relative flex items-center gap-2">Request early access<svg className="w-4 h-4 group-hover:translate-x-1 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" /></svg></span>
          </Link>
        </motion.div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/[0.04] py-10 px-6">
        <div className="max-w-5xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <img src="/logo-primary.svg" alt="Saibyl" className="h-5 opacity-50" />
          <p className="text-[12px] text-saibyl-muted/50">&copy; 2024–2026 Saido Labs LLC</p>
          <div className="flex gap-5"><Link to="/login" className="text-[12px] text-saibyl-muted/50 hover:text-saibyl-platinum transition-colors">Sign in</Link><Link to="/signup" className="text-[12px] text-saibyl-muted/50 hover:text-saibyl-platinum transition-colors">Get access</Link></div>
        </div>
      </footer>
    </div>
  );
}
