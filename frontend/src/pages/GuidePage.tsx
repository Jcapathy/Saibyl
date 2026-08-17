import { useState } from 'react';
import { Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Building2,
  FlaskConical,
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

/* ── How it works ──
   These are the five steps the product actually has, in the order each one
   consumes the last. It described a different four - "Create a Project",
   "Configure a Simulation" - which was the old shape and pointed the reader at
   the superseded pages. A guide that explains a product you no longer ship is
   worse than no guide: the reader trusts it and ends up somewhere else. */
const STEPS = [
  {
    num: 1,
    title: 'Work out who buys this',
    desc: 'Upload the deck, the landing page or the pricing page. Saibyl reads it and proposes the groups of people likely to buy — what they do, what they already use, and what would make them doubt you. You confirm it or correct it.',
    Icon: Users,
    color: 'text-saibyl-blue',
    link: '/app/home',
    linkLabel: 'Go to your products',
  },
  {
    num: 2,
    title: 'Find out what they object to',
    desc: 'Those buyers read your material and argue about it. You get back what they said and the things they pushed back on, ranked by how much of the room carried each one — not by how often the words appeared.',
    Icon: MessageSquare,
    color: 'text-saibyl-gold',
  },
  {
    num: 3,
    title: 'Answer the objections, and find out if it worked',
    desc: 'Draft the material that answers each objection, publish it, and put the same room through it again. Answers that moved nothing are reported as moving nothing.',
    Icon: FlaskConical,
    color: 'text-saibyl-positive',
  },
  {
    num: 4,
    title: 'Find real companies that match',
    desc: 'Your buyers become web searches, and the search brings back real companies with the page that says so attached to each one. A company you cannot trace back is a lead you cannot act on.',
    Icon: Building2,
    color: 'text-saibyl-blue',
  },
  {
    num: 5,
    title: 'Test which message wins',
    desc: 'Put several versions of the same pitch in front of one shared room, so the difference you see is the wording rather than who happened to be listening. When the versions are too close to call, it says so instead of naming a winner.',
    Icon: FileText,
    color: 'text-saibyl-gold',
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
    title: 'Test more than one version of your message',
    body: 'Write more than one version of the same pitch and the room reacts to each of them from scratch — so the only thing that differed is your wording, not who happened to be listening. The report names a winner only when the evidence actually separates them.',
  },
  {
    title: 'Start with 20 agents and 5 rounds',
    body: 'This is the sweet spot for fast iteration. You\'ll get results in ~3 minutes. Once you find an interesting signal, scale up to 50-100 agents with 10+ rounds for the full picture.',
  },
  {
    title: 'Use "Deep" report depth for rich analysis',
    body: 'Standard is quick and gives you the headline and the objections. Deep gathers twice as much evidence per section and goes back to more people for their reasoning, so you get how feeling moved round by round and how it split between different kinds of buyer.',
  },
];

/* ── FAQ ── */
const FAQ = [
  {
    q: 'What are "agents"?',
    a: 'Agents are AI-generated personas with unique demographics, personality traits, political leanings, and social media behavior patterns. They debate and react to your prediction goal as if they were real people on the platforms you selected.',
  },
  {
    q: 'How long does a run take?',
    a: 'A room of 20 people over 5 rounds takes 2–4 minutes. A big one — 100 people, 15 rounds, several places at once — takes 10–20 minutes. Writing the report adds another 1–3.',
  },
  {
    q: 'How is this different from a focus group?',
    a: 'Traditional focus groups cost $5,000-$15,000, take 2-4 weeks to recruit and run, and cover 8-12 people. Saibyl simulates 20-100 diverse personas in minutes at a fraction of the cost — and you can re-run with different variables instantly.',
  },
  {
    q: 'What are "persona packs"?',
    a: 'Ready-made rooms of people, grouped by who they are — "Tech Workers", "Retail Investors", "Healthcare Professionals". Each one holds a mix of ages, jobs and temperaments rather than one kind of person repeated. You can also describe a group of your own, and if you have uploaded your material we work your actual buyers out instead.',
  },
  {
    q: 'What does the report include?',
    a: 'A summary you can read in a minute, how the room felt round by round, how that differed by place and by kind of buyer, the moments that turned it, and what people objected to — with the sentences behind every one of them.',
  },
  {
    q: 'Can I chat with the report?',
    a: 'Yes. Once the report is written you can ask it follow-up questions, and it answers from what was actually said in the run rather than from general knowledge.',
  },
  {
    q: 'What is a message test?',
    a: 'Put two or more versions of the same message in front of one shared room. Everyone reacts to every version, so the comparison is like for like — and when the versions are too close to call, the report says so instead of picking one.',
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
            Find out what buyers will object to before you launch. Saibyl builds a room of AI buyers from
            your material and shows you what they push back on — in minutes, at a fraction of the cost of
            focus groups, ad testing, or polling.
          </p>
        </motion.div>

        {/* ── Section 1: How It Works ── */}
        <section className="mb-12">
          <div className="flex items-center gap-2 mb-6">
            <Zap className="w-4 h-4 text-saibyl-gold" />
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
                <span className="absolute top-3 right-4 text-[48px] font-display font-extrabold text-[#14294a]/[0.05] select-none leading-none">
                  {s.num}
                </span>

                <div className="flex items-center gap-3 mb-3">
                  <div className={`w-9 h-9 rounded-xl bg-[#14294a]/[0.04] flex items-center justify-center ${s.color}`}>
                    <s.Icon className="w-4.5 h-4.5" />
                  </div>
                  <h3 className="text-[15px] font-semibold text-saibyl-platinum">{s.title}</h3>
                </div>
                <p className="text-[13px] text-saibyl-muted leading-relaxed">{s.desc}</p>
                {s.link && (
                  <Link
                    to={s.link}
                    className="inline-block mt-3 text-[12px] text-saibyl-gold hover:text-saibyl-blue transition-colors"
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
            <Clock className="w-4 h-4 text-saibyl-blue" />
            <h2 className="text-[16px] font-semibold text-saibyl-white uppercase tracking-wide">What Affects Speed</h2>
          </div>

          {/* Key callout */}
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="rounded-2xl p-5 mb-5 border border-saibyl-gold/20 bg-saibyl-gold/5"
          >
            <div className="flex items-start gap-3">
              <Target className="w-5 h-5 text-saibyl-gold mt-0.5 shrink-0" />
              <div>
                <p className="text-[14px] text-saibyl-platinum font-medium mb-1">The sweet spot: 20 agents, 5 rounds, 1-2 platforms</p>
                <p className="text-[13px] text-saibyl-muted leading-relaxed">
                  Delivers actionable insights in <span className="text-saibyl-blue font-medium">~3 minutes</span>.
                  That's what would take a focus group 2-4 weeks and $5,000-$15,000.
                  Scale up when you need deeper analysis — even 100 people over 15 rounds finishes in under 20 minutes.
                </p>
              </div>
            </div>
          </motion.div>

          <div className="glass rounded-2xl overflow-hidden">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-saibyl-border">
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
                    className="border-b border-saibyl-border last:border-0"
                  >
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-2">
                        <f.Icon className="w-3.5 h-3.5 text-saibyl-gold shrink-0" />
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
            <Lightbulb className="w-4 h-4 text-saibyl-gold" />
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
                  <span className="w-6 h-6 rounded-lg bg-saibyl-gold/10 flex items-center justify-center shrink-0 mt-0.5">
                    <span className="text-[11px] font-bold text-saibyl-gold">{i + 1}</span>
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
            <MessageSquare className="w-4 h-4 text-saibyl-blue" />
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
            to="/app/home"
            className="inline-flex items-center gap-2 px-8 py-3 rounded-xl bg-saibyl-blue text-white font-semibold text-[15px] hover:bg-[#1e5ad9] transition-all hover:-translate-y-0.5 hover:shadow-[0_0_20px_rgba(40,108,240,0.3)]"
          >
            <FlaskConical className="w-4 h-4" />
            Add your first product
          </Link>
          <p className="text-[12px] text-saibyl-muted mt-3">Results in minutes, not weeks.</p>
        </motion.div>
      </div>
    </div>
  );
}
