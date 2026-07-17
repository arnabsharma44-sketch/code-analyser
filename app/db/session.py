from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    text,
)
from sqlalchemy.engine import Engine

from app.core.config import settings

metadata = MetaData()

users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("google_sub", String(255), unique=True),
    Column("github_id", String(255), unique=True),
    Column("password_hash", String(255)),
    Column("auth_provider", String(50), nullable=False, server_default="email"),
    Column("role", String(50), nullable=False, server_default="user"),
    Column("is_guest", Boolean, nullable=False, server_default=text("0")),
    Column("email", String(320), nullable=False, unique=True),
    Column("name", String(255)),
    Column("picture", String(512)),
    Column("is_active", Boolean, nullable=False, server_default=text("1")),
    Column("is_admin", Boolean, nullable=False, server_default=text("0")),
    Column("created_at", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
)

auth_sessions = Table(
    "auth_sessions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("token_hash", String(255), nullable=False, unique=True),
    Column("expires_at", DateTime, nullable=False),
    Column("created_at", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
)

saved_analyses = Table(
    "saved_analyses",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("code", Text, nullable=False),
    Column("filename", String(255)),
    Column("language", String(64)),
    Column("summary", Text),
    Column("nodes_json", Text),
    Column("edges_json", Text),
    Column("diagnostics_json", Text),
    Column("fixed_code", Text),
    Column("created_at", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
)

_engine: Engine | None = None


def _get_sqlite_url() -> str:
    database_path = Path(settings.database_path)
    if database_path.parent != Path("."):
        database_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{database_path}"


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        database_url = settings.get_database_url() if settings.database_url else _get_sqlite_url()
        connect_args = {}
        if database_url.startswith("sqlite"):
            connect_args = {"check_same_thread": False}
        _engine = create_engine(database_url, future=True, connect_args=connect_args)
    return _engine


def get_connection():
    return get_engine().connect()


def init_db() -> None:
    engine = get_engine()
    metadata.create_all(engine)
