import { useEffect } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';

import AppLayout from '@/components/AppLayout';
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

export default function App() {
  const loadSession = useAuthStore((s) => s.loadSession);

  useEffect(() => {
    loadSession();
  }, [loadSession]);

  return (
    <BrowserRouter>
      <Routes>
        {/* Public routes */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />

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
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="projects" element={<ProjectsPage />} />
          <Route path="projects/:id" element={<ProjectDetailPage />} />
          <Route path="simulations" element={<SimulationsPage />} />
          <Route path="simulations/new" element={<NewSimulationPage />} />
          <Route path="simulations/:id" element={<SimulationDetailPage />} />
          <Route path="simulations/:id/run" element={<SimulationRunPage />} />
          <Route path="simulations/:id/report" element={<ReportViewerPage />} />
          <Route path="markets" element={<MarketsPage />} />
          <Route path="markets/:id" element={<MarketDetailPage />} />
          <Route path="compare/:simId" element={<ComparisonPage />} />
          <Route path="settings/*" element={<SettingsPage />} />
        </Route>

        {/* Landing page */}
        <Route path="/" element={<LandingPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
