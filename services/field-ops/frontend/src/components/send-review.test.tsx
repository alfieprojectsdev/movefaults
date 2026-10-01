import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SendReview from "./SendReview";

const items = [
  { field: "departure_time", label: "Departure time", level: "blank" as const },
  { field: "bubble_centred", label: "Bubble centred is not ticked", level: "confirm" as const },
];

describe("the check-before-sending panel", () => {
  it("lists blank and second-look items under separate headings", () => {
    render(<SendReview items={items} onSend={vi.fn()} onBack={vi.fn()} />);
    expect(screen.getByText("Left blank:")).toBeInTheDocument();
    expect(screen.getByText("Departure time")).toBeInTheDocument();
    expect(screen.getByText("Worth a second look:")).toBeInTheDocument();
    expect(screen.getByText("Bubble centred is not ticked")).toBeInTheDocument();
  });

  it("omits a heading with nothing under it", () => {
    render(<SendReview items={[items[0]]} onSend={vi.fn()} onBack={vi.fn()} />);
    expect(screen.queryByText("Worth a second look:")).toBeNull();
  });

  it("sends only on Send anyway, and goes back only on Go back", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    const onBack = vi.fn();
    render(<SendReview items={items} onSend={onSend} onBack={onBack} />);
    await user.click(screen.getByRole("button", { name: /go back/i }));
    expect(onBack).toHaveBeenCalledTimes(1);
    expect(onSend).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: /send anyway/i }));
    expect(onSend).toHaveBeenCalledTimes(1);
  });

  it("disables both buttons while a send is in flight, so it can't be sent twice", () => {
    render(<SendReview items={items} onSend={vi.fn()} onBack={vi.fn()} sending />);
    for (const b of screen.getAllByRole("button")) expect(b).toBeDisabled();
  });
});
