import { useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';

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
                <p className="hero-text">Saibyl builds a room of <b>AI buyers from your own material</b> — your deck, your site, or just five answers — pitches them, and hands you every objection with the exact sentences behind it. Rehearse the launch. Fix what fails. <b>Then go.</b></p>
                <div className="hero-actions">
                  <Link className="button primary" to="/signup">Start your first run <span className="arrow">→</span></Link>
                  <a className="button secondary" href="#rehearsal">See a full run <span className="arrow">↓</span></a>
                </div>
                <div className="hero-footnote">One full run free <span className="foot-dot">·</span> No card <span className="foot-dot">·</span> Your files never train models</div>
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
              <div className="stat-intro"><span className="eyebrow">How far the room scales</span><p>Every number Saibyl reports opens into the sentences it came from. The room argues in written threads — nothing is ever posted anywhere real.</p></div>
              <div className="stat"><div className="stat-number"><span>1,000</span></div><p>AI buyers in the largest rooms<br />25 in your first free run</p></div>
              <div className="stat"><div className="stat-number"><span>12</span></div><p>places where the room argues<br />up to 6 self-serve, all 12 enterprise</p></div>
              <div className="stat"><div className="stat-number"><span>5</span></div><p>stages of the company<br />idea to raise, one platform</p></div>
            </div>
          </section>

          <section className="journey container" id="journey" aria-labelledby="journey-heading">
            <div className="journey-grid">
              <div className="journey-sticky reveal">
                <span className="eyebrow section-kicker">The journey</span>
                <h2 className="section-title" id="journey-heading">The platform grows with you.</h2>
                <p className="section-copy">Every stage of the company asks a different question. Saibyl answers each one with evidence — and the next answer is always one run away.</p>
                <Link className="button primary" to="/signup">Start at your stage <span className="arrow">→</span></Link>
              </div>
              <div className="journey-list reveal delay-1">
                <article className="journey-item"><span className="journey-mark">◎</span><div><h3 className="journey-title">Validate <small>IDEA STAGE</small></h3><p>Does the pain exist, who feels it most, and what would they pay? Five answers are enough to build your first room.</p></div></article>
                <article className="journey-item"><span className="journey-mark">✦</span><div><h3 className="journey-title">Position <small>PRE-LAUNCH</small></h3><p>Which objections kill the pitch — and which answers actually move them. Test the fix on the same room, and watch the delta.</p></div></article>
                <article className="journey-item"><span className="journey-mark">⌁</span><div><h3 className="journey-title">Launch <small>GO-TO-MARKET</small></h3><p>Up to eight versions of the message, head to head, in front of the same room — the winner earns your budget.</p></div></article>
                <article className="journey-item"><span className="journey-mark">↗</span><div><h3 className="journey-title">Grow <small>TRACTION</small></h3><p>Pricing moves, feature drops, expansion pitches — rehearsed before the market grades them.</p></div></article>
                <article className="journey-item"><span className="journey-mark">◈</span><div><h3 className="journey-title">Raise <small>FUNDRAISE</small></h3><p>How the story reads to investors — and the questions you'll be asked, before you're in the room that matters.</p></div></article>
              </div>
            </div>
          </section>

          <section className="rehearsal" id="rehearsal" aria-labelledby="rehearsal-heading">
            <div className="container">
              <div className="rehearsal-header reveal">
                <div><span className="eyebrow section-kicker">See a run</span><h2 className="section-title" id="rehearsal-heading">A launch,<br /><em>rehearsed.</em></h2></div>
                <p className="section-copy">We built a sample product — Tallyhook, invoice chasing for freelancers — and put it through a full run, so you can inspect real output before you upload a word.</p>
              </div>
              <div className="rehearsal-card reveal delay-1">
                <div className="rehearsal-copy">
                  <span className="run-tag"><span className="signal" /> Sample run · 25 AI buyers · 3 rounds · 2 places</span>
                  <h3>The room returned 26 objections. <em>Only one was about price.</em></h3>
                  <p className="kicker">The loudest were about client relationships — the lesson founders usually learn after launch. This room surfaced it in about an hour, before.</p>
                  <p>Every row opens into the exact sentences behind it, and who said them. That's the standard for everything Saibyl reports: no score you take on faith, no chart without a receipt.</p>
                  <Link className="button primary" to="/signup">Run yours <span className="arrow">→</span></Link>
                  <p className="synthetic-note">EVERY BUYER IN A SAIBYL ROOM IS AI — BUILT FROM YOUR MATERIAL, LABELED SYNTHETIC ON EVERY SCREEN.</p>
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
            <span className="eyebrow section-kicker reveal">How it works</span>
            <h2 className="section-title reveal" id="steps-heading">Five steps. About an hour.</h2>
            <div className="steps-strip reveal delay-1">
              <div className="step"><b>Start a product</b><p>Name the thing you're selling — one line is enough. Every room, run, and result attaches to it.</p></div>
              <div className="step"><b>Give it material</b><p>Your deck, your site, a rival's pricing page — or just answer five short questions.</p><span className="step-chip"><i />DECK · SITE · 5 ANSWERS</span></div>
              <div className="step"><b>Meet your audience</b><p>Who buys this and why we think so. Adjust anything, or approve it and run.</p></div>
              <div className="step"><b>Run it</b><p>The room argues over your pitch in written threads — nothing is posted anywhere real. You watch it live.</p></div>
              <div className="step"><b>Read the objections</b><p>Ranked, grouped, and each one opens into the sentences behind it.</p><span className="step-chip"><i />RANKED · WITH RECEIPTS</span></div>
            </div>
          </section>

          <section className="ladder container" id="ladder" aria-labelledby="ladder-heading">
            <div className="ladder-top reveal">
              <div><span className="eyebrow section-kicker">What you unlock</span><h2 className="section-title" id="ladder-heading">Your first run is the beginning.</h2></div>
              <p className="section-copy">The free run answers the first two questions. Each one after that turns the last answer into the next advantage.</p>
            </div>
            <div className="ladder-grid">
              <article className="cap-card reveal delay-1"><span className="cap-tag free">In your free run</span><h3>Audience</h3><p className="q">Who reacts to this?</p><p>Built from your material, not picked from a list. You approve it before anything runs.</p><span className="cap-arc" /></article>
              <article className="cap-card reveal delay-1"><span className="cap-tag free">In your free run</span><h3>Reactions</h3><p className="q">What do they object to?</p><p>The room argues with your pitch — and with each other. The pushback arrives ranked, with receipts.</p><span className="cap-arc" /></article>
              <article className="cap-card reveal delay-2"><span className="cap-tag next">Unlocks with any plan — from $99/mo</span><h3>Answers</h3><p className="q">Did my reply work?</p><p>Saibyl drafts a reply to each objection worth answering, runs the same room again, and shows whether it moved.</p><span className="cap-arc" /></article>
              <article className="cap-card reveal delay-2"><span className="cap-tag next">Unlocks with any plan — from $99/mo</span><h3>Buyers</h3><p className="q">Which real companies match?</p><p>The audience you approved becomes a list of real companies that fit it — each with the source shown.</p><span className="cap-arc" /></article>
              <article className="cap-card wide reveal delay-3"><span className="cap-tag next">Unlocks with any plan — 3 versions on Founder, 8 on Agency</span><h3>Messages</h3><p className="q">Which version wins?</p><p>Up to eight versions of the same message in front of the same room at the same moment — so what differs is the wording, never the crowd. The winner earns the budget; the rest never cost you a campaign.</p><span className="cap-arc" /></article>
            </div>
          </section>

          <section className="pricing" id="pricing" aria-labelledby="pricing-heading">
            <div className="container">
              <div className="pricing-top reveal">
                <div><span className="eyebrow section-kicker">Pricing</span><h2 className="section-title" id="pricing-heading">Start free.<br /><em>Scale on evidence.</em></h2></div>
                <p className="section-copy">A plan buys a bigger room, more rounds, more places, and more versions head to head. A standard run is 100 buyers over 5 rounds — and every run shows its exact price before it starts.</p>
              </div>
              <div className="tier-grid">
                <div className="tier free reveal">
                  <span className="flag">Start here</span>
                  <h3>Free</h3>
                  <p className="who">One complete run — every step, to see what the room finds.</p>
                  <p className="price">$0</p>
                  <p className="runs">1 COMPLETE RUN · 25-PERSON ROOM</p>
                  <ul>
                    <li><b>25</b> buyers in the room</li>
                    <li><b>3</b> rounds of back-and-forth</li>
                    <li><b>2</b> places at once</li>
                    <li>One message per run</li>
                  </ul>
                  <Link className="button primary" to="/signup">Start your first run <span className="arrow">→</span></Link>
                </div>
                <div className="tier popular reveal delay-1">
                  <span className="flag">Most popular</span>
                  <h3>Founder</h3>
                  <p className="who">For the founder proving the thing sells.</p>
                  <p className="price">$99<small>/mo</small></p>
                  <p className="runs">≈ 6 STANDARD RUNS A MONTH</p>
                  <ul>
                    <li>Up to <b>100</b> buyers</li>
                    <li>Up to <b>8</b> rounds</li>
                    <li>Up to <b>3</b> places</li>
                    <li><b>3</b> versions, head to head</li>
                  </ul>
                  <Link className="button ghost" to="/signup">Prove it sells <span className="arrow">→</span></Link>
                </div>
                <div className="tier reveal delay-2">
                  <h3>Growth</h3>
                  <p className="who">For the team testing messages before spending on them.</p>
                  <p className="price">$299<small>/mo</small></p>
                  <p className="runs">≈ 19 STANDARD RUNS A MONTH</p>
                  <ul>
                    <li>Up to <b>150</b> buyers</li>
                    <li>Up to <b>10</b> rounds</li>
                    <li>Up to <b>4</b> places</li>
                    <li><b>5</b> versions, head to head</li>
                  </ul>
                  <Link className="button ghost" to="/signup">Test before you spend <span className="arrow">→</span></Link>
                </div>
                <div className="tier reveal delay-3">
                  <h3>Agency</h3>
                  <p className="who">For the shop running this across clients.</p>
                  <p className="price">$999<small>/mo</small></p>
                  <p className="runs">≈ 66 STANDARD RUNS A MONTH</p>
                  <ul>
                    <li>Up to <b>250</b> buyers</li>
                    <li>Up to <b>12</b> rounds</li>
                    <li>Up to <b>6</b> places</li>
                    <li><b>8</b> versions, head to head</li>
                  </ul>
                  <Link className="button ghost" to="/signup">Run it across clients <span className="arrow">→</span></Link>
                </div>
              </div>
              <p className="pricing-note">Bigger rooms and more rounds draw down runs proportionally — you see the exact price before you press go, and top-ups are there for the weeks momentum spikes. Bigger than Agency? Rooms run to 1,000 buyers over 20 rounds, across all 12 places at once — <a href="mailto:info@saidolabs.com" style={{ color: 'var(--blue)', fontWeight: 700 }}>talk to us</a>.</p>
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
                  <p>No — and that's the point. Each is an AI given a specific role, what they already use, and what would make them doubt you, all drawn from your own material. What comes back is what people in that position tend to say and object to: a rehearsal you can run in an hour, at every stage, as many times as the decision deserves.</p>
                </details>
                <details>
                  <summary>What if I only have an idea?</summary>
                  <p>Then you're exactly who the first stage is for. Answer five short questions — the problem, who has it, what you're building, what they use today, a rough price — and Saibyl builds your room from those. They're also the five questions every investor will ask you, so the hour pays twice.</p>
                </details>
                <details>
                  <summary>What happens after my free run?</summary>
                  <p>You'll have your audience and your objection list — and a specific, quantified question the next stage answers. Pick the plan that matches your pace, or top up for the week you need more room. No card is ever taken at signup, so nothing charges you until you decide.</p>
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
