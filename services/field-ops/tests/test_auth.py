"""Tests for the authentication router.

`POST /api/v1/token` had no direct test of any kind before this file. It is the
one endpoint a field team cannot work around: no token, no logsheet, and the
only diagnosis available at a monument is whatever the screen says.

The `client` fixture seeds a single user, `testuser` / `testpass`.
"""

import pytest
from field_ops.models import User
from field_ops.routers.auth import (
    create_access_token,
    hash_password,
    verify_password,
)

TOKEN_URL = "/api/v1/token"


async def _login(client, username: str, password: str):
    return await client.post(
        TOKEN_URL, data={"username": username, "password": password}
    )


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_login_returns_a_bearer_token(client):
    resp = await _login(client, "testuser", "testpass")
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


@pytest.mark.asyncio
async def test_token_authenticates_against_me(client):
    token = (await _login(client, "testuser", "testpass")).json()["access_token"]
    resp = await client.get(
        "/api/v1/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"username": "testuser", "role": "field_staff"}


# ---------------------------------------------------------------------------
# Refusals — all 401, never 500
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_wrong_password_is_401(client):
    assert (await _login(client, "testuser", "nope")).status_code == 401


@pytest.mark.asyncio
async def test_unknown_user_is_401(client):
    assert (await _login(client, "nobody", "testpass")).status_code == 401


@pytest.mark.asyncio
async def test_refusal_does_not_say_which_half_was_wrong(client):
    """Same message either way — the response must not confirm a username."""
    wrong_pw = (await _login(client, "testuser", "nope")).json()["detail"]
    no_user = (await _login(client, "nobody", "testpass")).json()["detail"]
    assert wrong_pw == no_user


@pytest.mark.asyncio
async def test_me_without_a_token_is_401(client):
    assert (await client.get("/api/v1/me")).status_code == 401


@pytest.mark.asyncio
async def test_me_with_a_garbage_token_is_401(client):
    resp = await client.get(
        "/api/v1/me", headers={"Authorization": "Bearer not.a.jwt"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_token_for_a_deleted_account_is_401(client, db_session):
    """A signed token is not enough — the account must still exist.

    Tokens last 8 hours by default, so a revoked account has to stop working
    inside that window rather than at the next login.
    """
    token = create_access_token("ghost", "field_staff")
    resp = await client.get(
        "/api/v1/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# What a phone keyboard actually sends
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("typed", ["TESTUSER", "TestUser", "Testuser"])
@pytest.mark.asyncio
async def test_username_is_case_insensitive(client, typed):
    """A phone capitalises the first letter of a field by default.

    Documented behaviour of this endpoint, previously untested.
    """
    assert (await _login(client, typed, "testpass")).status_code == 200


@pytest.mark.asyncio
async def test_username_is_trimmed(client):
    """Autocomplete and copy-paste both add a trailing space."""
    assert (await _login(client, "  testuser  ", "testpass")).status_code == 200


@pytest.mark.asyncio
async def test_password_is_NOT_trimmed_or_case_folded(client):
    """Only the username is forgiving. A password is compared verbatim."""
    assert (await _login(client, "testuser", "TESTPASS")).status_code == 401
    assert (await _login(client, "testuser", " testpass ")).status_code == 401


# ---------------------------------------------------------------------------
# Ambiguity must never be a 500
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_case_colliding_accounts_do_not_500(client, db_session):
    """Two accounts differing only by case must not break login.

    `uq_users_username UNIQUE (username)` is case-SENSITIVE in PostgreSQL, so
    "testuser" and "TESTUSER" can coexist while every lookup in the app keys on
    lower(username). Before this was handled, the endpoint raised
    MultipleResultsFound from scalar_one_or_none() and returned 500 — on the
    one endpoint a field team cannot work around.

    Migration fo006 adds a unique index on lower(username) so the state cannot
    arise. This asserts the endpoint is safe even where that has not been
    applied yet.
    """
    db_session.add(
        User(
            username="TESTUSER",
            hashed_password=hash_password("different"),
            role="field_staff",
        )
    )
    await db_session.commit()

    resp = await _login(client, "testuser", "testpass")
    assert resp.status_code != 500
    # The exact-case account is the one that wins, so its own password works.
    assert resp.status_code == 200
    assert resp.json()["access_token"]


@pytest.mark.asyncio
async def test_case_collision_with_no_exact_match_is_401_not_500(client, db_session):
    db_session.add(
        User(
            username="TestUser",
            hashed_password=hash_password("aaa"),
            role="field_staff",
        )
    )
    db_session.add(
        User(
            username="TESTUSER",
            hashed_password=hash_password("bbb"),
            role="field_staff",
        )
    )
    await db_session.commit()

    resp = await _login(client, "tEsTuSeR", "aaa")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def test_hash_is_salted_so_equal_passwords_differ():
    assert hash_password("same") != hash_password("same")


def test_verify_password_round_trips():
    assert verify_password("hunter2", hash_password("hunter2"))
    assert not verify_password("hunter3", hash_password("hunter2"))


@pytest.mark.parametrize("stored", ["", "not-a-hash", "$2b$xx$broken"])
def test_verify_password_returns_false_on_an_unusable_stored_hash(stored):
    """bcrypt.checkpw raises ValueError on a malformed salt.

    One corrupt row must be a failed login for that account, not a 500 that
    reads from the field like the whole service being down.
    """
    assert verify_password("anything", stored) is False


@pytest.mark.asyncio
async def test_login_with_a_corrupt_stored_hash_is_401(client, db_session):
    db_session.add(
        User(username="broken", hashed_password="", role="field_staff")
    )
    await db_session.commit()
    assert (await _login(client, "broken", "whatever")).status_code == 401
