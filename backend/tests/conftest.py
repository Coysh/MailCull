import pytest

from mailcull import db, unsubscribe


@pytest.fixture
async def temp_db(tmp_path):
    db.init_db_path(tmp_path / "test.db")
    await db.migrate()
    await db.create_scan(365)  # scan 1
    await db.create_scan(365)  # scan 2 (senders reference scans by FK)
    yield db


@pytest.fixture(autouse=True)
def no_retry_delay(monkeypatch):
    monkeypatch.setattr(unsubscribe, "_RETRY_BASE_DELAY", 0.0)
