from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

class UserRead(BaseModel):
    id: int
    email: EmailStr
    name: str | None = None
    picture: str | None = None
    is_active: bool
    is_admin: bool
    role: str
    created_at: datetime
    updated_at: datetime
    auth_provider: str = "email"
    is_guest: bool = False

class AuthSessionResponse(BaseModel):
    access_token: str = Field(..., description="Opaque bearer token issued by this backend")
    token_type: str = "bearer"
    expires_at: datetime
    user: UserRead
