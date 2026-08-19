#!/usr/bin/env python3
"""
Create one field account per staff member: username = initials, password random.

    uv run python scripts/seed_field_accounts.py --dry-run
    uv run python scripts/seed_field_accounts.py --slips field_credentials.txt
    uv run python scripts/seed_field_accounts.py --reset ARP

Reads data/network_inventory/staff.csv for the roster. Passwords are generated
here, bcrypt-hashed before they reach the database, and written ONCE to the
--slips file for printing. Nothing recoverable is stored anywhere else.

Why not surnames any more
-------------------------
This script used to set each password to the holder's surname. That was a
deliberate trade for fieldwork -- nothing to forget, nothing to reset from a
monument with no signal -- and it carried one stated condition:

    "It is only defensible while the API is not reachable from the open
     internet."

That condition is now false. The API deploys to a public *.onrender.com URL
behind a public Vercel frontend, and this repository is public and names the
staff. Username and password would both be derivable by anyone who reads
staff.csv. Decision, 2026-08-19: random passwords, handed out on paper.

What the passwords look like, and why
-------------------------------------
Twelve characters from a 31-character alphabet, lowercase, in three
hyphenated groups:

    k7np-qr4m-vx82

The alphabet omits every pair that is misread on a damp phone screen or in
handwriting -- no 0/O, no 1/l/i. Lowercase only, so nobody hunts for a shift
key one-handed in the rain. ~59 bits of entropy, which is far past anything
this threat model needs; the binding constraint was never entropy, it was
whether an observer can type it correctly at a monument on the first try.

The slips file
--------------
--slips writes INITIALS and password, one per line, mode 600. Print it, cut it
up, hand each person their own line at the briefing, then destroy the file:

    shred -u field_credentials.txt

It is gitignored (*credentials*), but treat that as a safety net, not a plan.

--reset stays the escape hatch for one account: same generator, printed once.
"""

from __future__ import annotations

import argparse
import csv
import os
import secrets
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import bcrypt
import psycopg2

ROSTER = Path(__file__).resolve().parent.parent / "data" / "network_inventory" / "staff.csv"


def database_url() -> str:
    if explicit := os.getenv("DATABASE_URL", "").strip():
        return explicit.replace("postgresql+asyncpg://", "postgresql://", 1)
    return (
        f"postgresql://{os.getenv('POGF_DB_USER', 'pogf_user')}:"
        f"{os.getenv('POGF_DB_PASSWORD', 'pogf_password')}@"
        f"{os.getenv('POGF_DB_HOST', 'localhost')}:"
        f"{os.getenv('POGF_DB_PORT', '5433')}/"
        f"{os.getenv('POGF_DB_NAME', 'pogf_db')}"
    )


# Lowercase, digits, and nothing that is misread on a damp phone screen: no
# 0/O, no 1/l/i. 31 characters, so 12 of them carry ~59 bits — far more than
# this threat model needs. The binding constraint was never entropy; it was
# whether a wet, cold observer types it right first time at a monument.
FIELD_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


def field_password(groups: int = 3, size: int = 4) -> str:
    """A password a person can read off paper and type one-handed."""
    return "-".join(
        "".join(secrets.choice(FIELD_ALPHABET) for _ in range(size))
        for _ in range(groups)
    )


def load_surnames(path: Path) -> dict[str, str]:
    """Read `INITIALS,surname` pairs. Never logged, never echoed."""
    if not path.exists():
        raise SystemExit(
            f"{path} not found.\n"
            "Create it with one INITIALS,surname pair per line. It is a credential\n"
            "list — keep it untracked and delete it once the accounts exist."
        )
    out: dict[str, str] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            initials, _, surname = line.partition(",")
            if surname.strip():
                out[initials.strip().upper()] = surname.strip().lower()
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--slips",
        type=Path,
        help="write INITIALS,password here (mode 600) for printing; required "
        "unless --dry-run",
    )
    ap.add_argument(
        "--surnames",
        type=Path,
        help="LEGACY: untracked INITIALS,surname file. Only for an instance that "
        "is genuinely unreachable from the internet — see the module docstring.",
    )
    ap.add_argument("--dry-run", action="store_true", help="report, then roll back")
    ap.add_argument(
        "--reset",
        metavar="INITIALS",
        help="replace one account's password with a random one, printed once",
    )
    args = ap.parse_args()

    # Refuse to create accounts whose passwords go nowhere. Without --slips the
    # generated password is hashed straight into the database and never shown,
    # which produces accounts nobody can sign in to and no way to find out
    # except by trying. --dry-run is exempt: it writes nothing anywhere.
    if not args.surnames and not args.slips and not args.reset and not args.dry_run:
        raise SystemExit(
            "refusing to run: --slips PATH is required when generating passwords "
            "(or pass --dry-run to preview, or --surnames for the legacy scheme)"
        )

    url = database_url()
    parts = urlsplit(url)
    print(f"target: {parts.hostname}:{parts.port or 5432}{parts.path}")

    conn = psycopg2.connect(url)
    try:
        with conn, conn.cursor() as cur:
            if args.reset:
                # Escape hatch for the case this scheme cannot survive: someone
                # leaves, or the API ends up publicly reachable. Random, shown
                # once, never derived from a name.
                # Same generator as a fresh account: a reset handed to someone
                # in the field has to be typable there too.
                new = field_password()
                hashed = bcrypt.hashpw(new.encode(), bcrypt.gensalt()).decode()
                cur.execute(
                    "UPDATE field_ops.users SET hashed_password = %s WHERE lower(username) = %s",
                    (hashed, args.reset.lower()),
                )
                if cur.rowcount == 0:
                    raise SystemExit(f"no account for {args.reset}")
                print(f"\n{args.reset} password is now: {new}")
                print("Shown once. Hand it over in person; it is not recoverable.\n")
                return

            # Legacy path, opt-in and loud. Kept because an air-gapped or
            # tunnel-only instance still satisfies the condition the surname
            # scheme always depended on — but it is no longer what a plain run
            # does, because the deployed instance does not satisfy it.
            surnames = load_surnames(args.surnames) if args.surnames else None
            if surnames is not None:
                print(
                    "WARNING: --surnames sets each password to a public fact. "
                    "Only valid if this API is unreachable from the internet."
                )
            slips: list[tuple[str, str]] = []
            # The role travels with the account, not just with the staff row.
            # Until now every account was created as "field_staff" regardless of
            # what staff.csv said, so the roles someone had carefully edited
            # reached the observer picker and nothing else — and any UI that
            # gated on the signed-in role saw everyone as field staff.
            with ROSTER.open(encoding="utf-8") as fh:
                roster = [
                    (r["initials"].strip().upper(), (r.get("role") or "").strip() or "field_staff")
                    for r in csv.DictReader(fh)
                ]

            created, skipped, rerolled, missing = 0, 0, 0, []
            for initials, role in roster:
                if surnames is not None:
                    secret = surnames.get(initials)
                    if not secret:
                        missing.append(initials)
                        continue
                else:
                    secret = field_password()

                cur.execute(
                    "SELECT 1 FROM field_ops.users WHERE lower(username) = %s",
                    (initials.lower(),),
                )
                if cur.fetchone():
                    # Never silently rewrite a password: an account whose holder
                    # has already changed it must not be reverted to a guessable
                    # one by a re-run of the seed.
                    #
                    # The role is different — it is ours, sourced from the
                    # roster, and a promotion has to be able to take effect
                    # without deleting the account. So it updates while the
                    # password does not.
                    cur.execute(
                        "UPDATE field_ops.users SET role = %s "
                        "WHERE lower(username) = %s AND role IS DISTINCT FROM %s",
                        (role, initials.lower(), role),
                    )
                    rerolled += cur.rowcount
                    skipped += 1
                    continue

                cur.execute(
                    "INSERT INTO field_ops.users (username, hashed_password, role) "
                    "VALUES (%s, %s, %s)",
                    (
                        initials,
                        bcrypt.hashpw(secret.encode(), bcrypt.gensalt()).decode(),
                        role,
                    ),
                )
                created += 1
                if surnames is None:
                    # Only for accounts this run created. An existing account is
                    # skipped above without touching its password, so emitting a
                    # slip for it would hand someone a password that does not work.
                    slips.append((initials, secret))

            print(
                f"accounts: {created} created, {skipped} already existed"
                f"{f', {rerolled} role(s) updated' if rerolled else ''}"
            )
            if missing:
                # Initials only — printing the surname would put a live password
                # into a terminal scrollback and any CI log.
                print(f"no surname supplied for: {', '.join(missing)}")

            if slips and args.slips and not args.dry_run:
                # 600 before a single byte is written — not chmod afterwards,
                # which leaves a window where the file is world-readable.
                fd = os.open(args.slips, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write("# Field Ops credentials — PRINT, DISTRIBUTE, THEN DESTROY\n")
                    fh.write(f"# generated {datetime.now(UTC).isoformat(timespec='seconds')}\n")
                    fh.write("# shred -u this file once the slips are handed out.\n\n")
                    for who, pw in slips:
                        fh.write(f"{who}\t{pw}\n")
                print(f"\n{len(slips)} password(s) written to {args.slips} (mode 600)")
                print("Print it, hand each person their line, then: shred -u "
                      f"{args.slips}")
            elif slips and not args.slips:
                print("\nWARNING: passwords were generated but no --slips file "
                      "was given; they are unrecoverable.")

            if args.dry_run:
                conn.rollback()
                print("\ndry run — rolled back, nothing written")
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
