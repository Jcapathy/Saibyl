import { useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { FileText, Users, Activity, BarChart3, Zap, Globe, Shield, Code, Check, Plus } from 'lucide-react';
import HeroAnimation from '@/components/HeroAnimation';

/* ── Animation helpers ─────────────────────────────────────── */
const fadeUp = {
  initial: { opacity: 0, y: 32 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, amount: 0.2 },
  transition: { duration: 0.6 },
};
const stagger = (i: number) => ({ ...fadeUp, transition: { duration: 0.5, delay: i * 0.1 } });

/* ── Data ──────────────────────────────────────────────────── */
const howItWorksSteps = [
  { num: '01', title: 'Define Your Scenario', desc: 'Describe the event, announcement, or content you want to test before it goes live.', Icon: FileText },
  { num: '02', title: 'Choose Platforms & Personas', desc: 'Select from 8 simulated social platforms and configure persona packs to match your target audience.', Icon: Users },
  { num: '03', title: 'Watch Agents React', desc: 'Observe real-time simulation with live sentiment tracking as synthetic agents interact with your content.', Icon: Activity },
  { num: '04', title: 'Get Your Report', desc: 'Download a structured intelligence report with probability estimates, sentiment analysis, and evidence chains.', Icon: BarChart3 },
];

const featureCards = [
  { title: 'Agent Swarms', desc: 'Deploy up to 1M synthetic agents with unique personalities, backstories, and behavioral fingerprints.', Icon: Zap, color: '#5B5FEE' },
  { title: '8 Platforms', desc: 'X, Reddit, Instagram, TikTok, YouTube, LinkedIn, News, Hacker News.', Icon: Globe, color: '#00D4FF' },
  { title: 'Real-Time Sentiment', desc: 'Live sentiment tracking and consensus formation during simulation.', Icon: Activity, color: '#10B981' },
  { title: 'Actionable Reports', desc: 'Downloadable PDF/CSV with AI analysis, probability estimates, evidence chains.', Icon: FileText, color: '#C9A227' },
  { title: 'Enterprise Security', desc: 'SOC 2 compliant, 256-bit encryption, private infrastructure.', Icon: Shield, color: '#5B5FEE' },
  { title: 'API Access', desc: 'RESTful API to integrate predictions into your workflow.', Icon: Code, color: '#00D4FF' },
];

const useCases = [
  { title: 'PR & Crisis', tag: 'PR & Comms', tagColor: '#5B5FEE', question: 'Will this announcement cause backlash?', desc: 'Test press releases, executive statements, and crisis responses before they go live.', result: '87% probability of negative sentiment spike' },
  { title: 'Policy & Government', tag: 'Political Strategy', tagColor: '#00D4FF', question: 'How will voters react to this bill?', desc: 'Simulate constituent reactions across demographics and political leanings.', result: '62% support among swing demographics' },
  { title: 'Sports & Betting', tag: 'Sports Analytics', tagColor: '#C9A227', question: "What's the fan reaction to this trade?", desc: 'Predict fan engagement and sentiment around trades, signings, and announcements.', result: '3.2x engagement spike predicted' },
  { title: 'Marketing', tag: 'Enterprise', tagColor: '#10B981', question: 'Will this campaign go viral or flop?', desc: 'Test campaign creative and messaging across target demographics before launch.', result: '91% positive reception probability' },
];

const pricingPlans = [
  {
    name: 'Analyst', price: '$149', period: '/mo', featured: false,
    desc: 'For teams getting started with social prediction',
    items: ['10 simulations/month', 'Up to 5,000 agents per simulation', '50,000 agents/month total', '3 platforms', '3 persona packs', 'Basic reports', 'Email support'],
    cta: 'Get Started', ctaLink: '/signup',
  },
  {
    name: 'Strategist', price: '$499', period: '/mo', featured: true,
    desc: 'For teams that need comprehensive coverage',
    items: ['50 simulations/month', 'Up to 25,000 agents per simulation', '500,000 agents/month total', 'All 8 platforms', '8 persona packs', 'Advanced reports + PDF/CSV export', 'API access', 'Priority support'],
    cta: 'Get Started', ctaLink: '/signup',
  },
  {
    name: 'War Room', price: '$1,499', period: '/mo', featured: false,
    desc: 'For organizations running high-stakes simulations',
    items: ['200 simulations/month', 'Up to 100,000 agents per simulation', '2,000,000 agents/month total', 'All 8 platforms', 'All 16 persona packs', 'Custom report templates', 'Webhook integrations', 'Dedicated account manager'],
    cta: 'Get Started', ctaLink: '/signup',
  },
  {
    name: 'Enterprise', price: 'Custom', period: '', featured: false,
    desc: 'For maximum-scale analysis with dedicated infrastructure',
    items: ['Unlimited simulations', '500,000+ agents per simulation', 'Unlimited monthly volume', 'Custom persona creation', 'White-label reports', 'SSO/SAML', 'SLA guarantee', 'Dedicated infrastructure'],
    cta: 'Contact Sales', ctaLink: 'mailto:info@saidolabs.com',
  },
];

const faqItems = [
  { q: 'What is Saibyl?', a: 'Saibyl is a synthetic agent platform that simulates public reactions across social media platforms. Deploy AI personas to predict how the internet will react to your content, announcements, or policies — before you publish.' },
  { q: 'How do the synthetic agents work?', a: 'Each agent has a unique personality, backstory, political leaning, and behavioral fingerprint based on real demographic data. They interact with your content and each other across simulated platform environments, producing emergent consensus patterns.' },
  { q: 'Which platforms are supported?', a: 'We simulate X (Twitter), Reddit, Instagram, TikTok, YouTube, LinkedIn, News comment sections, and Hacker News. Each platform has its own algorithmic model for content ranking and engagement.' },
  { q: 'Is my data private?', a: "Absolutely. All simulations run in isolated environments. We're SOC 2 compliant, use 256-bit encryption, and never share your data with third parties. Enterprise customers get dedicated infrastructure." },
  { q: 'Can I try before subscribing?', a: 'Yes. All plans include a 14-day free trial with no credit card required. You can run simulations and see the full report output before committing.' },
  { q: 'How accurate are the predictions?', a: 'Our predictions achieve less than 3 percentage points of deviation from actual outcomes in controlled studies. Accuracy improves with higher agent counts and more specific scenario definitions.' },
];

/* ══════════════════════════════════════════════════════════════ */
/* PAGE                                                          */
/* ══════════════════════════════════════════════════════════════ */

export default function LandingPage() {
  const [openFaq, setOpenFaq] = useState<number[]>([]);

  const toggleFaq = (index: number) => {
    setOpenFaq((prev) =>
      prev.includes(index) ? prev.filter((i) => i !== index) : [...prev, index]
    );
  };

  return (
    <div className="scroll-smooth min-h-screen bg-[#070B14] text-[#E8ECF2] overflow-x-hidden">

      {/* ═══ 1. STICKY NAVIGATION ═══ */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-[#070B14]/80 backdrop-blur-xl border-b border-[#1B2433]">
        <div className="max-w-7xl mx-auto flex items-center justify-between px-6 h-16">
          {/* Left: Logo + brand */}
          <Link to="/" className="flex items-center gap-2.5">
            <img src="/logo-mark.svg" alt="Saibyl" className="h-7 w-7" />
            <span className="text-gradient-brand font-extrabold text-lg tracking-tight">SAIBYL</span>
          </Link>

          {/* Center: Nav links */}
          <div className="hidden md:flex items-center gap-8">
            <a href="#how-it-works" className="text-sm text-[#8B97A8] hover:text-[#E8ECF2] transition-colors">How It Works</a>
            <a href="#features" className="text-sm text-[#8B97A8] hover:text-[#E8ECF2] transition-colors">Features</a>
            <a href="#use-cases" className="text-sm text-[#8B97A8] hover:text-[#E8ECF2] transition-colors">Use Cases</a>
            <a href="#pricing" className="text-sm text-[#8B97A8] hover:text-[#E8ECF2] transition-colors">Pricing</a>
          </div>

          {/* Right: Auth */}
          <div className="flex items-center gap-4">
            <Link to="/login" className="text-sm text-[#8B97A8] hover:text-[#E8ECF2] transition-colors">Sign In</Link>
            <Link to="/signup" className="text-sm font-semibold px-5 py-2 rounded-lg bg-[#C9A227] text-[#070B14] hover:bg-[#D4AF37] transition-colors">
              Get Started
            </Link>
          </div>
        </div>
      </nav>

      {/* ═══ 2. HERO SECTION ═══ */}
      <section className="relative min-h-screen flex flex-col items-center justify-center text-center px-6 pt-16 overflow-hidden">
        {/* Background: HeroAnimation */}
        <div className="absolute inset-0 opacity-40 pointer-events-none">
          <HeroAnimation />
        </div>
        {/* Radial gradient overlay */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(91,95,238,0.08)_0%,transparent_60%)] pointer-events-none" />

        <div className="relative z-10 max-w-3xl">
          {/* Beta badge */}
          <motion.div {...stagger(0)} className="inline-flex items-center gap-2.5 px-4 py-1.5 rounded-full border border-[#5B5FEE]/20 bg-[#5B5FEE]/10 mb-8">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute h-full w-full rounded-full bg-green-400 opacity-75" />
              <span className="relative rounded-full h-2 w-2 bg-green-400" />
            </span>
            <span className="font-mono text-xs tracking-widest uppercase text-[#8B97A8]">Now in Private Beta</span>
          </motion.div>

          {/* Logo mark */}
          <motion.div {...stagger(1)} className="flex justify-center mb-8">
            <img src="/logo-mark.svg" alt="" className="w-[72px] h-[72px]" />
          </motion.div>

          {/* Headline */}
          <motion.h1 {...stagger(2)} className="font-display font-extrabold leading-[1.05] tracking-tight mb-6" style={{ fontSize: 'clamp(3rem, 6vw, 4.5rem)' }}>
            <span className="text-gradient-brand">Know the conversation</span>
            <br />
            <span className="text-gradient-brand">before it happens</span>
          </motion.h1>

          {/* Subtitle */}
          <motion.p {...stagger(3)} className="text-lg text-[#8B97A8] max-w-2xl mx-auto leading-relaxed mb-10">
            Simulate public reactions across 8 platforms with up to 1M synthetic agents. Get structured intelligence reports before you publish, launch, or announce.
          </motion.p>

          {/* CTAs */}
          <motion.div {...stagger(4)} className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-16">
            <Link to="/signup" className="px-8 py-3.5 rounded-xl font-semibold text-[#070B14] bg-[#C9A227] hover:bg-[#D4AF37] transition-colors text-base">
              Start Free Trial &rarr;
            </Link>
            <a href="#how-it-works" className="px-8 py-3.5 rounded-xl font-semibold text-[#E8ECF2] border border-[#1B2433] hover:border-[#5B5FEE]/30 transition-colors text-base">
              See how it works
            </a>
          </motion.div>

          {/* Stats bar */}
          <motion.div {...stagger(5)} className="border-t border-[#1B2433] pt-8 grid grid-cols-2 md:grid-cols-4 gap-6 max-w-2xl mx-auto">
            {[
              { value: '1M+', label: 'Max Agents' },
              { value: '8', label: 'Platforms' },
              { value: '42', label: 'Archetypes' },
              { value: '<3 Min', label: 'Results' },
            ].map((stat, i) => (
              <div key={i} className="text-center">
                <div className="text-gradient-brand font-mono text-2xl font-bold">{stat.value}</div>
                <div className="text-[#5A6578] text-xs mt-1">{stat.label}</div>
              </div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ═══ 3. TRUST BAR ═══ */}
      <section className="border-t border-b border-[#1B2433] py-6">
        <motion.div {...fadeUp} className="max-w-5xl mx-auto flex flex-wrap items-center justify-center gap-x-8 gap-y-3 px-6">
          {['PR & Comms', 'Political Strategy', 'FinTech', 'Sports Analytics', 'Enterprise'].map((label, i) => (
            <span key={label} className="flex items-center gap-8">
              <span className="font-mono text-xs uppercase tracking-[0.15em] text-[#5A6578]">{label}</span>
              {i < 4 && <span className="hidden sm:block w-px h-4 bg-[#1B2433]" />}
            </span>
          ))}
        </motion.div>
      </section>

      {/* ═══ 4. HOW IT WORKS ═══ */}
      <section id="how-it-works" className="py-28 px-6">
        <div className="max-w-6xl mx-auto">
          <motion.div {...fadeUp} className="text-center mb-16">
            <span className="font-mono text-xs tracking-[0.2em] uppercase text-[#00D4FF]">HOW IT WORKS</span>
            <h2 className="font-display font-extrabold text-4xl sm:text-5xl text-[#E8ECF2] mt-4 leading-tight tracking-tight">
              From scenario to strategy in four steps
            </h2>
          </motion.div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {howItWorksSteps.map((step, i) => (
              <motion.div
                key={step.num}
                {...stagger(i)}
                className="bg-[#111820] border border-[#1B2433] rounded-2xl p-8 hover:border-[#5B5FEE]/20 hover:-translate-y-1 transition-all duration-300"
              >
                <span className="font-mono text-sm text-[#5B5FEE] font-semibold">{step.num}</span>
                <div className="mt-4 mb-4 w-12 h-12 rounded-xl bg-[#5B5FEE]/10 flex items-center justify-center">
                  <step.Icon className="w-6 h-6 text-[#5B5FEE]" />
                </div>
                <h3 className="font-sans font-semibold text-lg text-[#E8ECF2] mb-2">{step.title}</h3>
                <p className="text-sm text-[#8B97A8] leading-relaxed">{step.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ═══ 5. FEATURES ═══ */}
      <section id="features" className="py-28 px-6 bg-[#0D1117] border-t border-b border-[#1B2433]">
        <div className="max-w-6xl mx-auto">
          <motion.div {...fadeUp} className="text-center mb-16">
            <span className="font-mono text-xs tracking-[0.2em] uppercase text-[#00D4FF]">CAPABILITIES</span>
            <h2 className="font-display font-extrabold text-4xl sm:text-5xl text-[#E8ECF2] mt-4 leading-tight tracking-tight">
              Everything you need to predict{' '}<span className="text-gradient-brand">the future</span>
            </h2>
          </motion.div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {featureCards.map((f, i) => (
              <motion.div
                key={f.title}
                {...stagger(i)}
                className="bg-[#111820] border border-[#1B2433] rounded-2xl p-8 hover:border-[#5B5FEE]/20 hover:-translate-y-1 transition-all duration-300"
              >
                <div className="w-12 h-12 rounded-xl flex items-center justify-center mb-5" style={{ background: f.color + '15' }}>
                  <f.Icon className="w-6 h-6" style={{ color: f.color }} />
                </div>
                <h3 className="font-sans font-semibold text-lg text-[#E8ECF2] mb-2">{f.title}</h3>
                <p className="text-sm text-[#8B97A8] leading-relaxed">{f.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ═══ 6. USE CASES ═══ */}
      <section id="use-cases" className="py-28 px-6">
        <div className="max-w-6xl mx-auto">
          <motion.div {...fadeUp} className="text-center mb-16">
            <span className="font-mono text-xs tracking-[0.2em] uppercase text-[#00D4FF]">USE CASES</span>
            <h2 className="font-display font-extrabold text-4xl sm:text-5xl text-[#E8ECF2] mt-4 leading-tight tracking-tight">
              Intelligence for every industry
            </h2>
          </motion.div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {useCases.map((uc, i) => (
              <motion.div
                key={uc.title}
                {...stagger(i)}
                className="bg-[#111820] border border-[#1B2433] rounded-2xl overflow-hidden hover:border-[#5B5FEE]/20 transition-all duration-300"
              >
                {/* Gradient top border */}
                <div className="h-0.5" style={{ background: `linear-gradient(90deg, ${uc.tagColor}, transparent)` }} />
                <div className="p-8">
                  {/* Tag pill */}
                  <span className="inline-block px-3 py-1 rounded-full text-xs font-mono font-medium mb-4" style={{ background: uc.tagColor + '15', color: uc.tagColor }}>
                    {uc.tag}
                  </span>
                  <h3 className="font-sans font-semibold text-xl text-[#E8ECF2] mb-2">{uc.question}</h3>
                  <p className="text-sm text-[#8B97A8] leading-relaxed mb-6">{uc.desc}</p>
                  {/* Result metric */}
                  <div className="flex items-center gap-2 text-sm">
                    <Check className="w-4 h-4 text-green-400 shrink-0" />
                    <span className="text-[#E8ECF2] font-medium">{uc.result}</span>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ═══ 7. PRICING ═══ */}
      <section id="pricing" className="py-28 px-6 bg-[#0D1117] border-t border-b border-[#1B2433]">
        <div className="max-w-7xl mx-auto">
          <motion.div {...fadeUp} className="text-center mb-16">
            <span className="font-mono text-xs tracking-[0.2em] uppercase text-[#00D4FF]">PRICING</span>
            <h2 className="font-display font-extrabold text-4xl sm:text-5xl text-[#E8ECF2] mt-4 leading-tight tracking-tight">
              Transparent pricing that scales
            </h2>
            <p className="text-lg text-[#8B97A8] mt-4 max-w-xl mx-auto">
              Choose the plan that matches your intelligence needs
            </p>
          </motion.div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {pricingPlans.map((plan, i) => (
              <motion.div
                key={plan.name}
                {...stagger(i)}
                className={`relative rounded-2xl p-8 flex flex-col ${
                  plan.featured
                    ? 'bg-[#111820] border-2 border-[#5B5FEE] shadow-[0_0_40px_rgba(91,95,238,0.1)]'
                    : 'bg-[#111820] border border-[#1B2433]'
                }`}
              >
                {plan.featured && (
                  <div className="absolute -top-3.5 left-1/2 -translate-x-1/2">
                    <span className="font-mono text-[10px] tracking-[0.15em] uppercase px-3 py-1.5 rounded-full bg-[#5B5FEE] text-white font-semibold">
                      MOST POPULAR
                    </span>
                  </div>
                )}

                <h3 className="font-sans font-semibold text-xl text-[#E8ECF2]">{plan.name}</h3>
                <p className="text-sm text-[#8B97A8] mt-2 mb-6">{plan.desc}</p>

                <div className="mb-6">
                  <span className="font-display font-extrabold text-4xl text-[#E8ECF2]">{plan.price}</span>
                  {plan.period && <span className="text-[#8B97A8] text-sm ml-1">{plan.period}</span>}
                </div>

                <ul className="space-y-3 mb-8 flex-1">
                  {plan.items.map((item) => (
                    <li key={item} className="flex items-start gap-2.5 text-sm text-[#8B97A8]">
                      <Check className="w-4 h-4 text-green-400 shrink-0 mt-0.5" />
                      {item}
                    </li>
                  ))}
                </ul>

                {plan.ctaLink.startsWith('mailto:') ? (
                  <a
                    href={plan.ctaLink}
                    className="block text-center py-3 rounded-xl font-semibold text-sm border border-[#1B2433] text-[#E8ECF2] hover:border-[#5B5FEE]/30 transition-colors"
                  >
                    {plan.cta}
                  </a>
                ) : (
                  <Link
                    to={plan.ctaLink}
                    className={`block text-center py-3 rounded-xl font-semibold text-sm transition-colors ${
                      plan.featured
                        ? 'bg-[#C9A227] text-[#070B14] hover:bg-[#D4AF37]'
                        : 'bg-[#C9A227] text-[#070B14] hover:bg-[#D4AF37]'
                    }`}
                  >
                    {plan.cta}
                  </Link>
                )}
              </motion.div>
            ))}
          </div>

          {/* Enterprise note */}
          <motion.p {...fadeUp} className="text-center text-sm text-[#5A6578] mt-10 max-w-2xl mx-auto">
            Need more than 100K agents per simulation? Our Enterprise plan gives you dedicated infrastructure. Contact{' '}
            <a href="mailto:info@saidolabs.com" className="text-[#00D4FF] hover:underline">info@saidolabs.com</a>
          </motion.p>
        </div>
      </section>

      {/* ═══ 8. FAQ ═══ */}
      <section id="faq" className="py-28 px-6">
        <div className="max-w-3xl mx-auto">
          <motion.div {...fadeUp} className="text-center mb-16">
            <h2 className="font-display font-extrabold text-4xl sm:text-5xl text-[#E8ECF2] leading-tight tracking-tight">
              Frequently asked questions
            </h2>
          </motion.div>

          <div className="space-y-[1px]">
            {faqItems.map((item, i) => {
              const isOpen = openFaq.includes(i);
              return (
                <motion.div
                  key={i}
                  {...stagger(i)}
                  className="bg-[#111820] border border-[#1B2433] rounded-2xl overflow-hidden"
                >
                  <button
                    onClick={() => toggleFaq(i)}
                    className="w-full flex items-center justify-between px-6 py-5 text-left cursor-pointer"
                  >
                    <span className="font-sans font-semibold text-base text-[#E8ECF2] pr-4">{item.q}</span>
                    <Plus className={`w-5 h-5 text-[#8B97A8] shrink-0 transition-transform duration-300 ${isOpen ? 'rotate-45' : ''}`} />
                  </button>
                  <div className={`overflow-hidden transition-all duration-300 ${isOpen ? 'max-h-96 pb-5' : 'max-h-0'}`}>
                    <p className="px-6 text-sm text-[#8B97A8] leading-relaxed">{item.a}</p>
                  </div>
                </motion.div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ═══ 9. CTA BANNER ═══ */}
      <section className="py-28 px-6 bg-[#0D1117] relative overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(91,95,238,0.1)_0%,transparent_60%)] pointer-events-none" />
        <motion.div {...fadeUp} className="relative z-10 max-w-2xl mx-auto text-center">
          <h2 className="font-display font-extrabold text-4xl sm:text-5xl text-[#E8ECF2] leading-tight tracking-tight mb-6">
            Ready to see what they'll say before they say it?
          </h2>
          <p className="text-lg text-[#8B97A8] mb-10">
            Start your free trial today. No credit card required.
          </p>
          <Link to="/signup" className="inline-block px-10 py-4 rounded-xl font-semibold text-[#070B14] bg-[#C9A227] hover:bg-[#D4AF37] transition-colors text-base">
            Start Free Trial &rarr;
          </Link>
        </motion.div>
      </section>

      {/* ═══ 10. FOOTER ═══ */}
      <footer className="border-t border-[#1B2433] py-16 px-6">
        <div className="max-w-6xl mx-auto">
          <div className="grid grid-cols-1 md:grid-cols-5 gap-12">
            {/* Brand */}
            <div className="md:col-span-2">
              <div className="flex items-center gap-2.5 mb-4">
                <img src="/logo-mark.svg" alt="Saibyl" className="h-7 w-7" />
                <span className="text-gradient-brand font-extrabold text-lg tracking-tight">SAIBYL</span>
              </div>
              <p className="text-sm text-[#8B97A8] leading-relaxed max-w-xs">
                Predictive intelligence powered by synthetic agent swarms. Know the conversation before it happens.
              </p>
            </div>

            {/* Product links */}
            <div>
              <h4 className="font-sans font-semibold text-sm text-[#E8ECF2] mb-4">Product</h4>
              <ul className="space-y-3">
                <li><a href="#features" className="text-sm text-[#8B97A8] hover:text-[#E8ECF2] transition-colors">Features</a></li>
                <li><a href="#pricing" className="text-sm text-[#8B97A8] hover:text-[#E8ECF2] transition-colors">Pricing</a></li>
                <li><a href="#" className="text-sm text-[#8B97A8] hover:text-[#E8ECF2] transition-colors">{/* TODO: API docs */}API</a></li>
              </ul>
            </div>

            {/* Company links */}
            <div>
              <h4 className="font-sans font-semibold text-sm text-[#E8ECF2] mb-4">Company</h4>
              <ul className="space-y-3">
                <li><a href="#" className="text-sm text-[#8B97A8] hover:text-[#E8ECF2] transition-colors">{/* TODO: About page */}About</a></li>
                <li><a href="#" className="text-sm text-[#8B97A8] hover:text-[#E8ECF2] transition-colors">{/* TODO: Blog page */}Blog</a></li>
                <li><a href="#" className="text-sm text-[#8B97A8] hover:text-[#E8ECF2] transition-colors">{/* TODO: Careers page */}Careers</a></li>
              </ul>
            </div>

            {/* Legal links */}
            <div>
              <h4 className="font-sans font-semibold text-sm text-[#E8ECF2] mb-4">Legal</h4>
              <ul className="space-y-3">
                <li><a href="#" className="text-sm text-[#8B97A8] hover:text-[#E8ECF2] transition-colors">{/* TODO: Privacy policy */}Privacy</a></li>
                <li><a href="#" className="text-sm text-[#8B97A8] hover:text-[#E8ECF2] transition-colors">{/* TODO: Terms of service */}Terms</a></li>
                <li><a href="#" className="text-sm text-[#8B97A8] hover:text-[#E8ECF2] transition-colors">{/* TODO: Security page */}Security</a></li>
              </ul>
            </div>
          </div>

          {/* Bottom row */}
          <div className="border-t border-[#1B2433] mt-12 pt-8 text-center">
            <p className="text-sm text-[#5A6578]">&copy; 2026 Saido Labs LLC. All rights reserved.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
