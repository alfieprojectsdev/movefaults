/**
 * The device's own position, for narrowing the station list to where you are.
 *
 * This is a convenience, never a gate. Every failure mode here — permission
 * denied, no fix under tree cover, a handset with a broken GPS — resolves to
 * "we do not know where you are", and the caller falls back to showing every
 * station. An observer standing at a monument must always be able to file a
 * sheet; a filter that cannot be escaped would be worse than no filter.
 *
 * ── Why watchPosition rather than a single read ─────────────────────────────
 *
 * A cold GPS fix outdoors takes 10–40 seconds and the first fix is usually the
 * worst one: phones answer immediately from wifi or cell triangulation, which
 * in rural Palawan can be tens of kilometres out. `watchPosition` lets the
 * accuracy improve while the observer is filling in the rest of the form, so by
 * the time they reach the station picker the fix is usually a real one.
 */

import { useEffect, useRef, useState } from "react";

export interface DeviceFix {
  latitude: number;
  longitude: number;
  /** Radius of 95% confidence, in metres, as reported by the platform. */
  accuracy: number;
  at: number;
}

export type LocationState =
  | { status: "unsupported" }
  | { status: "prompting" }
  | { status: "denied" }
  | { status: "unavailable"; reason: string }
  | { status: "located"; fix: DeviceFix };

/**
 * A fix wider than this is not telling us which municipality we are in, let
 * alone which monument. Cell-tower fixes in rural areas routinely report
 * 5–30 km; treating one as a position would filter the list down to the wrong
 * province entirely. Better to say we do not know.
 */
export const MAX_USEFUL_ACCURACY_M = 2_000;

export function useDeviceLocation(enabled: boolean): LocationState {
  const [state, setState] = useState<LocationState>(
    typeof navigator !== "undefined" && navigator.geolocation
      ? { status: "prompting" }
      : { status: "unsupported" }
  );
  const watchId = useRef<number | null>(null);

  useEffect(() => {
    if (!enabled) return;
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setState({ status: "unsupported" });
      return;
    }

    watchId.current = navigator.geolocation.watchPosition(
      (pos) => {
        const { latitude, longitude, accuracy } = pos.coords;
        if (accuracy > MAX_USEFUL_ACCURACY_M) {
          // A fix this coarse is worse than none: it would confidently filter
          // to a neighbouring province. Keep waiting for a better one.
          setState({
            status: "unavailable",
            reason: `Location is only accurate to ${Math.round(accuracy / 1000)} km`,
          });
          return;
        }
        setState({
          status: "located",
          fix: { latitude, longitude, accuracy, at: Date.now() },
        });
      },
      (err) => {
        if (err.code === err.PERMISSION_DENIED) {
          setState({ status: "denied" });
          return;
        }
        setState({
          status: "unavailable",
          reason:
            err.code === err.TIMEOUT
              ? "No GPS fix yet"
              : "Position unavailable on this device",
        });
      },
      {
        enableHighAccuracy: true,
        // Long: a cold fix under canopy genuinely takes this long, and timing
        // out early just means falling back to the full list for no reason.
        timeout: 30_000,
        // A fix from the last two minutes is fine — nobody walks between
        // monuments in that time, and reusing it avoids a fresh GPS spin-up.
        maximumAge: 120_000,
      }
    );

    return () => {
      if (watchId.current !== null) {
        navigator.geolocation.clearWatch(watchId.current);
        watchId.current = null;
      }
    };
  }, [enabled]);

  return state;
}
