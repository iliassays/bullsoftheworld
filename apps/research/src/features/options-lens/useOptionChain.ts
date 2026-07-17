import { useQuery } from "@tanstack/react-query";

import { optionChainGateway } from "./gateway";

export function useOptionChain(
  workspaceId: string,
  code: string,
  expiration: string | undefined,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ["research", "option-chain", workspaceId, code.toUpperCase(), expiration ?? "nearest"],
    queryFn: ({ signal }) => optionChainGateway.load(workspaceId, code, expiration, signal),
    enabled,
    staleTime: 15 * 60 * 1000,
    retry: 1,
  });
}
