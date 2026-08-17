/**
 * Who is signed in, and what their role is.
 *
 * Asks the server rather than decoding the JWT locally. The token does carry
 * the role and a browser can read it — a JWT is signed, not encrypted — but a
 * role changed in the database would then not take effect until the next
 * login, and a field session lasts 8 hours. Asking makes the server the
 * authority and the change land on the next reload.
 *
 * Cached for the session and served stale while revalidating, because this is
 * consulted on every render of the view switcher and must not put a request on
 * the critical path of a form the operator is filling in.
 *
 * ── Offline ────────────────────────────────────────────────────────────────
 *
 * When the fetch fails there is no role, and the caller must treat that as
 * "show everything" rather than "show nothing". An observer whose /me call
 * failed under a tree is still entitled to the whole app; the role decides a
 * default view, never access.
 */

import { useQuery } from "@tanstack/react-query";
import { fetchMe, type Me } from "../services/api";

export type Role = "field_staff" | "data_processor" | "admin";

export function useCurrentUser() {
  const { data, isLoading, isError } = useQuery<Me>({
    queryKey: ["me"],
    queryFn: fetchMe,
    staleTime: 30 * 60 * 1000,
    // One retry, not the default three: offline is the normal case here and
    // three failing attempts just delays the fallback the caller already
    // handles correctly.
    retry: 1,
  });

  return {
    username: data?.username ?? null,
    role: (data?.role as Role | undefined) ?? null,
    isLoading,
    isError,
  };
}
