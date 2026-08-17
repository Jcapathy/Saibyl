import { Link } from 'react-router-dom';

import './landing.css';

/**
 * The terms page the landing page's footer links to.
 *
 * Plain-language basics, honestly labeled as current practice — the same rule
 * as PrivacyPage.tsx: no invented legal boilerplate. Styled with the landing
 * tokens (`landing.css`, scoped under `.v3land`).
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
            <h1>Terms</h1>
            <p>
              Saibyl is made by <b>Saido Labs LLC</b>.
            </p>
            <p>
              The reports are <b>automated research support</b> — a rehearsal for decisions that
              are yours to make. They are not legal or financial advice, and the buyers in a room
              are AI, labeled synthetic on every screen.
            </p>
            <p>
              The free run is exactly what the site describes: one complete run, and no card is
              ever taken at signup. Credits and plans cost what the app shows when you buy them,
              and every run shows its exact price before it starts.
            </p>
            <p>
              Questions? Email <a href="mailto:info@saidolabs.com">info@saidolabs.com</a>.
            </p>
            <p className="legal-note">A formal set of terms is being prepared; this page states current practice.</p>
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
