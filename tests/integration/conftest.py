"""
Fixtures shared across integration test modules.

All integration fixtures use isolated, temporary resources so they can never
touch the real user database or production Azure project.
"""
import os
import sqlite3
import subprocess
import tempfile
import time
import pytest
import httpx
import sqlite_vec

from src.backend.database import init_db
from src.backend.cost import seed_pricing


# ---------------------------------------------------------------------------
# SQLite file fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def integration_db_path(tmp_path):
    """Return a path to a fresh SQLite file inside a pytest-managed temp dir."""
    return tmp_path / "test-local-assist.db"


@pytest.fixture
def integration_db(integration_db_path):
    """Open a real SQLite file connection with the full schema seeded."""
    conn = sqlite3.connect(str(integration_db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.load_extension(sqlite_vec.loadable_path())
    init_db(conn)
    seed_pricing(conn)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Live Ollama fixture
# ---------------------------------------------------------------------------

def _ollama_running() -> bool:
    try:
        r = httpx.get("http://localhost:11434/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="session")
def require_ollama():
    """Skip the entire test if Ollama is not reachable."""
    if not _ollama_running():
        pytest.skip("Ollama is not running — skipping Ollama integration tests")


@pytest.fixture
def ollama_base_url():
    return "http://localhost:11434"


# ---------------------------------------------------------------------------
# Live server fixture (Ollama-backed FastAPI)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def live_server(tmp_path_factory):
    """
    Spin up the FastAPI sidecar against a temp DB, pointed at local Ollama.
    Yields the base URL.  The process is terminated after the session.
    """
    if not _ollama_running():
        pytest.skip("Ollama is not running — skipping live server tests")

    db_dir = tmp_path_factory.mktemp("live_server_db")
    db_path = db_dir / "integration.db"
    port = 18799

    env = os.environ.copy()
    env["LOCAL_ASSIST_DB_PATH"] = str(db_path)
    # Disable Azure so the server always falls back to Ollama.
    # Clear both endpoint vars so azure._base() returns the unreachable address.
    env["AZURE_API_KEY"] = "integration-test-disabled"
    env["AZURE_OPENAI_ENDPOINT"] = "http://127.0.0.1:0"
    env["AZURE_INFERENCE_ENDPOINT"] = "http://127.0.0.1:0"

    proc = subprocess.Popen(
        [".venv/bin/python", "-m", "uvicorn", "src.backend.main:app",
         "--port", str(port), "--log-level", "warning"],
        env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    )

    # Wait for the server to be ready (up to 10 s)
    base_url = f"http://127.0.0.1:{port}"
    for _ in range(40):
        try:
            httpx.get(f"{base_url}/v1/health", timeout=1)
            break
        except Exception:
            time.sleep(0.25)
    else:
        proc.terminate()
        pytest.fail("Live server did not become ready in time")

    yield base_url

    proc.terminate()
    proc.wait(timeout=5)


# ---------------------------------------------------------------------------
# Azure credential fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def require_azure():
    """Skip if Azure credentials are not configured or endpoint is a test stub."""
    key = os.getenv("AZURE_API_KEY", "")
    if not key or key == "integration-test-disabled":
        pytest.skip("Azure credentials not set — skipping Azure contract tests")
    # Check both endpoint vars that azure._base() reads
    for var in ("AZURE_INFERENCE_ENDPOINT", "AZURE_OPENAI_ENDPOINT"):
        endpoint = os.getenv(var, "")
        if "127.0.0.1" in endpoint or "localhost" in endpoint:
            pytest.skip(f"{var} points to localhost — looks like a test override")
