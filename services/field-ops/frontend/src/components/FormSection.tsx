/**
 * A collapsible section of the log sheet.
 *
 * Design handoff `Field Ops Alternatives.dc.html`, option 1b.
 *
 * WHY COLLAPSE AT ALL
 *
 * The sheet is 1,200+ lines of form. On a phone that is a column of inputs
 * long enough that an observer scrolling to the photo field at the bottom has
 * no idea what they have already answered, and no way to check without losing
 * their place. The paper form solved this with physical layout — you can see a
 * whole page at once. A phone cannot, so it has to solve it with structure.
 *
 * THE RULE THAT MAKES COLLAPSING SAFE
 *
 * A collapsed section is HIDDEN, NEVER UNMOUNTED.
 *
 * This is not a performance preference. react-hook-form keeps the validation
 * rules of an unmounted field by default (`shouldUnregister` is false), so a
 * required field inside an unmounted section stays required and fails
 * validation — while its error message renders into markup nobody can see.
 * `handleSubmit` then refuses, `onSubmit` never runs, and the operator taps
 * Submit and watches the app do nothing at all.
 *
 * That is not hypothetical. It is the exact defect that made continuous-mode
 * Submit a dead button, found by reading the diff of an earlier PR, and it is
 * the reason this component uses native <details>: a closed <details> keeps
 * its children in the DOM. There is no "keep mounted" flag to forget.
 *
 * AND THE SECOND HALF OF THE RULE
 *
 * A section holding an error opens itself. Hiding the field is survivable
 * because the field still validates; hiding the *reason the form will not
 * submit* is not. `forceOpen` is how the parent says so, and it wins over the
 * operator's own collapse — being returned to a section you closed is
 * annoying, and being unable to find out why Submit does nothing is the bug
 * above wearing a different coat.
 *
 * WHY A SUMMARY IS REQUIRED, NOT OPTIONAL
 *
 * A collapsed section that says only its name has hidden information rather
 * than organised it. The observer now has to open all six to answer "what have
 * I not filled in". `summary` is what makes the closed state worth having: it
 * states what is inside, so the closed form is still readable as a whole.
 */

import { useState, type ReactNode } from "react";

interface Props {
  title: string;
  /**
   * What is inside, in a few words, shown when collapsed.
   *
   * Say the state, not the field names: "12.6 V, solar OK" rather than
   * "voltage, notes". An observer reads this to decide whether to open the
   * section, and field names do not answer that question.
   */
  summary: ReactNode;
  /** Open on first render. Sections holding required fields should be. */
  defaultOpen?: boolean;
  /**
   * Open regardless of what the operator chose, because something inside needs
   * to be seen — an unmet requirement, almost always.
   */
  forceOpen?: boolean;
  children: ReactNode;
}

export default function FormSection({
  title,
  summary,
  defaultOpen = false,
  forceOpen = false,
  children,
}: Props) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <details
      className={`form-section${forceOpen ? " form-section-alert" : ""}`}
      open={open || forceOpen}
      // Without this the browser's own toggle and our state drift apart: the
      // arrow turns, the content shows, and `open` still says false, so the
      // next render snaps it shut under the operator's thumb.
      onToggle={(e) => setOpen((e.currentTarget as HTMLDetailsElement).open)}
    >
      <summary>
        <span className="form-section-title">{title}</span>
        {/* Hidden from the accessibility tree once the OPERATOR has opened the
            section: the précis would otherwise be read out immediately before
            the same information in full.

            Keyed on `open && !forceOpen`, NOT on `open || forceOpen`, and
            NOT on `open` alone — that middle attempt does not work, for a
            reason worth writing down: opening the element fires `toggle`
            whatever caused it, so the onToggle handler below sets `open` to
            true when forceOpen opens the section. State converges on the DOM
            by design, so `open` cannot distinguish who opened it. Only the
            explicit `!forceOpen` can.

            A force-opened section was opened because something inside it
            blocks submission, and for that case the summary is not a
            duplicate — it is a statement of the blocker, sometimes the only
            one. `required — none attached` fires on an untouched form, where
            the in-content message that would otherwise carry it is suppressed
            by `isDirty`. So the earlier version removed the reason from the
            accessibility tree at the exact moment it existed: a sighted
            observer got alert styling and text, a screen-reader user got an
            open section and silence.

            The other three triggers do have ungated in-content messages
            today, so they would read the reason twice rather than not at all.
            That is the right way round, and it is also why this is keyed on
            `open` rather than audited trigger by trigger — the safety of the
            old version depended on every forceOpen having an unconditional
            announcement inside it, which nothing enforced and which the photo
            case already broke.

            Found by gps3 in review of #224. */}
        <span className="form-section-summary" aria-hidden={open && !forceOpen}>
          {summary}
        </span>
      </summary>
      <div className="form-section-body">{children}</div>
    </details>
  );
}
