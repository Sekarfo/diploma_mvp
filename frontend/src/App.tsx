import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "./components/layout/AppLayout";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { CandidateProfilePage } from "./pages/CandidateProfilePage";
import { CandidatesPage } from "./pages/CandidatesPage";
import { DashboardPage } from "./pages/DashboardPage";
import { FeedbackTrainingPage } from "./pages/FeedbackTrainingPage";
import { IntegrationsPage } from "./pages/IntegrationsPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { ProcessingPage } from "./pages/ProcessingPage";
import { SettingsPage } from "./pages/SettingsPage";
import { ShortlistsPage } from "./pages/ShortlistsPage";
import { VacancyCreatePage } from "./pages/VacancyCreatePage";
import { VacancyDetailPage } from "./pages/VacancyDetailPage";
import { VacanciesPage } from "./pages/VacanciesPage";

export function App(): JSX.Element {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<AppLayout />}>
          <Route index element={<DashboardPage />} />
          <Route path="dashboard" element={<Navigate replace to="/" />} />
          <Route path="vacancies" element={<VacanciesPage />} />
          <Route path="vacancies/new" element={<VacancyCreatePage />} />
          <Route path="vacancies/:vacancyId" element={<VacancyDetailPage />} />
          <Route path="processing/:jobId" element={<ProcessingPage />} />
          <Route path="shortlists" element={<ShortlistsPage />} />
          <Route path="candidates" element={<CandidatesPage />} />
          <Route path="candidates/:candidateId" element={<CandidateProfilePage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
          <Route path="feedback-training" element={<FeedbackTrainingPage />} />
          <Route path="integrations" element={<IntegrationsPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

