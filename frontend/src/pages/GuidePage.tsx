import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronDown } from 'lucide-react';

import { Action, Card, Deal, Eyebrow, Ground, Notice, PageHeader, Rise } from '@/components/design';
import { dealDelayMs } from '@/components/design';

/**
 * How this works — the guide, teaching the product Saibyl actually is.
 *
 * **It was teaching a different one.** Restyling this page was the smaller half
 * of the job. On 2026-08-23 it still described the old five-step rail, and its
 * fourth step was *"Find real companies that match"* — the Companies module,
 * which the founder had removed from the product that same day. A founder who
 * read the guide and went looking for step 4 would have found nothing there.
 *
 * Its tips were older still, and belonged to a product that no longer exists:
 * *"How will mid-career software engineers on Twitter and Reddit react to a
 * major tech company announcing 30% of coding roles will be automated by
 * 2027?"* That is the V1 news-reaction oracle, jettisoned by explicit decision
 * — and this page was the last surface in the app still selling it.
 *
 * Two claims are gone rather than restyled, under the honesty floor: that a
 * focus group costs $5,000–$15,000, and that it takes 2–4 weeks. Both were
 * stated as fact, neither was sourced, and this page cannot check either.
 * Saibyl's own numbers stay, because those are measured.
 *
 * The guide now teaches the five stages the landing page sells and the
 * navigation lists, in that order, with each card leading to its stage — the
 * whole point of a guide being that the reader can leave it for the thing it
 * describes.
 */

/** The journey, in the marks and words the landing page and the nav both use. */
const STAGES = [
  {
    mark: '◎',
    name: 'Validate',
    when: 'Idea stage',
    body:
      'Describe what you are building. Saibyl reads your deck, your page or five answers and works out who would buy it — what they do, what they already use, and what would make them doubt you. Then a room of those buyers reads your idea and argues about it, and you find out whether the pain is real before you build for it.',
    to: '/app/validate',
  },
  {
    mark: '✦',
    name: 'Position',
    when: 'Pre-launch',
    body:
      'The room reads your live page and tells you what stopped them, ranked by how many it stopped rather than by how often the words appeared. Saibyl rewrites the page to answer the worst of it, then puts the new version in front of that same room — so what you get back is a measured difference, and an answer that moved nothing is reported as moving nothing.',
    to: '/app/position',
  },
  {
    mark: '⌁',
    name: 'Launch',
    when: 'Go to market',
    body:
      'Write up to eight versions of the same pitch. One room reads all of them, so the only thing that differs is your wording and not who happened to be listening. When the versions are too close to call it says so instead of naming a winner — and the messaging document and outbound sequences underneath are written from what the room measured.',
    to: '/app/launch',
  },
  {
    mark: '↗',
    name: 'Grow',
    when: 'Traction',
    body:
      'You have customers, so every decision now costs something to get wrong. A price rise, a feature you cut, a market you move into — rehearse the move in front of the buyers you already measured and read the reaction before you commit to it.',
    to: '/app/grow',
  },
  {
    mark: '◈',
    name: 'Raise',
    when: 'Fundraise',
    body:
      'Investors ask the questions your buyers already asked, in a harder register. See which firms actually fit what you are building — matched on your sector, your stage and the objections real buyers raised — and how your story reads to them.',
    to: '/app/capital',
  },
] as const;

/**
 * What makes a run take longer, and what the extra time buys.
 *
 * Named the way a founder would say it. The old table's rows were
 * "Agent Count", "Rounds", "Platforms" and "Report Depth" — the configurator's
 * own field names, which is a table that explains the form rather than the
 * decision.
 */
const WHAT_COSTS_TIME = [
  {
    choice: 'How many people are in the room',
    quick: '10',
    full: '100',
    buys: 'More people means the smaller groups are actually represented, rather than inferred from two of them.',
  },
  {
    choice: 'How many rounds they argue for',
    quick: '3',
    full: '15',
    buys: 'More rounds is how you see somebody change their mind — which is the only evidence that an answer worked.',
  },
  {
    choice: 'How many places at once',
    quick: '1',
    full: '5+',
    buys: 'Each one adds how the same pitch reads to a different crowd, and where those crowds disagree.',
  },
  {
    choice: 'How deep the report goes',
    quick: 'Standard',
    full: 'Deep',
    buys: 'Deep gathers twice the evidence per section and goes back for the reasoning behind each number.',
  },
] as const;

/** Where a founder actually loses time, from what the runs show. */
const TIPS = [
  {
    title: 'Upload something before you answer questions',
    body:
      'Saibyl derives your buyers from what you have already written — a deck, a landing page, a pricing page. Answer the five questions instead and it is working from your description of your buyer rather than from your product, which is the one input you are least able to be objective about.',
  },
  {
    title: 'Start at 20 people and 5 rounds',
    body:
      'That finishes in about three minutes and is enough to see the top two or three objections. Scale up once you know which one you are chasing — a 100-person run is worth spending when you have a specific question, and wasted when you are still looking around.',
  },
  {
    title: 'Test more than one version of your message',
    body:
      'Write several versions of the same pitch and one room reads all of them, so the only thing that differed is your wording. The report names a winner only when the evidence actually separates them, and tells you how many more people it would take when it does not.',
  },
  {
    title: 'Re-run the same room after you change the page',
    body:
      'The delta is the point. A revision judged on its own is a new opinion; a revision judged by the room that objected in the first place is a measurement of whether you fixed anything.',
  },
  {
    title: 'Read the sentences under the numbers',
    body:
      'Every figure in a report opens into the things people actually said to produce it. A number you cannot trace back is a number you should not act on, which is why they all open.',
  },
] as const;

const FAQ = [
  {
    q: 'Who are these buyers, exactly?',
    a: 'Written characters with their own job, seniority, budget, tooling and temperament, built from what you uploaded rather than picked off a shelf. They argue in written threads with each other, and nothing is ever posted anywhere real.',
  },
  {
    q: 'How long does a run take?',
    a: 'A room of 20 people over 5 rounds takes 2–4 minutes. A big one — 100 people, 15 rounds, several places at once — takes 10–20 minutes. Writing the report adds another 1–3.',
  },
  {
    q: 'How is this different from a focus group?',
    a: 'A focus group is eight to twelve people, recruited once, and you get one shot at the questions. This is twenty to a hundred, in minutes, and you can change one word and run the same room again — which is the part that is genuinely hard to do with people, not just the part that is expensive.',
  },
  {
    q: 'What are audience packs?',
    a: 'Ready-made rooms grouped by who they are — tech workers, retail investors, healthcare professionals. Each holds a mix of ages, jobs and temperaments rather than one kind of person repeated. You can describe a group of your own, and if you have uploaded your material Saibyl works your actual buyers out instead.',
  },
  {
    q: 'What does the report include?',
    a: 'A summary you can read in a minute, how the room felt round by round, how that differed by place and by kind of buyer, the moments that turned it, and what people objected to — with the sentences behind every one of them.',
  },
  {
    q: 'Can I ask the report questions?',
    a: 'Yes. Once it is written you can ask follow-up questions, and it answers from what was actually said in your run rather than from general knowledge.',
  },
  {
    q: 'What is a message test?',
    a: 'Two or more versions of the same message in front of one shared room. Everyone reacts to every version, so the comparison is like for like — and when the versions are too close to call, the report says so instead of picking one.',
  },
] as const;

/** A section heading, on the system's eyebrow rather than an uppercase h2. */
function Section({
  eyebrow,
  title,
  children,
  delayMs = 0,
}: {
  eyebrow: string;
  title: string;
  children: React.ReactNode;
  delayMs?: number;
}) {
  return (
    <Rise as="section" delayMs={delayMs} className="mb-12">
      <Eyebrow>{eyebrow}</Eyebrow>
      <h2 className="text-[1.375rem] font-bold tracking-[-0.02em] font-display text-saibyl-ink mt-2 mb-5">
        {title}
      </h2>
      {children}
    </Rise>
  );
}

export default function GuidePage() {
  const [openFaq, setOpenFaq] = useState<number | null>(null);

  return (
    <Ground className="p-6 lg:p-8 min-h-full">
      <div className="max-w-4xl mx-auto">
        <Rise className="mb-11">
          <PageHeader
            eyebrow="How this works"
            title="How this works"
            phrase="Find out what they object to, before you launch and not after."
          >
            <p>
              Saibyl builds a room of the buyers you are trying to reach, puts
              what you have written in front of them, and reports what they
              pushed back on &mdash; with the sentences behind every number.
              Five stages, in the order each one feeds the next. You do not have
              to do them in order, but each one is better with the last one
              behind it.
            </p>
          </PageHeader>
        </Rise>

        {/* ── The journey ── */}
        <Section eyebrow="The five stages" title="Where you are, and what happens there" delayMs={dealDelayMs(1)}>
          <div className="space-y-3">
            {STAGES.map((stage, i) => (
              <Deal key={stage.name} index={i}>
                {/* `meaning`, and it lifts — each card is the door to its own
                    stage. A guide whose cards cannot be left for the thing they
                    describe is a guide the reader has to navigate around. */}
                <Card carries="meaning" lift as={Link} to={stage.to} className="block p-5">
                  <div className="flex items-start gap-4">
                    <span
                      aria-hidden
                      className="mt-0.5 w-7 shrink-0 text-center text-[17px] leading-7 text-saibyl-blue"
                    >
                      {stage.mark}
                    </span>
                    <div>
                      <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
                        <h3 className="text-[15px] font-semibold text-saibyl-ink">
                          {stage.name}
                        </h3>
                        <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-saibyl-muted">
                          {stage.when}
                        </span>
                      </div>
                      <p className="text-[13px] text-saibyl-muted leading-relaxed mt-1.5">
                        {stage.body}
                      </p>
                    </div>
                  </div>
                </Card>
              </Deal>
            ))}
          </div>
        </Section>

        {/* ── What a run costs you in time ── */}
        <Section eyebrow="Time and cost" title="What makes a run longer, and what that buys" delayMs={dealDelayMs(2)}>
          <Notice tone="live" title="Start at 20 people, 5 rounds, one place" className="mb-4">
            That finishes in about three minutes and is enough to see your top
            two or three objections. Scale up once you know which one you are
            chasing.
          </Notice>

          {/* A dense table: hairlines, no shadow per row. */}
          <Card carries="density" className="overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="border-b border-saibyl-border">
                    {['What you choose', 'Quick', 'Full', 'What the extra time buys'].map((h) => (
                      <th
                        key={h}
                        className="text-left px-5 py-3 font-mono text-[10px] uppercase tracking-[0.16em] text-saibyl-muted font-medium"
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {WHAT_COSTS_TIME.map((row) => (
                    <tr key={row.choice} className="border-b border-saibyl-border last:border-0">
                      <td className="px-5 py-3.5 text-saibyl-ink font-medium">{row.choice}</td>
                      <td className="px-5 py-3.5 font-mono tabular-nums text-saibyl-positive">
                        {row.quick}
                      </td>
                      <td className="px-5 py-3.5 font-mono tabular-nums text-saibyl-muted">
                        {row.full}
                      </td>
                      <td className="px-5 py-3.5 text-saibyl-muted leading-relaxed">{row.buys}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </Section>

        {/* ── Tips ── */}
        <Section eyebrow="Getting more out of it" title="Where founders lose time" delayMs={dealDelayMs(3)}>
          <div className="space-y-3">
            {TIPS.map((tip, i) => (
              <Card key={tip.title} carries="density" className="p-5">
                <div className="flex items-start gap-3">
                  <span className="w-6 h-6 rounded-lg bg-saibyl-blue/[0.09] flex items-center justify-center shrink-0 mt-0.5">
                    <span className="font-mono text-[11px] font-bold text-saibyl-blue tabular-nums">
                      {i + 1}
                    </span>
                  </span>
                  <div>
                    <h3 className="text-[13.5px] font-semibold text-saibyl-ink mb-1">
                      {tip.title}
                    </h3>
                    <p className="text-[13px] text-saibyl-muted leading-relaxed">{tip.body}</p>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </Section>

        {/* ── FAQ ── */}
        <Section eyebrow="Questions" title="The ones people actually ask" delayMs={dealDelayMs(4)}>
          <div className="space-y-2">
            {FAQ.map((item, i) => {
              const isOpen = openFaq === i;
              return (
                <Card key={item.q} carries="density" className="overflow-hidden">
                  <button
                    type="button"
                    onClick={() => setOpenFaq(isOpen ? null : i)}
                    aria-expanded={isOpen}
                    className="w-full flex items-center justify-between px-5 py-4 text-left group"
                  >
                    <span className="text-[13.5px] font-medium text-saibyl-ink group-hover:text-saibyl-blue transition-colors">
                      {item.q}
                    </span>
                    <ChevronDown
                      className={`w-4 h-4 text-saibyl-muted transition-transform duration-200 shrink-0 ml-4 ${
                        isOpen ? 'rotate-180' : ''
                      }`}
                    />
                  </button>
                  {/* Height is not animated. The old version tweened `height:
                      auto` on every answer, which is a per-item micro-interaction
                      — the canvas asks for one orchestrated arrival per screen,
                      not a page that moves every time it is touched. */}
                  {isOpen && (
                    <p className="px-5 pb-4 text-[13px] text-saibyl-muted leading-relaxed">
                      {item.a}
                    </p>
                  )}
                </Card>
              );
            })}
          </div>
        </Section>

        {/* ── The way out ── */}
        <Rise delayMs={dealDelayMs(5)} className="pb-8">
          <Card carries="stage" className="sb-hero p-7 text-center">
            <h2 className="text-[1.375rem] font-bold tracking-[-0.02em] font-display text-saibyl-ink">
              Nothing here is worth reading twice
            </h2>
            <p className="text-[13px] text-saibyl-muted leading-relaxed mt-2 max-w-xl mx-auto">
              The first run tells you more than this page can. Name what you are
              building &mdash; a sentence is enough &mdash; and the first room is
              about three minutes away.
            </p>
            <Action as={Link} to="/app/validate" className="mt-5">
              Start with Validate
            </Action>
          </Card>
        </Rise>
      </div>
    </Ground>
  );
}
