import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ObserverPicker from "./ObserverPicker";
import type { Staff } from "../services/api";

/**
 * The grid trades legibility for height, and these are the tests that say the
 * trade was actually paid rather than just taken.
 *
 * A tile shows a monogram. Nothing in the record may depend on someone
 * recognising one: the accessible name is the full name and role, and every
 * selected person is restated in full underneath. Those two are what make
 * initials an acceptable thing to tap, so they are what is asserted hardest.
 *
 * The other claim worth locking down is that nobody can fall out of the grid.
 * A person missing from this control is a sheet that cannot record who was
 * present, and the previous version's scroll region already hid seven of
 * thirteen names behind a fold.
 */

const staff = (over: Partial<Staff> = {}): Staff => ({
  id: 1,
  full_name: "R. J. Mendoza",
  initials: "RJM",
  role: "field_staff",
  ...over,
});

const thirteen: Staff[] = [
  staff({ id: 1, full_name: "R. J. Mendoza", initials: "RJM" }),
  staff({ id: 2, full_name: "A. B. Bautista", initials: "ABB" }),
  staff({ id: 3, full_name: "C. D. Cruz", initials: "CDC" }),
  staff({ id: 4, full_name: "P. P. Garcia", initials: "PPG" }),
  staff({ id: 5, full_name: "J. L. Santos", initials: "JLS" }),
  staff({ id: 6, full_name: "M. T. Villanueva", initials: "MTV" }),
  staff({ id: 7, full_name: "R. S. Aquino", initials: "RSA" }),
  staff({ id: 8, full_name: "D. B. Quinto", initials: "DBQ" }),
  staff({ id: 9, full_name: "L. M. Flores", initials: "LMF" }),
  staff({ id: 10, full_name: "A. G. Tolentino", initials: "AGT" }),
  staff({ id: 11, full_name: "E. R. Perez", initials: "ERPE", role: "data_processor" }),
  staff({ id: 12, full_name: "V. H. Castro", initials: "VHC", role: "data_processor" }),
  staff({ id: 13, full_name: "N. J. Tamayo", initials: "NJTM", role: "admin" }),
];

const setup = (props: Partial<React.ComponentProps<typeof ObserverPicker>> = {}) => {
  const onChange = vi.fn();
  render(
    <ObserverPicker
      staff={thirteen}
      loading={false}
      selectedIds={[]}
      onChange={onChange}
      {...props}
    />,
  );
  return { onChange };
};

describe("nobody falls out of the grid", () => {
  it("renders every member of staff", () => {
    setup();
    // The previous control was a 15rem scroll region holding thirteen 48px
    // rows: seven names were below the fold and the box scrolled inside a
    // scrolling page. A person who is not on screen cannot be ticked.
    expect(screen.getAllByRole("checkbox")).toHaveLength(13);
  });

  it("keeps someone whose role the app does not recognise", () => {
    setup({ staff: [...thirteen, staff({ id: 14, full_name: "X. Y. Reyes", initials: "XYR", role: "seismologist" })] });
    // A missing person is a sheet that cannot say who was there, which is
    // worse than an unfamiliar role label.
    expect(screen.queryByRole("checkbox", { name: /X\. Y\. Reyes/ })).not.toBeNull();
    expect(screen.getAllByRole("checkbox")).toHaveLength(14);
  });

  it("counts against the real total", () => {
    setup({ selectedIds: [1, 2, 11] });
    expect(screen.queryByText("3 of 13")).not.toBeNull();
  });
});

describe("the monogram is never what the record rests on", () => {
  it("names a tile by full name and role, not by initials", () => {
    setup();
    // This is the handoff's stated cost — "initials-only is the least legible
    // option for anyone new" — paid for assistive technology outright: a
    // screen reader never has to read a monogram.
    expect(screen.queryByRole("checkbox", { name: "R. J. Mendoza, Technical" })).not.toBeNull();
    expect(screen.queryByRole("checkbox", { name: "E. R. Perez, Processing" })).not.toBeNull();
    expect(screen.queryByRole("checkbox", { name: "N. J. Tamayo, Admin" })).not.toBeNull();
  });

  it("restates every selected person in full, with their role", () => {
    setup({ selectedIds: [1, 11] });
    // The other half of the payment, for everyone else. Role also survives
    // here, which is what the grouped list carried and a tile has no room for.
    expect(
      screen.queryByText("R. J. Mendoza (Technical), E. R. Perez (Processing)"),
    ).not.toBeNull();
  });

  it("stays unambiguous when two people share initials", () => {
    // Initials are the username scheme, so collisions should not happen — but
    // "should not" is not "cannot", and the failure would be silent: two
    // identical tiles and no way to tell which was ticked.
    setup({
      staff: [staff({ id: 1, full_name: "R. J. Mendoza", initials: "RJM" }),
              staff({ id: 2, full_name: "R. J. Marquez", initials: "RJM" })],
      selectedIds: [2],
    });
    expect(screen.queryByRole("checkbox", { name: "R. J. Mendoza, Technical" })).not.toBeNull();
    expect(screen.queryByRole("checkbox", { name: "R. J. Marquez, Technical" })).not.toBeNull();
    expect(screen.queryByText("R. J. Marquez (Technical)")).not.toBeNull();
  });

  it("prompts rather than showing an empty line when nobody is ticked", () => {
    setup();
    expect(screen.queryByText(/more than one is normal/)).not.toBeNull();
  });
});

describe("order is not arbitrary without headings", () => {
  it("puts Technical before Processing before Admin, whatever order they arrive in", () => {
    // Deliberately scrambled relative to ROLE_ORDER. The first version of this
    // test fed it `thirteen`, which is already grouped, so replacing the sort
    // with `const ordered = staff` passed it — an assertion with no failing
    // input, which is the third time that shape has turned up in this
    // project's tests this week.
    //
    // The endpoint makes no ordering promise, so arrival order is exactly what
    // must not be trusted.
    setup({
      staff: [
        staff({ id: 13, full_name: "N. J. Tamayo", initials: "NJTM", role: "admin" }),
        staff({ id: 11, full_name: "E. R. Perez", initials: "ERPE", role: "data_processor" }),
        staff({ id: 1, full_name: "R. J. Mendoza", initials: "RJM" }),
        staff({ id: 12, full_name: "V. H. Castro", initials: "VHC", role: "data_processor" }),
        staff({ id: 2, full_name: "A. B. Bautista", initials: "ABB" }),
      ],
    });
    const names = screen.getAllByRole("checkbox").map((c) => c.getAttribute("aria-label"));
    expect(names).toEqual([
      // Technical first: the group a field team picks from most often.
      "R. J. Mendoza, Technical",
      "A. B. Bautista, Technical",
      "E. R. Perez, Processing",
      "V. H. Castro, Processing",
      "N. J. Tamayo, Admin",
    ]);
  });
});

describe("selection", () => {
  it("adds an id when a tile is tapped", async () => {
    const { onChange } = setup({ selectedIds: [1] });
    await userEvent.click(screen.getByRole("checkbox", { name: "A. B. Bautista, Technical" }));
    expect(onChange).toHaveBeenCalledWith([1, 2]);
  });

  it("removes an id when a selected tile is tapped", async () => {
    const { onChange } = setup({ selectedIds: [1, 2] });
    await userEvent.click(screen.getByRole("checkbox", { name: "R. J. Mendoza, Technical" }));
    expect(onChange).toHaveBeenCalledWith([2]);
  });

  it("cannot produce a duplicate id", async () => {
    // Rebuilt from the array rather than toggled in place. A duplicate would
    // reach the server as the same observer recorded twice on one sheet.
    const { onChange } = setup({ selectedIds: [2] });
    await userEvent.click(screen.getByRole("checkbox", { name: "A. B. Bautista, Technical" }));
    expect(onChange).toHaveBeenCalledWith([]);
  });
});

describe("states where there is no grid to show", () => {
  it("says it is loading", () => {
    setup({ loading: true, staff: undefined });
    expect(screen.queryByText(/loading staff/i)).not.toBeNull();
    expect(screen.queryAllByRole("checkbox")).toHaveLength(0);
  });

  it("says staff are unavailable rather than showing an empty grid", () => {
    setup({ staff: [] });
    expect(screen.queryByText(/staff unavailable/i)).not.toBeNull();
  });
});
