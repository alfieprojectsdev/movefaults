/**
 * The reconcile queue, and the two decisions that empty it.
 *
 * DELIBERATELY NOT OFFLINE-CAPABLE
 *
 * Everything else in this app queues. This does not, and the asymmetry is the
 * point. Creating a site is done by someone standing at a monument with no
 * signal; reconciling one is done at a desk by someone who can see the
 * inventory. Promote writes to `public.stations` — the one write field-ops
 * makes there — and a queued promotion would be a decision taken against a
 * view of the world that may have changed by the time it lands.
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
