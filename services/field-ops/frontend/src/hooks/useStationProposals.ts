/**
 * The reconcile queue, and the two decisions that empty it.
 *
 * DELIBERATELY NOT OFFLINE-CAPABLE
 *
 * Everything else in this app queues. This does not, and the reason is simpler
 * than the one that first suggested itself.
 *
 * There is nothing to queue. The list cannot be read offline at all: the
 * Workbox runtime cache in `vite.config.ts` matches `/\/api\/v1\/stations/`,
 * and `/api/v1/station-proposals` does not contain that substring — "station-"
 * has a hyphen where "stations" has an s. Checked, not assumed:
 *
 *   /api/v1/stations                     -> true
 *   /api/v1/station-proposals            -> false
 *   /api/v1/station-proposals/1/promote  -> false
 *
 * So offline there is no list, no row, and no decision to defer. Not a stale
 * decision — an absent one.
 *
 * The argument this replaces was that a queued promotion would be "a decision
 * taken against a view of the world that may have changed". That is mostly
 * handled already: `_get_pending` answers 409 for an already-reconciled row,
 * deliberately, and this file cites that 409 two paragraphs down. What it
 * genuinely leaves is narrower — the COALESCE upsert cannot null a field, but
 * a non-NULL stale value does win, so a queue would widen the window for
 * overwriting a good office value with one typed at a monument.
 *
 * The cache fact is the better reason because it is checkable in thirty
 * seconds, and because it correctly STOPS being true if someone gives this
 * list an offline cache — at which point the question should reopen. The
 * story about desks would still have sounded persuasive then.
 *
 * Both the finding and the replacement are gps3's, from review of #227.
 *
 * So these are plain mutations. Offline, they fail and say so.
 *
 * TWO PEOPLE ON ONE QUEUE
 *
 * The endpoints answer 409 for an already-reconciled proposal rather than 404,
 * because "already handled" is what a second reviewer needs to hear. The list
 * is refetched after every outcome including that one, so the row disappears
 * instead of sitting there inviting a second attempt.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  ApiError,
  fetchProposals,
  promoteProposal,
  rejectProposal,
  type StationProposalOut,
} from "../services/api";

const KEY = ["station-proposals"];

export function useStationProposals(pendingOnly = true) {
  return useQuery<StationProposalOut[]>({
    queryKey: [...KEY, pendingOnly],
    queryFn: () => fetchProposals(pendingOnly),
    // A reviewer works through this list; a minute-old view is fine and a
    // refetch on every focus change is not.
    staleTime: 60 * 1000,
    // One retry for a transient failure, none for a permanent one. A 403 is
    // the case that matters: the app offers this tab whenever /me has not
    // answered, so a field_staff account can land here legitimately, and
    // retrying only delays the sentence that explains why. ApiError.isPermanent
    // already excludes 401, 408 and 429, which do resolve on their own.
    retry: (count, err) => !(err instanceof ApiError && err.isPermanent) && count < 1,
  });
}

export function useReconcile() {
  const qc = useQueryClient();
  // Invalidate on settled, not on success: a 409 means someone else has
  // already dealt with the row, which changes the list exactly as much as a
  // success does.
  const invalidate = () => void qc.invalidateQueries({ queryKey: KEY });

  const promote = useMutation({
    mutationFn: (id: number) => promoteProposal(id),
    onSettled: invalidate,
  });

  const reject = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) => rejectProposal(id, reason),
    onSettled: invalidate,
  });

  return { promote, reject };
}
