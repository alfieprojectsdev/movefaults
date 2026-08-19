/**
 * Turning what an operator types into an unambiguous instant.
 *
 * Every time column on `field_ops.logsheets` is `timestamptz`. A value sent
 * without a zone is stored as UTC, so a Philippine local time typed as
 * "14:30" and sent bare lands in the database as 06:30 local — eight hours
 * wrong, with nothing on screen to show it. These helpers make the zone
 * explicit at the point of conversion so that cannot happen quietly.
 *
 * Two different meanings share the same shape here, and keeping them apart is
 * the whole job:
 *
 *   Arrival / departure — LOCAL wall clock. When the team reached the site.
 *                         An <input type="time"> gives "HH:MM" with no date.
 *   UTC start / end     — UTC, by GNSS convention and by the field's own
 *                         label. An <input type="datetime-local"> shows the
 *                         operator a wall clock, and here that clock is UTC.
 */

/** Two-digit pad for building wall-clock strings. */
const pad = (n: number) => String(n).padStart(2, "0");

/**
 * Combine the visit date with a local "HH:MM" into an ISO instant.
 *
 * `<input type="time">` carries no date, so "14:30" alone cannot be a
 * timestamp — and sending it bare is what made this field fail validation with
 * 422 on every sheet that used it. The visit date supplies the missing half.
 *
 * Constructed through the Date constructor's local-time form, then serialised
 * with toISOString(), so the offset is applied by the device's own timezone
 * rather than assumed. A phone set to Manila and a laptop set to UTC both
 * produce the correct instant.
 */
export function localTimeToISO(visitDate: string, hhmm: string): string | undefined {
  if (!visitDate || !hhmm) return undefined;

  const [y, m, d] = visitDate.split("-").map(Number);
  const [hh, mm] = hhmm.split(":").map(Number);
  if ([y, m, d, hh, mm].some(Number.isNaN)) return undefined;

  // Month is 0-indexed. This form of the constructor reads the numbers as
  // local time, which is what the operator meant by "we arrived at 14:30".
  return new Date(y, m - 1, d, hh, mm).toISOString();
}

/**
 * Mark a datetime-local value as the UTC instant it already represents.
 *
 * The operator is entering UTC — that is what the field is called, and what a
 * GNSS session log records. The browser control simply renders a wall clock
 * and does not know which zone it belongs to, so the "Z" is added here rather
 * than left for the server to guess.
 */
export function utcFieldToISO(value: string): string | undefined {
  if (!value) return undefined;
  // "2026-08-17T06:30" → "2026-08-17T06:30:00Z". Seconds are added because the
  // control omits them and some parsers are stricter than others.
  const withSeconds = value.length === 16 ? `${value}:00` : value;
  return `${withSeconds}Z`;
}

/** Current local wall clock as "HH:MM", for an <input type="time">. */
export function nowLocalHHMM(now: Date = new Date()): string {
  return `${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

/**
 * Current UTC wall clock as "YYYY-MM-DDTHH:MM", for the UTC datetime-local
 * inputs. Built from the getUTC* accessors so the value shown is UTC even
 * though the control labels itself "local".
 */
export function nowUTCFieldValue(now: Date = new Date()): string {
  return (
    `${now.getUTCFullYear()}-${pad(now.getUTCMonth() + 1)}-${pad(now.getUTCDate())}` +
    `T${pad(now.getUTCHours())}:${pad(now.getUTCMinutes())}`
  );
}

/**
 * Today's LOCAL calendar date as "YYYY-MM-DD", for the visit-date field.
 *
 * `new Date().toISOString().split("T")[0]` — which this replaced — takes the
 * **UTC** calendar date. In Manila (UTC+8) that is the previous day for every
 * moment between 00:00 and 08:00 local, which is exactly when a field team
 * leaves for a site. A sheet filled at 05:30 was pre-dated to yesterday, and
 * nothing on screen suggested otherwise: the date box simply looked filled in.
 *
 * `visit_date` is a SQL `date`, not a timestamp. A calendar day carries no
 * zone, so there is nothing to "store as UTC and convert on display" — writing
 * the UTC date into it does not record an instant, it records a different day
 * from the one the observer was standing there. The local date is the fact the
 * field log is asserting.
 *
 * Contrast the four `timestamptz` columns, which genuinely are instants and are
 * handled by `localTimeToISO` and `utcFieldToISO` above.
 */
export function todayLocalISODate(now: Date = new Date()): string {
  return (
    `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
  );
}

/**
 * Day of year of an instant, counted in UTC.
 *
 * RINEX names a session by its UTC day, so a session id derived from a LOCAL
 * date can disagree with the file it is meant to identify. For a Philippine
 * occupation starting after 08:00 local the two coincide; before that they do
 * not, and the mismatch is invisible until someone tries to pair the logsheet
 * with the observation file.
 *
 * Returns null for an unparseable or empty instant so the caller can fall back
 * to the visit date rather than emit a session id containing "NaN".
 */
export function utcDayOfYear(instant: string | null | undefined): number | null {
  if (!instant) return null;
  const d = new Date(instant);
  if (Number.isNaN(d.getTime())) return null;
  const startOfYear = Date.UTC(d.getUTCFullYear(), 0, 0);
  return Math.floor((d.getTime() - startOfYear) / 86_400_000);
}
