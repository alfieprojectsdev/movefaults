/**
 * Live online/offline state.
 *
 * `navigator.onLine` read during render never re-renders on a connectivity
 * change, so a component reading it directly shows whatever was true when it
 * last happened to render — a "Sync now (offline)" button that stays disabled
 * after signal returns, for instance.
 *
 * Shared rather than local to a component because App (banner), QueueView (sync
 * button) and anything added later all need the same answer at the same moment.
 */

import { useEffect, useState } from "react";

export function useOnline(): boolean {
  const [online, setOnline] = useState(navigator.onLine);

  useEffect(() => {
    // Re-read before attaching. useState() sampled navigator.onLine during
    // render; the listeners only exist from here on, so a transition in that
    // gap would be missed entirely and the hook would stay wrong until the
    // *next* one — which, on a device that just went offline as the app
    // started, may be a long time coming.
    setOnline(navigator.onLine);

    const up = () => setOnline(true);
    const down = () => setOnline(false);
    window.addEventListener("online", up);
    window.addEventListener("offline", down);
    return () => {
      window.removeEventListener("online", up);
      window.removeEventListener("offline", down);
    };
  }, []);

  return online;
}
