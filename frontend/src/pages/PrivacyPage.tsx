import { Link } from 'react-router-dom';

import './landing.css';

/**
 * The privacy page the landing page's footer and FAQ link to.
 *
 * It states current practice in plain sentences — exactly what the product's
 * FAQ already promises — and says so. No invented legal boilerplate: a
 * paragraph of law-sounding text nobody wrote for us would promise things we
 * have not checked. Styled with the landing tokens (`landing.css`, scoped
 * under `.v3land`) so the two pages read as one site.
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
            <h1>Privacy</h1>
            <p>
              What you upload — your deck, your site, your answers to our questions — is used to
              build your audience and your reports, and for nothing else. <b>It never trains
              models</b>, it is never shown outside your account, and you can delete it any time.
            </p>
            <p>
              When a run checks a site — yours, or a rival's page you pointed it at — a screenshot
              of what it read is stored so your own reports can show their sources. Those captures
              stay in your account like everything else.
            </p>
            <p>
              To delete your data, or to ask anything about it, email{' '}
              <a href="mailto:info@saidolabs.com">info@saidolabs.com</a>.
            </p>
            <p className="legal-note">A formal policy is being prepared; this page states current practice.</p>
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
