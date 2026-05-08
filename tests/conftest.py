import sqlite3
import pytest
import sqlite_vec
from httpx import AsyncClient, ASGITransport

from src.backend.database import init_db
from src.backend.cost import seed_pricing


@pytest.fixture
def db_conn():
    """In-memory SQLite connection with schema and pricing seeds loaded."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.load_extension(sqlite_vec.loadable_path())
    init_db(conn)
    seed_pricing(conn)
    return conn


@pytest.fixture
async def async_client(db_conn):
    """AsyncClient wired to the FastAPI app with the test DB injected."""
    import src.backend.main as main_module

    original_conn = main_module._conn
    main_module._conn = db_conn

    transport = ASGITransport(app=main_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    main_module._conn = original_conn
