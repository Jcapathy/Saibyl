import { useEffect } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';

import AppLayout from '@/components/AppLayout';
import PageTransition from '@/components/PageTransition';
import ProtectedRoute from '@/components/ProtectedRoute';
import ComparisonPage from '@/pages/ComparisonPage';
import LandingPage from '@/pages/LandingPage';
import DashboardPage from '@/pages/DashboardPage';
import LoginPage from '@/pages/LoginPage';
import MarketDetailPage from '@/pages/MarketDetailPage';
import MarketsPage from '@/pages/MarketsPage';
import NewSimulationPage from '@/pages/NewSimulationPage';
import ProjectDetailPage from '@/pages/ProjectDetailPage';
import ProjectsPage from '@/pages/ProjectsPage';
import ReportViewerPage from '@/pages/ReportViewerPage';
import SettingsPage from '@/pages/SettingsPage';
import SignupPage from '@/pages/SignupPage';
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

        {/* Protected app routes */}
        <Route
          path="/app"
          element={
            <ProtectedRoute>
              <AppLayout />
            </ProtectedRoute>
          }
        >
          <Route index element={<Navigate to="dashboard" replace />} />
          <Route path="dashboard" element={<PageTransition><DashboardPage /></PageTransition>} />
          <Route path="projects" element={<PageTransition><ProjectsPage /></PageTransition>} />
          <Route path="projects/:id" element={<PageTransition><ProjectDetailPage /></PageTransition>} />
          <Route path="simulations" element={<PageTransition><SimulationsPage /></PageTransition>} />
          <Route path="simulations/new" element={<PageTransition><NewSimulationPage /></PageTransition>} />
          <Route path="simulations/:id" element={<PageTransition><SimulationDetailPage /></PageTransition>} />
          <Route path="simulations/:id/run" element={<SimulationRunPage />} />
          <Route path="simulations/:id/report" element={<PageTransition><ReportViewerPage /></PageTransition>} />
          <Route path="markets" element={<PageTransition><MarketsPage /></PageTransition>} />
          <Route path="markets/:id" element={<PageTransition><MarketDetailPage /></PageTransition>} />
          <Route path="simulations/:id/compare" element={<PageTransition><ComparisonPage /></PageTransition>} />
          <Route path="settings/*" element={<PageTransition><SettingsPage /></PageTransition>} />
        </Route>

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
      <AnimatedRoutes />
    </BrowserRouter>
  );
}
