from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


DATABASE_PATH = Path(__file__).resolve().parent.parent / "iot.db"
engine = create_async_engine(f"sqlite+aiosqlite:///{DATABASE_PATH}", echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def create_database() -> None:
    from app.models import Base

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
