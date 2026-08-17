import { describe, it, expect } from "vitest";
import { roleLabel, groupByRole, ROLE_LABEL } from "./roles";

/**
 * Roles are stored as `field_staff` / `data_processor` / `admin` and shown as
 * the names PHIVOLCS actually uses. The mapping is display-only on purpose:
 * the stored values are referenced by the seeder, its validation gate, the API
 * and staff.csv, so renaming them would be a migration across all four.
 */

describe("roleLabel", () => {
  it("uses the names people use, not the schema's", () => {
    expect(roleLabel("field_staff")).toBe("Technical");
    expect(roleLabel("data_processor")).toBe("Processing");
    expect(roleLabel("admin")).toBe("Admin");
  });

  it("falls back to the raw value for a role the database grows later", () => {
    // Better an odd heading than a person missing from the observer list.
    expect(roleLabel("surveyor")).toBe("surveyor");
  });

  it("names the absence rather than rendering blank", () => {
    expect(roleLabel(null)).toBe("Unassigned");
    expect(roleLabel(undefined)).toBe("Unassigned");
    expect(roleLabel("")).toBe("Unassigned");
  });

  it("maps exactly the three seeded roles", () => {
    expect(Object.keys(ROLE_LABEL).sort()).toEqual([
      "admin",
      "data_processor",
      "field_staff",
    ]);
  });
});

describe("groupByRole", () => {
  const people = [
    { id: 1, initials: "CJVC", role: "data_processor" },
    { id: 2, initials: "ARP", role: "admin" },
    { id: 3, initials: "MDL", role: "field_staff" },
    { id: 4, initials: "RSB", role: "field_staff" },
  ];

  it("puts Technical first — the largest group and the usual pick", () => {
    const groups = groupByRole(people);
    expect(groups.map((g) => g.role)).toEqual([
      "field_staff",
      "data_processor",
      "admin",
    ]);
  });

  it("labels each group for display", () => {
    expect(groupByRole(people).map((g) => g.label)).toEqual([
      "Technical",
      "Processing",
      "Admin",
    ]);
  });

  it("keeps every person, in their own group", () => {
    const groups = groupByRole(people);
    expect(groups.flatMap((g) => g.members.map((m) => m.initials)).sort()).toEqual([
      "ARP",
      "CJVC",
      "MDL",
      "RSB",
    ]);
    expect(groups.find((g) => g.role === "field_staff")!.members).toHaveLength(2);
  });

  it("drops groups nobody is in, rather than showing empty headings", () => {
    const groups = groupByRole([{ id: 1, initials: "ARP", role: "admin" }]);
    expect(groups).toHaveLength(1);
    expect(groups[0].role).toBe("admin");
  });

  it("keeps an unrecognised role instead of silently omitting the person", () => {
    // A person missing from the observer list is a sheet that cannot record
    // who was present — worse than an unfamiliar heading.
    const groups = groupByRole([
      ...people,
      { id: 5, initials: "XYZ", role: "surveyor" },
    ]);
    const extra = groups.find((g) => g.role === "surveyor");
    expect(extra).toBeDefined();
    expect(extra!.label).toBe("surveyor");
    expect(extra!.members).toHaveLength(1);
  });

  it("puts unknown roles after the known ones", () => {
    const groups = groupByRole([
      { id: 5, initials: "XYZ", role: "surveyor" },
      { id: 3, initials: "MDL", role: "field_staff" },
    ]);
    expect(groups.map((g) => g.role)).toEqual(["field_staff", "surveyor"]);
  });

  it("returns nothing for nobody", () => {
    expect(groupByRole([])).toEqual([]);
  });
});
