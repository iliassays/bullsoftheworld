import { useQuery } from "@tanstack/react-query";

import { catalystCalendarGateway, type CatalystCalendarRequest } from "./gateway";

export function useCatalystCalendar(
  workspaceId: string | undefined,
  request: CatalystCalendarRequest,
) {
  return useQuery({
    queryKey: ["research", "catalysts", workspaceId, request.horizonDays, request.code ?? ""],
    queryFn: ({ signal }) => catalystCalendarGateway.loadCalendar(workspaceId!, request, signal),
    enabled: Boolean(workspaceId),
    placeholderData: (previous) => previous,
  });
}
