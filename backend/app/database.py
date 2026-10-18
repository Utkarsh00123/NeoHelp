from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from app.config import settings

import urllib.parse

# Robustly normalize DATABASE_URL for asyncpg (strips unsupported query parameters like channel_binding and translates sslmode to ssl)
raw_db_url = str(settings.DATABASE_URL).strip().strip("'").strip('"')
parsed = urllib.parse.urlsplit(raw_db_url)
query_params = urllib.parse.parse_qs(parsed.query)

# Filter query params for asyncpg compatibility
valid_asyncpg_query_params = {'ssl', 'server_settings', 'timeout', 'command_timeout'}
cleaned_query = {}
for k, v in query_params.items():
    if k in ('sslmode', 'ssl'):
        cleaned_query['ssl'] = 'require'
    elif k in valid_asyncpg_query_params:
        cleaned_query[k] = v[0]

new_query_str = urllib.parse.urlencode(cleaned_query)
# Ensure scheme is postgresql+asyncpg
scheme = parsed.scheme
if scheme in ("postgres", "postgresql"):
    scheme = "postgresql+asyncpg"

db_url = urllib.parse.urlunsplit((scheme, parsed.netloc, parsed.path, new_query_str, parsed.fragment))

# Engine configuration
engine = create_async_engine(
    db_url,
    echo=(settings.ENVIRONMENT == "development"),
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True
)

# Async session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

Base = declarative_base()

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
