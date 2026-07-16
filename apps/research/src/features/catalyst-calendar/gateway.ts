import { researchApi } from "../../app/api-client";
import { isResearchPreview, researchDeployment } from "../../app/deployment";
import type { CatalystCalendar } from "./model";
import { demoCatalystEvents } from "./preview-data";

export interface CatalystCalendarRequest {
  horizonDays: number;
  code?: string;
}

export interface CatalystCalendarGateway {
  loadCalendar(
    workspaceId: string,
    request: CatalystCalendarRequest,
    signal?: AbortSignal,
  ): Promise<CatalystCalendar>;
}

class PreviewCatalystCalendarGateway implements CatalystCalendarGateway {
  async loadCalendar(
    workspaceId: string,
    request: CatalystCalendarRequest,
  ): Promise<CatalystCalendar> {
    return {
      tenantId: researchDeployment.tenant,
      market: researchDeployment.market,
      workspaceId,
      generatedAt: new Date().toISOString(),
      horizonDays: request.horizonDays,
      events: demoCatalystEvents,
    };
  }
}

class ApiCatalystCalendarGateway implements CatalystCalendarGateway {
  loadCalendar(
    workspaceId: string,
    request: CatalystCalendarRequest,
    signal?: AbortSignal,
  ): Promise<CatalystCalendar> {
    return researchApi.catalystCalendar(workspaceId, request, signal);
  }
}

export const catalystCalendarGateway: CatalystCalendarGateway = isResearchPreview
  ? new PreviewCatalystCalendarGateway()
  : new ApiCatalystCalendarGateway();
