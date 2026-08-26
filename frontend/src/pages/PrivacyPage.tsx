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
 * **What is load-bearing here is the subprocessor list.** Every name in it is
 * read off `render.yaml` rather than assembled from a template: Supabase,
 * Anthropic, Stripe, Resend, Sentry, Render, and the USPTO's public APIs. A
 * policy that lists processors a product does not use, or omits ones it does,
 * is worse than no policy, because it is a specific claim that happens to be
 * false. If a service is added to `render.yaml`, it belongs on this page in the
 * same change.
 *
 * **Declared in `render.yaml` is not the same as used.** The first draft of this
 * list named Resend, because `RESEND_API_KEY` is declared there. Nothing sends
 * email through Resend: the only match for the word in the backend is the
 * English verb, in a comment. Account email goes through Supabase Auth. Every
 * other name here was checked the same way, in code rather than in config, and
 * the next person to edit this list owes it the same check.
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
              <b>Payment.</b> When you buy credits, Stripe handles the payment. Card numbers are
              entered on Stripe&rsquo;s systems and <b>never reach ours</b>. We keep a record of
              what you bought, when, and how many credits it was worth.
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
              Running this product means other companies touch some of your data. This is the
              complete list, and each one only receives what its job requires:
            </p>
            <ul className="legal-list">
              <li><b>Supabase</b> (United States) &mdash; the database, file storage, sign-in, and the account emails that go with it.</li>
              <li><b>Anthropic</b> (United States) &mdash; the models that read your material and produce your results.</li>
              <li><b>Render</b> (United States, Oregon) &mdash; hosting for the application.</li>
              <li><b>Stripe</b> &mdash; payments. They hold the card details; we hold the receipt.</li>
              <li><b>Sentry</b> &mdash; error reports, so a failure is something we can find.</li>
              <li><b>The USPTO</b> &mdash; when you run a prior-art or trademark check, the search terms are sent to the United States Patent and Trademark Office&rsquo;s public APIs.</li>
            </ul>
            <p>
              We are a United States company and your data is processed in the United States.
              If you are outside the US, using Saibyl means your data is transferred there.
            </p>

            <h2>How long we keep it</h2>
            <p>
              Your uploads, runs and reports stay until you delete them or close your account.
              Delete a document and it goes from storage. Close the account and we remove the
              content associated with it, keeping only what we have to keep for tax and payment
              records, which Stripe and our accounting obligations govern rather than us.
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
