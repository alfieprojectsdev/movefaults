/**
 * Filed sheets, cached.
 *
 * `SheetsView` fetches these directly into `useState`. This hook exists
 * because Today needs the same data for a different question — when was this
 * station last visited, and how many sheets went in this week — and two
 * components fetching the same list independently is two requests on a handset
 * that may have one bar.
 *
 * Deliberately NOT a refactor of SheetsView in the same change. That component
 * also drives photo loading and its own error states; moving it to react-query
 * is worth doing and is not worth doing while adding a screen.
 *
 * Failure is not surfaced to the caller. Today degrades to "no sheet on
 * record" if this fails, which is honest — the app genuinely does not know —
 * and a landing screen that refuses to render because a secondary read failed
 * would be worse than one missing a date.
 */

import { useQuery } from "@tanstack/react-query";

import { fetchSheets, type Sheet } from "../services/api";

export function useSheets() {
  return useQuery<Sheet[]>({
    queryKey: ["sheets"],
    queryFn: fetchSheets,
    // Filed sheets change when this observer files one, which the app knows
    // about by other means. A minute is short enough to reflect a sync and
    // long enough to not re-request on every tab switch.
    staleTime: 60 * 1000,
    // A landing screen must render offline. Without this the query retries
    // three times with backoff before settling, and the counts sit empty for
    // several seconds on a handset with no signal.
    retry: 1,
  });
}
