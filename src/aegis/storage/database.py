"""Database connection and migration management.

Supports two backends:
- SQLite (development): DATABASE_URL not set or starts with "sqlite"
- PostgreSQL (production): DATABASE_URL starts with "postgresql"

Both backends expose the same interface: execute, fetchone, fetchall, commit.
SQL uses $1/$2 parameter style (PostgreSQL native). For SQLite, parameters
are auto-converted from $N to ? style.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from ..utils.errors import StorageError
from ..utils.logging import get_logger

logger = get_logger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _pg_to_sqlite_params(sql: str, params: tuple[object, ...]) -> tuple[str, tuple[object, ...]]:
    """Convert $1, $2 style placeholders to ? style for SQLite."""
    converted = re.sub(r'\$\d+', '?', sql)
    return converted, params


def _coerce_params_for_pg(params: tuple[object, ...]) -> tuple[object, ...]:
    """Convert ISO string timestamps to datetime objects for asyncpg."""
    result = []
    for p in params:
        if isinstance(p, str) and len(p) >= 19 and p[4:5] == '-' and p[10:11] == 'T':
            try:
                result.append(datetime.fromisoformat(p))
                continue
            except (ValueError, TypeError):
                pass
        result.append(p)
    return tuple(result)


class Database:
    """Async database wrapper supporting SQLite and PostgreSQL."""

    def __init__(
        self,
        database_url: str = "",
        db_path: str | Path = "data/aegis.db",
        wal_mode: bool = True,
        pool_min: int = 2,
        pool_max: int = 10,
    ) -> None:
        self._database_url = database_url
        self._db_path = Path(db_path)
        self._wal_mode = wal_mode
        self._pool_min = pool_min
        self._pool_max = pool_max

        self._backend: str = "sqlite"
        self._sqlite_conn: Any = None
        self._pg_pool: Any = None

        if database_url and database_url.startswith("postgresql"):
            self._backend = "postgresql"

    @property
    def backend(self) -> str:
        return self._backend

    async def connect(self) -> None:
        """Open the database connection and run migrations."""
        if self._backend == "postgresql":
            await self._connect_pg()
        else:
            await self._connect_sqlite()

        await self._run_migrations()
        logger.info("Database connected", backend=self._backend)

    async def _connect_sqlite(self) -> None:
        import aiosqlite
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._sqlite_conn = await aiosqlite.connect(str(self._db_path))
        self._sqlite_conn.row_factory = aiosqlite.Row
        if self._wal_mode:
            await self._sqlite_conn.execute("PRAGMA journal_mode=WAL")
        await self._sqlite_conn.execute("PRAGMA foreign_keys=ON")
        await self._sqlite_conn.execute("PRAGMA synchronous=NORMAL")

    async def _connect_pg(self) -> None:
        import asyncpg
        self._pg_pool = await asyncpg.create_pool(
            self._database_url,
            min_size=self._pool_min,
            max_size=self._pool_max,
            command_timeout=30,
            init=self._pg_init_connection,
        )

    @staticmethod
    async def _pg_init_connection(conn: Any) -> None:
        """Set up JSON codec so asyncpg accepts plain strings for JSONB columns."""
        await conn.set_type_codec(
            'jsonb', encoder=str, decoder=json.loads,
            schema='pg_catalog', format='text',
        )
        await conn.set_type_codec(
            'json', encoder=str, decoder=json.loads,
            schema='pg_catalog', format='text',
        )

    async def close(self) -> None:
        """Close the database connection."""
        if self._backend == "postgresql" and self._pg_pool:
            await self._pg_pool.close()
            self._pg_pool = None
        elif self._sqlite_conn:
            await self._sqlite_conn.close()
            self._sqlite_conn = None
        logger.info("Database disconnected")

    async def execute(self, sql: str, params: tuple[object, ...] = ()) -> Any:
        """Execute a SQL statement."""
        if self._backend == "postgresql":
            async with self._pg_pool.acquire() as conn:
                return await conn.execute(sql, *_coerce_params_for_pg(params))
        else:
            s, p = _pg_to_sqlite_params(sql, params)
            return await self._sqlite_conn.execute(s, p)

    async def fetchone(self, sql: str, params: tuple[object, ...] = ()) -> Any | None:
        """Fetch a single row as a dict-like object."""
        if self._backend == "postgresql":
            async with self._pg_pool.acquire() as conn:
                row = await conn.fetchrow(sql, *_coerce_params_for_pg(params))
                return dict(row) if row else None
        else:
            s, p = _pg_to_sqlite_params(sql, params)
            async with self._sqlite_conn.execute(s, p) as cursor:
                return await cursor.fetchone()

    async def fetchall(self, sql: str, params: tuple[object, ...] = ()) -> list[Any]:
        """Fetch all rows."""
        if self._backend == "postgresql":
            async with self._pg_pool.acquire() as conn:
                rows = await conn.fetch(sql, *_coerce_params_for_pg(params))
                return [dict(r) for r in rows]
        else:
            s, p = _pg_to_sqlite_params(sql, params)
            async with self._sqlite_conn.execute(s, p) as cursor:
                return await cursor.fetchall()

    async def commit(self) -> None:
        """Commit (SQLite only — PostgreSQL auto-commits)."""
        if self._backend == "sqlite" and self._sqlite_conn:
            await self._sqlite_conn.commit()

    async def _run_migrations(self) -> None:
        """Run SQL migration files in order."""
        # Use the correct migrations subdirectory
        migrations_subdir = "pg" if self._backend == "postgresql" else "sqlite"
        migrations_path = MIGRATIONS_DIR / migrations_subdir

        if not migrations_path.exists():
            # Fallback to root migrations dir (backward compat)
            migrations_path = MIGRATIONS_DIR

        # Create schema_migrations table
        if self._backend == "postgresql":
            async with self._pg_pool.acquire() as conn:
                await conn.execute(
                    """CREATE TABLE IF NOT EXISTS schema_migrations (
                        version TEXT PRIMARY KEY,
                        applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )"""
                )
        else:
            await self._sqlite_conn.execute(
                """CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
                )"""
            )
            await self._sqlite_conn.commit()

        migration_files = sorted(migrations_path.glob("*.sql"))
        for migration_file in migration_files:
            version = migration_file.stem

            # Check if already applied
            if self._backend == "postgresql":
                async with self._pg_pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT version FROM schema_migrations WHERE version = $1", version
                    )
                    if row is None:
                        sql = migration_file.read_text(encoding="utf-8")
                        await conn.execute(sql)
                        await conn.execute(
                            "INSERT INTO schema_migrations (version) VALUES ($1)", version
                        )
                        logger.debug("Applied migration", version=version)
            else:
                async with self._sqlite_conn.execute(
                    "SELECT version FROM schema_migrations WHERE version = ?", (version,)
                ) as cursor:
                    row = await cursor.fetchone()

                if row is None:
                    sql = migration_file.read_text(encoding="utf-8")
                    await self._sqlite_conn.executescript(sql)
                    await self._sqlite_conn.execute(
                        "INSERT INTO schema_migrations (version) VALUES (?)", (version,)
                    )
                    await self._sqlite_conn.commit()
                    logger.debug("Applied migration", version=version)

    def json_encode(self, obj: object) -> str:
        """Encode object to JSON string."""
        return json.dumps(obj)

    def json_decode(self, s: str | None) -> object:
        """Decode JSON string."""
        if s is None:
            return None
        try:
            return json.loads(s)
        except (json.JSONDecodeError, TypeError):
            return s


# Module-level singleton
_db: Database | None = None


def get_db_instance() -> Database:
    """Get the module-level database instance."""
    global _db
    if _db is None:
        raise StorageError("Database not initialized")
    return _db


def set_db_instance(db: Database) -> None:
    """Set the module-level database instance."""
    global _db
    _db = db
