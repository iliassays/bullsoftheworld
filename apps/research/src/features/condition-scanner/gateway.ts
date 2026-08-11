import { researchApi, type ResearchWorkspace } from "../../app/api-client";
import { isResearchPreview } from "../../app/deployment";
import { previewWorkspace } from "../research-queue/gateway";
import type { ConditionKey, ConditionScan, ConditionSubscription } from "./model";
import { previewConditionScan } from "./preview-data";

export interface ConditionScanRequest {
  conditionKey: ConditionKey;
  capTier?: string;
  newOnly?: boolean;
  limit?: number;
}

export interface ConditionScannerGateway {
  loadWorkspaces(): Promise<ResearchWorkspace[]>;
  loadScan(
    workspaceId: string,
    request: ConditionScanRequest,
    signal?: AbortSignal,
  ): Promise<ConditionScan>;
  setSubscription(
    workspaceId: string,
    conditionKey: ConditionKey,
    ticker: string,
    enabled: boolean,
  ): Promise<ConditionSubscription>;
}

class PreviewConditionScannerGateway implements ConditionScannerGateway {
  private readonly subscriptions = new Map<string, boolean>();

  async loadWorkspaces(): Promise<ResearchWorkspace[]> {
    return [previewWorkspace];
  }

  async loadScan(
    workspaceId: string,
    request: ConditionScanRequest,
    signal?: AbortSignal,
  ): Promise<ConditionScan> {
    await new Promise<void>((resolve, reject) => {
      const timer = window.setTimeout(resolve, 120);
      signal?.addEventListener("abort", () => {
        window.clearTimeout(timer);
        reject(new DOMException("Request aborted", "AbortError"));
      }, { once: true });
    });
    const snapshot = previewConditionScan(workspaceId, request.conditionKey);
    const items = snapshot.items
      .filter((item) => !request.capTier || request.capTier === "all" || item.capTier === request.capTier)
      .filter((item) => !request.newOnly || item.isNew)
      .map((item) => ({
        ...item,
        subscribed:
          this.subscriptions.get(`${request.conditionKey}:${item.ticker}`) ?? item.subscribed,
      }));
    return { ...snapshot, returnedCount: items.length, items };
  }

  async setSubscription(
    _workspaceId: string,
    conditionKey: ConditionKey,
    ticker: string,
    enabled: boolean,
  ): Promise<ConditionSubscription> {
    const key = `${conditionKey}:${ticker}`;
    this.subscriptions.set(key, enabled);
    return {
      tenantId: previewWorkspace.tenantId,
      market: previewWorkspace.market,
      ticker,
      conditionKey,
      conditionVersion: "1.0.0",
      methodologyVersion: "research-conditions-v1",
      enabled,
      lastAlertedOn: null,
    };
  }
}

class ApiConditionScannerGateway implements ConditionScannerGateway {
  loadWorkspaces(): Promise<ResearchWorkspace[]> {
    return researchApi.workspaces();
  }

  loadScan(
    workspaceId: string,
    request: ConditionScanRequest,
    signal?: AbortSignal,
  ): Promise<ConditionScan> {
    return researchApi.conditionScan(workspaceId, request, signal);
  }

  setSubscription(
    workspaceId: string,
    conditionKey: ConditionKey,
    ticker: string,
    enabled: boolean,
  ): Promise<ConditionSubscription> {
    return researchApi.setConditionSubscription(
      workspaceId,
      conditionKey,
      ticker,
      enabled,
    );
  }
}

export const conditionScannerGateway: ConditionScannerGateway = isResearchPreview
  ? new PreviewConditionScannerGateway()
  : new ApiConditionScannerGateway();
