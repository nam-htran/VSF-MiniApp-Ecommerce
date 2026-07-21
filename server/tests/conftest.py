import socket
import threading
import time
from urllib.parse import urlparse

import pytest
import uvicorn

SERVER_PORT = 4900

BUYER_ID = "11111111-1111-4111-8111-111111111111"
SELLER_A_ID = "22222222-2222-4222-8222-222222222222"


def _reachable(url: str) -> bool:
    parsed = urlparse(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((parsed.hostname, port), timeout=2):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session", autouse=True)
def require_vapp():
    """mock-openAPI is a separate program, so tests need it already running.

    Deliberately not imported and booted from here: the whole point is
    that the gateway reaches V-App over the network, exactly as it will
    against the real API.
    """
    from app.config import settings

    if not _reachable(settings.vapp_base_url):
        pytest.skip(
            f"No V-App at {settings.vapp_base_url}. Start it with:\n"
            "  cd mock-openAPI && "
            ".venv\\Scripts\\python.exe -m uvicorn main:app --port 4001",
            allow_module_level=True,
        )


@pytest.fixture(scope="session")
def base_url(require_vapp):
    """Run the V-Market backend for tests that call its own endpoints."""
    from app.main import create_app

    config = uvicorn.Config(
        create_app(), host="127.0.0.1", port=SERVER_PORT, log_level="warning"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 15
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        raise RuntimeError("Test server did not start in time")

    yield f"http://127.0.0.1:{SERVER_PORT}"

    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture(autouse=True)
def clean_users():
    from app.users.store import reset

    reset()
    yield
