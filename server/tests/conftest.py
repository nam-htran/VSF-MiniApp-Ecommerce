import socket
import threading
import time
from urllib.parse import urlparse

import pytest
import pytest_asyncio
import uvicorn
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

SERVER_PORT = 4900

# Seed accounts in mock-openAPI. No role attached — roles are earned in
# V-Market, not handed out by V-App.
USER_A_ID = "11111111-1111-4111-8111-111111111111"
USER_B_ID = "22222222-2222-4222-8222-222222222222"
USER_C_ID = "33333333-3333-4333-8333-333333333333"


def _reachable(url: str) -> bool:
    parsed = urlparse(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((parsed.hostname, port), timeout=3):
            return True
    except OSError:
        return False


def _throwaway_engine():
    """A short-lived engine for test bookkeeping.

    The app's engine is shared with the uvicorn thread, which runs its own
    event loop; an asyncpg pool cannot be used from two loops. So tests get
    their own NullPool engine and dispose it right away.
    """
    from app.config import settings

    return create_async_engine(settings.database_url, poolclass=NullPool)


@pytest.fixture(scope="session", autouse=True)
def require_vapp():
    """mock-openAPI is a separate program, so tests need it already running.

    Deliberately not booted from here: the point is that the gateway reaches
    V-App over the network, exactly as it will against the real API.
    """
    from app.config import settings

    if not _reachable(settings.vapp_base_url):
        pytest.skip(
            f"No V-App at {settings.vapp_base_url}. Start it with:\n"
            "  cd mock-openAPI && "
            ".venv\\Scripts\\python.exe -m uvicorn main:app --port 4001",
            allow_module_level=True,
        )


# Not autouse: the contract tests only exercise the gateway against
# mock-openAPI and never touch the database, so they must keep running even
# with no database around.
@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def prepare_db(require_vapp):
    from app.db import Base

    # Import registers each model on Base before create_all runs.
    from app.addresses import store as _addresses  # noqa: F401
    from app.orders import store as _orders  # noqa: F401
    from app.products import store as _products  # noqa: F401
    from app.reviews import store as _reviews  # noqa: F401
    from app.shops import store as _shops  # noqa: F401
    from app.users import store as _users  # noqa: F401

    engine = _throwaway_engine()
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except OSError as error:
        pytest.skip(
            f"No database reachable: {error}\n"
            "Start it with:  docker compose up -d",
            allow_module_level=True,
        )
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def clean_db(prepare_db):
    """Each test starts with empty tables.

    Truncating rather than rolling back: the app runs in another thread with
    its own sessions, so a test-side transaction would not isolate it.
    CASCADE because shops reference users.
    """
    engine = _throwaway_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE order_items, shop_orders, orders,"
                " products, shops, users CASCADE"
            )
        )
    await engine.dispose()
    yield


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
