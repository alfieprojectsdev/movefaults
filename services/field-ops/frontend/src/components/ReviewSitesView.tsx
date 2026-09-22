/**
 * Review sites proposed from the field.
 *
 * The other half of #219. The API to list, promote and reject has existed
 * since fo007 with no caller, so a site created at a monument was invisible to
 * the office until someone queried the database by hand. Shipping the create
 * half without this made that worse rather than better: before, there was
 * nothing to be invisible.
 *
 * THE DECISION THIS SCREEN EXISTS TO SUPPORT
 *
 * Not "is this row well-formed". It is: *is there a monument there, and is
 * this the right code for it.* Two things carry that and both are given more
 * room than their field size suggests:
 *
 *   sheet_count — logsheets already filed against this code. Rejecting a
 *   proposal with sheets against it orphans real observations that were
 *   validly collected at something. The endpoint's own docstring says so, and
 *   the reject confirmation says it again at the moment it matters.
 *
 *   notes — where the field form writes the position accuracy, because there
 *   is no column for it. A coordinate from a 4 km cell fix and one from a 12 m
 *   GNSS fix look identical in latitude and longitude, and only one of them
 *   identifies a monument.
 *
 * REJECT IS NOT DELETE, AND THE SCREEN SAYS SO
 *
 * The row is kept, the reason is recorded, and stamping reconciled_at releases
 * the code from the partial unique index so a corrected proposal can be made —
 * including by the same person, when the rejection was itself the mistake.
 * A reviewer who believes reject destroys the record will hesitate over rows
 * they should decline.
 */

import { useState } from "react";

import { useStationProposals, useReconcile } from "../hooks/useStationProposals";
import { useOnline } from "../hooks/useOnline";
import { ApiError, type StationProposalOut } from "../services/api";

function describeError(err: unknown, online: boolean): string {
  if (!online) return "You are offline. Reviewing a site needs a connection.";
  if (err instanceof ApiError) {
    if (err.status === 403) {
      return "Your account cannot review sites. This needs the admin or data-processor role.";
    }
    if (err.status === 409) {
      // Not a failure. The endpoint answers 409 rather than 404 precisely so a
      // second reviewer hears "already handled" instead of "not found".
      return "Someone else has already dealt with this one. The list has been refreshed.";
    }
    if (err.status === 401) return "Your session has expired. Sign in again.";
    return err.message;
  }
  return "Could not reach the server.";
}

function coordinates(p: StationProposalOut): string {
  if (p.latitude == null || p.longitude == null) return "No position recorded";
  return `${p.latitude.toFixed(5)}, ${p.longitude.toFixed(5)}`;
}

export default function ReviewSitesView() {
  const online = useOnline();
  const { data: proposals, isLoading, isError, error, refetch } = useStationProposals(true);
  const { promote, reject } = useReconcile();

  /** Which row is mid-rejection, and the reason typed so far. */
  const [rejecting, setRejecting] = useState<number | null>(null);
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  const busy = promote.isPending || reject.isPending;

  const doPromote = (p: StationProposalOut) => {
    setMessage(null);
    promote.mutate(p.id, {
      onSuccess: () => setMessage(`${p.station_code} is now in the inventory.`),
      onError: (err) => setMessage(describeError(err, online)),
    });
  };

  const doReject = (p: StationProposalOut) => {
    if (reason.trim() === "") return;
    setMessage(null);
    reject.mutate(
      { id: p.id, reason: reason.trim() },
      {
        onSuccess: () => {
          setMessage(`${p.station_code} declined. The record and your reason are kept.`);
          setRejecting(null);
          setReason("");
        },
        onError: (err) => setMessage(describeError(err, online)),
      },
    );
  };

  if (isLoading) return <p className="hint">Loading proposed sites…</p>;

  if (isError) {
    return (
      <section className="review-sites">
        <h2>Sites proposed from the field</h2>
        <p className="msg msg-error">{describeError(error, online)}</p>
        <button type="button" onClick={() => void refetch()}>
          Try again
        </button>
      </section>
    );
  }

  const rows = proposals ?? [];

  return (
    <section className="review-sites">
      <h2>Sites proposed from the field</h2>

      {message && <p className="msg msg-info">{message}</p>}

      {rows.length === 0 ? (
        <p className="hint">
          Nothing waiting. Sites created in the field appear here for review.
        </p>
      ) : (
        <ul className="review-list">
          {rows.map((p) => {
            const hasSheets = p.sheet_count > 0;
            return (
              <li key={p.id} className="review-row">
                <div className="review-head">
                  <strong>{p.station_code}</strong>
                  <span className="review-method">
                    {p.monitoring_method === "campaign" ? "Campaign" : "Continuous"}
                  </span>
                </div>

                <div className="review-name">{p.name ?? "(no name given)"}</div>

                <dl className="review-facts">
                  <dt>Position</dt>
                  <dd>{coordinates(p)}</dd>
                  <dt>Place</dt>
                  <dd>
                    {[p.municipality, p.province].filter(Boolean).join(", ") || "not given"}
                  </dd>
                  <dt>Proposed</dt>
                  <dd>{(p.proposed_at ?? p.created_at ?? "").slice(0, 10) || "unknown"}</dd>
                  <dt>Sheets filed</dt>
                  {/* The number the decision turns on, so it is never just a
                      figure in a row — it is labelled as a consequence. */}
                  <dd className={hasSheets ? "review-has-sheets" : undefined}>
                    {p.sheet_count}
                    {hasSheets && " — rejecting this orphans them"}
                  </dd>
                </dl>

                {/* Where the field form writes the fix accuracy, because there
                    is no column for it. Shown in full rather than truncated:
                    it is the difference between a coordinate that identifies a
                    monument and one that identifies a municipality. */}
                {p.notes && <p className="review-notes">{p.notes}</p>}

                {rejecting === p.id ? (
                  <div className="review-reject">
                    <label>
                      Why is this being declined?
                      <input
                        type="text"
                        value={reason}
                        onChange={(e) => setReason(e.target.value)}
                        placeholder="e.g. duplicate of PBIS, code mistyped"
                        autoFocus
                      />
                      <small>
                        Recorded against the proposal. The row is kept, and the
                        code is freed so a corrected one can be made.
                      </small>
                    </label>
                    {hasSheets && (
                      <p className="msg msg-warn">
                        {p.sheet_count} {p.sheet_count === 1 ? "sheet names" : "sheets name"}{" "}
                        {p.station_code}. Those observations were collected somewhere real;
                        declining the site leaves them pointing at a code the inventory does
                        not have.
                      </p>
                    )}
                    <div className="review-actions">
                      <button
                        type="button"
                        onClick={() => doReject(p)}
                        disabled={busy || reason.trim() === ""}
                      >
                        Decline {p.station_code}
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => {
                          setRejecting(null);
                          setReason("");
                        }}
                        disabled={busy}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="review-actions">
                    <button type="button" onClick={() => doPromote(p)} disabled={busy}>
                      Add to inventory
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => {
                        setRejecting(p.id);
                        setReason("");
                        setMessage(null);
                      }}
                      disabled={busy}
                    >
                      Decline
                    </button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
