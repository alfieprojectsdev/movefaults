#!/usr/bin/env python3
"""
Create one field account per staff member: username = initials, password = surname.

    uv run python scripts/seed_field_accounts.py --dry-run
    uv run python scripts/seed_field_accounts.py
    uv run python scripts/seed_field_accounts.py --reset ARP

Reads data/network_inventory/staff.csv for the roster and takes surnames from a
separate, UNTRACKED file (see below). Passwords are bcrypt-hashed before they
reach the database; the plaintext exists only in the operator's hands.

Why the surnames are not in this repository
-------------------------------------------
The repository is public. Committing surnames here would publish both halves of
every credential in one place, so the roster CSV holds initials only and the
surname file is gitignored. Point --surnames at it:

    ARP,pelicano
    TCB,bacolcol

That file is a credential list. Keep it out of git, off shared drives, and
delete it once the accounts exist.

What this scheme is, honestly
-----------------------------
Username and password are both derived from a person's name, which appears on
PHIVOLCS org charts, published papers and this app's own observer list. Anyone
who knows the team can sign in as any member. The password is not a secret; it
is a name badge.

That is a deliberate trade for fieldwork — nothing to forget, nothing to reset
from a monument with no signal, and the accounts exist to attribute a sheet to
an observer rather than to keep anyone out.

It is only defensible while the API is not reachable from the open internet.
The one control that makes it so is documented in DEPLOY.md: keep the backend
off a public URL, or put it behind an allowlist. If that ever changes, this
script's assumption is void and the accounts need real passwords — which is why
--reset exists.
"""

from __future__ import annotations

import argparse
import csv
import os
import secrets
import sys
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
    ap.add_argument("--surnames", type=Path, required=True, help="untracked INITIALS,surname file")
    ap.add_argument("--dry-run", action="store_true", help="report, then roll back")
    ap.add_argument(
        "--reset",
        metavar="INITIALS",
        help="replace one account's password with a random one, printed once",
    )
    args = ap.parse_args()

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
                new = secrets.token_urlsafe(12)
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

            surnames = load_surnames(args.surnames)
            with ROSTER.open(encoding="utf-8") as fh:
                roster = [r["initials"].strip().upper() for r in csv.DictReader(fh)]

            created, skipped, missing = 0, 0, []
            for initials in roster:
                surname = surnames.get(initials)
                if not surname:
                    missing.append(initials)
                    continue

                cur.execute(
                    "SELECT 1 FROM field_ops.users WHERE lower(username) = %s",
                    (initials.lower(),),
                )
                if cur.fetchone():
                    # Never silently rewrite a password: an account whose holder
                    # has already changed it must not be reverted to a guessable
                    # one by a re-run of the seed.
                    skipped += 1
                    continue

                cur.execute(
                    "INSERT INTO field_ops.users (username, hashed_password, role) "
                    "VALUES (%s, %s, %s)",
                    (
                        initials,
                        bcrypt.hashpw(surname.encode(), bcrypt.gensalt()).decode(),
                        "field_staff",
                    ),
                )
                created += 1

            print(f"accounts: {created} created, {skipped} already existed")
            if missing:
                # Initials only — printing the surname would put a live password
                # into a terminal scrollback and any CI log.
                print(f"no surname supplied for: {', '.join(missing)}")

            if args.dry_run:
                conn.rollback()
                print("\ndry run — rolled back, nothing written")
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
