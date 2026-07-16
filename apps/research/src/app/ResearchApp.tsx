import { Navigate, Route, Routes } from "react-router-dom";

import { ResearchShell } from "../layout/ResearchShell";
import { CompanyDossierPage } from "../features/company-dossier/CompanyDossierPage";
import { CompanyDossierLibraryPage } from "../features/company-dossier/CompanyDossierLibraryPage";
import { CatalystCalendarPage } from "../features/catalyst-calendar/CatalystCalendarPage";
import { ResearchQueuePage } from "../features/research-queue/ResearchQueuePage";
import { LoginPage } from "../features/auth/LoginPage";
import { HypothesisLabPage } from "../features/autonomous-research/HypothesisLabPage";
import { LifecycleControlPage } from "../features/autonomous-research/LifecycleControlPage";
import { PortfolioIntelligencePage } from "../features/autonomous-research/PortfolioIntelligencePage";
import { ResearchMemoryPage } from "../features/autonomous-research/ResearchMemoryPage";
import { useResearchAuth } from "./auth";

export function ResearchApp() {
  const auth = useResearchAuth();

  if (auth.loading) {
    return <div aria-label="Restoring research session" className="research-app-boot" />;
  }
  if (!auth.user) return <LoginPage />;

  return (
    <Routes>
      <Route element={<ResearchShell />}>
        <Route path="/queue" element={<ResearchQueuePage />} />
        <Route path="/companies" element={<CompanyDossierLibraryPage />} />
        <Route path="/companies/:ticker" element={<CompanyDossierPage />} />
        <Route path="/catalysts" element={<CatalystCalendarPage />} />
        <Route path="/hypotheses" element={<HypothesisLabPage />} />
        <Route path="/lifecycle" element={<LifecycleControlPage />} />
        <Route path="/portfolio" element={<PortfolioIntelligencePage />} />
        <Route path="/memory" element={<ResearchMemoryPage />} />
        <Route path="*" element={<Navigate to="/queue" replace />} />
      </Route>
    </Routes>
  );
}
