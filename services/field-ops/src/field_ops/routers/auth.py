"""
Authentication router — POST /api/v1/token

Issues JWT Bearer tokens using OAuth2 password flow.
Tokens expire after field_ops_jwt_expire_hours (default 8 h — a full field shift).

JWT payload:
    {"sub": "<username>", "role": "<role>"}

Usage:
    POST /api/v1/token
    Content-Type: application/x-www-form-urlencoded
    Body: username=alice&password=secret

    → {"access_token": "...", "token_type": "bearer"}
"""

from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from field_ops.config import settings
from field_ops.database import get_db
from field_ops.models import User

router = APIRouter(prefix="/api/v1", tags=["auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/token")


class Token(BaseModel):
    access_token: str
    token_type: str


class Me(BaseModel):
    """Who the caller is, according to the server."""

    username: str
    role: str


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def create_access_token(username: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.field_ops_jwt_expire_hours)
    payload = {"sub": username, "role": role, "exp": expire}
    return jwt.encode(payload, settings.field_ops_jwt_secret, algorithm=settings.field_ops_jwt_algorithm)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """FastAPI dependency: validates JWT and returns the User ORM object."""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            settings.field_ops_jwt_secret,
            algorithms=[settings.field_ops_jwt_algorithm],
        )
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exc
    return user


@router.post("/token", response_model=Token)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Token:
    # Case-insensitive on the username. Usernames are staff initials, and a
    # phone keyboard capitalises the first letter of a field by default — so
    # "Arp" is what an observer actually types when the account is "ARP".
    # Rejecting that is a lockout with no diagnosis available in the field.
    result = await db.execute(
        select(User).where(func.lower(User.username) == form.username.strip().lower())
    )
    user = result.scalar_one_or_none()

    if user is None or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(user.username, user.role)
    return Token(access_token=token, token_type="bearer")


# ── Role enforcement ────────────────────────────────────────────────────────


def require_role(*allowed: str):
    """
    Dependency that refuses a caller whose role is not in `allowed`.

    This exists because hiding a control in the frontend is not a security
    boundary. A view the UI declines to render is still a reachable endpoint —
    devtools, curl, or a stale bundle all bypass it. Anything that actually
    needs restricting has to be refused here, on the server, and the UI gating
    is decluttering on top of that.

    Deliberately unused so far: nothing in this app is admin-only yet. It is
    added with the roles so that the first genuinely privileged endpoint has an
    obvious thing to reach for, rather than inventing a check under deadline.
    """

    async def _check(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            # 403, not 404: the caller is authenticated and we are telling them
            # this is not theirs. Hiding the endpoint's existence buys nothing
            # here — the frontend bundle names every route it can call.
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires one of: {', '.join(sorted(allowed))}",
            )
        return user

    return _check


@router.get("/me", response_model=Me)
async def read_me(user: User = Depends(get_current_user)) -> Me:
    """
    The signed-in account and its role.

    The role is already inside the JWT, and the frontend could decode it — a JWT
    is signed, not encrypted. It is served here instead so the server stays the
    authority: a role changed in the database takes effect on the next call
    rather than at the next login, which on an 8-hour field session could be
    the next day.
    """
    return Me(username=user.username, role=user.role)
