"""PostgreSQL connection pool.

Uses asyncpg for non-blocking I/O. The pool is initialized on app startup
and closed on shutdown. Each request borrows a connection from the pool.
"""
from __future__ import annotations

import asyncpg

from app.config import settings

_pool: asyncpg.Pool | None = None

async def init_pool() -> None:
    """Create the connection pool. Called once on app startup."""
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=2,
        max_size=10,
        command_timeout=5,
    )

async def close_pool() -> None:
    """Close the pool. Called once on app shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None

def get_pool() -> asyncpg.Pool:
    """Return the current pool. Raises if init_pool hasn't been called."""
    if _pool is None:
        raise RuntimeError("database pool not initialized — call init_pool() first")
    return _pool

async def init_schema() -> None:
    """Create the orders table if it doesn't exist. Idempotent."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id UUID PRIMARY KEY,
                customer_email TEXT NOT NULL,
                items JSONB NOT NULL,
                subtotal_cents INTEGER NOT NULL,
                shipping_cents INTEGER NOT NULL,
                total_cents INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'confirmed',
                payment_id TEXT,
                tracking_number TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_email)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at DESC)"
        )
