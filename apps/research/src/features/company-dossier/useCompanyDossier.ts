import { useQuery } from "@tanstack/react-query";

import { companyDossierGateway } from "./gateway";

export function useCompanyDossier(workspaceId: string | undefined, ticker: string | undefined) {
  return useQuery({
    queryKey: ["research", "dossier", workspaceId, ticker?.toUpperCase()],
    queryFn: ({ signal }) => companyDossierGateway.load(workspaceId!, ticker!, signal),
    enabled: Boolean(workspaceId && ticker),
  });
}
