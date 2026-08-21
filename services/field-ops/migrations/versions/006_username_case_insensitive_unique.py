"""enforce case-insensitive uniqueness on users.username

Revision ID: fo006
Revises: fo005
Create Date: 2026-08-22 UTC

The application has always assumed usernames are unique WITHOUT regard to case.
The schema has never enforced it.

  * `POST /api/v1/token` looks the account up with
    `func.lower(User.username) == form.username.strip().lower()`, because a
    phone keyboard capitalises the first letter of a field and rejecting "Arp"
    for an account named "ARP" is a lockout with no diagnosis available at a
    monument.
  * `scripts/seed_field_accounts.py` does the same: its existence check, its
    password reset and its role update all key on `lower(username)`.

But `fo001` created `CONSTRAINT uq_users_username UNIQUE (username)`, which in
PostgreSQL is case-SENSITIVE. So "ARP" and "arp" can both exist, and the moment
they do:

  * login raises `MultipleResultsFound` from `scalar_one_or_none()` and returns
    **500** — an opaque failure on the one endpoint a field team cannot work
    around, and
  * the seeder's `UPDATE ... WHERE lower(username) = %s` rewrites the password
    of BOTH accounts at once.

Neither is hypothetical: reproduced in a test against the real router before
this migration was written.

The seeder cannot create the collision by itself (it checks case-insensitively
first), so today's rows are almost certainly clean. This closes the door rather
than fixing damage — the point is that the invariant stops depending on every
future writer remembering to lower-case.

IF THIS MIGRATION FAILS
-----------------------
A unique-violation here means duplicate accounts already exist. That is
information, not an obstacle: find them before deciding which to keep, because
one of them is somebody's working login.

    SELECT lower(username) AS name, count(*), array_agg(username), array_agg(id)
    FROM field_ops.users GROUP BY 1 HAVING count(*) > 1;

Resolve by hand, then re-run. Do not "fix" it by dropping rows blind.
"""

from alembic import op

revision = "fo006"
down_revision = "fo005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A functional unique index, which is how PostgreSQL expresses
    # case-insensitive uniqueness without a citext column. Choosing the index
    # over `ALTER COLUMN ... TYPE citext` deliberately: citext is an extension,
    # and a managed provider may not have it available.
    #
    # The existing case-sensitive constraint stays. It is strictly weaker than
    # this one, so it is now redundant rather than wrong, and dropping a
    # constraint on a live table buys nothing here.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_username_lower "
        "ON field_ops.users (lower(username))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS field_ops.uq_users_username_lower")
