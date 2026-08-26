import { Link } from 'react-router-dom';

import './landing.css';

/**
 * The privacy policy.
 *
 * **The version this replaced was deliberately thin**, and said so: it stated
 * current practice in four paragraphs and closed with "a formal policy is being
 * prepared". That was the right call for a product with no customers. It stops
 * being the right call the day the site takes money at its own domain.
 *
 * **Processors are disclosed by category, not by name (founder decision,
 * 2026-08-25).** An earlier version named all six. The reasoning for changing
 * it was that publishing the stack helps anyone looking for a way in, and GDPR
 * permits describing *categories* of recipients, so the categorical form is a
 * real option rather than a shortcut.
 *
 * Two things a future editor should know before touching this section:
 *
 * · **Most of the stack is public anyway.** The site is served from a
 *   `*.onrender.com` address, the CSP in `render.yaml` names `*.supabase.co`,
 *   and the payment processor appears at checkout. The concealment is partial
 *   by nature, so do not let this section become the reason a security control
 *   is skipped somewhere it would actually matter.
 * · **Enterprise buyers will ask for the names.** That is why the page says the
 *   list is available on request. If that sentence is ever removed, the page
 *   stops being usable in a security review.
 *
 * **The categories are still checked against code, not config.** An earlier
 * draft named Resend because `RESEND_API_KEY` is declared in `render.yaml`.
 * Nothing sends email through it: the only match for the word in the backend is
 * the English verb, in a comment. Account email goes through the storage and
 * sign-in provider. A category listed here must correspond to something the
 * code actually calls.
 *
 * Not legal advice and not drafted by a lawyer. It describes what the system
 * actually does, accurately, which is the part counsel cannot supply and the
 * part that has to be true before any wording around it matters.
 */
export default function PrivacyPage() {
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
            <span className="eyebrow">Privacy</span>
            <h1>Privacy policy</h1>
            <p className="legal-updated">Last updated 25 August 2026</p>

            <p>
              Saibyl is operated by <b>Saido Labs LLC</b>. This page explains what we collect,
              why, who else processes it, and how to get rid of it. It is written to be read
              rather than to be survived.
            </p>

            <h2>What we collect</h2>
            <p>
              <b>Your account.</b> Your name, email address, organisation name, and a password
              we never see in plain text.
            </p>
            <p>
              <b>What you give a run.</b> Documents you upload, text you write into the guided
              form, and the addresses of any pages you ask us to read. When a run reads a page,
              we store the text and a screenshot of what the page looked like, because your
              report has to be able to show you its sources.
            </p>
            <p>
              <b>What a run produces.</b> The audience, the reactions, the objections, the
              reports, and the record of which runs you have made.
            </p>
            <p>
              <b>Payment.</b> When you buy credits, a payment processor handles the transaction.
              Card numbers are entered on their systems and <b>never reach ours</b>. We keep a
              record of what you bought, when, and how many credits it was worth.
            </p>
            <p>
              <b>Ordinary technical data.</b> Log entries and error reports produced while the
              product runs.
            </p>

            <h2>What we do not do</h2>
            <p>
              <b>Your material never trains a model.</b> Not ours, and not anybody else&rsquo;s.
              It is sent to a model to produce your results and for nothing else.
            </p>
            <p>
              We do not sell your data, we do not share it with advertisers, and nothing you
              upload is visible to other customers.
            </p>

            <h2>Who else processes it</h2>
            <p>
              Running this product means established third-party providers process some of your
              data on our behalf. Each receives only what its job requires, and each is bound to
              use it for that job and nothing else. They fall into these categories:
            </p>
            <ul className="legal-list">
              <li><b>Hosting and infrastructure</b> &mdash; running the application itself.</li>
              <li><b>Database and file storage</b> &mdash; where your account, uploads and results are kept, and the sign-in that protects them.</li>
              <li><b>AI model providers</b> &mdash; the models that read your material and produce your results. <b>They do not train on it.</b></li>
              <li><b>Payment processing</b> &mdash; card details are entered on the processor&rsquo;s systems and never reach ours.</li>
              <li><b>Error monitoring</b> &mdash; so a failure is something we can find and fix.</li>
            </ul>
            <p>
              <b>We do not name these providers here, and that is a deliberate choice rather
              than an omission.</b> If you are evaluating Saibyl and need the current list, ask
              and we will send it. Security reviews get a straight answer.
            </p>
            <p>
              <b>One exception, because it is your data leaving rather than a vendor of ours.</b>{' '}
              When you run a prior-art or trademark check, your search terms are sent to the
              United States Patent and Trademark Office&rsquo;s public search systems. That is a
              government database, not a company we chose, and there is no way to search it
              without querying it.
            </p>
            <p>
              We are a United States company and your data is processed in the United States.
              If you are outside the US, using Saibyl means your data is transferred there.
            </p>

            <h2>How long we keep it</h2>
            <p>
              Your uploads, runs and reports stay until you delete them or close your account.
              Delete a document and it goes from storage. Close the account and we remove the
              content associated with it, keeping only what we have to keep for tax and payment
              records, which our accounting obligations and the payment processor&rsquo;s own
              retention rules govern rather than us.
            </p>

            <h2>Your choices</h2>
            <p>
              You can ask us for a copy of what we hold, ask us to correct it, or ask us to
              delete it. Depending on where you live you may have these as legal rights; we
              intend to honour the requests either way. Email{' '}
              <a href="mailto:info@saidolabs.com">info@saidolabs.com</a> and we will answer
              within 30 days.
            </p>

            <h2>Security</h2>
            <p>
              Traffic is encrypted in transit. Each organisation&rsquo;s data is isolated at the
              database level rather than only in application code. We will not claim a
              certification we do not hold: Saibyl has no SOC 2 report, and when that changes
              this sentence will change with it.
            </p>

            <h2>Children</h2>
            <p>
              Saibyl is a business tool and is not intended for anyone under 18. We do not
              knowingly collect information from children.
            </p>

            <h2>Changes</h2>
            <p>
              If this policy changes in a way that affects you, we will say so by email rather
              than by quietly editing the date at the top.
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
