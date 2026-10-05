from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_async_engine(settings.database_url, echo=settings.app_debug, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def _ensure_scheduled_enum(conn) -> None:
    """Add recoverystatus.scheduled if the enum already existed from earlier boots."""
    await conn.execute(
        text(
            """
            DO $$
            BEGIN
              IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'recoverystatus') THEN
                ALTER TYPE recoverystatus ADD VALUE IF NOT EXISTS 'scheduled';
              END IF;
            END
            $$;
            """
        )
    )


async def _ensure_payment_id_unique(conn) -> None:
    """Best-effort unique index for existing DBs (skips if duplicates already exist)."""
    await conn.execute(
        text(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM pg_indexes WHERE indexname = 'uq_recovery_runs_payment_id'
              ) THEN
                BEGIN
                  CREATE UNIQUE INDEX uq_recovery_runs_payment_id ON recovery_runs (payment_id);
                EXCEPTION WHEN unique_violation THEN
                  RAISE NOTICE 'uq_recovery_runs_payment_id skipped — duplicate payment_ids exist';
                END;
              END IF;
            END
            $$;
            """
        )
    )


async def init_db() -> None:
    from db import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_scheduled_enum(conn)
        await _ensure_payment_id_unique(conn)
