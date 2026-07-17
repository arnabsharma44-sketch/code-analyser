import hashlib
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text

from app.db.models.user import User
from app.db.session import get_connection
from app.core.security import verify_access_token

security_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security_scheme)],
) -> User:
    if credentials is None or not credentials.scheme.lower() == "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    claims = verify_access_token(credentials.credentials)
    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_hash = hashlib.sha256(credentials.credentials.encode("utf-8")).hexdigest()
    with get_connection() as connection:
        row = connection.execute(
            text(
                "SELECT u.id, u.google_sub, u.github_id, u.auth_provider, u.role, u.is_guest, u.email, u.name, u.picture, u.is_active, u.is_admin, u.created_at, u.updated_at "
                "FROM users u JOIN auth_sessions s ON u.id = s.user_id "
                "WHERE u.id = :id AND s.token_hash = :token_hash AND s.expires_at > CURRENT_TIMESTAMP"
            ),
            {"id": int(claims["sub"]), "token_hash": token_hash},
        ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User is unavailable",
        )

    mapping = row._mapping if hasattr(row, "_mapping") else row
    if not mapping["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User is unavailable",
        )

    return User(
        id=mapping["id"],
        google_sub=mapping["google_sub"],
        email=mapping["email"],
        name=mapping["name"],
        picture=mapping["picture"],
        is_active=bool(mapping["is_active"]),
        is_admin=bool(mapping["is_admin"]),
        role=mapping["role"],
        created_at=mapping["created_at"],
        updated_at=mapping["updated_at"],
        github_id=mapping["github_id"],
        auth_provider=mapping["auth_provider"] or "email",
        is_guest=bool(mapping["is_guest"]),
    )
