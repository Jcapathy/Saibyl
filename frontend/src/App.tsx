import { useEffect } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';

import AppLayout from '@/components/AppLayout';
import ErrorBoundary from '@/components/ErrorBoundary';
import PageTransition from '@/components/PageTransition';
import ProductLayout from '@/components/stages/ProductLayout';
import ProtectedRoute from '@/components/ProtectedRoute';
import AnswersStagePage from '@/pages/product/AnswersStagePage';
import AudienceStagePage from '@/pages/product/AudienceStagePage';
import BuyersStagePage from '@/pages/product/BuyersStagePage';
import MessagesStagePage from '@/pages/product/MessagesStagePage';
import NewProductPage from '@/pages/product/NewProductPage';
import ProductHomePage from '@/pages/product/ProductHomePage';
import ReactionsStagePage from '@/pages/product/ReactionsStagePage';
import CapitalPage from '@/pages/CapitalPage';
import ComparisonPage from '@/pages/ComparisonPage';
import ForgotPasswordPage from '@/pages/ForgotPasswordPage';
import ResetPasswordPage from '@/pages/ResetPasswordPage';
import LandingPage from '@/pages/LandingPage';
import DashboardPage from '@/pages/DashboardPage';
import GuidePage from '@/pages/GuidePage';
import GrowPage from '@/pages/GrowPage';
import LaunchPage from '@/pages/LaunchPage';
import PositionPage from '@/pages/PositionPage';
import ValidatePage from '@/pages/ValidatePage';
import LoginPage from '@/pages/LoginPage';
import NewSimulationPage from '@/pages/NewSimulationPage';
import PackLibraryPage from '@/pages/PackLibraryPage';
import ProjectDetailPage from '@/pages/ProjectDetailPage';
import PrivacyPage from '@/pages/PrivacyPage';
import ProjectsPage from '@/pages/ProjectsPage';
import ProspectDetailPage from '@/pages/ProspectDetailPage';
import ProspectDiscoverPage from '@/pages/ProspectDiscoverPage';
import ProspectSettingsPage from '@/pages/ProspectSettingsPage';
import ProspectsPage from '@/pages/ProspectsPage';
import ReportPrintPage from '@/pages/ReportPrintPage';
import ReportViewerPage from '@/pages/ReportViewerPage';
import SettingsPage from '@/pages/SettingsPage';
import SignupPage from '@/pages/SignupPage';
import TermsPage from '@/pages/TermsPage';
import SimulationDetailPage from '@/pages/SimulationDetailPage';
import SimulationRunPage from '@/pages/SimulationRunPage';
import SimulationsPage from '@/pages/SimulationsPage';
import { useAuthStore } from '@/store/auth';

/**
 * A path a stage absorbed, kept alive for the links people already hold.
 *
 * Four modules stopped having a noun of their own when the nav became the
 * journey. Their pages were deleted rather than left orphaned — a second
 * implementation of a screen is how two surfaces end up disagreeing — but the
 * paths stay, because a bookmark, a shared link or a founder's muscle memory
 * would otherwise fall through to the catch-all and land on the marketing site.
 *
 * `<Navigate to="/app/launch">` with a literal string would drop the query,
 * and every inbound link to these carried `?project=<id>`. That redirect puts
 * the founder on the right stage looking at the wrong product, which is worse
 * than a 404 because nothing about it looks wrong.
 */
function Absorbed({ by }: { by: string }) {
  const { search } = useLocation();
  return <Navigate to={`${by}${search}`} replace />;
}

function AnimatedRoutes() {
  const location = useLocation();

  return (
    <AnimatePresence mode="wait" initial={false}>
      <Routes location={location} key={location.pathname}>
        {/* Public routes */}
        <Route path="/login" element={<PageTransition><LoginPage /></PageTransition>} />
        <Route path="/signup" element={<PageTransition><SignupPage /></PageTransition>} />
        {/* The way back into a locked account. Both public: somebody who cannot
            sign in cannot be behind `ProtectedRoute` to reach them. */}
        <Route path="/forgot-password" element={<PageTransition><ForgotPasswordPage /></PageTransition>} />
        <Route path="/reset-password" element={<PageTransition><ResetPasswordPage /></PageTransition>} />
        <Route path="/privacy" element={<PageTransition><PrivacyPage /></PageTransition>} />
        <Route path="/terms" element={<PageTransition><TermsPage /></PageTransition>} />

        {/* Protected app routes */}
        <Route
          path="/app"
          element={
            <ProtectedRoute>
              <AppLayout />
            </ProtectedRoute>
          }
        >
          {/* Home leads with products. `dashboard` still resolves — the staged
              rail ships as additive routes with every existing one working, so
              a decision to back it out is a navigation change rather than a
              revert. */}
          <Route index element={<Navigate to="home" replace />} />
          <Route path="home" element={<PageTransition><ProductHomePage /></PageTransition>} />
          <Route path="products/new" element={<PageTransition><NewProductPage /></PageTransition>} />
          {/* The five steps, inside one product. `ProductLayout` fetches the
              whole rail once and hands it down, so no stage page invents its
              own idea of what "the audience is confirmed" means — that
              reasoning lives in `services/stages/` and is read in one place.
              Declared before `products/:id` cannot shadow anything here
              because `new` is a sibling static path registered above. */}
          <Route path="products/:id" element={<ProductLayout />}>
            <Route index element={<Navigate to="audience" replace />} />
            <Route path="audience" element={<AudienceStagePage />} />
            <Route path="reactions" element={<ReactionsStagePage />} />
            <Route path="answers" element={<AnswersStagePage />} />
            <Route path="buyers" element={<BuyersStagePage />} />
            <Route path="messages" element={<MessagesStagePage />} />
          </Route>
          <Route path="dashboard" element={<PageTransition><DashboardPage /></PageTransition>} />

          {/* ── The journey ──────────────────────────────────────────────
              Validate · Position · Launch · Grow · Raise, the five stages the
              landing page sells, at the paths their names imply.

              The nav these replaced was a list of nouns that mapped to none of
              them, so a founder read one product on the way in and arrived at
              another. Each stage page composes the modules that already
              existed — no module moved, and every old path below still
              resolves, so backing the journey out is a navigation change
              rather than a revert. */}
          <Route path="validate" element={<PageTransition><ValidatePage /></PageTransition>} />
          <Route path="position" element={<PageTransition><PositionPage /></PageTransition>} />
          <Route path="launch" element={<PageTransition><LaunchPage /></PageTransition>} />
          <Route path="grow" element={<PageTransition><GrowPage /></PageTransition>} />
          {/* Raise. The path stays `capital` — every link, bookmark and test
              that points at it keeps working; only the label joined the
              journey. */}
          <Route path="capital" element={<PageTransition><CapitalPage /></PageTransition>} />

          {/* ── Absorbed ──
              Four modules that were their own noun in the old sidebar and are
              now a panel inside the stage that owns them. In each case the
              stage's component is a superset of the page it replaced — the
              clearance card and the head-to-head panel render strictly more
              than `IpCheckPage` and `MarketingPage` did — so the pages were
              deleted rather than kept as a second way to see the same thing. */}
          <Route path="ip-check" element={<Absorbed by="/app/validate" />} />
          <Route path="website" element={<Absorbed by="/app/position" />} />
          <Route path="sales" element={<Absorbed by="/app/launch" />} />
          <Route path="marketing" element={<Absorbed by="/app/launch" />} />

          <Route path="guide" element={<PageTransition><GuidePage /></PageTransition>} />
          <Route path="projects" element={<PageTransition><ProjectsPage /></PageTransition>} />
          <Route path="projects/:id" element={<PageTransition><ProjectDetailPage /></PageTransition>} />
          <Route path="audiences" element={<PageTransition><PackLibraryPage /></PageTransition>} />
          {/* Prospects. `discover` and `settings` are declared before `:id` —
              a static segment shadowed by a parameterised one would send the
              literal string "discover" to GET /gtm/candidates/{id}. */}
          <Route path="prospects" element={<PageTransition><ProspectsPage /></PageTransition>} />
          <Route path="prospects/discover" element={<PageTransition><ProspectDiscoverPage /></PageTransition>} />
          <Route path="prospects/settings" element={<PageTransition><ProspectSettingsPage /></PageTransition>} />
          <Route path="prospects/:id" element={<PageTransition><ProspectDetailPage /></PageTransition>} />
          <Route path="simulations" element={<PageTransition><SimulationsPage /></PageTransition>} />
          <Route path="simulations/new" element={<PageTransition><NewSimulationPage /></PageTransition>} />
          <Route path="simulations/:id" element={<PageTransition><SimulationDetailPage /></PageTransition>} />
          <Route path="simulations/:id/run" element={<SimulationRunPage />} />
          <Route path="simulations/:id/report" element={<PageTransition><ReportViewerPage /></PageTransition>} />
          <Route path="simulations/:id/compare" element={<PageTransition><ComparisonPage /></PageTransition>} />
          <Route path="settings/*" element={<PageTransition><SettingsPage /></PageTransition>} />
        </Route>

        {/* Print-optimized report (no sidebar, no transitions) */}
        <Route path="/app/simulations/:id/report/print" element={<ProtectedRoute><ReportPrintPage /></ProtectedRoute>} />

        {/* Landing page */}
        <Route path="/" element={<LandingPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AnimatePresence>
  );
}

export default function App() {
  const loadSession = useAuthStore((s) => s.loadSession);

  useEffect(() => {
    loadSession();
  }, [loadSession]);

  return (
    <BrowserRouter>
      {/*
        Inside the router, so the recovery links are real navigation, and
        keyed on nothing — a boundary that remounts per route would swallow
        its own reset. `AnimatedRoutes` is the whole tree, so this catches a
        throw on any screen rather than only the ones somebody remembered to
        wrap.
      */}
      <ErrorBoundary>
        <AnimatedRoutes />
      </ErrorBoundary>
    </BrowserRouter>
  );
}
