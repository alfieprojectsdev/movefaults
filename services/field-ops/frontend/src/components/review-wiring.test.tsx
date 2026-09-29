import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import LogSheetForm from "./LogSheetForm";
import { submitLogSheet } from "../services/api";

/**
 * The wiring between the form and the check-before-sending step: that a
 * submit with something to flag shows the panel INSTEAD of sending, and sends
 * only after "Send anyway". The rules and the panel are tested on their own
 * (utils/review.test.ts, send-review.test.tsx); without this, the form could
 * stop calling them and every one of those tests would still pass.
 *
 * The submit button is disabled without a photo, and jsdom can't supply one,
 * so the form is submitted directly. The check under test runs inside the
 * submit handler, so it is reached either way.
 */

vi.mock("../services/api", () => ({
  fetchStaff: vi.fn().mockResolvedValue([]),
  submitLogSheet: vi.fn().mockResolvedValue([{ id: 1 }]),
  uploadLogSheetPhoto: vi.fn(),
}));

vi.mock("../hooks/useOfflineQueue", () => ({
  useOfflineQueue: () => ({ addToQueue: vi.fn(), pendingCount: 0, flushQueue: vi.fn() }),
}));

vi.mock("./StationPicker", () => ({ default: () => <div data-testid="station-picker" /> }));

const renderForm = () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LogSheetForm stationRequest={{ code: "PTAG", nonce: 1 }} />
    </QueryClientProvider>
  );
};

const fillRequired = async () => {
  const user = userEvent.setup();
  await user.selectOptions(screen.getByLabelText(/monitoring method/i), "continuous");
  await user.type(screen.getByLabelText(/arrival time/i), "09:15");
  await user.selectOptions(screen.getByLabelText(/equipment status/i), "ok");
  return user;
};

const submitForm = () => fireEvent.submit(document.querySelector("form")!);

beforeEach(() => vi.clearAllMocks());

describe("check before sending, in the form", () => {
  it("shows the panel instead of sending when something expected is blank", async () => {
    renderForm();
    await fillRequired();
    submitForm();
    expect(await screen.findByText(/check before sending/i)).toBeInTheDocument();
    // Scoped to the panel: "Departure time" is also the form field's own label.
    expect(within(screen.getByRole("alertdialog")).getByText("Departure time")).toBeInTheDocument();
    expect(submitLogSheet).not.toHaveBeenCalled();
  });

  it("sends after Send anyway", async () => {
    renderForm();
    const user = await fillRequired();
    submitForm();
    await user.click(await screen.findByRole("button", { name: /send anyway/i }));
    await vi.waitFor(() => expect(submitLogSheet).toHaveBeenCalledTimes(1));
  });

  it("returns to the form on Go back, without sending", async () => {
    renderForm();
    const user = await fillRequired();
    submitForm();
    await user.click(await screen.findByRole("button", { name: /go back/i }));
    expect(screen.queryByText(/check before sending/i)).toBeNull();
    expect(submitLogSheet).not.toHaveBeenCalled();
  });

  it("checks again after a Send anyway that failed validation (review of #261)", async () => {
    // Send anyway arms a one-shot pass, but handleSubmit validates BEFORE
    // onSubmit, which is where the pass is spent. If validation fails, the pass
    // stayed armed, and a later ordinary Submit skipped the check entirely.
    renderForm();
    const user = await fillRequired();
    submitForm();
    await screen.findByText(/check before sending/i);
    await user.clear(screen.getByLabelText(/arrival time/i)); // now invalid
    await user.click(screen.getByRole("button", { name: /send anyway/i }));
    await user.click(screen.getByRole("button", { name: /go back/i }));
    await user.type(screen.getByLabelText(/arrival time/i), "09:15"); // repaired
    submitForm();
    expect(await screen.findByText(/check before sending/i)).toBeInTheDocument();
    expect(submitLogSheet).not.toHaveBeenCalled();
  });

  it("disarms a failed Send anyway even if Go back is never pressed", async () => {
    // Pins the invalid-submit handler on its own: here nothing else clears the
    // pass, so without the handler the next submit would skip the check.
    renderForm();
    const user = await fillRequired();
    submitForm();
    await screen.findByText(/check before sending/i);
    await user.clear(screen.getByLabelText(/arrival time/i));
    await user.click(screen.getByRole("button", { name: /send anyway/i }));
    await user.type(screen.getByLabelText(/arrival time/i), "09:15");
    submitForm(); // any submit that doesn't go through the panel's buttons
    await screen.findByText(/check before sending/i);
    expect(submitLogSheet).not.toHaveBeenCalled();
  });
});
