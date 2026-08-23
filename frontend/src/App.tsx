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
import LandingPage from '@/pages/LandingPage';
import DashboardPage from '@/pages/DashboardPage';
import GuidePage from '@/pages/GuidePage';
import IpCheckPage from '@/pages/IpCheckPage';
import SalesToolkitPage from '@/pages/SalesToolkitPage';
import WebsitePage from '@/pages/WebsitePage';
import LoginPage from '@/pages/LoginPage';
import MarketingPage from '@/pages/MarketingPage';
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

function AnimatedRoutes() {
  const location = useLocation();

  return (
    <AnimatePresence mode="wait" initial={false}>
      <Routes location={location} key={location.pathname}>
        {/* Public routes */}
        <Route path="/login" element={<PageTransition><LoginPage /></PageTransition>} />
        <Route path="/signup" element={<PageTransition><SignupPage /></PageTransition>} />
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
          <Route path="ip-check" element={<PageTransition><IpCheckPage /></PageTransition>} />
          {/* "Who would fund this?" — the family-office bank. Global for the
              same reason the clearance check is: it is asked before there is a
              rail to hang it on, and the answer is stored against one product
              rather than being a step in one. */}
          <Route path="capital" element={<PageTransition><CapitalPage /></PageTransition>} />
          {/* The website check and the three sales artifacts, global as well
              as being steps on a product's rail. They were reachable only from
              inside a product, so a founder on `/app/home` had no path to the
              flagship module at all — see the pages' own docstrings. Same
              components, same props; these routes add a way in, not a second
              implementation. */}
          <Route path="website" element={<PageTransition><WebsitePage /></PageTransition>} />
          <Route path="sales" element={<PageTransition><SalesToolkitPage /></PageTransition>} />
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
          {/* Testing more than one message had no surface at all — it was
              reachable only by setting a variant count inside the simulation
              wizard, which is why nobody could find it. */}
          <Route path="marketing" element={<PageTransition><MarketingPage /></PageTransition>} />
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
