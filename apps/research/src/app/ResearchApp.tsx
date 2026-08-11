import { Navigate, Route, Routes } from "react-router-dom";

import { ResearchShell } from "../layout/ResearchShell";
import { CompanyDossierPage } from "../features/company-dossier/CompanyDossierPage";
import { CompanyDossierLibraryPage } from "../features/company-dossier/CompanyDossierLibraryPage";
import { CatalystCalendarPage } from "../features/catalyst-calendar/CatalystCalendarPage";
import { ConditionScannerPage } from "../features/condition-scanner/ConditionScannerPage";
import { ResearchQueuePage } from "../features/research-queue/ResearchQueuePage";
import { LoginPage } from "../features/auth/LoginPage";
import { HypothesisLabPage } from "../features/autonomous-research/HypothesisLabPage";
import { LifecycleControlPage } from "../features/autonomous-research/LifecycleControlPage";
import { PortfolioIntelligencePage } from "../features/autonomous-research/PortfolioIntelligencePage";
import { ResearchMemoryPage } from "../features/autonomous-research/ResearchMemoryPage";
import { InvestmentCommandPage } from "../features/investment-command/InvestmentCommandPage";
import { SetupMonitorPage } from "../features/investment-command/SetupMonitorPage";
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
        <Route path="/today" element={<InvestmentCommandPage />} />
        <Route path="/queue" element={<ResearchQueuePage />} />
        <Route path="/companies" element={<CompanyDossierLibraryPage />} />
        <Route path="/companies/:ticker" element={<CompanyDossierPage />} />
        <Route path="/catalysts" element={<CatalystCalendarPage />} />
        <Route path="/conditions" element={<ConditionScannerPage />} />
        <Route path="/setups" element={<SetupMonitorPage />} />
        <Route path="/hypotheses" element={<HypothesisLabPage />} />
        <Route path="/operations" element={<LifecycleControlPage />} />
        <Route path="/lifecycle" element={<Navigate to="/operations" replace />} />
        <Route path="/portfolio" element={<PortfolioIntelligencePage />} />
        <Route path="/memory" element={<ResearchMemoryPage />} />
        <Route path="*" element={<Navigate to="/today" replace />} />
      </Route>
    </Routes>
  );
}
