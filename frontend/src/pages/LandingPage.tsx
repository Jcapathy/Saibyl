import { useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';

import { BENCHMARKS } from '@/lib/benchmarks';
import { useReveal } from '@/components/design/useReveal';

import './landing.css';

/**
 * The public landing page — the founder-approved light redesign.
 *
 * This is a faithful port of the critic-approved prototype
 * (`Saibyl Redesign examples/saibyl-landing-v3-saido.html`), which survived
 * three critique rounds (docs/CRITICS_LOG.md, 2026-08-16). The copy ships
 * verbatim from that prototype — do not rewrite a word without re-running the
 * critique. All styling lives in `landing.css`, scoped under `.v3land` so the
 * app shell's dark globals cannot reach this page and nothing here leaks back.
 *
 * The prototype's inline <script> becomes the three effects below:
 *   1. one passive scroll listener driving the progress line + condensed nav;
 *   2. smooth anchor scrolling on <html> while this page is mounted (the
 *      prototype set it in CSS; a route component cannot own <html>);
 *   3. an IntersectionObserver adding `is-visible` to `.reveal` sections.
 *
 * Reduced motion is respected exactly as the prototype's CSS does — the
 * media query in landing.css collapses every animation and transition, and
 * the reveal effect shows everything immediately rather than waiting on
 * scroll positions a non-scrolling reader will never produce.
 */
export default function LandingPage() {
  const rootRef = useRef<HTMLDivElement>(null);
  const progressRef = useRef<HTMLDivElement>(null);
  const navWrapRef = useRef<HTMLDivElement>(null);

  // Progress line + nav condensing: one passive scroll listener.
  useEffect(() => {
    const progress = progressRef.current;
    const navWrap = navWrapRef.current;
    if (!progress || !navWrap) return;

    const setScrollState = () => {
      const max = document.documentElement.scrollHeight - window.innerHeight;
      progress.style.transform = `scaleX(${max > 0 ? window.scrollY / max : 0})`;
      navWrap.classList.toggle('is-scrolled', window.scrollY > 16);
    };
    setScrollState();
    window.addEventListener('scroll', setScrollState, { passive: true });
    return () => window.removeEventListener('scroll', setScrollState);
  }, []);

  // The prototype's `html { scroll-behavior: smooth; }`. Applied while this
  // page is mounted and removed on unmount, so the app shell is untouched.
  // Skipped under reduced motion, exactly as the prototype's media query
  // forces `scroll-behavior: auto` there.
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const html = document.documentElement;
    const previous = html.style.scrollBehavior;
    html.style.scrollBehavior = 'smooth';
    return () => {
      html.style.scrollBehavior = previous;
    };
  }, []);

  /* Reveal-on-scroll, from the design system.

     This was ~45 lines here — observer, reduced-motion branch, and the 2.5s
     post-load fallback that keeps a screenshot from photographing a blank
     page. It moved to `components/design/useReveal` on 2026-08-23 so the app
     pages behind the login could have the same behaviour rather than a second
     implementation of it, which is exactly the divergence that made the app
     feel like a different product from this page. Same code, one copy. */
  useReveal(rootRef, '.reveal');

  return (
    <div className="v3land" ref={rootRef}>
      <div className="progress-line" aria-hidden="true" ref={progressRef} />
      <div className="site-shell">
        <div className="container nav-wrap" id="top" ref={navWrapRef}>
          <nav className="nav" aria-label="Primary navigation">
            <a className="brand" href="#top" aria-label="Saibyl home"><span className="brand-mark">S</span><span>Saibyl</span><small>BY SAIDO LABS</small></a>
            <div className="nav-links">
              <a href="#journey">The journey</a>
              <a href="#rehearsal">See a run</a>
              <a href="#pricing">Pricing</a>
              <a href="#faq">Questions</a>
            </div>
            <Link className="nav-cta" to="/signup">Start your first run <span className="arrow">→</span></Link>
          </nav>
        </div>

        <main>
          <section className="hero container" aria-labelledby="hero-heading">
            <div className="hero-grid">
              <div className="hero-copy reveal">
                <span className="eyebrow">Buyer intelligence <span className="mono">·</span> Early access</span>
                <h1 id="hero-heading">Test your startup on a <span className="serif">synthetic market.</span></h1>
                {/* "every objection" -> "every objection the room raised".
                    The check: "The claim 'every objection' is uncheckable and
                    absolute. The sample run itself shows only 6 of 26… If a
                    paying user finds a missed objection" — and they will, since
                    no room is every buyer alive. Scoped to what a run actually
                    returns, the sentence is both smaller and true, and the
                    sample run's own 26 is the receipt for it. */}
                <p className="hero-text">Saibyl builds a room of <b>AI buyers from your own material</b>: your deck, your site, or just five answers — pitches them, and hands you every objection the room raised, with the exact sentences behind it. Rehearse the launch. Fix what fails. <b>Then go.</b></p>
                <div className="hero-actions">
                  <Link className="button primary" to="/signup">Start your first run <span className="arrow">→</span></Link>
                  <a className="button secondary" href="#rehearsal">See a full run <span className="arrow">↓</span></a>
                </div>
                {/* The privacy claim links to the policy that backs it.
                    The check's wording: "'Your files never train models' is a
                    strong privacy claim but has no backing — no link to a
                    privacy policy". The policy existed the whole time, 300
                    lines below in the footer, which is no use to a reader
                    deciding whether to upload an investor deck. A claim and
                    its receipt belong in the same sentence. */}
                <div className="hero-footnote">One full run free <span className="foot-dot">·</span> No card <span className="foot-dot">·</span> <Link className="foot-link" to="/privacy">Your files never train models</Link></div>
              </div>

              <div className="room-stage reveal delay-1" aria-label="A Saibyl room: AI buyers around your pitch, objections streaming in">
                <div className="stage-grid" /><div className="stage-halo" />
                <div className="orbit one"><i /></div><div className="orbit two"><i /></div>
                <div className="buyer buyer-a"><span className="avatar">SF</span><span><b>Solo freelancer</b><small>BUYER · SYNTHETIC</small></span></div>
                <div className="buyer buyer-b"><span className="avatar">SO</span><span><b>Studio owner</b><small>BUYER · SYNTHETIC</small></span></div>
                <div className="buyer buyer-c"><span className="avatar">SH</span><span><b>Side-hustler</b><small>BUYER · SYNTHETIC</small></span></div>
                <div className="buyer buyer-d"><span className="avatar">SK</span><span><b>The skeptic</b><small>PUSHES BACK · SYNTHETIC</small></span></div>
                <div className="core-card"><div><span className="small">In the room</span><strong>Your<br />pitch</strong><b>25 AI BUYERS · 3 ROUNDS</b></div></div>
                <div className="objection-console" aria-hidden="true">
                  <div className="console-top"><span>WHAT THEY PUSHED BACK ON</span><span className="console-live"><i /> SAMPLE RUN</span></div>
                  <div className="obj-row"><i /><span>Risk to client relationships</span><b>3 buyers</b></div>
                  <div className="obj-row"><i /><span>Sounds robotic, impersonal</span><b>2 buyers</b></div>
                  <div className="obj-row"><i /><span>Price versus value <small>· THE SKEPTIC</small></span><b>2 buyers</b></div>
                </div>
              </div>
            </div>
          </section>

          <div className="ticker" aria-label="The Saibyl journey">
            <div className="ticker-track">
              <div className="ticker-group"><strong>One platform</strong><span className="ticker-dot" /><span>Validate the idea</span><span className="ticker-dot" /><span>Sharpen the pitch</span><span className="ticker-dot" /><span>Launch the message</span><span className="ticker-dot" /><span>Grow on evidence</span><span className="ticker-dot" /><span>Raise with answers</span></div>
              <div className="ticker-group" aria-hidden="true"><strong>One platform</strong><span className="ticker-dot" /><span>Validate the idea</span><span className="ticker-dot" /><span>Sharpen the pitch</span><span className="ticker-dot" /><span>Launch the message</span><span className="ticker-dot" /><span>Grow on evidence</span><span className="ticker-dot" /><span>Raise with answers</span></div>
            </div>
          </div>

          <section className="stats container" aria-label="Saibyl at a glance">
            <div className="stats-grid reveal">
              <div className="stat-intro"><span className="eyebrow">How far the room scales</span><p>Every number Saibyl reports opens into the sentences it came from. The room argues in written threads. Nothing is ever posted anywhere real.</p></div>
              <div className="stat"><div className="stat-number"><span>250</span></div><p>AI buyers in the largest rooms<br />30 in your first free run</p></div>
              <div className="stat"><div className="stat-number"><span>12</span></div><p>places where the room argues<br />up to 6 in a single run</p></div>
              <div className="stat"><div className="stat-number"><span>5</span></div><p>stages of the company<br />idea to raise, one platform</p></div>
            </div>
          </section>

          <section className="journey container" id="journey" aria-labelledby="journey-heading">
            <div className="journey-grid">
              <div className="journey-sticky reveal">
                <span className="eyebrow section-kicker">The journey</span>
                <h2 className="section-title" id="journey-heading">The platform grows with you.</h2>
                <p className="section-copy">Every stage of the company asks a different question. Saibyl answers each one with evidence, and the next answer is always one run away.</p>
                <Link className="button primary" to="/signup">Start at your stage <span className="arrow">→</span></Link>
              </div>
              <div className="journey-list reveal delay-1">
                <article className="journey-item"><span className="journey-mark">◎</span><div><h3 className="journey-title">Validate <small>IDEA STAGE</small></h3><p>Is it just you, and has anyone already built it? Saibyl checks the trademark and patent record first, then puts the idea in front of a room.</p></div></article>
                <article className="journey-item"><span className="journey-mark">✦</span><div><h3 className="journey-title">Position <small>PRE-LAUNCH</small></h3><p>Which objections kill the pitch, and which answers actually move them. Test the fix on the same room, and watch the delta.</p></div></article>
                <article className="journey-item"><span className="journey-mark">⌁</span><div><h3 className="journey-title">Launch <small>GO-TO-MARKET</small></h3><p>Up to eight versions of the message, head to head, in front of the same room. The winner earns your budget.</p></div></article>
                <article className="journey-item"><span className="journey-mark">↗</span><div><h3 className="journey-title">Grow <small>TRACTION</small></h3><p>Pricing moves, feature drops, expansion pitches, rehearsed before the market grades them.</p></div></article>
                <article className="journey-item"><span className="journey-mark">◈</span><div><h3 className="journey-title">Raise <small>FUNDRAISE</small></h3><p>How the story reads to investors, and the questions you'll be asked, before you're in the room that matters.</p></div></article>
              </div>
            </div>
          </section>

          <section className="rehearsal" id="rehearsal" aria-labelledby="rehearsal-heading">
            <div className="container">
              <div className="rehearsal-header reveal">
                <div><h2 className="section-title" id="rehearsal-heading">What does a run<br /><em>actually find?</em></h2></div>
                <p className="section-copy">We built a sample product, Tallyhook, invoice chasing for freelancers, and put it through a full run, so you can inspect real output before you upload a word.</p>
              </div>
              <div className="rehearsal-card reveal delay-1">
                <div className="rehearsal-copy">
                  <span className="run-tag"><span className="signal" /> Sample run · 25 AI buyers · 3 rounds · 2 places</span>
                  <h3>The room returned 26 objections. <em>Only one was about price.</em></h3>
                  <p className="kicker">The loudest were about client relationships. That is the lesson founders usually learn after launch. This room surfaced it in about an hour, before.</p>
                  <p>Every row opens into the exact sentences behind it, and who said them. That's the standard for everything Saibyl reports: no score you take on faith, no chart without a receipt.</p>
                  <Link className="button primary" to="/signup">Run yours <span className="arrow">→</span></Link>
                  <p className="synthetic-note">EVERY BUYER IN A SAIBYL ROOM IS AI, BUILT FROM YOUR MATERIAL, LABELED SYNTHETIC ON EVERY SCREEN.</p>
                </div>
                <div className="objection-stack" aria-label="Top objections from the rehearsal run">
                  <div className="stack-title"><span>TOP OBJECTIONS / 26</span><span>BUYERS CARRYING IT</span></div>
                  <div className="objection-card"><b>Risk of damaging client relationships</b><span>3 BUYERS</span></div>
                  <div className="objection-card"><b>Won't work on clients who delay on purpose</b><span>3 BUYERS</span></div>
                  <div className="objection-card"><b>Too expensive for what it does</b><span>2 BUYERS</span></div>
                  <div className="objection-card"><b>The real problem is the relationship</b><span>2 BUYERS</span></div>
                  <div className="objection-card"><b>Automated messages sound robotic</b><span>2 BUYERS</span></div>
                  <div className="objection-card"><b>Guilt about chasing clients for money</b><span>2 BUYERS</span></div>
                </div>
              </div>
            </div>
          </section>

          <section className="steps-band container" aria-labelledby="steps-heading">
            <h2 className="section-title reveal" id="steps-heading">How does Saibyl work? <em>Five steps, about an hour.</em></h2>
            <figure className="run-diagram reveal delay-1">
              <img src="/how-a-run-works.svg" width="1120" height="260" loading="lazy"
                alt="How a Saibyl run works: your material becomes a room of buyers, some built to argue against you; they argue over several rounds; the run returns objections ranked by how much of the room carried each one, and every number opens into the sentences behind it." />
            </figure>
            <div className="steps-strip reveal delay-1">
              <div className="step"><b>Start a product</b><p>Name the thing you're selling. One line is enough. Every room, run, and result attaches to it.</p></div>
              <div className="step"><b>Give it material</b><p>Your deck, your site, a rival's pricing page, or just answer five short questions.</p><span className="step-chip"><i />DECK · SITE · 5 ANSWERS</span></div>
              <div className="step"><b>Meet your audience</b><p>Who buys this and why we think so. Adjust anything, or approve it and run.</p></div>
              <div className="step"><b>Run it</b><p>The room argues over your pitch in written threads. Nothing is posted anywhere real. You watch it live.</p></div>
              <div className="step"><b>Read the objections</b><p>Ranked, grouped, and each one opens into the sentences behind it.</p><span className="step-chip"><i />RANKED · WITH RECEIPTS</span></div>
            </div>
          </section>

          <section className="ladder container" id="ladder" aria-labelledby="ladder-heading">
            <div className="ladder-top reveal">
              <div><h2 className="section-title" id="ladder-heading">What do you get <em>in the free run?</em></h2></div>
              <p className="section-copy">The free run answers the first two questions. Each one after that turns the last answer into the next advantage, and each is priced on its own, so you only buy the ones you want.</p>
            </div>
            <div className="ladder-grid">
              <article className="cap-card reveal delay-1"><span className="cap-tag free">In your free run</span><h3>Audience</h3><p className="q">Who reacts to this?</p><p>Built from your material, not picked from a list. You approve it before anything runs.</p><span className="cap-arc" /></article>
              <article className="cap-card reveal delay-1"><span className="cap-tag free">In your free run</span><h3>Reactions</h3><p className="q">What do they object to?</p><p>The room argues with your pitch, and with each other. The pushback arrives ranked, with receipts.</p><span className="cap-arc" /></article>
              <article className="cap-card reveal delay-2"><span className="cap-tag next">$7.50 a time</span><h3>Answers</h3><p className="q">Did my reply work?</p><p>Saibyl drafts a reply to each objection worth answering, runs the same room again, and shows whether it moved.</p><span className="cap-arc" /></article>
              <article className="cap-card reveal delay-2"><span className="cap-tag next">$15 a list</span><h3>Buyers</h3><p className="q">Which real companies match?</p><p>The audience you approved becomes a list of real companies that fit it, each with the source shown.</p><span className="cap-arc" /></article>
              <article className="cap-card wide reveal delay-3"><span className="cap-tag next">Up to 8 versions, priced per run</span><h3>Messages</h3><p className="q">Which version wins?</p><p>Up to eight versions of the same message in front of the same room at the same moment, so what differs is the wording, never the crowd. The winner earns the budget; the rest never cost you a campaign.</p><span className="cap-arc" /></article>
            </div>
          </section>

          {/* ── What it costs to skip this ──
              **Three outside numbers, each with its primary source linked.**
              They lived in `lib/benchmarks.ts` and rendered only on the billing
              page behind the login, where no crawler will ever read them. The
              KDD 2024 GEO study measured citing sources at +30%, and up to
              +115% for lower-ranked sites, which `docs/SEO_AEO.md` says is
              exactly this site's position. The citations existed and were
              pointed at the one audience that could not use them. */}
          <section className="evidence container" aria-labelledby="evidence-heading">
            <div className="evidence-head reveal">
              <h2 className="section-title" id="evidence-heading">What does it cost to <em>find out late?</em></h2>
              <p className="section-copy">Not our figures. Three published ones, each linked to the study it came from, because a number on a marketing page that you cannot check is not evidence.</p>
            </div>
            <div className="evidence-grid reveal delay-1">
              {BENCHMARKS.map((b) => (
                <article className="evidence-card" key={b.href + b.stat}>
                  <p className="evidence-stat">{b.stat}</p>
                  <p className="evidence-short">{b.short}</p>
                  <p className="evidence-claim">{b.claim}</p>
                  <a className="evidence-src" href={b.href} target="_blank" rel="noreferrer noopener">
                    {b.provenance} ↗
                  </a>
                </article>
              ))}
            </div>
          </section>

          {/* ── The objection, answered rather than avoided ──
              This is the load-bearing objection in every dogfood run of this
              product (6.56, present in 6 of 8 groups, unanswered across three
              rounds) and the only caveat an outside AI raised when asked to
              review the site. Competitors answer it by citing third-party
              research; both papers below are cited to arXiv and were checked
              against their primary sources rather than copied from a rival's
              landing page.

              The framing is the whole of it: these are studies of the METHOD.
              Presenting them as evidence about Saibyl specifically would be the
              exact fabrication this product exists to catch. */}
          <section className="predict container" aria-labelledby="predict-heading">
            <div className="predict-head reveal">
              <h2 className="section-title" id="predict-heading">Does synthetic feedback <em>predict real buyers?</em></h2>
              <p className="section-copy">Nobody has run that study on Saibyl, and we are not going to imply otherwise. Here is what is known about the method, what we can prove about our own output, and what a run will never tell you.</p>
            </div>

            <div className="predict-grid reveal delay-1">
              <article className="predict-card">
                <p className="predict-stat">85%</p>
                <p className="predict-short">as accurate as people are about themselves</p>
                <p className="predict-claim">Stanford built agents from interviews with 1,052 real people. On the General Social Survey, the agents replicated each person&rsquo;s answers 85% as accurately as that person replicated their own answers two weeks later.</p>
                <a className="predict-src" href="https://arxiv.org/abs/2411.10109" target="_blank" rel="noreferrer noopener">Park et al., arXiv:2411.10109 ↗</a>
              </article>
              <article className="predict-card">
                <p className="predict-stat">90%</p>
                <p className="predict-short">of human test-retest reliability</p>
                <p className="predict-claim">PyMC Labs and Colgate-Palmolive ran 57 real product surveys against 9,300 human responses. Synthetic panels matched real purchase intent at 90% of the reliability humans manage against themselves.</p>
                <a className="predict-src" href="https://arxiv.org/abs/2510.08338" target="_blank" rel="noreferrer noopener">Maier et al., arXiv:2510.08338 ↗</a>
              </article>
              <article className="predict-card is-ours">
                <p className="predict-stat">0</p>
                <p className="predict-short">variance, on the half we count</p>
                <p className="predict-claim">Our own measurement. Five sites, scored twice, five minutes apart, pages unchanged. The counted half of a website check returned identical results every time. Reproducibility is not accuracy, but nothing is accurate without it.</p>
                <span className="predict-src">Saibyl, 26 August 2026</span>
              </article>
            </div>

            <div className="predict-limits reveal delay-2">
              <p className="predict-limits-head">What a run will not tell you, printed on every report</p>
              <ul>
                <li><b>Whether the pain is real.</b> The room is built from your description of it, so a room agreeing is not evidence anyone outside the run has the problem.</li>
                <li><b>How many people have it.</b> The size of the room is a setting you chose, not a sample of a population.</li>
                <li><b>Whether they would actually pay.</b> Stated willingness to pay from an audience with no product in front of it indicates direction, not a number.</li>
                <li><b>What they will do.</b> A run measures how material reads. Behaviour is a different question and we do not answer it.</li>
              </ul>
              <p className="predict-note">These are not a disclaimer at the bottom of a page. They are in the code that plans every report, and they print inside the results you buy.</p>
            </div>
          </section>

          <section className="pricing" id="pricing" aria-labelledby="pricing-heading">
            <div className="container">
              <div className="pricing-top reveal">
                <div><h2 className="section-title" id="pricing-heading">How much does<br /><em>Saibyl cost?</em></h2></div>
                <p className="section-copy">Your first run is free, and after that a full run costs about $15. There is no subscription: you buy credits when you want them, they never expire, and every run shows its exact price before it starts.</p>
              </div>
              <div className="price-table-wrap reveal delay-1">
                <table className="price-table">
                  <caption>Every price in credits and in dollars. $1 buys 200 credits.</caption>
                  <thead>
                    <tr><th scope="col">What you run</th><th scope="col">Credits</th><th scope="col">Cost</th></tr>
                  </thead>
                  <tbody>
                    <tr className="is-free">
                      <th scope="row">Your first run <small>30 buyers, 3 rounds, 2 places</small></th>
                      <td>1,335</td><td><b>Free</b></td>
                    </tr>
                    <tr>
                      <th scope="row">A full run <small>100 buyers, 5 rounds</small></th>
                      <td>3,014</td><td>$15.07</td>
                    </tr>
                    <tr>
                      <th scope="row">Website check <small>six reviewers read your page</small></th>
                      <td>1,750</td><td>$8.75</td>
                    </tr>
                    <tr>
                      <th scope="row">Rewrite and re-score <small>the page, tested on the same room</small></th>
                      <td>5,000</td><td>$25.00</td>
                    </tr>
                    <tr>
                      <th scope="row">What to say back <small>an answer to each objection</small></th>
                      <td>1,500</td><td>$7.50</td>
                    </tr>
                    <tr className="is-free">
                      <th scope="row">Name check <small>is the trademark taken</small></th>
                      <td>0</td><td><b>Free</b></td>
                    </tr>
                    <tr>
                      <th scope="row">Prior-art search <small>patents, with claim deep-reads</small></th>
                      <td>2,000</td><td>$10.00</td>
                    </tr>
                    <tr>
                      <th scope="row">Full patent landscape <small>assignees, continuity, examiners</small></th>
                      <td>6,000</td><td>$30.00</td>
                    </tr>
                    <tr>
                      <th scope="row">Real companies that match <small>with the evidence they match</small></th>
                      <td>3,000</td><td>$15.00</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <p className="pricing-note"><b>$1 buys 200 credits, and a credit never expires.</b> Top up between $10 and $500 whenever you want, in one payment. Nothing renews, nothing expires, and no card is taken at signup. A bigger room or more rounds costs proportionally more, and you always see the exact price before you press go. Running this across a lot of clients? <a href="mailto:info@saidolabs.com" style={{ color: 'var(--blue)', fontWeight: 700 }}>Talk to us</a>.</p>
            </div>
          </section>

          <section className="faq container" id="faq" aria-labelledby="faq-heading">
            <div className="faq-grid">
              <div className="reveal">
                <span className="eyebrow section-kicker">Questions</span>
                <h2 className="section-title" id="faq-heading">Asked and answered.</h2>
              </div>
              <div className="reveal delay-1">
                <details open>
                  <summary>Where does my deck go?</summary>
                  <p>Into building your audience, and nowhere else. Your uploads never train models, are never visible outside your account, and you can delete them any time. The full policy is linked below.</p>
                </details>
                <details>
                  <summary>Are the buyers real people?</summary>
                  <p>No, and that is the point. Each is an AI given a specific role, what they already use, and what would make them doubt you, all drawn from your own material. What comes back is what people in that position tend to say and object to: a rehearsal you can run in an hour, at every stage, as many times as the decision deserves.</p>
                </details>
                <details>
                  <summary>What if I only have an idea?</summary>
                  <p>Then you're exactly who the first stage is for. Answer five short questions: the problem, who has it, what you're building, what they use today, a rough price — and Saibyl builds your room from those. They're also the five questions every investor will ask you, so the hour pays twice.</p>
                </details>
                <details>
                  <summary>What happens after my free run?</summary>
                  <p>You'll have your audience and your objection list, and a specific, quantified question the next stage answers. After that you buy credits when you want them: $1 buys 200 credits, a full 100-buyer run is about $15, and top-ups run from $10 to $500. No card is ever taken at signup, so nothing charges you until you decide.</p>
                </details>
                <details>
                  <summary>Is Saibyl a subscription?</summary>
                  <p>No. There are no plans and no monthly fee. You top up credits as you go and they never expire. Nothing renews, so there is nothing to cancel. Every run is priced before it starts, and you spend against a balance you chose to buy.</p>
                </details>
                <details>
                  <summary>Do the synthetic buyers just agree with you?</summary>
                  <p>No. The room is built to argue. A share of every audience is constructed specifically to push back before it has seen your pitch, with its lean set by what those buyers already use and would have to rip out, not by anything you wrote. Every run reports how many of those people were in the room and what the score was with and without them. In Saibyl's own test of itself, the harshest room returned zero support for the pitch.</p>
                </details>
                <details>
                  <summary>How is this different from asking ChatGPT what buyers think?</summary>
                  <p>One model answering as "a buyer" gives you one voice, agreeable by default, with nothing behind it. Saibyl builds a room of buyers from your own material, gives each one a role, an incumbent tool and a reason to doubt you, and lets them argue over several rounds, then ranks the objections by how much of the room actually carried each one and opens every number into the sentences it came from.</p>
                </details>
              </div>
            </div>
          </section>

          <section className="closing container" id="connect" aria-labelledby="connect-heading">
            <div className="closing-panel reveal">
              <div className="closing-content">
                <span className="eyebrow">Early access · Instant</span>
                <h2 id="connect-heading">The market will tell you <em>eventually.</em><br />Saibyl tells you now.</h2>
                <p>One complete run, free. Your room is built from your material, your objections arrive with receipts, and your next move stops being a guess.</p>
                <Link className="button" to="/signup">Start your first run <span className="arrow">→</span></Link>
              </div>
            </div>
          </section>
        </main>

        <footer className="container">
          <div className="footer-inner">
            <a className="brand" href="#top"><span className="brand-mark">S</span><span>Saibyl</span></a>
            <span>© 2026 Saido Labs LLC</span>
            <div className="footer-right"><Link to="/privacy">Privacy</Link><Link to="/terms">Terms</Link><a href="mailto:info@saidolabs.com">info@saidolabs.com</a></div>
          </div>
        </footer>
      </div>
    </div>
  );
}
