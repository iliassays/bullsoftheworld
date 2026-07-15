import { researchApi } from "../../app/api-client";
import { isResearchPreview } from "../../app/deployment";
import type { ResearchCompanyDossier } from "./model";
import { previewDossier } from "./preview-data";

export interface CompanyDossierGateway {
  load(workspaceId: string, ticker: string, signal?: AbortSignal): Promise<ResearchCompanyDossier>;
}

class ApiCompanyDossierGateway implements CompanyDossierGateway {
  load(workspaceId: string, ticker: string, signal?: AbortSignal) {
    return researchApi.dossier(workspaceId, ticker, signal);
  }
}

class PreviewCompanyDossierGateway implements CompanyDossierGateway {
  async load(workspaceId: string, ticker: string, signal?: AbortSignal) {
    if (signal?.aborted) throw new DOMException("Request aborted", "AbortError");
    return previewDossier(workspaceId, ticker);
  }
}

export const companyDossierGateway: CompanyDossierGateway = isResearchPreview
  ? new PreviewCompanyDossierGateway()
  : new ApiCompanyDossierGateway();
