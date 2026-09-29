/**
 * The check-before-sending panel.
 *
 * Shown in place of an immediate submit when utils/review.ts finds something
 * worth a second look. It never appears for a sheet with nothing to flag: a
 * step that always shows teaches people to tap straight through it.
 *
 * "Send anyway" is a real choice, not a nag. Every item here is allowed to be
 * blank; the panel only asks whether it was meant to be.
 */

import type { ReviewItem } from "../utils/review";

interface Props {
  items: ReviewItem[];
  onSend: () => void;
  onBack: () => void;
  sending?: boolean;
}

export default function SendReview({ items, onSend, onBack, sending = false }: Props) {
  const blank = items.filter((i) => i.level === "blank");
  const confirm = items.filter((i) => i.level === "confirm");
  return (
    <div className="msg msg-warn" role="alertdialog" aria-labelledby="send-review-title">
      <strong id="send-review-title">Check before sending</strong>
      {blank.length > 0 && (
        <>
          <p>Left blank:</p>
          <ul>
            {blank.map((i) => (
              <li key={i.field}>{i.label}</li>
            ))}
          </ul>
        </>
      )}
      {confirm.length > 0 && (
        <>
          <p>Worth a second look:</p>
          <ul>
            {confirm.map((i) => (
              <li key={i.field}>{i.label}</li>
            ))}
          </ul>
        </>
      )}
      <p>A sheet can’t be changed once it reaches the server.</p>
      <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
        <button type="button" className="secondary" onClick={onBack} disabled={sending}>
          Go back and fill in
        </button>
        <button type="button" onClick={onSend} disabled={sending}>
          {sending ? "Saving…" : "Send anyway"}
        </button>
      </div>
    </div>
  );
}
