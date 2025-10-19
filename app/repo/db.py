from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from contextlib import asynccontextmanager
import os

DATABASE_URL = f"postgresql+asyncpg://{os.getenv('DATABASE_USER')}:{os.getenv('DATABASE_PASSWORD')}@{os.getenv('DATABASE_HOST')}/{os.getenv('DATABASE_NAME')}"

engine: AsyncEngine = create_async_engine(
    DATABASE_URL, 
    echo=False, 
    pool_size=20, 
    max_overflow=20,
    pool_recycle=3600,
    pool_pre_ping=True
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()

@asynccontextmanager
async def get_session():
    async with SessionLocal() as session:
        yield session

async def close_db():
    """Close database engine and all connections"""
    await engine.dispose()
