import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronDown } from 'lucide-react';

import {
  Action,
  Card,
  Chapter,
  Ground,
  Hero,
  Longform,
  Notice,
  Reveal,
} from '@/components/design';

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
 * ---
 *
 * **The shape, decided later the same day: this page is a landing page.**
 *
 * The founder's words for what the app felt like next to the public site were
 * "very sterile, mechanical, and looks AI-generated", and his instruction was
 * to treat every page behind the login the way the landing page treats itself —
 * a hero, large type, then scroll, with the content arriving as you reach it.
 * This is the first page built that way and the test case for the rest.
 *
 * So the frame is `Longform` / `Hero` / `Chapter` / `Reveal`, whose values are
 * `pages/landing.css`'s own. What is *inside* each chapter did not change: the
 * cards, the table and the answers are the same density they were, because the
 * canvas's constraint was about those and it still holds. A guide that opens
 * like the landing page and then gets on with the work is the whole idea.
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

export default function GuidePage() {
  const [openFaq, setOpenFaq] = useState<number | null>(null);

  return (
    <Ground className="min-h-full pb-24">
      <Longform>
        {/* The hero is not wrapped in `Reveal`: it is the first screen, and a
            page whose opening fades in looks broken for 700ms. */}
        <Hero
          eyebrow="How this works"
          title="Find out what they object to,"
          serif="before you launch."
          actions={
            <>
              <Action as={Link} to="/app/validate">
                Start with Validate
              </Action>
              <Action as={Link} to="/app/home" kind="quiet">
                See what you are building
              </Action>
            </>
          }
        >
          <p>
            Saibyl builds a room of the buyers you are trying to reach, puts what
            you have written in front of them, and reports what they pushed back
            on &mdash; <b className="text-saibyl-ink font-semibold">with the
            sentences behind every number</b>. Five stages, in the order each one
            feeds the next. You do not have to do them in order, but each one is
            better with the last one behind it.
          </p>
        </Hero>

        {/* ── The journey ── */}
        <Chapter
          kicker="The five stages"
          title={
            <>
              Where you are, and <em>what happens there</em>
            </>
          }
          lead="Each one leads to the stage it describes — this page is a map, and a map you cannot leave is a poster."
        >
          <div className="space-y-3">
            {STAGES.map((stage, i) => (
              /* Dealt three at a time. The landing page carries exactly three
                 stagger delays and a fourth stops reading as a sequence, so the
                 fourth and fifth cards land with the third rather than growing
                 the wait. */
              <Reveal key={stage.name} step={(Math.min(i, 3) || 0) as 0 | 1 | 2 | 3}>
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
              </Reveal>
            ))}
          </div>
        </Chapter>

        {/* ── What a run costs you in time ── */}
        <Chapter
          kicker="Time and cost"
          title={
            <>
              What makes a run longer, and <em>what that buys</em>
            </>
          }
        >
          <Reveal>
            <Notice tone="live" title="Start at 20 people, 5 rounds, one place" className="mb-4">
              That finishes in about three minutes and is enough to see your top
              two or three objections. Scale up once you know which one you are
              chasing.
            </Notice>
          </Reveal>

          {/* A dense table: hairlines, no shadow per row. The chapter around it
              grew; the rows inside it did not. */}
          <Reveal step={1}>
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
          </Reveal>
        </Chapter>

        {/* ── Tips ── */}
        <Chapter
          kicker="Getting more out of it"
          title={
            <>
              Where founders <em>lose time</em>
            </>
          }
        >
          <div className="space-y-3">
            {TIPS.map((tip, i) => (
              <Reveal key={tip.title} step={(Math.min(i, 3) || 0) as 0 | 1 | 2 | 3}>
                <Card carries="density" className="p-5">
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
              </Reveal>
            ))}
          </div>
        </Chapter>

        {/* ── FAQ ── */}
        <Chapter
          kicker="Questions"
          title={
            <>
              The ones people <em>actually ask</em>
            </>
          }
        >
          <div className="space-y-2">
            {FAQ.map((item, i) => {
              const isOpen = openFaq === i;
              return (
                <Reveal key={item.q}>
                  <Card carries="density" className="overflow-hidden">
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
                        auto` on every answer — a per-item micro-interaction, where
                        the page wants one arrival per section. */}
                    {isOpen && (
                      <p className="px-5 pb-4 text-[13px] text-saibyl-muted leading-relaxed">
                        {item.a}
                      </p>
                    )}
                  </Card>
                </Reveal>
              );
            })}
          </div>
        </Chapter>

        {/* ── The way out ──
            The landing page closes by asking for the next step, and so does
            this. A guide is a means, and the honest end of one is the door. */}
        <Chapter
          kicker="Then stop reading"
          title={
            <>
              Nothing here is worth <em>reading twice</em>
            </>
          }
          lead="The first run tells you more than this page can. Name what you are building — a sentence is enough — and the first room is about three minutes away."
        >
          <Reveal>
            <Action as={Link} to="/app/validate">
              Start with Validate
            </Action>
          </Reveal>
        </Chapter>
      </Longform>
    </Ground>
  );
}
