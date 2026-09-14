/**
 * React Query hook for fetching and caching the stations list.
 *
 * The Workbox runtime cache (configured in vite.config.ts) returns a
 * cached response when offline — this hook therefore works offline too,
 * as long as the user has visited the app once while online.
 */

import { useQuery } from "@tanstack/react-query";
import { fetchStations, Station } from "../services/api";

/**
 * Why the caller needs `error` and not just `isError`.
 *
 * Every failure here used to render as "Stations unavailable (offline?)". On
 * 2026-09-12 a field observer reported the picker as permanently offline while
 * demonstrably on a network, on two operating systems -- and the message sent
 * everyone looking for a browser-specific fault, because it describes the one
 * cause it happened to name and hides the other four.
 *
 * A timeout, a 500, a dead session and an actual absence of network need
 * different actions from the person holding the tablet. Telling them to
 * "connect to a network" when they already are costs a field trip.
 */

export function useStations() {
  return useQuery<Station[]>({
    queryKey: ["stations"],
    queryFn: fetchStations,
    staleTime: 60 * 60 * 1000,  // 1 hour — station list changes rarely
    gcTime: 24 * 60 * 60 * 1000, // keep in cache for 24 h
  });
}
