/**
 * The station picker's failure classifier.
 *
 * Every failure here once rendered as "Stations unavailable (offline?)". A
 * field observer reported the picker as permanently offline while on a
 * network, on two operating systems, and the message sent everyone looking
 * for a browser fault -- because it named the one cause it happened to guess
 * and hid the other four.
 *
 * These tests pin the distinction rather than the wording: what matters is
 * that a person holding the tablet is told which of five things went wrong,
 * and whether pressing a button can help.
 */
import { describe, expect, it } from "vitest";
import { ApiError, TimeoutError } from "../services/api";
import { describeStationFailure } from "./StationPicker";

describe("describeStationFailure", () => {
  it("names a genuine offline state and offers no retry", () => {
    const r = describeStationFailure(new Error("whatever"), false);
    expect(r.label).toMatch(/no network/i);
    expect(r.retryable).toBe(false);
  });

  it("distinguishes a timeout from being offline, and allows retry", () => {
    // The case that produced the field report: network up, server waking.
    const r = describeStationFailure(new TimeoutError(45_000), true);
    expect(r.label).toMatch(/not answering/i);
    expect(r.label).not.toMatch(/no network/i);
    expect(r.retryable).toBe(true);
  });

  it("names an expired session and sends the operator to log in", () => {
    const r = describeStationFailure(new ApiError(401, "Session expired"), true);
    expect(r.label).toMatch(/session expired/i);
    expect(r.hint).toMatch(/log in/i);
    expect(r.retryable).toBe(false);
  });

  it("blames the server for a 5xx and still allows retry", () => {
    const r = describeStationFailure(new ApiError(503, "upstream"), true);
    expect(r.label).toContain("503");
    expect(r.hint).toMatch(/server failed/i);
    expect(r.retryable).toBe(true);
  });

  it("does not offer retry for a permanent 4xx", () => {
    const r = describeStationFailure(new ApiError(422, "bad request"), true);
    expect(r.label).toContain("422");
    expect(r.retryable).toBe(false);
  });

  it("treats an unreachable host as distinct from offline", () => {
    // navigator.onLine says the device has a link, not that anything answers:
    // a captive portal is the common field case and needs a different action.
    const r = describeStationFailure(new TypeError("Failed to fetch"), true);
    expect(r.label).toMatch(/cannot reach/i);
    expect(r.hint).toMatch(/sign-in page/i);
    expect(r.retryable).toBe(true);
  });
});
