import { Link } from 'react-router-dom';

import './landing.css';

/**
 * The terms of use.
 *
 * **The section that matters most is "What Saibyl is not".** Everything else
 * here is ordinary and could be lifted from any template. That section cannot
 * be, because it is the one place where the product's actual limits get written
 * down as a commitment rather than as marketing modesty: the buyers are
 * software, the output is a reaction and not a prediction, and the prior-art
 * check is not a legal opinion. Every one of those is already enforced
 * somewhere in the codebase, and this is where a customer is told.
 *
 * **Pricing here has to track `PRD_V3` §6.** Saibyl sells credits, not
 * subscriptions. If a sentence on this page ever says "plan", "tier" or
 * "monthly", it is describing a product that was deliberately removed on
 * 2026-08-24 and it is wrong.
 *
 * Not legal advice and not drafted by a lawyer.
 */
export default function TermsPage() {
  return (
    <div className="v3land">
      <div className="site-shell">
        <div className="container nav-wrap">
          <nav className="nav" aria-label="Primary navigation">
            <Link className="brand" to="/" aria-label="Saibyl home"><span className="brand-mark">S</span><span>Saibyl</span><small>BY SAIDO LABS</small></Link>
            <Link className="nav-cta" to="/signup">Start your first run <span className="arrow">→</span></Link>
          </nav>
        </div>

        <main className="legal-main container">
          <div className="legal-card">
            <span className="eyebrow">Terms</span>
            <h1>Terms of use</h1>
            <p className="legal-updated">Last updated 25 August 2026</p>

            <p>
              Saibyl is operated by <b>Saido Labs LLC</b>. By creating an account you agree to
              what follows. If you are agreeing on behalf of a company, you are confirming you
              are allowed to.
            </p>

            <h2>What Saibyl is not</h2>
            <p>
              <b>The buyers are not people.</b> Every participant in a Saibyl room is software,
              built from the material you provided. They are labelled as such on every screen and
              in every export. Nothing is ever posted anywhere real, and no human being said any
              of the sentences in your report.
            </p>
            <p>
              <b>The output is a reaction, not a prediction.</b> Saibyl measures how material
              reads to an audience it constructed. It does not tell you whether a market exists,
              whether a product will sell, or what a real customer will do. Each report states
              what that particular run cannot support, and those statements are the honest limit
              of the result rather than a disclaimer bolted onto it.
            </p>
            <p>
              <b>The prior-art check is not a legal opinion.</b> Trademark and patent results
              come from the USPTO&rsquo;s public records for the searches we ran, on the day we
              ran them. An empty result means those searches found nothing, which is not the same
              as a clearance. Do not file, launch, or name a company on it without a lawyer.
            </p>
            <p>
              Nothing Saibyl produces is legal, financial, medical or investment advice.
            </p>

            <h2>Your account</h2>
            <p>
              Keep your credentials to yourself and tell us if something looks wrong. You are
              responsible for what happens under your account. One account belongs to one
              organisation.
            </p>

            <h2>What you may not do</h2>
            <p>
              Do not upload material you have no right to use. Do not use Saibyl to build
              audiences that target or profile real, identifiable individuals. Do not present
              its output as though real people said it. Do not attempt to break, overload, or
              reverse the service, and do not resell it as your own.
            </p>

            <h2>Your material stays yours</h2>
            <p>
              You keep every right you had in what you upload. You give us permission to store
              and process it for the single purpose of running the service for you, and that
              permission ends when you delete the material. We claim nothing else, and your
              reports are yours to publish, forward or sell as you see fit.
            </p>

            <h2>Credits and payment</h2>
            <p>
              <b>There is no subscription.</b> Saibyl runs on credits: you buy them when you
              want them, they do not expire, and nothing renews. Your first run is free.
            </p>
            <p>
              Every run is priced before it starts, and the price is shown to you before any
              credits move. Credits already spent on a completed run are not refundable, because
              the work was performed. If a run fails through our fault, the credits go back. If
              you want a refund on credits you have not spent, email us and we will sort it out.
            </p>

            <h2>Availability</h2>
            <p>
              Saibyl is provided as it is. We do not promise it will be available at a particular
              time, that a run will always succeed, or that a result will be right for your
              purpose. We will tell you plainly when something has gone wrong rather than
              reporting a partial result as a complete one.
            </p>

            <h2>Liability</h2>
            <p>
              To the extent the law allows, Saido Labs LLC is not liable for indirect or
              consequential loss, including lost profits or lost opportunity, arising from your
              use of Saibyl. Our total liability is limited to what you paid us in the twelve
              months before the claim.
            </p>

            <h2>Ending it</h2>
            <p>
              You can close your account whenever you like. We can suspend an account that
              breaks these terms, and we will say why. If we discontinue the service, we will
              give you notice and time to export your work.
            </p>

            <h2>Governing law</h2>
            <p>
              These terms are governed by the laws of the State of Delaware, United States.
            </p>

            <h2>Changes</h2>
            <p>
              If these terms change in a way that affects you, we will tell you by email before
              the change takes effect.
            </p>

            <h2>Contact</h2>
            <p>
              Saido Labs LLC &mdash; <a href="mailto:info@saidolabs.com">info@saidolabs.com</a>
            </p>

            <Link className="button primary" to="/">Back to Saibyl <span className="arrow">→</span></Link>
          </div>
        </main>

        <footer className="container">
          <div className="footer-inner">
            <Link className="brand" to="/"><span className="brand-mark">S</span><span>Saibyl</span></Link>
            <span>© 2026 Saido Labs LLC</span>
            <div className="footer-right"><Link to="/privacy">Privacy</Link><Link to="/terms">Terms</Link><a href="mailto:info@saidolabs.com">info@saidolabs.com</a></div>
          </div>
        </footer>
      </div>
    </div>
  );
}
