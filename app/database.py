import aiosqlite
from contextlib import asynccontextmanager
from typing import AsyncGenerator
import secrets

from .config import get_settings

settings = get_settings()

SCHEMA = """
-- Users table
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    api_key TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Usage records
CREATE TABLE IF NOT EXISTS usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_tokens INTEGER NOT NULL,
    completion_tokens INTEGER NOT NULL,
    total_tokens INTEGER NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Rate limits (set by admin)
CREATE TABLE IF NOT EXISTS rate_limits (
    user_id TEXT PRIMARY KEY,
    requests_per_minute INTEGER,
    requests_per_day INTEGER,
    tokens_per_minute INTEGER,
    tokens_per_day INTEGER,
    total_token_limit INTEGER,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Model pricing
CREATE TABLE IF NOT EXISTS model_pricing (
    model TEXT PRIMARY KEY,
    input_cost_per_million REAL NOT NULL DEFAULT 0.0,
    output_cost_per_million REAL NOT NULL DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Pricing history (audit log)
CREATE TABLE IF NOT EXISTS pricing_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model TEXT NOT NULL,
    input_cost_per_million REAL NOT NULL,
    output_cost_per_million REAL NOT NULL,
    changed_by TEXT NOT NULL DEFAULT 'admin',
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_usage_user_id ON usage(user_id);
CREATE INDEX IF NOT EXISTS idx_usage_timestamp ON usage(timestamp);
CREATE INDEX IF NOT EXISTS idx_usage_user_timestamp ON usage(user_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_users_api_key ON users(api_key);
CREATE INDEX IF NOT EXISTS idx_pricing_history_model ON pricing_history(model);
CREATE INDEX IF NOT EXISTS idx_pricing_history_changed_at ON pricing_history(changed_at);
"""


async def init_db() -> None:
    """Initialize the database with schema."""
    async with aiosqlite.connect(settings.database_path) as db:
        await db.executescript(SCHEMA)

        # Migrations - Add cost column to usage table
        try:
            await db.execute("ALTER TABLE usage ADD COLUMN cost REAL DEFAULT 0.0")
            await db.commit()
        except aiosqlite.OperationalError:
            # Column already exists
            pass

        # Migrations - Add request_id column to usage table
        try:
            await db.execute("ALTER TABLE usage ADD COLUMN request_id TEXT DEFAULT NULL")
            await db.commit()
        except aiosqlite.OperationalError:
            # Column already exists
            pass


@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Get a database connection."""
    db = await aiosqlite.connect(settings.database_path)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()


def generate_api_key(user_id: str) -> str:
    """Generate an API key for a user."""
    random_part = secrets.token_hex(16)
    return f"sk-{user_id}-{random_part}"


async def create_user(user_id: str) -> tuple[str, str]:
    """Create a new user and return (user_id, api_key)."""
    api_key = generate_api_key(user_id)
    settings = get_settings()

    async with get_db() as db:
        await db.execute(
            "INSERT INTO users (id, api_key) VALUES (?, ?)",
            (user_id, api_key),
        )
        await db.execute(
            """INSERT INTO rate_limits
               (user_id, requests_per_minute, requests_per_day,
                tokens_per_minute, tokens_per_day, total_token_limit)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                settings.default_requests_per_minute,
                settings.default_requests_per_day,
                settings.default_tokens_per_minute,
                settings.default_tokens_per_day,
                settings.default_total_token_limit,
            ),
        )
        await db.commit()

    return user_id, api_key


async def get_user_by_api_key(api_key: str) -> dict | None:
    """Get user by API key."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, api_key, created_at FROM users WHERE api_key = ?",
            (api_key,),
        )
        row = await cursor.fetchone()
        if row:
            return {"id": row["id"], "api_key": row["api_key"], "created_at": row["created_at"]}
        return None


async def get_user_by_id(user_id: str) -> dict | None:
    """Get user by ID."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, api_key, created_at FROM users WHERE id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        if row:
            return {"id": row["id"], "api_key": row["api_key"], "created_at": row["created_at"]}
        return None


async def get_all_users() -> list[dict]:
    """Get all users."""
    async with get_db() as db:
        cursor = await db.execute("SELECT id, api_key, created_at FROM users")
        rows = await cursor.fetchall()
        return [{"id": row["id"], "api_key": row["api_key"], "created_at": row["created_at"]} for row in rows]


async def delete_all_users() -> int:
    """Delete all users, their rate limits, and usage records. Returns count of deleted users."""
    async with get_db() as db:
        cursor = await db.execute("SELECT COUNT(*) as count FROM users")
        row = await cursor.fetchone()
        count = row["count"]
        await db.execute("DELETE FROM usage")
        await db.execute("DELETE FROM rate_limits")
        await db.execute("DELETE FROM users")
        await db.commit()
        return count


async def delete_user(user_id: str) -> bool:
    """Delete a user and their rate limits."""
    async with get_db() as db:
        cursor = await db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        await db.execute("DELETE FROM rate_limits WHERE user_id = ?", (user_id,))
        await db.commit()
        return cursor.rowcount > 0


async def get_rate_limits(user_id: str) -> dict | None:
    """Get rate limits for a user."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT requests_per_minute, requests_per_day,
                      tokens_per_minute, tokens_per_day, total_token_limit
               FROM rate_limits WHERE user_id = ?""",
            (user_id,),
        )
        row = await cursor.fetchone()
        if row:
            return {
                "requests_per_minute": row["requests_per_minute"],
                "requests_per_day": row["requests_per_day"],
                "tokens_per_minute": row["tokens_per_minute"],
                "tokens_per_day": row["tokens_per_day"],
                "total_token_limit": row["total_token_limit"],
            }
        return None


async def update_rate_limits(
    user_id: str,
    requests_per_minute: int | None = None,
    requests_per_day: int | None = None,
    tokens_per_minute: int | None = None,
    tokens_per_day: int | None = None,
    total_token_limit: int | None = None,
) -> bool:
    """Update rate limits for a user."""
    async with get_db() as db:
        # Build update query dynamically
        updates = []
        params = []

        if requests_per_minute is not None:
            updates.append("requests_per_minute = ?")
            params.append(requests_per_minute)
        if requests_per_day is not None:
            updates.append("requests_per_day = ?")
            params.append(requests_per_day)
        if tokens_per_minute is not None:
            updates.append("tokens_per_minute = ?")
            params.append(tokens_per_minute)
        if tokens_per_day is not None:
            updates.append("tokens_per_day = ?")
            params.append(tokens_per_day)
        if total_token_limit is not None:
            updates.append("total_token_limit = ?")
            params.append(total_token_limit)

        if not updates:
            return False

        params.append(user_id)
        query = f"UPDATE rate_limits SET {', '.join(updates)} WHERE user_id = ?"

        cursor = await db.execute(query, params)
        await db.commit()
        return cursor.rowcount > 0


async def record_usage(
    user_id: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    cost: float = 0.0,
    request_id: str | None = None,
) -> None:
    """Record token usage for a request."""
    async with get_db() as db:
        await db.execute(
            """INSERT INTO usage (user_id, model, prompt_tokens, completion_tokens, total_tokens, cost, request_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, model, prompt_tokens, completion_tokens, total_tokens, cost, request_id),
        )
        await db.commit()


async def get_usage_stats(user_id: str) -> dict:
    """Get usage statistics for a user."""
    async with get_db() as db:
        # Total usage
        cursor = await db.execute(
            """SELECT COALESCE(SUM(total_tokens), 0) as total_tokens,
                      COALESCE(SUM(prompt_tokens), 0) as prompt_tokens,
                      COALESCE(SUM(completion_tokens), 0) as completion_tokens,
                      COALESCE(SUM(cost), 0.0) as total_cost,
                      COUNT(*) as request_count
               FROM usage WHERE user_id = ?""",
            (user_id,),
        )
        row = await cursor.fetchone()
        total_stats = {
            "total_tokens": row["total_tokens"],
            "prompt_tokens": row["prompt_tokens"],
            "completion_tokens": row["completion_tokens"],
            "total_cost": row["total_cost"],
            "request_count": row["request_count"],
        }

        # Usage by model
        cursor = await db.execute(
            """SELECT model,
                      COALESCE(SUM(total_tokens), 0) as total_tokens,
                      COALESCE(SUM(prompt_tokens), 0) as prompt_tokens,
                      COALESCE(SUM(completion_tokens), 0) as completion_tokens,
                      COALESCE(SUM(cost), 0.0) as total_cost,
                      COUNT(*) as request_count
               FROM usage WHERE user_id = ?
               GROUP BY model""",
            (user_id,),
        )
        rows = await cursor.fetchall()
        by_model = {
            row["model"]: {
                "total_tokens": row["total_tokens"],
                "prompt_tokens": row["prompt_tokens"],
                "completion_tokens": row["completion_tokens"],
                "total_cost": row["total_cost"],
                "request_count": row["request_count"],
            } for row in rows
        }

        return {**total_stats, "by_model": by_model}


async def get_requests_in_window(user_id: str, window_seconds: int) -> int:
    """Get number of requests in the last N seconds."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT COUNT(*) as count FROM usage
               WHERE user_id = ? AND timestamp > datetime('now', ?)""",
            (user_id, f"-{window_seconds} seconds"),
        )
        row = await cursor.fetchone()
        return row["count"]


async def get_tokens_in_window(user_id: str, window_seconds: int) -> int:
    """Get total tokens used in the last N seconds."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT COALESCE(SUM(total_tokens), 0) as total FROM usage
               WHERE user_id = ? AND timestamp > datetime('now', ?)""",
            (user_id, f"-{window_seconds} seconds"),
        )
        row = await cursor.fetchone()
        return row["total"]


async def get_total_tokens(user_id: str) -> int:
    """Get total tokens ever used by a user."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT COALESCE(SUM(total_tokens), 0) as total FROM usage WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        return row["total"]


# Pricing functions
async def set_model_pricing(
    model: str,
    input_cost_per_million: float,
    output_cost_per_million: float,
    changed_by: str = "admin",
) -> None:
    """Set or update pricing for a model. Also logs to pricing_history."""
    async with get_db() as db:
        # Upsert pricing
        await db.execute(
            """INSERT INTO model_pricing (model, input_cost_per_million, output_cost_per_million, updated_at)
               VALUES (?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(model) DO UPDATE SET
                   input_cost_per_million = excluded.input_cost_per_million,
                   output_cost_per_million = excluded.output_cost_per_million,
                   updated_at = CURRENT_TIMESTAMP""",
            (model, input_cost_per_million, output_cost_per_million),
        )

        # Log to pricing history
        await db.execute(
            """INSERT INTO pricing_history (model, input_cost_per_million, output_cost_per_million, changed_by)
               VALUES (?, ?, ?, ?)""",
            (model, input_cost_per_million, output_cost_per_million, changed_by),
        )

        await db.commit()


async def get_model_pricing(model: str) -> dict | None:
    """Get pricing for a specific model."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT model, input_cost_per_million, output_cost_per_million,
                      created_at, updated_at
               FROM model_pricing WHERE model = ?""",
            (model,),
        )
        row = await cursor.fetchone()
        if row:
            return {
                "model": row["model"],
                "input_cost_per_million": row["input_cost_per_million"],
                "output_cost_per_million": row["output_cost_per_million"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        return None


async def get_all_model_pricing() -> list[dict]:
    """Get pricing for all models."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT model, input_cost_per_million, output_cost_per_million,
                      created_at, updated_at
               FROM model_pricing
               ORDER BY model"""
        )
        rows = await cursor.fetchall()
        return [
            {
                "model": row["model"],
                "input_cost_per_million": row["input_cost_per_million"],
                "output_cost_per_million": row["output_cost_per_million"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]


async def delete_model_pricing(model: str) -> bool:
    """Delete pricing for a model."""
    async with get_db() as db:
        cursor = await db.execute("DELETE FROM model_pricing WHERE model = ?", (model,))
        await db.commit()
        return cursor.rowcount > 0


async def get_pricing_history(model: str | None = None) -> list[dict]:
    """Get pricing change history, optionally filtered by model."""
    async with get_db() as db:
        if model:
            cursor = await db.execute(
                """SELECT id, model, input_cost_per_million, output_cost_per_million,
                          changed_by, changed_at
                   FROM pricing_history WHERE model = ?
                   ORDER BY changed_at DESC""",
                (model,),
            )
        else:
            cursor = await db.execute(
                """SELECT id, model, input_cost_per_million, output_cost_per_million,
                          changed_by, changed_at
                   FROM pricing_history
                   ORDER BY changed_at DESC"""
            )

        rows = await cursor.fetchall()
        return [
            {
                "id": row["id"],
                "model": row["model"],
                "input_cost_per_million": row["input_cost_per_million"],
                "output_cost_per_million": row["output_cost_per_million"],
                "changed_by": row["changed_by"],
                "changed_at": row["changed_at"],
            }
            for row in rows
        ]


async def calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Calculate cost for a request based on model pricing."""
    pricing = await get_model_pricing(model)
    if not pricing:
        return 0.0

    input_cost = (prompt_tokens / 1_000_000) * pricing["input_cost_per_million"]
    output_cost = (completion_tokens / 1_000_000) * pricing["output_cost_per_million"]

    return input_cost + output_cost
