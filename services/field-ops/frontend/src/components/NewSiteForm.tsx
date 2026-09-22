/**
 * Create a site from the monument you are standing at.
 *
 * Closes the half of #118 that was never built: the API to propose a station
 * has existed and been tested since fo007, and nothing in the app referenced
 * it. An observer at an uncatalogued site could not file a sheet at all.
 *
 * IT IS A PROPOSAL, AND THE FORM SAYS SO
 *
 * This does not add a station to the inventory. It records that someone stood
 * somewhere and says a site is there, for a human in the office to accept or
 * reject. The wording throughout is "site", "proposed", "awaiting review" —
 * never "created" — because an observer who believes they have added a station
 * to the national inventory from a phone will be surprised later, and the
 * surprise will arrive as a missing station rather than as an explanation.
 *
 * WHY THE POSITION IS CAPTURED AND NOT TYPED
 *
 * The one thing the office cannot reconstruct afterwards is where the monument
 * actually is. Everything else on this form can be corrected from a desk; a
 * coordinate cannot, without sending someone back. So the fix is taken from
 * the device automatically, its accuracy is shown, and a poor fix is recorded
 * as a poor fix rather than being silently rounded into a claim.
 *
 * It is not required. A site under canopy with no fix is still a site worth
 * recording, and refusing the proposal would send the observer home with
 * nothing — which is the exact failure this form exists to end.
 */

import { useState } from "react";

import { useDeviceLocation, MAX_USEFUL_ACCURACY_M } from "../hooks/useDeviceLocation";
import { formatDistance } from "../utils/distance";
import { generateUUID } from "../utils/uuid";
import type { StationProposalIn } from "../services/api";

interface Props {
  /**
   * Codes already taken — the inventory plus anything proposed on this device.
   *
   * Layer 1 of the three-layer duplicate guard described in the endpoint's
   * docstring. It is the only layer an offline handset can reach, and the
   * cheapest place to catch the common case: someone typing a code that is
   * already in the list they were just looking at.
   */
  takenCodes: string[];
  onCancel: () => void;
  onCreated: (proposal: StationProposalIn) => void;
}

const METHODS = [
  { value: "campaign", label: "Campaign — temporary deployment" },
  { value: "continuous", label: "Continuous — permanent CORS" },
];

export default function NewSiteForm({ takenCodes, onCancel, onCreated }: Props) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [method, setMethod] = useState("campaign");
  const [municipality, setMunicipality] = useState("");
  const [province, setProvince] = useState("");
  const [notes, setNotes] = useState("");

  const location = useDeviceLocation(true);
  const fix = location.status === "located" ? location.fix : null;
  const coarse = fix != null && fix.accuracy > MAX_USEFUL_ACCURACY_M;

  // Upper-cased and trimmed here to match the server's own normaliser, so the
  // duplicate check below compares the same string the unique index will.
  const normalised = code.trim().toUpperCase();
  const taken = normalised !== "" && takenCodes.some((c) => c.toUpperCase() === normalised);
  const tooLong = normalised.length > 10;
  const valid = normalised.length > 0 && !taken && !tooLong;

  const submit = () => {
    if (!valid) return;
    onCreated({
      // Minted once, here, and carried through the queue unchanged. This is
      // what stops a retried sync creating a second site.
      client_uuid: generateUUID(),
      station_code: normalised,
      name: name.trim() || null,
      latitude: fix ? fix.latitude : null,
      longitude: fix ? fix.longitude : null,
      monitoring_method: method,
      municipality: municipality.trim() || null,
      province: province.trim() || null,
      proposed_at: new Date().toISOString(),
      notes:
        // The accuracy goes in the notes rather than being dropped. A
        // reconciler deciding whether to promote this needs to know the
        // coordinate came from a 4 km cell fix, and there is no column for it.
        [notes.trim(), fix ? `Fix accuracy ±${formatDistance(fix.accuracy)}.` : "No position fix."]
          .filter(Boolean)
          .join(" ") || null,
    });
  };

  return (
    <div className="new-site">
      <h3 className="section-header">Add a site that is not listed</h3>

      <p className="hint">
        This records the site for review — it does not add it to the national
        inventory. You can file a sheet against it straight away.
      </p>

      <label>
        Site code *
        <input
          type="text"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="e.g. PBIS"
          maxLength={10}
          autoCapitalize="characters"
          autoCorrect="off"
          spellCheck={false}
          aria-describedby="new-site-code-help"
        />
        <small id="new-site-code-help">
          Four letters, as it will appear in RINEX. Saved in capitals.
        </small>
        {taken && (
          <span className="field-error">
            {normalised} is already in use. If this is a different site, choose
            another code and say so in the notes.
          </span>
        )}
        {tooLong && <span className="field-error">Ten characters at most.</span>}
      </label>

      <label>
        Site name
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Bislig City Hall"
        />
      </label>

      <label>
        Type
        <select value={method} onChange={(e) => setMethod(e.target.value)}>
          {METHODS.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </select>
      </label>

      <div className="form-grid-2">
        <label>
          Municipality
          <input
            type="text"
            value={municipality}
            onChange={(e) => setMunicipality(e.target.value)}
          />
        </label>
        <label>
          Province
          <input type="text" value={province} onChange={(e) => setProvince(e.target.value)} />
        </label>
      </div>

      {/* Stated, never silent. A coordinate is the one thing on this form that
          cannot be corrected from a desk, so the observer is told exactly what
          is about to be recorded as the site's position. */}
      <p className={coarse || !fix ? "msg msg-warn" : "msg msg-info"}>
        {fix ? (
          <>
            Position: {fix.latitude.toFixed(5)}, {fix.longitude.toFixed(5)} (±
            {formatDistance(fix.accuracy)})
            {coarse && " — too coarse to identify a monument, but recorded as a starting point."}
          </>
        ) : location.status === "denied" ? (
          "No position: location permission is off. The site will be recorded without coordinates."
        ) : (
          "Waiting for a position fix. You can save without one."
        )}
      </p>

      <label>
        Notes
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
          placeholder="Access, landowner, why this site — anything the office will need."
        />
      </label>

      <div className="new-site-actions">
        <button type="button" onClick={submit} disabled={!valid}>
          Save site and select it
        </button>
        <button type="button" className="secondary" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}
