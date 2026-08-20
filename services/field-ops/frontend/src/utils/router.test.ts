import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { usePath, navigate } from "./router";

/**
 * Routing is 25 lines, and every one of them is a thing react-router would have
 * done. These cover the three that are easy to get wrong by hand: programmatic
 * navigation not emitting popstate, Back not being heard, and repeat taps
 * stacking history entries the user then has to walk back through.
 */

beforeEach(() => window.history.replaceState({}, "", "/"));
afterEach(() => vi.restoreAllMocks());

describe("usePath", () => {
  it("starts at the current pathname", () => {
    window.history.replaceState({}, "", "/sheets");
    expect(renderHook(() => usePath()).result.current).toBe("/sheets");
  });

  it("follows a programmatic navigate", () => {
    // pushState does NOT emit popstate — that event is for the user moving
    // through history, not the program writing to it. Without the custom event
    // the hook would never hear this and the nav would appear dead.
    const { result } = renderHook(() => usePath());
    act(() => navigate("/sheets"));
    expect(result.current).toBe("/sheets");
    expect(window.location.pathname).toBe("/sheets");
  });

  it("follows Back", () => {
    const { result } = renderHook(() => usePath());
    act(() => navigate("/sheets"));
    act(() => {
      window.history.replaceState({}, "", "/queue");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(result.current).toBe("/queue");
  });

  it("stops listening once unmounted", () => {
    // A view that keeps setting state after unmount is a leak and a React
    // warning; on this app it would accumulate one listener per tab switch.
    const remove = vi.spyOn(window, "removeEventListener");
    renderHook(() => usePath()).unmount();
    const events = remove.mock.calls.map((c) => c[0]);
    expect(events).toContain("popstate");
    expect(events).toContain("app:navigate");
  });
});

describe("navigate", () => {
  it("ignores a navigation to the path already shown", () => {
    // Tapping the current tab must not stack history entries — otherwise Back
    // appears broken, needing as many presses as the user made taps.
    const push = vi.spyOn(window.history, "pushState");
    window.history.replaceState({}, "", "/sheets");
    navigate("/sheets");
    expect(push).not.toHaveBeenCalled();
  });

  it("pushes rather than replaces, so Back returns to the form", () => {
    const push = vi.spyOn(window.history, "pushState");
    navigate("/sheets");
    expect(push).toHaveBeenCalledTimes(1);
  });
});
