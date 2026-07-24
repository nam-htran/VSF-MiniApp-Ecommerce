from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


# The pool has to be at least as wide as the checkouts that can be in
# flight at once. A checkout holds its connection while it waits on a stock
# row lock, so twenty buyers racing for the same product occupy twenty
# connections for as long as the slowest one takes. SQLAlchemy's default of
# 5 + 10 overflow ran out at exactly that point and the surplus requests
# failed on connection checkout rather than queueing — found by LOAD-02.
#
# pool_timeout keeps a genuine overload from hanging for ever: past this,
# a request fails fast with a clear error instead of holding the client.
engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=25,
    max_overflow=25,
    pool_timeout=20,
)

SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session
