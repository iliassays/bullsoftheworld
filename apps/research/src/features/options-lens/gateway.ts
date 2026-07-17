import { researchApi } from "../../app/api-client";
import { isResearchPreview } from "../../app/deployment";
import type { OptionChainPreview } from "./model";
import { previewOptionChain } from "./preview-data";

export interface OptionChainGateway {
  load(
    workspaceId: string,
    code: string,
    expiration?: string,
    signal?: AbortSignal,
  ): Promise<OptionChainPreview>;
}

class ApiOptionChainGateway implements OptionChainGateway {
  load(workspaceId: string, code: string, expiration?: string, signal?: AbortSignal) {
    return researchApi.optionChain(workspaceId, code, expiration, signal);
  }
}

class PreviewOptionChainGateway implements OptionChainGateway {
  async load(
    workspaceId: string,
    code: string,
    _expiration?: string,
    signal?: AbortSignal,
  ) {
    if (signal?.aborted) throw new DOMException("Request aborted", "AbortError");
    return previewOptionChain(workspaceId, code);
  }
}

export const optionChainGateway: OptionChainGateway = isResearchPreview
  ? new PreviewOptionChainGateway()
  : new ApiOptionChainGateway();
