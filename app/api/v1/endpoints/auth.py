import hashlib
from datetime import datetime, timedelta, timezone
from typing import Annotated
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import text

from app.core.config import settings
from app.core.security import create_access_token, verify_access_token
from app.db.session import get_connection, init_db
from app.dependencies.auth import get_current_user
from app.db.models.user import User
from app.schemas.auth import AuthSessionResponse, UserRead
from app.services.captcha import verify_captcha_token

router = APIRouter(prefix="/auth", tags=["Auth"])
security_scheme = HTTPBearer(auto_error=False)

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
ALLOWED_EMAIL_DOMAINS = {"gmail.com", "hotmail.com", "yahoo.com", "outlook.com", "icloud.com", "example.com"}


def _is_allowed_email(email: str) -> bool:
    try:
        domain = email.split("@", 1)[1].lower()
    except IndexError:
        return False
    return domain in ALLOWED_EMAIL_DOMAINS


class CaptchaRequest(BaseModel):
    captcha_token: str | None = Field(
        default=None,
        description="CAPTCHA token from the client when CAPTCHA protection is enabled",
    )


class GoogleTokenRequest(CaptchaRequest):
    google_sub: str = Field(..., min_length=1)
    email: EmailStr
    name: str | None = None


class EmailSignupRequest(CaptchaRequest):
    email: EmailStr
    password: str = Field(..., min_length=8)
    name: str | None = None

    @field_validator("email")
    def validate_email_domain(cls, value: str) -> str:
        if not _is_allowed_email(value):
            raise ValueError("Email domain must be one of: gmail.com, hotmail.com, yahoo.com, outlook.com, icloud.com")
        return value

    @field_validator("password")
    def validate_password_strength(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not any(char.isalpha() for char in value):
            raise ValueError("Password must contain at least one letter")
        if not any(char in "!@#$%^&*()-_+=[]{}|:;'<>,.?/" for char in value):
            raise ValueError("Password must contain at least one special character")
        return value


class EmailLoginRequest(CaptchaRequest):
    email: EmailStr
    password: str = Field(..., min_length=8)

    @field_validator("email")
    def validate_email_domain(cls, value: str) -> str:
        if not _is_allowed_email(value):
            raise ValueError("Email domain must be one of: gmail.com, hotmail.com, yahoo.com, outlook.com, icloud.com")
        return value


class GitHubLoginRequest(CaptchaRequest):
    github_id: str = Field(..., min_length=1)
    email: EmailStr | None = None
    name: str | None = None


class GuestLoginRequest(CaptchaRequest):
    name: str | None = None


def _hash_password(password: str) -> str:
    return pwd_context.hash(password)


def _verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


def _row_to_mapping(row):
    return row._mapping if hasattr(row, "_mapping") else row


def _build_user_from_row(row) -> User:
    mapping = _row_to_mapping(row)
    return User(
        id=mapping["id"],
        google_sub=mapping["google_sub"],
        email=mapping["email"],
        name=mapping["name"],
        picture=mapping["picture"],
        is_active=bool(mapping["is_active"]),
        is_admin=bool(mapping["is_admin"]),
        role=mapping["role"] if "role" in mapping.keys() else "user",
        created_at=mapping["created_at"],
        updated_at=mapping["updated_at"],
        github_id=mapping["github_id"],
        auth_provider=mapping["auth_provider"] or "email",
        is_guest=bool(mapping["is_guest"]),
    )


def _issue_session(user: User) -> AuthSessionResponse:
    token = create_access_token(user.id)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.auth_session_ttl_seconds)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    with get_connection() as connection:
        connection.execute(
            text(
                "INSERT INTO auth_sessions (user_id, token_hash, expires_at, created_at)"
                " VALUES (:user_id, :token_hash, :expires_at, CURRENT_TIMESTAMP)"
            ),
            {
                "user_id": user.id,
                "token_hash": token_hash,
                "expires_at": expires_at,
            },
        )
        connection.commit()

    return AuthSessionResponse(
        access_token=token,
        token_type="bearer",
        expires_at=expires_at,
        user=UserRead(**user.__dict__),
    )


@router.post("/token", response_model=AuthSessionResponse)
async def issue_google_token(payload: GoogleTokenRequest) -> AuthSessionResponse:
    await verify_captcha_token(payload.captcha_token)
    init_db()

    with get_connection() as connection:
        existing = connection.execute(
            text("SELECT id, google_sub, github_id, auth_provider, role, is_guest, email, name, picture, is_active, is_admin, created_at, updated_at FROM users WHERE google_sub = :google_sub"),
            {"google_sub": payload.google_sub},
        ).fetchone()

        if existing is None:
            cursor = connection.execute(
                text(
                    "INSERT INTO users (google_sub, email, name, picture, auth_provider, is_guest, is_active, is_admin, created_at, updated_at)"
                    " VALUES (:google_sub, :email, :name, :picture, 'google', 0, 1, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {
                    "google_sub": payload.google_sub,
                    "email": str(payload.email),
                    "name": payload.name,
                    "picture": None,
                },
            )
            user_id = cursor.lastrowid
            connection.commit()
        else:
            existing_mapping = existing._mapping if hasattr(existing, "_mapping") else existing
            user_id = existing_mapping["id"]
            connection.execute(
                text("UPDATE users SET email = :email, name = :name, updated_at = CURRENT_TIMESTAMP WHERE id = :id"),
                {"email": str(payload.email), "name": payload.name, "id": user_id},
            )
            connection.commit()

        row = connection.execute(
            text("SELECT id, google_sub, github_id, auth_provider, role, is_guest, email, name, picture, is_active, is_admin, created_at, updated_at FROM users WHERE id = :id"),
            {"id": user_id},
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=500, detail="Unable to create or load user")

    return _issue_session(_build_user_from_row(row))


@router.post("/email/signup", response_model=AuthSessionResponse)
async def email_signup(payload: EmailSignupRequest) -> AuthSessionResponse:
    await verify_captcha_token(payload.captcha_token)
    init_db()

    with get_connection() as connection:
        existing = connection.execute(
            text("SELECT id FROM users WHERE email = :email"),
            {"email": str(payload.email)},
        ).fetchone()
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

        cursor = connection.execute(
            text(
                "INSERT INTO users (email, password_hash, name, auth_provider, role, is_guest, is_active, is_admin, created_at, updated_at)"
                " VALUES (:email, :password_hash, :name, 'email', 'user', 0, 1, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {
                "email": str(payload.email),
                "password_hash": _hash_password(payload.password),
                "name": payload.name,
            },
        )
        user_id = cursor.lastrowid
        connection.commit()

        row = connection.execute(
            text("SELECT id, google_sub, github_id, auth_provider, role, is_guest, email, name, picture, is_active, is_admin, created_at, updated_at FROM users WHERE id = :id"),
            {"id": user_id},
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=500, detail="Unable to create or load user")

    return _issue_session(_build_user_from_row(row))


@router.post("/email/login", response_model=AuthSessionResponse)
async def email_login(payload: EmailLoginRequest) -> AuthSessionResponse:
    await verify_captcha_token(payload.captcha_token)
    init_db()

    def _mapping_for_row(row):
        return row._mapping if hasattr(row, "_mapping") else row

    with get_connection() as connection:
        row = connection.execute(
            text("SELECT id, google_sub, github_id, auth_provider, role, is_guest, email, name, picture, is_active, is_admin, created_at, updated_at, password_hash FROM users WHERE email = :email"),
            {"email": str(payload.email)},
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    mapping = _mapping_for_row(row)
    if not _verify_password(payload.password, mapping["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    return _issue_session(_build_user_from_row(row))


@router.post("/github/login", response_model=AuthSessionResponse)
async def github_login(payload: GitHubLoginRequest) -> AuthSessionResponse:
    await verify_captcha_token(payload.captcha_token)
    init_db()

    with get_connection() as connection:
        existing = connection.execute(
            text("SELECT id, google_sub, github_id, auth_provider, role, is_guest, email, name, picture, is_active, is_admin, created_at, updated_at FROM users WHERE github_id = :github_id"),
            {"github_id": payload.github_id},
        ).fetchone()

        if existing is None:
            cursor = connection.execute(
                text(
                    "INSERT INTO users (github_id, email, name, picture, auth_provider, is_guest, is_active, is_admin, created_at, updated_at)"
                    " VALUES (:github_id, :email, :name, :picture, 'github', 0, 1, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {
                    "github_id": payload.github_id,
                    "email": str(payload.email) if payload.email else f"github-{payload.github_id}@example.com",
                    "name": payload.name,
                    "picture": None,
                },
            )
            user_id = cursor.lastrowid
            connection.commit()
        else:
            existing_mapping = existing._mapping if hasattr(existing, "_mapping") else existing
            user_id = existing_mapping["id"]
            connection.execute(
                text("UPDATE users SET email = COALESCE(:email, email), name = COALESCE(:name, name), updated_at = CURRENT_TIMESTAMP WHERE id = :id"),
                {"email": str(payload.email) if payload.email else None, "name": payload.name, "id": user_id},
            )
            connection.commit()

        row = connection.execute(
            text("SELECT id, google_sub, github_id, auth_provider, role, is_guest, email, name, picture, is_active, is_admin, created_at, updated_at FROM users WHERE id = :id"),
            {"id": user_id},
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=500, detail="Unable to create or load user")

    return _issue_session(_build_user_from_row(row))


@router.post("/guest", response_model=AuthSessionResponse)
async def guest_login(payload: GuestLoginRequest | None = None) -> AuthSessionResponse:
    await verify_captcha_token(payload.captcha_token if payload else None)
    init_db()

    with get_connection() as connection:
        email = f"guest-{int(datetime.now(timezone.utc).timestamp())}@example.com"
        cursor = connection.execute(
            text(
                "INSERT INTO users (email, name, auth_provider, role, is_guest, is_active, is_admin, created_at, updated_at)"
                " VALUES (:email, :name, 'guest', 'guest', 1, 1, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {
                "email": email,
                "name": payload.name if payload and payload.name else "Guest User",
            },
        )
        user_id = cursor.lastrowid
        connection.commit()

        row = connection.execute(
            text("SELECT id, google_sub, github_id, auth_provider, role, is_guest, email, name, picture, is_active, is_admin, created_at, updated_at FROM users WHERE id = :id"),
            {"id": user_id},
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=500, detail="Unable to create or load user")

    return _issue_session(_build_user_from_row(row))


@router.get("/google/authorize")
async def google_authorize() -> RedirectResponse:
    if not settings.google_oauth_client_id:
        raise HTTPException(status_code=503, detail="Google OAuth client ID is not configured")

    params = {
        "client_id": settings.google_oauth_client_id,
        "redirect_uri": settings.google_oauth_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
    }

    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}")


@router.get("/callback", response_model=AuthSessionResponse)
async def google_callback(code: str | None = Query(None)) -> AuthSessionResponse:
    if not code:
        raise HTTPException(status_code=400, detail="Missing Google authorization code")

    client_secret = settings.get_google_oauth_client_secret()
    if client_secret is None:
        raise HTTPException(status_code=503, detail="Google OAuth client secret is not configured")

    async with httpx.AsyncClient(timeout=20) as client:
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.google_oauth_client_id,
                "client_secret": client_secret,
                "redirect_uri": settings.google_oauth_redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    if token_resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Google token exchange failed: {token_resp.text}")

    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=502, detail="Google token response did not include access_token")

    async with httpx.AsyncClient(timeout=20) as client:
        user_resp = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if user_resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Google user info fetch failed: {user_resp.text}")

    user_info = user_resp.json()
    google_sub = user_info.get("sub")
    email = user_info.get("email")
    name = user_info.get("name") or user_info.get("email")
    picture = user_info.get("picture")

    if not google_sub or not email:
        raise HTTPException(status_code=502, detail="Google user info did not include required identifiers")

    init_db()
    with get_connection() as connection:
        existing = connection.execute(
            text("SELECT id FROM users WHERE google_sub = :google_sub"),
            {"google_sub": google_sub},
        ).fetchone()

        if existing is not None:
            existing_mapping = existing._mapping if hasattr(existing, "_mapping") else existing
            user_id = existing_mapping["id"]
            connection.execute(
                text("UPDATE users SET email = :email, name = :name, picture = :picture, updated_at = CURRENT_TIMESTAMP WHERE id = :id"),
                {"email": email, "name": name, "picture": picture, "id": user_id},
            )
            connection.commit()
        else:
            existing_by_email = connection.execute(
                text("SELECT id FROM users WHERE email = :email"),
                {"email": email},
            ).fetchone()

            if existing_by_email is not None:
                existing_mapping = existing_by_email._mapping if hasattr(existing_by_email, "_mapping") else existing_by_email
                user_id = existing_mapping["id"]
                connection.execute(
                    text(
                        "UPDATE users SET google_sub = :google_sub, name = :name, picture = :picture, updated_at = CURRENT_TIMESTAMP WHERE id = :id"
                    ),
                    {"google_sub": google_sub, "name": name, "picture": picture, "id": user_id},
                )
                connection.commit()
            else:
                cursor = connection.execute(
                    text(
                        "INSERT INTO users (google_sub, email, name, picture, auth_provider, role, is_guest, is_active, is_admin, created_at, updated_at)"
                        " VALUES (:google_sub, :email, :name, :picture, 'google', 'user', 0, 1, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    ),
                    {
                        "google_sub": google_sub,
                        "email": email,
                        "name": name,
                        "picture": picture,
                    },
                )
                user_id = cursor.lastrowid
                connection.commit()

        row = connection.execute(
            text("SELECT id, google_sub, github_id, auth_provider, role, is_guest, email, name, picture, is_active, is_admin, created_at, updated_at FROM users WHERE id = :id"),
            {"id": user_id},
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=500, detail="Unable to create or load user")

    return _issue_session(_build_user_from_row(row))


@router.get("/github/authorize")
async def github_authorize() -> RedirectResponse:
    if not settings.github_oauth_client_id:
        raise HTTPException(status_code=503, detail="GitHub OAuth client ID is not configured")

    params = {
        "client_id": settings.github_oauth_client_id,
        "redirect_uri": settings.github_oauth_redirect_uri,
        "scope": "read:user user:email",
        "allow_signup": "true",
    }

    return RedirectResponse(f"https://github.com/login/oauth/authorize?{urlencode(params)}")


@router.get("/github/callback", response_model=AuthSessionResponse)
async def github_callback(code: str | None = Query(None)) -> AuthSessionResponse:
    if not code:
        raise HTTPException(status_code=400, detail="Missing GitHub authorization code")

    client_secret = settings.get_github_oauth_client_secret()
    if client_secret is None:
        raise HTTPException(status_code=503, detail="GitHub OAuth client secret is not configured")

    async with httpx.AsyncClient(timeout=20) as client:
        token_resp = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_oauth_client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": settings.github_oauth_redirect_uri,
            },
        )

    if token_resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"GitHub token exchange failed: {token_resp.text}")

    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=502, detail="GitHub token response did not include access_token")

    async with httpx.AsyncClient(timeout=20) as client:
        user_resp = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
            },
        )

    if user_resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"GitHub user fetch failed: {user_resp.text}")

    user_info = user_resp.json()
    github_id = str(user_info.get("id"))
    name = user_info.get("name") or user_info.get("login")
    picture = user_info.get("avatar_url")
    email = user_info.get("email")

    if not email:
        async with httpx.AsyncClient(timeout=20) as client:
            email_resp = await client.get(
                "https://api.github.com/user/emails",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
            )
        if email_resp.status_code == 200:
            emails = email_resp.json()
            primary = next((item for item in emails if item.get("primary") and item.get("verified")), None)
            if primary:
                email = primary.get("email")

    if not github_id:
        raise HTTPException(status_code=502, detail="GitHub user info did not include an ID")

    if not email:
        email = f"github-{github_id}@github.example.com"

    init_db()
    with get_connection() as connection:
        existing = connection.execute(
            text("SELECT id FROM users WHERE github_id = :github_id"),
            {"github_id": github_id},
        ).fetchone()

        if existing is not None:
            existing_mapping = existing._mapping if hasattr(existing, "_mapping") else existing
            user_id = existing_mapping["id"]
            connection.execute(
                text("UPDATE users SET email = COALESCE(:email, email), name = COALESCE(:name, name), picture = COALESCE(:picture, picture), updated_at = CURRENT_TIMESTAMP WHERE id = :id"),
                {"email": email, "name": name, "picture": picture, "id": user_id},
            )
            connection.commit()
        else:
            existing_by_email = connection.execute(
                text("SELECT id FROM users WHERE email = :email"),
                {"email": email},
            ).fetchone()

            if existing_by_email is not None:
                existing_mapping = existing_by_email._mapping if hasattr(existing_by_email, "_mapping") else existing_by_email
                user_id = existing_mapping["id"]
                connection.execute(
                    text(
                        "UPDATE users SET github_id = :github_id, name = COALESCE(:name, name), picture = COALESCE(:picture, picture), updated_at = CURRENT_TIMESTAMP WHERE id = :id"
                    ),
                    {"github_id": github_id, "name": name, "picture": picture, "id": user_id},
                )
                connection.commit()
            else:
                cursor = connection.execute(
                    text(
                        "INSERT INTO users (github_id, email, name, picture, auth_provider, role, is_guest, is_active, is_admin, created_at, updated_at)"
                        " VALUES (:github_id, :email, :name, :picture, 'github', 'user', 0, 1, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    ),
                    {
                        "github_id": github_id,
                        "email": email,
                        "name": name,
                        "picture": picture,
                    },
                )
                user_id = cursor.lastrowid
                connection.commit()

        row = connection.execute(
            text("SELECT id, google_sub, github_id, auth_provider, role, is_guest, email, name, picture, is_active, is_admin, created_at, updated_at FROM users WHERE id = :id"),
            {"id": user_id},
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=500, detail="Unable to create or load user")

    return _issue_session(_build_user_from_row(row))


@router.post("/logout")
async def logout(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security_scheme)],
) -> dict[str, str]:
    if credentials is None or not credentials.scheme.lower() == "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    claims = verify_access_token(token)
    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    init_db()
    with get_connection() as connection:
        connection.execute(
            text("DELETE FROM auth_sessions WHERE token_hash = :token_hash"),
            {"token_hash": token_hash},
        )
        connection.commit()

    return {"detail": "Logged out successfully"}


@router.get("/me", response_model=UserRead)
async def get_me(current_user: Annotated[User, Depends(get_current_user)]) -> UserRead:
    return UserRead(**current_user.__dict__)
