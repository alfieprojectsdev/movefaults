/**
 * A client-side UUID.
 *
 * Moved out of LogSheetForm unchanged so the station-proposal queue can mint
 * one too. Both use it for the same thing, and it is the same value to the
 * server: the idempotency key that makes a retried sync return the existing
 * row instead of creating a second one.
 *
 * Deliberately still a bare `crypto.randomUUID()`. It needs a secure context —
 * HTTPS or localhost, which covers production and development but not a
 * handset opened over plain http on a LAN address. Whether that is worth a
 * fallback is a real question and not this change's to answer: adding one here
 * would alter how sheets are identified, inside a pull request about creating
 * sites.
 */
export function generateUUID(): string {
  return crypto.randomUUID();
}
