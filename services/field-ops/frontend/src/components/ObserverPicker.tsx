/**
 * Who was present, as a grid of initials.
 *
 * Design handoff `Field Ops Alternatives.dc.html`, option 1g.
 *
 * WHAT WAS WRONG WITH THE LIST
 *
 * Thirteen 48 px rows inside `max-height: 15rem; overflow-y: auto` — a scroll
 * region inside a scrolling page, on a phone. A thumb-flick either moves the
 * inner box or the whole form depending on where it lands, and seven of the
 * thirteen names are never on screen. The observer field is in the part of the
 * sheet that does not collapse, because it says which visit this is, so it
 * cannot be folded away either.
 *
 * WHY THE GRID AND NOT THE FLAT LIST
 *
 * 1f — flat, recency-ordered — kills the nested scroll by becoming page flow,
 * and the handoff names its own cost: "adds ~13 × 48 px to a form already too
 * long — pairs badly with 1b". 1b is the collapsible sections, which shipped
 * an hour before this did. Six hundred pixels of permanently visible list
 * above five sections that exist to shorten the form is the two changes
 * cancelling out.
 *
 * The grid fits all thirteen in roughly a third of the height with no scroll
 * at any phone size, and the interaction is two or three taps.
 *
 * WHAT THE GRID COSTS, AND WHAT PAYS IT BACK
 *
 * The handoff is straight about it: initials alone are the least legible
 * option for anyone new, and a tile has nowhere to put a role.
 *
 * Both are answered below the grid rather than on it. Every selected person is
 * restated in full underneath, with their role — so the sheet never depends on
 * recognising a monogram, and the role information the grouped list carried is
 * still on screen for exactly the people it now matters for. A tile's
 * accessible name is the full name and role, not the initials, so a screen
 * reader never has to read a monogram at all.
 *
 * Order is still ROLE_ORDER — Technical, Processing, Admin — so the grid is
 * not arbitrary even without headings, and the group a field team picks from
 * most is first.
 */

import type { Staff } from "../services/api";
import { groupByRole, roleLabel } from "../utils/roles";

interface Props {
  staff: Staff[] | undefined;
  loading: boolean;
  selectedIds: number[];
  onChange: (ids: number[]) => void;
}

export default function ObserverPicker({ staff, loading, selectedIds, onChange }: Props) {
  if (loading) {
    return (
      <fieldset className="observer-field">
        <legend>Observers</legend>
        <p className="hint">Loading staff…</p>
      </fieldset>
    );
  }

  if (!staff || staff.length === 0) {
    return (
      <fieldset className="observer-field">
        <legend>Observers</legend>
        <p className="hint">Staff unavailable (offline?)</p>
      </fieldset>
    );
  }

  // Flattened, but still in ROLE_ORDER. groupByRole also keeps anyone with an
  // unrecognised role rather than dropping them, which matters more here than
  // it did with headings: a person missing from this grid is a sheet that
  // cannot record who was present.
  const ordered = groupByRole(staff).flatMap((g) => g.members);
  const selected = ordered.filter((s) => selectedIds.includes(s.id));

  const toggle = (id: number, checked: boolean) => {
    // Rebuilt from the current array rather than toggled in place, so the
    // stored order stays stable and a double tap cannot leave a duplicate.
    onChange(checked ? [...selectedIds, id] : selectedIds.filter((x) => x !== id));
  };

  return (
    <fieldset className="observer-field">
      <legend>Observers</legend>

      <div className="observer-head">
        <span>Who was present?</span>
        <span className="observer-count">
          {selectedIds.length} of {staff.length}
        </span>
      </div>

      <div className="observer-grid">
        {ordered.map((s) => {
          const checked = selectedIds.includes(s.id);
          return (
            <label key={s.id} className={`observer-tile${checked ? " is-selected" : ""}`}>
              <input
                type="checkbox"
                className="sr-only"
                checked={checked}
                onChange={(e) => toggle(s.id, e.target.checked)}
                // The accessible name is the full name and role, never the
                // monogram. A screen-reader user gets the legible version of
                // this control; the tile is the compact version of the same
                // thing, not a lesser one.
                aria-label={`${s.full_name}, ${roleLabel(s.role)}`}
              />
              <span aria-hidden="true">{s.initials}</span>
            </label>
          );
        })}
      </div>

      {/* The grid's own cost, paid here. Initials are how the paper sheet and
          staff.csv already refer to people, so they are the right thing to
          tap; they are not the right thing for the record to rest on. */}
      {selected.length > 0 ? (
        <p className="observer-selected">
          {selected.map((s) => `${s.full_name} (${roleLabel(s.role)})`).join(", ")}
        </p>
      ) : (
        <small>Tap everyone who was present — more than one is normal.</small>
      )}
    </fieldset>
  );
}
