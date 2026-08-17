/**
 * How roles are named to the people using this app.
 *
 * The stored values (`field_staff`, `data_processor`, `admin`) stay as they
 * are: they are referenced by the seeder, by its validation gate, by the API
 * and by staff.csv, and renaming them would be a migration touching all four
 * for no gain. What changes is only what an observer reads on screen.
 *
 * "Technical" and "Processing" are what these groups are actually called at
 * PHIVOLCS. A picker that says `data_processor` is showing its schema to
 * someone who just wants to tick the two colleagues who were with them.
 */

export const ROLE_LABEL: Record<string, string> = {
  field_staff: "Technical",
  data_processor: "Processing",
  admin: "Admin",
};

/**
 * Display order for grouped lists.
 *
 * Technical first because it is the largest group and the one a field team is
 * most often picking from — the common case should not require a scroll.
 */
export const ROLE_ORDER = ["field_staff", "data_processor", "admin"] as const;

/** A role's label, falling back to the raw value if the database grows a new one. */
export function roleLabel(role: string | null | undefined): string {
  if (!role) return "Unassigned";
  return ROLE_LABEL[role] ?? role;
}

/**
 * Group people by role, in display order, dropping empty groups.
 *
 * Anything with an unrecognised role is kept and shown under its raw name
 * rather than silently omitted — a person missing from the observer list is a
 * sheet that cannot record who was present, which is worse than an odd
 * heading.
 */
export function groupByRole<T extends { role: string }>(
  people: T[]
): Array<{ role: string; label: string; members: T[] }> {
  const seen = new Set<string>();
  const ordered: string[] = [];

  for (const role of ROLE_ORDER) {
    if (people.some((p) => p.role === role)) {
      ordered.push(role);
      seen.add(role);
    }
  }
  for (const p of people) {
    if (!seen.has(p.role)) {
      ordered.push(p.role);
      seen.add(p.role);
    }
  }

  return ordered.map((role) => ({
    role,
    label: roleLabel(role),
    members: people.filter((p) => p.role === role),
  }));
}
