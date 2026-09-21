"""station_proposals.collides_with — a contested code becomes a row, not a 409

Revision ID: fo008
Revises: fo007
Create Date: 2026-09-21 UTC

Issue #228. Decision recorded on the issue 2026-09-17: accept the colliding
proposal, so the office sees both claims and settles them on the reconcile
screen.

WHAT WAS WRONG
--------------
`propose_station` answered 409 when a code was already taken, and the proposal
never became a row. The handset kept it marked `conflict` and nothing
server-side ever heard of it: the reconcile screen reads
`field_ops.station_proposals`, and there was nothing to read. A real site
somebody travelled to and stood at could sit on one phone, invisible to
everyone, until that phone was wiped.

That 409 was not the observer's mistake. `propose_station`'s own docstring
says the duplicate guard cannot reach a handset that has been offline for two
days, so two teams independently proposing the same code is the *expected*
outcome of working offline correctly. The design accounted for the collision
happening and not for what the loser does next.

WHY THE UNIQUE INDEX HAS TO NARROW
----------------------------------
fo007's `uq_station_proposals_pending_code` is UNIQUE on `station_code`,
partial on `reconciled_at IS NULL`. That index *is* the 409 — while it stands,
a second pending claim cannot be stored at all, whatever the router does.

Narrowing it to `reconciled_at IS NULL AND collides_with IS NULL` keeps the
part that is still wanted and drops the part that strands people:

  * at most one **uncontested** pending claim per code, so the ordinary
    double-submit is still refused by the schema rather than by trust in the
    router;
  * any number of claims **marked as collisions**, because that is the state
    the office is being asked to settle. Two is the common case; more than two
    is rare and equally legitimate.

`collides_with` is the marker: NULL, 'inventory' or 'proposal'. It records
what was true when the server heard, which is what a reviewer needs to
understand the disagreement. It is deliberately not a live flag — see the
model and `promote_proposal`, which re-checks the inventory rather than
trusting a value that may be days old.

NO BACKFILL IS POSSIBLE, AND NONE IS NEEDED
-------------------------------------------
Every row already in the table was accepted under the old rule, so every one
of them was uncontested at the time: `collides_with` is correctly NULL for all
of them, which is what adding a nullable column gives. The proposals that were
*refused* are not recoverable here — they were never rows, and the only copies
live in whatever handsets still hold them. Those return by being synced again,
which now succeeds.

THE DOWNGRADE CAN FAIL, AND SHOULD
----------------------------------
Restoring the wider index will fail if any code has more than one pending
claim — exactly the rows this migration exists to allow. That is the correct
behaviour: silently deleting somebody's field-collected site to make an index
fit would destroy the record this change was written to preserve. Resolve the
collisions (promote or reject) and run the downgrade again.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "fo008"
down_revision = "fo007"
branch_labels = None
depends_on = None

SCHEMA = "field_ops"

_PENDING_CODE_INDEX = "uq_station_proposals_pending_code"


def upgrade() -> None:
    op.add_column(
        "station_proposals",
        sa.Column("collides_with", sa.String(20)),
        schema=SCHEMA,
    )

    # Recreated rather than altered: Postgres has no ALTER INDEX ... WHERE.
    op.drop_index(_PENDING_CODE_INDEX, table_name="station_proposals", schema=SCHEMA)
    op.create_index(
        _PENDING_CODE_INDEX,
        "station_proposals",
        ["station_code"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("reconciled_at IS NULL AND collides_with IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(_PENDING_CODE_INDEX, table_name="station_proposals", schema=SCHEMA)
    # Fails if a code has more than one pending claim. See the module
    # docstring: that failure is the point, not an oversight.
    op.create_index(
        _PENDING_CODE_INDEX,
        "station_proposals",
        ["station_code"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("reconciled_at IS NULL"),
    )
    op.drop_column("station_proposals", "collides_with", schema=SCHEMA)
