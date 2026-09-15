import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import NewSiteForm from "./NewSiteForm";
import type { LocationState } from "../hooks/useDeviceLocation";

/**
 * Creating a site at the monument.
 *
 * Two things here are worth more than the rest, and both are about honesty
 * rather than mechanics.
 *
 * The form must never let an observer believe they have added a station to the
 * national inventory. It creates a PROPOSAL. Someone in the office accepts or
 * rejects it, and if the wording hides that, the surprise arrives weeks later
 * as a missing station rather than as an explanation.
 *
 * And the position it records is the one thing the office cannot reconstruct
 * without sending someone back. So it is captured rather than typed, its
 * accuracy is stated, and a poor fix is recorded as a poor fix. It is not
 * required — a site under canopy is still a site, and refusing it would send
 * the observer home with nothing, which is the failure this form exists to
 * end.
 */

const locationResult = vi.fn();
vi.mock("../hooks/useDeviceLocation", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../hooks/useDeviceLocation")>();
  return { ...actual, useDeviceLocation: () => locationResult() as LocationState };
});

const goodFix: LocationState = {
  status: "located",
  fix: { latitude: 14.6537, longitude: 121.0584, accuracy: 12, at: Date.now() },
};

const setup = (props: Partial<React.ComponentProps<typeof NewSiteForm>> = {}) => {
  const onCreated = vi.fn();
  const onCancel = vi.fn();
  render(
    <NewSiteForm takenCodes={["PBIS", "PPPC"]} onCreated={onCreated} onCancel={onCancel} {...props} />,
  );
  return { onCreated, onCancel };
};

const codeBox = () => screen.getByLabelText(/site code/i);
const saveBtn = () => screen.getByRole("button", { name: /save site/i });

beforeEach(() => {
  vi.clearAllMocks();
  locationResult.mockReturnValue(goodFix);
});

describe("it does not pretend to create a station", () => {
  it("says the site is recorded for review", () => {
    setup();
    expect(screen.queryByText(/does not add it to the national inventory/i)).not.toBeNull();
  });

  it("promises the observer can file a sheet against it immediately", () => {
    // This is the claim the whole offline design exists to make good on, so it
    // must not be made unless it is true — see the queue tests.
    setup();
    expect(screen.queryByText(/file a sheet against it straight away/i)).not.toBeNull();
  });
});

describe("the duplicate guard an offline handset can actually reach", () => {
  it("refuses a code already in the list", async () => {
    setup();
    await userEvent.type(codeBox(), "PBIS");
    expect(screen.queryByText(/PBIS is already in use/)).not.toBeNull();
    expect(saveBtn()).toBeDisabled();
  });

  it("compares case-insensitively, as the server does", async () => {
    // The endpoint upper-cases before checking, and the whole point of its
    // guard is that `pbis` and `PBIS` collide rather than becoming two
    // stations. A phone keyboard capitalises inconsistently.
    setup();
    await userEvent.type(codeBox(), "pbis");
    expect(screen.queryByText(/PBIS is already in use/)).not.toBeNull();
  });

  it("allows a code that is free", async () => {
    setup();
    await userEvent.type(codeBox(), "NEWA");
    expect(screen.queryByText(/already in use/)).toBeNull();
    expect(saveBtn()).not.toBeDisabled();
  });

  it("will not save without a code", () => {
    setup();
    expect(saveBtn()).toBeDisabled();
  });
});

describe("the position", () => {
  it("states what will be recorded, with its accuracy", () => {
    setup();
    expect(screen.queryByText(/14\.65370, 121\.05840/)).not.toBeNull();
  });

  it("sends the captured fix rather than anything typed", async () => {
    const { onCreated } = setup();
    await userEvent.type(codeBox(), "NEWA");
    await userEvent.click(saveBtn());
    expect(onCreated).toHaveBeenCalledWith(
      expect.objectContaining({ latitude: 14.6537, longitude: 121.0584 }),
    );
  });

  it("warns that a coarse fix cannot identify a monument, and still saves", async () => {
    locationResult.mockReturnValue({
      status: "located",
      fix: { latitude: 14.65, longitude: 121.05, accuracy: 4_000, at: Date.now() },
    });
    const { onCreated } = setup();
    expect(screen.queryByText(/too coarse to identify a monument/i)).not.toBeNull();
    await userEvent.type(codeBox(), "NEWA");
    await userEvent.click(saveBtn());
    expect(onCreated).toHaveBeenCalled();
  });

  it("records the accuracy in the notes, where a reconciler will see it", async () => {
    // There is no column for it, and someone deciding whether to promote this
    // needs to know the coordinate came from a 4 km cell fix.
    locationResult.mockReturnValue({
      status: "located",
      fix: { latitude: 14.65, longitude: 121.05, accuracy: 4_000, at: Date.now() },
    });
    const { onCreated } = setup();
    await userEvent.type(codeBox(), "NEWA");
    await userEvent.click(saveBtn());
    expect(onCreated.mock.calls[0][0].notes).toMatch(/Fix accuracy/);
  });

  it("saves with no position at all rather than refusing", async () => {
    // A site under canopy is still a site. Refusing would send the observer
    // home with nothing, which is the failure this form exists to end.
    locationResult.mockReturnValue({ status: "denied" });
    const { onCreated } = setup();
    expect(screen.queryByText(/location permission is off/i)).not.toBeNull();
    await userEvent.type(codeBox(), "NEWA");
    await userEvent.click(saveBtn());
    expect(onCreated).toHaveBeenCalledWith(
      expect.objectContaining({ latitude: null, longitude: null }),
    );
    expect(onCreated.mock.calls[0][0].notes).toMatch(/No position fix/);
  });
});

describe("what reaches the queue", () => {
  it("normalises the code to capitals, as the server will", async () => {
    const { onCreated } = setup();
    await userEvent.type(codeBox(), "  newa  ");
    await userEvent.click(saveBtn());
    expect(onCreated.mock.calls[0][0].station_code).toBe("NEWA");
  });

  it("mints a client_uuid", async () => {
    // The idempotency key. Without it a retried sync creates a second site.
    const { onCreated } = setup();
    await userEvent.type(codeBox(), "NEWA");
    await userEvent.click(saveBtn());
    expect(onCreated.mock.calls[0][0].client_uuid).toMatch(/^[0-9a-f-]{36}$/i);
  });

  it("sends blank optional fields as null, not empty strings", async () => {
    const { onCreated } = setup();
    await userEvent.type(codeBox(), "NEWA");
    await userEvent.click(saveBtn());
    const sent = onCreated.mock.calls[0][0];
    expect(sent.name).toBeNull();
    expect(sent.municipality).toBeNull();
    expect(sent.province).toBeNull();
  });
});
