"""Database connection, session management, and table initialization."""

from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from backend.app.config import get_settings

settings = get_settings()

# SQLite requires check_same_thread=False for FastAPI concurrency
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy models."""
    pass


def get_db() -> Generator[Session, None, None]:
    """Dependency that yields a database session and safely closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Initialize database tables, ensure directories exist, and apply lightweight schema updates."""
    settings.ensure_directories()
    # Import models to register them with Base.metadata before create_all
    import backend.app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)

    # Lightweight automatic schema migration for SQLite development
    if settings.database_url.startswith("sqlite"):
      try:
        with engine.connect() as conn:
          raw_conn = conn.connection
          cursor = raw_conn.cursor()
          cursor.execute("PRAGMA table_info(documents)")
          cols = [row[1] for row in cursor.fetchall()]
          if cols and "extracted_text" not in cols:
            cursor.execute("ALTER TABLE documents ADD COLUMN extracted_text TEXT")
            raw_conn.commit()
      except Exception:
        pass
