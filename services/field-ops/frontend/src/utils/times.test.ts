import { describe, it, expect } from "vitest";
import {
  localTimeToISO,
  utcFieldToISO,
  nowLocalHHMM,
  nowUTCFieldValue,
} from "./times";

/**
 * These helpers exist because every time column is `timestamptz`, so a value
 * sent without a zone is stored as UTC. A Philippine local time typed as
 * "14:30" and sent bare lands in the database as 06:30 local — eight hours
 * wrong, and nothing on screen says so. The assertions below are about that
 * offset, not about formatting.
 */

describe("timezone assumption", () => {
  it("runs in Asia/Manila, as vitest.config.ts pins it", () => {
    // UTC+8 is -480 minutes by getTimezoneOffset's sign convention. If this
    // fails, every local-time expectation below is meaningless — better to
    // say so here than to have the real assertions fail confusingly.
    expect(new Date("2026-08-17T00:00:00Z").getTimezoneOffset()).toBe(-480);
  });
});

describe("localTimeToISO", () => {
  it("reads the wall clock as local and emits the matching UTC instant", () => {
    // 14:30 in Manila is 06:30 UTC the same day.
    expect(localTimeToISO("2026-08-17", "14:30")).toBe("2026-08-17T06:30:00.000Z");
  });

  it("rolls back a day when local morning precedes the UTC date", () => {
    // 07:00 Manila is 23:00 UTC on the 16th — the case a naive
    // `${date}T${time}Z` would silently get wrong by a whole day.
    expect(localTimeToISO("2026-08-17", "07:00")).toBe("2026-08-16T23:00:00.000Z");
  });

  it("handles midnight without wrapping to the wrong date", () => {
    expect(localTimeToISO("2026-08-17", "00:00")).toBe("2026-08-16T16:00:00.000Z");
  });

  it("returns undefined when either half is missing", () => {
    // The API takes `undefined` for an absent optional time. Emitting a
    // half-built string instead is what produced 422s on departure_time.
    expect(localTimeToISO("", "14:30")).toBeUndefined();
    expect(localTimeToISO("2026-08-17", "")).toBeUndefined();
  });

  it("returns undefined rather than an Invalid Date for junk input", () => {
    expect(localTimeToISO("not-a-date", "14:30")).toBeUndefined();
    expect(localTimeToISO("2026-08-17", "ab:cd")).toBeUndefined();
  });
});

describe("utcFieldToISO", () => {
  it("marks a datetime-local value as the UTC instant it already is", () => {
    // The control renders a bare wall clock and does not know its zone. The
    // field is labelled UTC, so the Z is added rather than left to the server.
    expect(utcFieldToISO("2026-08-17T06:30")).toBe("2026-08-17T06:30:00Z");
  });

  it("does not double up seconds when the control supplies them", () => {
    expect(utcFieldToISO("2026-08-17T06:30:15")).toBe("2026-08-17T06:30:15Z");
  });

  it("returns undefined for an empty field", () => {
    expect(utcFieldToISO("")).toBeUndefined();
  });

  it("is NOT shifted by the local zone", () => {
    // The distinction this whole module turns on: the same digits mean
    // different instants depending on which helper produced them.
    const utc = utcFieldToISO("2026-08-17T14:30");
    const local = localTimeToISO("2026-08-17", "14:30");
    expect(new Date(utc!).toISOString()).toBe("2026-08-17T14:30:00.000Z");
    expect(new Date(local!).toISOString()).toBe("2026-08-17T06:30:00.000Z");
  });
});

describe("autofill values", () => {
  it("nowLocalHHMM renders the local clock, zero-padded", () => {
    // 2026-08-17T01:05Z is 09:05 in Manila.
    expect(nowLocalHHMM(new Date("2026-08-17T01:05:00Z"))).toBe("09:05");
  });

  it("nowLocalHHMM pads a single-digit hour", () => {
    expect(nowLocalHHMM(new Date("2026-08-16T20:07:00Z"))).toBe("04:07");
  });

  it("nowUTCFieldValue renders UTC, not local, despite the control's name", () => {
    // The bug this guards: filling a UTC-labelled field from the local clock
    // is eight hours out and looks entirely plausible on screen.
    expect(nowUTCFieldValue(new Date("2026-08-17T01:05:00Z"))).toBe("2026-08-17T01:05");
  });

  it("nowUTCFieldValue pads month and day", () => {
    expect(nowUTCFieldValue(new Date("2026-01-02T03:04:00Z"))).toBe("2026-01-02T03:04");
  });

  it("round-trips: autofilled arrival time reads back as the same wall clock", () => {
    // What the operator sees on the form must survive the trip to the server
    // and back. This is the end-to-end claim the two helpers jointly make.
    const now = new Date("2026-08-17T06:30:00Z"); // 14:30 Manila
    const shown = nowLocalHHMM(now); // "14:30"
    const stored = localTimeToISO("2026-08-17", shown)!;
    const readBack = new Date(stored).toLocaleTimeString("en-GB", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
    expect(shown).toBe("14:30");
    expect(stored).toBe("2026-08-17T06:30:00.000Z");
    expect(readBack).toBe("14:30");
  });
});
