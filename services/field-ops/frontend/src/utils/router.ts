/**
 * The smallest routing that answers "/sheets".
 *
 * Not react-router: three views do not justify a dependency, a bundle increase
 * and another thing inside the service worker's precache. What is needed is the
 * current path, a way to change it without a reload, and correct Back — which
 * is history.pushState plus a popstate listener.
 *
 * vercel.json already rewrites every non-/api path to index.html, so a deep
 * link to /sheets serves the app rather than 404ing. Nothing on the hosting
 * side needs to change for this.
 */

import { useEffect, useState } from "react";

/** Current pathname, kept in sync with Back and Forward. */
export function usePath(): string {
  const [path, setPath] = useState(() => window.location.pathname);

  useEffect(() => {
    const onPop = () => setPath(window.location.pathname);
    window.addEventListener("popstate", onPop);
    // Also fires for navigate() below, so two components asking for the path
    // cannot disagree about it.
    window.addEventListener("app:navigate", onPop);
    return () => {
      window.removeEventListener("popstate", onPop);
      window.removeEventListener("app:navigate", onPop);
    };
  }, []);

  return path;
}

/**
 * Change the path without a reload.
 *
 * pushState does not emit popstate — that event is for the user moving through
 * history, not for the program writing to it — so the listeners above would
 * never hear about a programmatic navigation. The custom event closes that gap.
 *
 * Navigating to the path already shown is ignored, so tapping the current tab
 * does not stack duplicate history entries that Back then has to walk through.
 */
export function navigate(to: string): void {
  if (window.location.pathname === to) return;
  window.history.pushState({}, "", to);
  window.dispatchEvent(new Event("app:navigate"));
}
