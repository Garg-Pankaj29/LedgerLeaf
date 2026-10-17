"""Tests for application startup and database initialization."""

from pathlib import Path
from sqlalchemy import inspect
from backend.app.config import get_settings
from backend.app.database import init_db, engine, Base


def test_settings_ensures_directories():
    """Verify that configuration automatically creates runtime data directories."""
    settings = get_settings()
    settings.ensure_directories()
    assert Path(settings.data_dir).exists()
    assert Path(settings.upload_dir).exists()


def test_database_initialization():
    """Verify that init_db creates all expected tables."""
    init_db()
    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    assert "documents" in table_names
    assert "extraction_results" in table_names
    assert "field_provenance" in table_names
    assert "ledger_entries" in table_names
