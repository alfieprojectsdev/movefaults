import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useForm } from "react-hook-form";
import FormSection from "./FormSection";

/**
 * The claim that matters here is not "it opens and closes".
 *
 * It is that collapsing a section does not change what the form validates.
 * react-hook-form keeps an unmounted field's rules by default, so a required
 * field inside an UNMOUNTED section stays required while its error renders
 * into markup nobody can see — handleSubmit refuses, onSubmit never runs, and
 * the operator taps Submit and watches nothing happen. That defect has already
 * shipped once in this form, in continuous mode.
 *
 * Native <details> is the defence: a closed one keeps its children in the DOM.
 * These tests assert that property directly, because it is the only reason
 * this component is allowed to exist.
 */

function Harness({ hiddenRequired = true }: { hiddenRequired?: boolean }) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<{ visible: string; buried: string }>();
  const onSubmit = vi.fn();

  return (
    <form onSubmit={handleSubmit((v) => onSubmit(v))}>
      <label>
        Visible
        <input {...register("visible")} />
      </label>
      <FormSection
        title="Extra detail"
        summary="nothing recorded"
        forceOpen={!!errors.buried}
      >
        <label>
          Buried
          <input {...register("buried", { required: hiddenRequired })} />
        </label>
        {errors.buried && <span role="alert">Buried is required</span>}
      </FormSection>
      <button type="submit">Submit</button>
    </form>
  );
}

describe("a collapsed section is hidden, not unmounted", () => {
  it("keeps its fields in the DOM while closed", () => {
    render(<Harness />);
    const details = document.querySelector("details") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    // The assertion the whole design rests on.
    expect(screen.queryByLabelText("Buried")).not.toBeNull();
  });

  it("still registers a closed field's value on submit", async () => {
    render(<Harness hiddenRequired={false} />);
    const details = document.querySelector("details") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    // Closed, but reachable and writable — which is what "not unmounted" buys.
    await userEvent.type(screen.getByLabelText("Buried"), "recorded");
    expect((screen.getByLabelText("Buried") as HTMLInputElement).value).toBe("recorded");
  });
});

describe("a section holding an error opens itself", () => {
  it("reveals the reason Submit did nothing", async () => {
    render(<Harness />);
    const details = document.querySelector("details") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    expect(screen.queryByRole("alert")).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: "Submit" }));

    // Without forceOpen this error exists and is invisible, which reads to the
    // operator as a dead button.
    expect(await screen.findByRole("alert")).not.toBeNull();
    expect(details.open).toBe(true);
  });
});

describe("the summary", () => {
  it("states what is inside while collapsed", () => {
    render(<Harness />);
    expect(screen.queryByText("nothing recorded")).not.toBeNull();
  });

  it("is hidden from assistive tech once the content it describes is visible", async () => {
    render(<Harness hiddenRequired={false} />);
    await userEvent.click(screen.getByText("Extra detail"));
    const summary = screen.getByText("nothing recorded");
    // Still in the DOM (CSS hides it visually); marked hidden so a screen
    // reader does not announce a précis immediately before the full content.
    expect(summary.getAttribute("aria-hidden")).toBe("true");
  });
});

describe("a force-opened summary stays announced", () => {
  it("keeps the summary in the accessibility tree when the section opened itself", async () => {
    // The distinction the earlier version got wrong. Suppressing the précis is
    // right when the OPERATOR opened the section: they are about to hear the
    // same information in full. A section that opened ITSELF did so because
    // something inside blocks submission, and the summary is then a statement
    // of the blocker rather than a duplicate of the content.
    //
    // In the real form `required — none attached` fires on an untouched sheet,
    // where the in-content message that would otherwise carry it is suppressed
    // by isDirty. So `aria-hidden={open || forceOpen}` removed the reason from
    // the accessibility tree at precisely the moment it existed: alert styling
    // and text for a sighted observer, an open section and silence for a
    // screen-reader user.
    //
    // Found by gps3 in review of #224.
    render(<Harness />);
    const summary = screen.getByText("nothing recorded");
    expect(summary.getAttribute("aria-hidden")).toBe("false");

    await userEvent.click(screen.getByRole("button", { name: "Submit" }));

    const details = document.querySelector("details") as HTMLDetailsElement;
    expect(details.open).toBe(true);
    expect(summary.getAttribute("aria-hidden")).toBe("false");
  });
});

describe("open state tracks the browser's own toggle", () => {
  it("keeps the component's own notion of open in step with the DOM", async () => {
    // What this is really about, having been checked by mutation rather than
    // assumed: removing the onToggle handler does NOT make the section snap
    // shut. React compares against its previous vdom value, sees `open` is
    // still false, and never writes the attribute — so the browser's own
    // toggle survives, and a test asserting "it stays open" passes with the
    // sync deleted. That test would have been decoration.
    //
    // What actually breaks is agreement: the DOM is open, the component still
    // believes it is closed, and every decision keyed on that belief is wrong.
    // aria-hidden on the summary is the observable one — the précis stays
    // announced to a screen reader while the full content it summarises is on
    // screen — so that is what this asserts.
    render(<Harness hiddenRequired={false} />);
    const details = document.querySelector("details") as HTMLDetailsElement;
    const summary = screen.getByText("nothing recorded");

    expect(details.open).toBe(false);
    expect(summary.getAttribute("aria-hidden")).toBe("false");

    await userEvent.click(screen.getByText("Extra detail"));
    expect(details.open).toBe(true);
    expect(summary.getAttribute("aria-hidden")).toBe("true");

    // And it survives an unrelated re-render.
    await userEvent.type(screen.getByLabelText("Buried"), "x");
    expect(details.open).toBe(true);
    expect(summary.getAttribute("aria-hidden")).toBe("true");
  });
});
