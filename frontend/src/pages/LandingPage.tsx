import { Link } from 'react-router-dom';
import { MotionConfig, motion } from 'framer-motion';
import {
  ArrowRight,
  Check,
  MessageSquare,
  PenLine,
  Search,
  SlidersHorizontal,
  Users,
  type LucideIcon,
} from 'lucide-react';

import HeroAnimation from '@/components/HeroAnimation';
import Faq, { type FaqItem } from '@/components/landing/Faq';
import { Section, SectionHead } from '@/components/landing/Section';
import { ObjectionList, Shot, Split } from '@/components/landing/Showcase';
import { DEMO_OBJECTIONS_TOTAL } from '@/components/landing/demoRun';
import { fadeUp, stagger } from '@/components/landing/motion';
import {
  CONTACT_EMAIL,
  ENTERPRISE_SHAPE,
  PLACES,
  TIERS,
  shapeLines,
} from '@/components/landing/tiers';
import { BENCHMARKS } from '@/lib/benchmarks';

/**
 * The landing page.
 *
 * ── WHO IS READING THIS ────────────────────────────────────────────────────
 * A SaaS founder who has built something — probably with Claude Code, probably
 * fast — and does not yet know whether anyone wants it. Some of them have never
 * heard the phrase "ideal customer profile" and will not learn it here. The
 * register is the one in `components/founder/AudienceReview.tsx`: short
 * sentences, no vocabulary the reader has to acquire before the page makes
 * sense. If a word on this page needs a glossary, it is the wrong word.
 *
 * ── WHAT THE PAGE ARGUES ───────────────────────────────────────────────────
 * Two sentences, and everything else is in service of them:
 *
 *   Your audience is built from your own material.
 *   Every number traces back to something an agent said.
 *
 * The previous version of this page never said either one. It sold scale — a
 * "1M agents" figure against an enforced ceiling of 1,000, a stats bar of
 * invented metrics, verticals like Sports & Betting and Policy & Government —
 * to a buyer who is not shopping for scale and is not in any of those verticals.
 *
 * ── WHAT WAS REMOVED, AND WHY ──────────────────────────────────────────────
 * Everything below was on this page and is deliberately gone. None of it should
 * come back without a constant behind it:
 *
 *   "1M+ Max Agents"            1,000x over the enforced cap
 *   "8 Platforms"               there are twelve adapters
 *   "42 Archetypes"             no such constant exists anywhere
 *   "<3 Min Results"            no measured figure behind it
 *   "<3pp deviation in
 *    controlled studies"        there are no controlled studies
 *   "SOC 2 compliant,
 *    256-bit encryption"        no compliance artifact exists; the only SOC 2
 *                               in this repo is a *simulated buyer asking about
 *                               it* in a persona pack
 *   "14-day free trial"         there is no trial clock; there is a credit grant
 *   "Need more than 100K
 *    agents?"                   400x over the enterprise cap of 1,000
 *   "87% probability of
 *    negative sentiment spike"  and its three siblings — invented report output
 *                               presented as sample results
 *   "All 16 persona packs"      the packs are real, but selling a catalogue to
 *                               pick from contradicts the entire argument: the
 *                               founder is the wrong person to ask which pack
 *                               matches their buyer (DECISIONS_V2 §3)
 *   API access, webhooks,
 *   white-label, SSO/SAML,
 *   SLA, dedicated AM           unbuilt; a tier feature list is not a roadmap
 *   six footer links to `#`     a link that goes nowhere is a dead end
 *
 * ── NUMBERS ────────────────────────────────────────────────────────────────
 * Every figure that renders comes from one of three files, and **nothing in
 * this file writes a number of its own**:
 *
 *   `components/landing/tiers.ts`      tier caps and grants, transcribed from
 *                                      agent_pricing.py with its line numbers
 *   `lib/benchmarks.ts`                the three outside statistics, each with
 *                                      a linked primary source and its date
 *   `components/landing/demoRun.ts`    what the demo run actually returned
 *
 * ── IMAGERY ────────────────────────────────────────────────────────────────
 * The page shipped with none: 6,910px of centred prose on a starfield, which
 * read to the founder as "an internal tool that somebody built over a weekend".
 * The copy was not the problem. Three real screenshots now carry the argument —
 * see `Showcase.tsx` for where they come from and why the demo product is
 * fictional — and the sections alternate between a centred block and a
 * copy-beside-screen split so the page has a rhythm instead of a wall.
 */

/* ── The five things the product does ──────────────────────────────────────
 * The settled vocabulary, in the order the work happens. There is no Crisis
 * entry and there must not be one until it exists — an advertised feature that
 * leads nowhere is the same defect as a nav item that leads nowhere, one step
 * earlier in the funnel.
 */
interface Capability {
  name: string;
  question: string;
  body: string;
  Icon: LucideIcon;
  colour: string;
  /** Whether the free grant reaches it. It covers one run, and no more. */
  free: boolean;
}

const CAPABILITIES: readonly Capability[] = [
  {
    name: 'Audience',
    question: 'Who reacts to this?',
    body: "Built out of what you uploaded — your deck, your site, your docs — not picked off a list. You get told who we think buys this and why we think so, and you correct anything that’s wrong before a single thing runs.",
    Icon: Users,
    colour: '#8B5CF6',
    free: true,
  },
  {
    name: 'Reactions',
    question: 'What did they say, and what did they object to?',
    body: 'They read your pitch, argue with it and with each other, and what they push back on gets grouped so you can see which objection is the big one rather than reading five hundred comments.',
    Icon: MessageSquare,
    colour: '#2563EB',
    free: true,
  },
  {
    name: 'Answers',
    question: 'What do I say back, and did it work?',
    body: "Saibyl drafts a reply to each objection worth answering. Then it runs the same people again with those replies already in front of them, so you find out whether the objection actually moved — not whether the reply sounded good.",
    Icon: PenLine,
    colour: '#10B981',
    free: false,
  },
  {
    name: 'Buyers',
    question: 'Which real companies match?',
    body: 'Once you agree who buys this, Saibyl goes and finds actual companies that look like them, and shows you where it found each one so you can check.',
    Icon: Search,
    colour: '#C9A227',
    free: false,
  },
  {
    name: 'Messages',
    question: 'Which version wins?',
    body: 'Put several versions of the same message in front of the same people, in the same run. Same room, same moment — so what differs is the wording and not the crowd.',
    Icon: SlidersHorizontal,
    colour: '#8B5CF6',
    free: false,
  },
];

/* ── The free teaser, exactly as it happens ────────────────────────────────
 * This is a real journey, end to end, and it is the page's primary promise. Do
 * not add a step the product does not have and do not quietly drop one it does:
 * a founder who is told six steps and meets seven has been misled about the
 * only thing this page asked them to do.
 */
const FREE_RUN_STEPS: readonly { title: string; body: string }[] = [
  {
    title: 'Sign up',
    body: `${TIERS[0].credits} credits land on your account. We never ask for a card, so nothing can start charging you later.`,
  },
  {
    title: 'Start a product',
    body: 'One product means one thing you are selling. Everything else hangs off it.',
  },
  {
    title: 'Upload your deck',
    body: 'Plus your landing page, your docs, a rival’s pricing page — whatever you have. This is the material your audience gets built out of, so more of it makes the run sharper.',
  },
  {
    title: 'Read your audience',
    body: 'Who we think buys this, what they already use, what would make them doubt you, and the reason we think so. Change what looks wrong. Or change nothing and carry on.',
  },
  {
    title: 'Run it',
    body: `${TIERS[0].shape.people} people, ${TIERS[0].shape.rounds} rounds of back-and-forth, across ${TIERS[0].shape.places} places. You watch it happen rather than waiting on an email.`,
  },
  {
    title: 'Read the objections',
    body: 'What they pushed back on, grouped and ranked, each one opening into the exact sentences it was built from and who said them.',
  },
];

const FAQ_ITEMS: readonly FaqItem[] = [
  {
    q: 'I don’t really know who my buyers are yet. Is that a problem?',
    a: 'No — it is the normal case, and it is most of what you are here for. You upload what you have and Saibyl proposes who buys this and what they would care about, with a reason attached to each one. You read it and correct it. You are never asked to pick your buyer off a menu, because choosing correctly from that menu would require already knowing the answer.',
  },
  {
    q: 'Are these real people?',
    a: 'No, and we are not going to pretend otherwise. They are language models each given a specific job, a thing they already use, what they would judge you on and what would make them doubt you — all of it drawn from your own material. What you get back is what people in that position tend to say and object to. It is a rehearsal, not a survey, and it is a great deal cheaper than finding out by running the campaign.',
  },
  {
    q: 'What stops it from making things up?',
    a: "Two things you can check. Where your documents never said something, it is left blank and listed as a gap rather than filled in with something plausible. And a competitor is never named in a run unless you uploaded something that competitor actually published — otherwise the model would be inventing what your rival says and you would have no way of telling.",
  },
  {
    q: 'Where does every number in the report come from?',
    a: 'Something one of them actually said. There is no scoring model quietly assigning points behind the scenes. Open any finding and you get the sentences it was built from, and who said them. When there was nothing to say, nothing is shown — no zero, no placeholder that reads like a measurement.',
  },
  {
    q: 'What do I actually need to upload?',
    a: 'A deck is enough to get started. Landing page copy, product docs, and a competitor’s pricing page each make the audience sharper, because they are what your buyers are really comparing you against.',
  },
  {
    q: 'What happens when my free credits run out?',
    a: 'Nothing, unless you decide otherwise. The grant is sized to cover one full run, and there is no card on file to charge — signing up never takes one. If the run was worth it, pick a plan; if it was not, you have lost an afternoon rather than a campaign budget.',
  },
];

/* ── Page ──────────────────────────────────────────────────────────────── */

const NAV_LINKS = [
  // First, because it is the only link that answers "what does this actually
  // give me" without asking the reader to take a sentence on trust.
  { href: '#demo', label: 'A real run' },
  { href: '#free-run', label: 'How it works' },
  { href: '#product', label: 'What you get' },
  { href: '#pricing', label: 'Pricing' },
  { href: '#faq', label: 'Questions' },
];

const goldButton =
  'inline-flex items-center justify-center gap-2 rounded-xl bg-saibyl-gold text-saibyl-void font-semibold transition-colors hover:bg-saibyl-gold-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-saibyl-gold/60 focus-visible:ring-offset-2 focus-visible:ring-offset-saibyl-void';
const quietButton =
  'inline-flex items-center justify-center gap-2 rounded-xl border border-saibyl-border text-saibyl-platinum font-semibold transition-colors hover:border-saibyl-insight-violet/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-saibyl-gold/60';

export default function LandingPage() {
  const free = TIERS[0];

  return (
    // `reducedMotion="user"` rather than a hook in every component: it drops the
    // travel out of every transition on the page at once for a visitor who has
    // asked for that, and cannot be forgotten on the next section someone adds.
    <MotionConfig reducedMotion="user">
      <div className="scroll-smooth min-h-screen bg-saibyl-void text-saibyl-platinum overflow-x-hidden">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-[60] focus:px-4 focus:py-2 focus:rounded-lg focus:bg-saibyl-gold focus:text-saibyl-void focus:font-semibold"
        >
          Skip to content
        </a>

        {/* ═══ Navigation ═══ */}
        <nav className="fixed top-0 left-0 right-0 z-50 bg-saibyl-void/80 backdrop-blur-xl border-b border-saibyl-border">
          <div className="max-w-6xl mx-auto flex items-center justify-between px-6 h-16">
            <Link to="/" className="flex items-center gap-2.5 shrink-0">
              <img src="/logo-mark.svg" alt="" className="h-7 w-7" />
              <span className="text-gradient-brand font-extrabold text-lg tracking-tight">
                SAIBYL
              </span>
            </Link>

            <div className="hidden md:flex items-center gap-8">
              {NAV_LINKS.map((link) => (
                <a
                  key={link.href}
                  href={link.href}
                  className="text-sm text-saibyl-silver hover:text-saibyl-platinum transition-colors"
                >
                  {link.label}
                </a>
              ))}
            </div>

            <div className="flex items-center gap-4 shrink-0">
              <Link
                to="/login"
                className="text-sm text-saibyl-silver hover:text-saibyl-platinum transition-colors"
              >
                Sign in
              </Link>
              <Link to="/signup" className={`${goldButton} text-sm px-4 sm:px-5 py-2`}>
                Start a free run
              </Link>
            </div>
          </div>
        </nav>

        <main id="main">
          {/* ═══ Hero ═══ */}
          <section className="relative flex flex-col items-center justify-center text-center px-6 pt-32 pb-24 sm:pt-40 sm:pb-28 overflow-hidden">
            <div className="absolute inset-0 opacity-40 pointer-events-none" aria-hidden="true">
              <HeroAnimation />
            </div>
            <div
              className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(139,92,246,0.08)_0%,transparent_60%)] pointer-events-none"
              aria-hidden="true"
            />

            <div className="relative z-10 max-w-4xl">
              <motion.div
                {...stagger(0)}
                className="inline-flex items-center gap-2.5 px-4 py-1.5 rounded-full border border-saibyl-insight-violet/20 bg-saibyl-insight-violet/10 mb-8"
              >
                <span className="relative flex h-2 w-2" aria-hidden="true">
                  <span className="animate-ping absolute h-full w-full rounded-full bg-saibyl-positive opacity-75" />
                  <span className="relative rounded-full h-2 w-2 bg-saibyl-positive" />
                </span>
                <span className="font-mono text-xs tracking-widest uppercase text-saibyl-silver">
                  Now in private beta
                </span>
              </motion.div>

              <motion.h1
                {...stagger(1)}
                className="font-display font-extrabold leading-[1.05] tracking-tight mb-6 text-balance"
                style={{ fontSize: 'clamp(2.5rem, 5.5vw, 4rem)' }}
              >
                <span className="text-gradient-brand">Find out what your buyers say</span>
                <br className="hidden sm:block" />{' '}
                <span className="text-saibyl-platinum">before you pay to find out</span>
              </motion.h1>

              <motion.p
                {...stagger(2)}
                className="text-lg text-saibyl-silver max-w-2xl mx-auto leading-relaxed mb-4"
              >
                Upload your deck. Saibyl works out who would buy this{' '}
                <strong className="text-saibyl-platinum font-semibold">
                  from your own material
                </strong>{' '}
                — not from a list of stock personas you pick off — puts your pitch in front of
                them, and shows you what they said and what they objected to.
              </motion.p>

              <motion.p
                {...stagger(3)}
                className="text-lg text-saibyl-silver max-w-2xl mx-auto leading-relaxed mb-10"
              >
                <strong className="text-saibyl-platinum font-semibold">
                  Every number opens into the words it came from.
                </strong>{' '}
                Nothing on the report is a score you have to take on faith.
              </motion.p>

              <motion.div
                {...stagger(4)}
                className="flex flex-col sm:flex-row items-center justify-center gap-4"
              >
                <Link to="/signup" className={`${goldButton} px-8 py-3.5 text-base`}>
                  Start a free run <ArrowRight className="w-4 h-4" aria-hidden="true" />
                </Link>
                <a href="#free-run" className={`${quietButton} px-8 py-3.5 text-base`}>
                  See what a free run gives you
                </a>
              </motion.div>

              <motion.p {...stagger(5)} className="text-sm text-saibyl-muted mt-5">
                {free.credits} credits at signup — enough for one full run. No card, ever.
              </motion.p>
            </div>

            {/* The four-second story.

                A reader who has to get through three paragraphs before they
                know what the thing looks like has already decided. This is the
                second step of a real run on the demo product: the five steps
                down the side, and the objections underneath. `priority` because
                it is the one image above the fold. */}
            <motion.div
              {...stagger(6)}
              className="relative z-10 mt-16 w-full max-w-5xl sm:mt-20"
            >
              <Shot
                src="/demo/rail.png"
                alt="Step 2 of a run: the five steps down the left, and underneath them the objections a room of freelancers raised about an invoice-chasing tool."
                width={2240}
                height={1240}
                priority
              />
              <p className="mt-4 text-xs text-saibyl-muted">
                A real run on a product we made up, so nobody&rsquo;s launch is on this
                page. Everything below is what it returned.
              </p>
            </motion.div>
          </section>

          {/* ═══ The argument ═══ */}
          <Section id="argument" tone="raised">
            <div className="max-w-6xl mx-auto">
              <SectionHead
                eyebrow="Why this is different"
                title={
                  <>
                    Two claims, and you can check{' '}
                    <span className="text-gradient-brand">both of them</span>
                  </>
                }
                lede="Most of this category asks you to trust a model. Both of the things Saibyl does differently are things you can go and verify yourself."
              />

              <div className="space-y-24 sm:space-y-28">
                <Split
                  eyebrow="Claim one"
                  title="Your audience is built from your own material"
                  shot={
                    <Shot
                      src="/demo/audience.png"
                      // The step rail down the left edge, cut.
                      crop={{ left: 0.21 }}
                      alt="Step 1: one uploaded file, and under it the five kinds of buyer read out of it — solo freelancer, small studio owner, new freelancer who avoids confrontation, experienced freelancer with a process, and side-hustler watching every dollar."
                      width={2240}
                      height={1400}
                    />
                  }
                >
                  <p>
                    Other tools hand you a catalogue of personas and ask you to choose. You are
                    the wrong person to ask — which buyer you are actually selling to is the
                    thing you came here to work out.
                  </p>
                  <p>
                    So Saibyl reads what you uploaded and proposes who buys this, what they use
                    today, and what would make them doubt you — with the reason attached to each
                    one. You confirm it or you fix it.
                  </p>
                  <p>
                    Where your documents never said something, it stays blank and gets listed as
                    a gap. A guess dressed up as a finding is worse than an empty field.
                  </p>
                  <p className="text-saibyl-muted">
                    Those five came out of one uploaded file, and nothing else.
                  </p>
                </Split>

                <Split
                  flip
                  eyebrow="Claim two"
                  title="Every number traces to something someone said"
                  shot={
                    <Shot
                      src="/demo/objections.png"
                      // The rail, and the stage chips above the list that mean
                      // nothing without the page around them.
                      crop={{ left: 0.21, top: 0.3 }}
                      alt="Four objections from the run, each with a one-line summary and the number of people who carried it."
                      width={2240}
                      height={1060}
                    />
                  }
                >
                  <p>
                    There is no scoring model quietly assigning points. When the report tells you
                    price was the objection, you open it and read the sentences that objected to
                    the price, and see who said them.
                  </p>
                  <ol className="space-y-2">
                    {[
                      'A finding in the report',
                      'The sentences it was built from',
                      'The buyer who said each one',
                    ].map((step, i) => (
                      <li
                        key={step}
                        className="flex items-center gap-3 text-sm text-saibyl-platinum"
                      >
                        <span className="font-mono text-xs text-saibyl-signal-blue w-4 shrink-0">
                          {i + 1}
                        </span>
                        <span className="rounded-lg border border-saibyl-border bg-saibyl-void px-3 py-2 flex-1">
                          {step}
                        </span>
                      </li>
                    ))}
                  </ol>
                  <p>
                    And when nothing was said, nothing is shown. Not a zero, not a dash that
                    reads like a measurement of nobody.
                  </p>
                  <p className="text-saibyl-muted">
                    &ldquo;3 people&rdquo; means three of the room, not three comments.
                    Somebody who says it five times still counts once.
                  </p>
                </Split>
              </div>
            </div>
          </Section>

          {/* ═══ What a run gives back ═══

              The page's honest substitute for social proof. There are no
              customer logos because there are no customers, and the last set of
              invented "sample results" on this page took a week to remove. A
              run anyone could repeat, on a product nobody owns, is the version
              of this claim that survives being checked. */}
          <Section id="demo">
            <div className="max-w-5xl mx-auto">
              <SectionHead
                eyebrow="What comes back"
                title={
                  <>
                    We invented a product and{' '}
                    <span className="text-gradient-brand">ran it for real</span>
                  </>
                }
                lede="Tallyhook chases late invoices for freelancers. It does not exist — we wrote it, uploaded it, and put it through the same five steps you would. Nobody is a customer yet, so this is what we can show you instead of a logo wall."
              />

              <motion.div {...fadeUp} className="grid gap-8 lg:grid-cols-[1.15fr_1fr]">
                <div>
                  <p className="text-sm text-saibyl-silver leading-relaxed mb-5">
                    {DEMO_OBJECTIONS_TOTAL} objections came back. These are the six the most
                    people carried, unedited &mdash; and none of them is the one a founder
                    building this would have braced for.
                  </p>
                  <ObjectionList />
                </div>

                <div className="rounded-2xl border border-saibyl-border bg-saibyl-surface p-7">
                  <h3 className="font-sans font-semibold text-lg text-saibyl-platinum">
                    What that is worth knowing on a Tuesday
                  </h3>
                  <p className="text-sm text-saibyl-silver leading-relaxed mt-3">
                    Two of the top six are about the relationship with the client, not the
                    software. One is that the tool sounds robotic. Only one is price.
                  </p>
                  <p className="text-sm text-saibyl-silver leading-relaxed mt-3">
                    A founder about to write a pricing page has just found out that pricing is
                    not the argument. That is the whole point of doing this before the launch
                    rather than after it.
                  </p>
                  <p className="text-xs text-saibyl-muted leading-relaxed mt-5">
                    Everyone in that room is synthetic, and the page says so on every screen it
                    appears on. It is a rehearsal, not a survey.
                  </p>
                </div>
              </motion.div>
            </div>
          </Section>

          {/* ═══ The free run ═══ */}
          <Section id="free-run" tone="raised">
            <div className="max-w-6xl mx-auto">
              <SectionHead
                eyebrow="The free run"
                title={
                  <>
                    Six steps, and you are reading{' '}
                    <span className="text-gradient-brand">your objections</span>
                  </>
                }
                lede="This is the whole thing, start to finish. No demo call, no sales conversation, no card."
              />

              <ol className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {FREE_RUN_STEPS.map((step, i) => (
                  <motion.li
                    key={step.title}
                    {...stagger(i)}
                    className="bg-saibyl-surface border border-saibyl-border rounded-2xl p-7 hover:border-saibyl-insight-violet/20 transition-colors"
                  >
                    <span className="font-mono text-sm text-saibyl-insight-violet font-semibold">
                      {String(i + 1).padStart(2, '0')}
                    </span>
                    <h3 className="font-sans font-semibold text-lg text-saibyl-platinum mt-3 mb-2">
                      {step.title}
                    </h3>
                    <p className="text-sm text-saibyl-silver leading-relaxed">{step.body}</p>
                  </motion.li>
                ))}
              </ol>

              <motion.div {...fadeUp} className="mt-12 text-center">
                <Link to="/signup" className={`${goldButton} px-8 py-3.5 text-base`}>
                  Start a free run <ArrowRight className="w-4 h-4" aria-hidden="true" />
                </Link>
                <p className="text-sm text-saibyl-muted mt-4">
                  {free.credits} credits, once. Enough for one run of {free.shape.people} people
                  over {free.shape.rounds} rounds.
                </p>
              </motion.div>
            </div>
          </Section>

          {/* ═══ The five things ═══ */}
          <Section id="product">
            <div className="max-w-6xl mx-auto">
              <SectionHead
                eyebrow="What you get"
                title={
                  <>
                    Five questions, in the order{' '}
                    <span className="text-gradient-brand">you hit them</span>
                  </>
                }
                lede="You do not have to use all of it on day one. The free run covers the first two, which is where you find out whether the rest is worth anything to you."
              />

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {CAPABILITIES.map((cap, i) => (
                  <motion.div
                    key={cap.name}
                    {...stagger(i)}
                    className="bg-saibyl-surface border border-saibyl-border rounded-2xl p-7 flex flex-col hover:border-saibyl-insight-violet/20 transition-colors"
                  >
                    <div className="flex items-center justify-between gap-3 mb-5">
                      <div
                        className="w-12 h-12 rounded-xl flex items-center justify-center"
                        style={{ background: `${cap.colour}15` }}
                        aria-hidden="true"
                      >
                        <cap.Icon className="w-6 h-6" style={{ color: cap.colour }} />
                      </div>
                      <span
                        className={`font-mono text-[10px] uppercase tracking-[0.12em] px-2.5 py-1 rounded-full border ${
                          cap.free
                            ? 'border-saibyl-positive/30 bg-saibyl-positive/10 text-saibyl-positive'
                            : 'border-saibyl-border bg-saibyl-void text-saibyl-muted'
                        }`}
                      >
                        {cap.free ? 'In the free run' : 'On a plan'}
                      </span>
                    </div>

                    <h3 className="font-sans font-semibold text-lg text-saibyl-platinum">
                      {cap.name}
                    </h3>
                    <p className="text-sm text-saibyl-silver/80 italic mt-1 mb-3">
                      {cap.question}
                    </p>
                    <p className="text-sm text-saibyl-silver leading-relaxed flex-1">{cap.body}</p>

                    {cap.free ? (
                      <Link
                        to="/signup"
                        className="text-sm font-semibold text-saibyl-gold hover:underline mt-5 inline-flex items-center gap-1.5"
                      >
                        Start a free run <ArrowRight className="w-3.5 h-3.5" aria-hidden="true" />
                      </Link>
                    ) : (
                      <a
                        href="#pricing"
                        className="text-sm font-semibold text-saibyl-signal-blue hover:underline mt-5 inline-flex items-center gap-1.5"
                      >
                        What a plan costs{' '}
                        <ArrowRight className="w-3.5 h-3.5" aria-hidden="true" />
                      </a>
                    )}
                  </motion.div>
                ))}

                {/* Sixth cell rather than an empty gap in the grid. It is also
                    the honest answer to "so what does the free grant not do",
                    which is the question the five cards above raise. */}
                <motion.div
                  {...stagger(5)}
                  className="rounded-2xl border border-dashed border-saibyl-border p-7 flex flex-col justify-center"
                >
                  <h3 className="font-sans font-semibold text-lg text-saibyl-platinum mb-2">
                    Where the free grant stops
                  </h3>
                  <p className="text-sm text-saibyl-silver leading-relaxed">
                    It is sized to cover one run all the way through, and that is all. Writing
                    answers, running them back at the same people, and going out to find real
                    companies are each real work on top of that — so they come with a plan rather
                    than pretending to be free.
                  </p>
                </motion.div>
              </div>
            </div>
          </Section>

          {/* ═══ What this is competing with ═══

              The comparison a founder actually makes is not to their other
              subscriptions. It is to the campaign they are about to run.

              The three figures are the ones in `lib/benchmarks.ts`, shared with
              the billing page, each with its primary source linked and its date
              stated. The two that were researched and rejected are recorded
              there too. This page has shipped an invented statistic before; the
              sourcing rule is what stops it happening twice. */}
          <Section id="stakes" tone="raised">
            <div className="max-w-5xl mx-auto">
              <SectionHead
                eyebrow="The arithmetic"
                title={
                  <>
                    Testing the message first is the{' '}
                    <span className="text-gradient-brand">cheapest thing on this list</span>
                  </>
                }
                lede="Not compared to your other subscriptions. Compared to the campaign you are about to run, and the quarter you are about to spend saying the wrong thing to the right people."
              />

              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {BENCHMARKS.map((benchmark, i) => (
                  <motion.div
                    key={benchmark.href}
                    {...stagger(i)}
                    className="rounded-2xl border border-saibyl-border bg-saibyl-surface p-7 flex flex-col"
                  >
                    <p className="font-display font-extrabold text-3xl text-saibyl-gold leading-none">
                      {benchmark.stat}
                    </p>
                    <p className="font-mono text-[11px] uppercase tracking-[0.12em] text-saibyl-muted mt-2">
                      {benchmark.short}
                    </p>
                    <p className="text-sm text-saibyl-silver leading-relaxed mt-4 flex-1">
                      {benchmark.claim}
                    </p>
                    {/* The source is shown, not footnoted. A statistic whose
                        provenance a reader has to hunt for is one they are
                        being asked to take on faith. */}
                    <a
                      href={benchmark.href}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="text-[11px] text-saibyl-muted mt-5 leading-relaxed hover:text-saibyl-gold transition-colors"
                    >
                      {benchmark.provenance} ↗
                    </a>
                  </motion.div>
                ))}
              </div>

              <motion.p
                {...fadeUp}
                className="text-sm text-saibyl-silver max-w-3xl mx-auto text-center mt-10 leading-relaxed"
              >
                Saibyl does not run your campaign and does not promise it will work. It tells
                you what a room of your buyers argues about before you have paid to find out,
                and shows you the sentence behind every number so you can disagree with it.
              </motion.p>
            </div>
          </Section>

          {/* ═══ Pricing ═══ */}
          <Section id="pricing">
            <div className="max-w-6xl mx-auto">
              <SectionHead
                eyebrow="Pricing"
                title={
                  <>
                    Start free. Pay when it has{' '}
                    <span className="text-gradient-brand">earned it</span>
                  </>
                }
                lede="A plan buys you a bigger room, more rounds, more places at once, and more versions of a message to compare. Every run is priced before it starts and you see that price before you commit to it."
              />

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 items-start">
                {TIERS.map((tier, i) => (
                  <motion.div
                    key={tier.id}
                    {...stagger(i)}
                    className={`relative rounded-2xl p-7 flex flex-col h-full bg-saibyl-surface ${
                      tier.featured
                        ? 'border-2 border-saibyl-gold shadow-[0_0_40px_rgba(201,162,39,0.08)]'
                        : 'border border-saibyl-border'
                    }`}
                  >
                    {tier.featured && (
                      <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                        <span className="font-mono text-[10px] tracking-[0.15em] uppercase px-3 py-1.5 rounded-full bg-saibyl-gold text-saibyl-void font-semibold whitespace-nowrap">
                          Start here
                        </span>
                      </div>
                    )}

                    <h3 className="font-sans font-semibold text-xl text-saibyl-platinum mt-2">
                      {tier.name}
                    </h3>
                    <p className="text-sm text-saibyl-silver mt-2 mb-6 min-h-[3.5rem]">
                      {tier.blurb}
                    </p>

                    <div className="mb-1">
                      <span className="font-display font-extrabold text-4xl text-saibyl-platinum">
                        {tier.price}
                      </span>
                      {tier.period && (
                        <span className="text-saibyl-silver text-sm ml-1">{tier.period}</span>
                      )}
                    </div>
                    <p className="text-xs text-saibyl-muted mb-6">
                      <span className="font-mono text-saibyl-gold">{tier.credits}</span>{' '}
                      {tier.creditsNote}
                    </p>

                    <ul className="space-y-3 mb-8 flex-1">
                      {shapeLines(tier.shape).map((line) => (
                        <li
                          key={line}
                          className="flex items-start gap-2.5 text-sm text-saibyl-silver"
                        >
                          <Check
                            className="w-4 h-4 text-saibyl-positive shrink-0 mt-0.5"
                            aria-hidden="true"
                          />
                          {line}
                        </li>
                      ))}
                    </ul>

                    <Link
                      to={tier.ctaTo}
                      className={
                        tier.featured
                          ? `${goldButton} w-full py-3 text-sm`
                          : `${quietButton} w-full py-3 text-sm`
                      }
                    >
                      {tier.cta}
                    </Link>
                  </motion.div>
                ))}
              </div>

              <motion.div
                {...fadeUp}
                className="mt-10 max-w-3xl mx-auto space-y-4 text-center text-sm text-saibyl-muted"
              >
                <p>
                  <span className="text-saibyl-silver">Places</span> means {PLACES.join(', ')}.
                </p>
                <p>
                  Bigger than Agency? Enterprise runs up to{' '}
                  {ENTERPRISE_SHAPE.people.toLocaleString()} people over {ENTERPRISE_SHAPE.rounds}{' '}
                  rounds across all {ENTERPRISE_SHAPE.places} places. Email{' '}
                  <a
                    href={`mailto:${CONTACT_EMAIL}`}
                    className="text-saibyl-signal-blue hover:underline"
                  >
                    {CONTACT_EMAIL}
                  </a>
                  .
                </p>
              </motion.div>
            </div>
          </Section>

          {/* ═══ Questions ═══ */}
          <Section id="faq" tone="raised">
            <div className="max-w-3xl mx-auto">
              <SectionHead eyebrow="Questions" title="The ones people actually ask" />
              <Faq items={FAQ_ITEMS} />
              <motion.p {...fadeUp} className="text-center text-sm text-saibyl-muted mt-8">
                Something else on your mind? Email{' '}
                <a
                  href={`mailto:${CONTACT_EMAIL}`}
                  className="text-saibyl-signal-blue hover:underline"
                >
                  {CONTACT_EMAIL}
                </a>{' '}
                — or just{' '}
                <Link to="/signup" className="text-saibyl-gold hover:underline">
                  start a free run
                </Link>{' '}
                and find out.
              </motion.p>
            </div>
          </Section>

          {/* ═══ Closing ═══ */}
          <Section className="relative overflow-hidden">
            <div
              className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(139,92,246,0.1)_0%,transparent_60%)] pointer-events-none"
              aria-hidden="true"
            />
            <motion.div {...fadeUp} className="relative z-10 max-w-2xl mx-auto text-center">
              <h2 className="font-display font-extrabold text-3xl sm:text-4xl lg:text-[2.75rem] text-saibyl-platinum leading-[1.1] tracking-tight mb-5 text-balance">
                You already built the thing. Find out who wants it.
              </h2>
              <p className="text-lg text-saibyl-silver mb-9">
                One run, {free.credits} credits, no card. If it tells you nothing, you have lost
                an afternoon instead of a campaign budget.
              </p>
              <Link to="/signup" className={`${goldButton} px-10 py-4 text-base`}>
                Start a free run <ArrowRight className="w-4 h-4" aria-hidden="true" />
              </Link>
            </motion.div>
          </Section>
        </main>

        {/* ═══ Footer ═══ */}
        <footer className="border-t border-saibyl-border py-14 px-6 bg-saibyl-void">
          <div className="max-w-6xl mx-auto">
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-10">
              <div className="sm:col-span-2">
                <div className="flex items-center gap-2.5 mb-4">
                  <img src="/logo-mark.svg" alt="" className="h-7 w-7" />
                  <span className="text-gradient-brand font-extrabold text-lg tracking-tight">
                    SAIBYL
                  </span>
                </div>
                <p className="text-sm text-saibyl-silver leading-relaxed max-w-sm">
                  An audience built out of your own material, reacting to your pitch. Every
                  number traces back to something one of them said.
                </p>
              </div>

              {/* Only links that go somewhere. The previous footer carried six
                  `href="#"` placeholders for pages that do not exist — every one
                  of them a dead end at the very bottom of the funnel. */}
              <div>
                <h2 className="font-sans font-semibold text-sm text-saibyl-platinum mb-4">
                  On this page
                </h2>
                <ul className="space-y-3">
                  {NAV_LINKS.map((link) => (
                    <li key={link.href}>
                      <a
                        href={link.href}
                        className="text-sm text-saibyl-silver hover:text-saibyl-platinum transition-colors"
                      >
                        {link.label}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>

              <div>
                <h2 className="font-sans font-semibold text-sm text-saibyl-platinum mb-4">
                  Get started
                </h2>
                <ul className="space-y-3">
                  <li>
                    <Link
                      to="/signup"
                      className="text-sm text-saibyl-gold hover:underline transition-colors"
                    >
                      Start a free run
                    </Link>
                  </li>
                  <li>
                    <Link
                      to="/login"
                      className="text-sm text-saibyl-silver hover:text-saibyl-platinum transition-colors"
                    >
                      Sign in
                    </Link>
                  </li>
                  <li>
                    <a
                      href={`mailto:${CONTACT_EMAIL}`}
                      className="text-sm text-saibyl-silver hover:text-saibyl-platinum transition-colors"
                    >
                      Contact us
                    </a>
                  </li>
                </ul>
              </div>
            </div>

            <div className="border-t border-saibyl-border mt-12 pt-8 text-center">
              <p className="text-sm text-saibyl-muted">
                &copy; 2026 Saido Labs LLC. All rights reserved.
              </p>
            </div>
          </div>
        </footer>
      </div>
    </MotionConfig>
  );
}
