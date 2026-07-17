from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class User:
    id: int
    google_sub: str | None
    email: str
    name: str | None
    picture: str | None
    is_active: bool
    is_admin: bool
    role: str
    created_at: datetime
    updated_at: datetime
    github_id: str | None = None
    auth_provider: str = "email"
    is_guest: bool = False
