import { useState } from 'react';
import { Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  FolderOpen,
  FlaskConical,
  Play,
  FileText,
  Clock,
  Users,
  RotateCcw,
  Layers,
  ChevronDown,
  Lightbulb,
  Zap,
  Target,
  MessageSquare,
  BarChart3,
} from 'lucide-react';

const stagger = (i: number) => ({ delay: i * 0.06 });

/* ── How-it-works steps ── */
const STEPS = [
  {
    num: 1,
    title: 'Create a Project',
    desc: 'Projects group related simulations together. Think of them as folders — one for each topic, campaign, or research question.',
    Icon: FolderOpen,
    color: 'text-saibyl-cyan',
    link: '/app/projects',
    linkLabel: 'Go to Projects',
  },
  {
    num: 2,
    title: 'Configure a Simulation',
    desc: 'Write your prediction goal in plain language, pick the social platforms to simulate, choose persona packs, and set how many AI agents will participate.',
    Icon: FlaskConical,
    color: 'text-saibyl-indigo',
    link: '/app/simulations/new',
    linkLabel: 'New Simulation',
  },
  {
    num: 3,
    title: 'Watch It Run',
    desc: 'Agents debate, react, and post in real time across the platforms you selected. Watch sentiment shift, viral moments emerge, and narratives form — live.',
    Icon: Play,
    color: 'text-saibyl-positive',
  },
  {
    num: 4,
    title: 'Read Your Report',
    desc: 'When the simulation finishes, an intelligence report is generated automatically — complete with sentiment trajectories, agent archetypes, platform dynamics, and predictive insights.',
    Icon: FileText,
    color: 'text-saibyl-violet',
  },
];

/* ── Speed & cost factors ── */
const SPEED_FACTORS = [
  { factor: 'Agent Count', low: '10 agents', high: '100 agents', impact: 'More agents = richer debate but longer run time', Icon: Users },
  { factor: 'Rounds', low: '3 rounds', high: '15 rounds', impact: 'More rounds = deeper sentiment evolution', Icon: RotateCcw },
  { factor: 'Platforms', low: '1 platform', high: '5+ platforms', impact: 'Each platform adds cross-platform dynamics', Icon: Layers },
  { factor: 'Report Depth', low: 'Standard', high: 'Exhaustive', impact: 'Deeper analysis = more tool calls per section', Icon: BarChart3 },
];

/* ── Tips ── */
const TIPS = [
  {
    title: 'Write specific prediction goals',
    body: 'Instead of "How will people react to AI?", try "How will mid-career software engineers on Twitter and Reddit react to a major tech company announcing 30% of coding roles will be automated by 2027?" Specificity drives sharper results.',
  },
  {
    title: 'Mix your persona packs',
    body: 'Combining different persona packs (e.g. "Tech Workers" + "Policy Analysts") creates realistic cross-demographic debates. The friction between groups is where the best insights live.',
  },
  {
    title: 'Use A/B testing for narrative comparison',
    body: 'Enable A/B testing to run two variants of your prediction simultaneously — for example, testing how the same audience reacts to an optimistic vs. pessimistic framing of the same news.',
  },
  {
    title: 'Start with 20 agents and 5 rounds',
    body: 'This is the sweet spot for fast iteration. You\'ll get results in ~3 minutes. Once you find an interesting signal, scale up to 50-100 agents with 10+ rounds for the full picture.',
  },
  {
    title: 'Use "Deep" report depth for rich analysis',
    body: 'Standard depth is fast but may produce thinner sections. Deep depth gathers 2x more evidence per section and interviews more agents — producing reports with sentiment arcs, archetype clusters, and predictive forecasts.',
  },
];

/* ── FAQ ── */
const FAQ = [
  {
    q: 'What are "agents"?',
    a: 'Agents are AI-generated personas with unique demographics, personality traits, political leanings, and social media behavior patterns. They debate and react to your prediction goal as if they were real people on the platforms you selected.',
  },
  {
    q: 'How long does a simulation take?',
    a: 'A typical simulation with 20 agents and 5 rounds completes in 2-4 minutes. Larger simulations (100 agents, 15 rounds, multiple platforms) can take 10-20 minutes. The report generation adds 1-3 minutes depending on depth.',
  },
  {
    q: 'How is this different from a focus group?',
    a: 'Traditional focus groups cost $5,000-$15,000, take 2-4 weeks to recruit and run, and cover 8-12 people. Saibyl simulates 20-100 diverse personas in minutes at a fraction of the cost — and you can re-run with different variables instantly.',
  },
  {
    q: 'What are "persona packs"?',
    a: 'Pre-built collections of agent archetypes organized by domain — like "Tech Workers", "Retail Investors", or "Healthcare Professionals". Each pack includes diverse archetypes with different demographics, MBTI types, and behavior patterns. You can also create custom personas.',
  },
  {
    q: 'What does the report include?',
    a: 'Reports include an executive summary, sentiment trajectory analysis (how feelings changed over rounds), platform-specific dynamics, agent archetype clusters, key trigger events, viral moments, and predictive implications.',
  },
  {
    q: 'Can I chat with the report?',
    a: 'Yes. After a report is generated, you can ask follow-up questions using the chat interface. The AI will reference the simulation data and report content to answer.',
  },
  {
    q: 'What is A/B testing?',
    a: 'A/B testing runs two simulation variants simultaneously with the same agents. This lets you compare how different framings, announcements, or scenarios play out — and the report will identify which variant achieved stronger results.',
  },
];

export default function GuidePage() {
  const [openFaq, setOpenFaq] = useState<number | null>(null);

  return (
    <div className="p-8 bg-saibyl-void min-h-full">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-10"
        >
          <h1 className="text-h1 text-saibyl-white mb-2">Getting Started</h1>
          <p className="text-[15px] text-saibyl-muted leading-relaxed max-w-2xl">
            Know the conversation before it happens. Saibyl simulates how real people will react to any topic —
            in minutes, at a fraction of the cost of focus groups, ad testing, or polling.
          </p>
        </motion.div>

        {/* ── Section 1: How It Works ── */}
        <section className="mb-12">
          <div className="flex items-center gap-2 mb-6">
            <Zap className="w-4 h-4 text-saibyl-indigo" />
            <h2 className="text-[16px] font-semibold text-saibyl-white uppercase tracking-wide">How It Works</h2>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {STEPS.map((s, i) => (
              <motion.div
                key={s.num}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={stagger(i)}
                className="glass rounded-2xl p-6 relative overflow-hidden group"
              >
                {/* Step number watermark */}
                <span className="absolute top-3 right-4 text-[48px] font-display font-extrabold text-white/[0.03] select-none leading-none">
                  {s.num}
                </span>

                <div className="flex items-center gap-3 mb-3">
                  <div className={`w-9 h-9 rounded-xl bg-white/[0.04] flex items-center justify-center ${s.color}`}>
                    <s.Icon className="w-4.5 h-4.5" />
                  </div>
                  <h3 className="text-[15px] font-semibold text-saibyl-platinum">{s.title}</h3>
                </div>
                <p className="text-[13px] text-saibyl-muted leading-relaxed">{s.desc}</p>
                {s.link && (
                  <Link
                    to={s.link}
                    className="inline-block mt-3 text-[12px] text-saibyl-indigo hover:text-saibyl-cyan transition-colors"
                  >
                    {s.linkLabel} &rarr;
                  </Link>
                )}
              </motion.div>
            ))}
          </div>
        </section>

        {/* ── Section 2: Speed & Cost ── */}
        <section className="mb-12">
          <div className="flex items-center gap-2 mb-6">
            <Clock className="w-4 h-4 text-saibyl-cyan" />
            <h2 className="text-[16px] font-semibold text-saibyl-white uppercase tracking-wide">What Affects Speed</h2>
          </div>

          {/* Key callout */}
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="rounded-2xl p-5 mb-5 border border-saibyl-indigo/20 bg-saibyl-indigo/5"
          >
            <div className="flex items-start gap-3">
              <Target className="w-5 h-5 text-saibyl-indigo mt-0.5 shrink-0" />
              <div>
                <p className="text-[14px] text-saibyl-platinum font-medium mb-1">The sweet spot: 20 agents, 5 rounds, 1-2 platforms</p>
                <p className="text-[13px] text-saibyl-muted leading-relaxed">
                  Delivers actionable insights in <span className="text-saibyl-cyan font-medium">~3 minutes</span>.
                  That's what would take a focus group 2-4 weeks and $5,000-$15,000.
                  Scale up when you need deeper analysis — even a 100-agent, 15-round simulation finishes in under 20 minutes.
                </p>
              </div>
            </div>
          </motion.div>

          <div className="glass rounded-2xl overflow-hidden">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-white/[0.06]">
                  <th className="text-left px-5 py-3 text-[11px] uppercase tracking-wider text-saibyl-muted font-medium">Factor</th>
                  <th className="text-left px-5 py-3 text-[11px] uppercase tracking-wider text-saibyl-muted font-medium">Faster</th>
                  <th className="text-left px-5 py-3 text-[11px] uppercase tracking-wider text-saibyl-muted font-medium">Slower</th>
                  <th className="text-left px-5 py-3 text-[11px] uppercase tracking-wider text-saibyl-muted font-medium">What You Get</th>
                </tr>
              </thead>
              <tbody>
                {SPEED_FACTORS.map((f, i) => (
                  <motion.tr
                    key={f.factor}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={stagger(i)}
                    className="border-b border-white/[0.03] last:border-0"
                  >
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-2">
                        <f.Icon className="w-3.5 h-3.5 text-saibyl-indigo shrink-0" />
                        <span className="text-saibyl-platinum font-medium">{f.factor}</span>
                      </div>
                    </td>
                    <td className="px-5 py-3.5 text-saibyl-positive">{f.low}</td>
                    <td className="px-5 py-3.5 text-saibyl-muted">{f.high}</td>
                    <td className="px-5 py-3.5 text-saibyl-muted">{f.impact}</td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* ── Section 3: Tips ── */}
        <section className="mb-12">
          <div className="flex items-center gap-2 mb-6">
            <Lightbulb className="w-4 h-4 text-saibyl-violet" />
            <h2 className="text-[16px] font-semibold text-saibyl-white uppercase tracking-wide">Tips for Best Results</h2>
          </div>

          <div className="space-y-3">
            {TIPS.map((tip, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={stagger(i)}
                className="glass rounded-xl p-5"
              >
                <div className="flex items-start gap-3">
                  <span className="w-6 h-6 rounded-lg bg-saibyl-violet/10 flex items-center justify-center shrink-0 mt-0.5">
                    <span className="text-[11px] font-bold text-saibyl-violet">{i + 1}</span>
                  </span>
                  <div>
                    <h3 className="text-[14px] font-medium text-saibyl-platinum mb-1">{tip.title}</h3>
                    <p className="text-[13px] text-saibyl-muted leading-relaxed">{tip.body}</p>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </section>

        {/* ── Section 4: FAQ ── */}
        <section className="mb-12">
          <div className="flex items-center gap-2 mb-6">
            <MessageSquare className="w-4 h-4 text-saibyl-cyan" />
            <h2 className="text-[16px] font-semibold text-saibyl-white uppercase tracking-wide">Frequently Asked Questions</h2>
          </div>

          <div className="space-y-2">
            {FAQ.map((item, i) => {
              const isOpen = openFaq === i;
              return (
                <motion.div
                  key={i}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={stagger(i)}
                  className="glass rounded-xl overflow-hidden"
                >
                  <button
                    onClick={() => setOpenFaq(isOpen ? null : i)}
                    className="w-full flex items-center justify-between px-5 py-4 text-left group"
                  >
                    <span className="text-[14px] font-medium text-saibyl-platinum group-hover:text-saibyl-white transition-colors">
                      {item.q}
                    </span>
                    <ChevronDown
                      className={`w-4 h-4 text-saibyl-muted transition-transform duration-200 shrink-0 ml-4 ${
                        isOpen ? 'rotate-180' : ''
                      }`}
                    />
                  </button>
                  <AnimatePresence>
                    {isOpen && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="overflow-hidden"
                      >
                        <p className="px-5 pb-4 text-[13px] text-saibyl-muted leading-relaxed">
                          {item.a}
                        </p>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.div>
              );
            })}
          </div>
        </section>

        {/* ── CTA ── */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="text-center pb-8"
        >
          <Link
            to="/app/projects"
            className="relative inline-flex items-center gap-2 px-8 py-3 rounded-xl text-white font-semibold text-[15px] overflow-hidden hover:scale-[1.02] transition-transform"
          >
            <div className="absolute inset-0 bg-gradient-to-r from-[#5B5FEE] to-[#00D4FF]" />
            <div className="absolute inset-0 animate-glow-pulse rounded-xl" />
            <FlaskConical className="relative w-4 h-4" />
            <span className="relative">Start a New Project</span>
          </Link>
          <p className="text-[12px] text-saibyl-muted mt-3">Results in minutes, not weeks.</p>
        </motion.div>
      </div>
    </div>
  );
}
