/**
 * React Query hook for fetching and caching the stations list.
 *
 * The Workbox runtime cache (configured in vite.config.ts) returns a
 * cached response when offline — this hook therefore works offline too,
 * as long as the user has visited the app once while online.
 */

import { useQuery } from "@tanstack/react-query";
import { fetchStations, Station } from "../services/api";

export function useStations() {
  return useQuery<Station[]>({
    queryKey: ["stations"],
    queryFn: fetchStations,
    staleTime: 60 * 60 * 1000,  // 1 hour — station list changes rarely
    gcTime: 24 * 60 * 60 * 1000, // keep in cache for 24 h
  });
}
