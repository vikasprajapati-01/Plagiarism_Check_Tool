"""Database access layer — all queries to Supabase/Postgres via asyncpg.

Logic preserved from storage/repository.py.
New additions:
  - async_delete_batch()     → DELETE /batches/{batch_id}
  - async_rename_batch()     → PATCH  /batches/{batch_id}
  - async_fetch_all_batches() updated to include entry_count and created_at
"""

import asyncio
import logging
import os
from typing import Iterable, List, Optional, Sequence, Tuple

import asyncpg
import psycopg2

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _vector_literal(vec: Sequence[float]) -> str:
    """Format a float list as a pgvector literal string."""
    return "[" + ",".join(str(v) for v in vec) + "]"


def _get_conn():
    """Open a synchronous psycopg2 connection from DATABASE_URL."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL not set")
    return psycopg2.connect(db_url)


# ── Async connection pool ─────────────────────────────────────────────────────

_pool: Optional[asyncpg.Pool] = None
_pool_lock: Optional[asyncio.Lock] = None  # created lazily inside an async context


async def _get_pool() -> asyncpg.Pool:
    """Lazy singleton pool — created once, reused by all async functions."""
    global _pool, _pool_lock
    if _pool is not None:
        return _pool
    # Create the lock lazily here, inside an async context, so it is bound
    # to the correct running event loop (avoids DeprecationWarning on 3.10+).
    if _pool_lock is None:
        _pool_lock = asyncio.Lock()
    async with _pool_lock:
        if _pool is None:
            db_url = os.getenv("DATABASE_URL")
            if not db_url:
                raise RuntimeError("DATABASE_URL not set")
            _pool = await asyncpg.create_pool(dsn=db_url, min_size=1, max_size=10)
    return _pool


# ── Sync helpers (used by exact_match.py sync path) ──────────────────────────

def fetch_hashes_by_batch(batch_id: str) -> List[str]:
    """Fetch all SHA-256 hashes for a given batch synchronously."""
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute("select sha256 from reference_text where batch_id = %s;", (batch_id,))
        return [r[0] for r in cur.fetchall()]


def fetch_all_hashes() -> List[str]:
    """Fetch all SHA-256 hashes across all batches synchronously."""
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute("select sha256 from reference_text;")
        return [r[0] for r in cur.fetchall()]


# ── Async CRUD — batches ──────────────────────────────────────────────────────

async def async_create_batch(name: Optional[str] = None) -> str:
    """Insert a new reference_batch row and return its UUID as a string."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        batch_id = await conn.fetchval(
            "insert into reference_batch (name) values ($1) returning id;",
            name,
        )
        return str(batch_id)


async def async_fetch_all_batches() -> List[dict]:
    """Return all stored batches with id, name, entry_count, and created_at."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            select
                rb.id,
                rb.name,
                rb.created_at,
                count(rt.id) as entry_count
            from reference_batch rb
            left join reference_text rt on rt.batch_id = rb.id
            group by rb.id, rb.name, rb.created_at
            order by rb.created_at desc;
            """
        )
        return [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "created_at": r["created_at"],
                "entry_count": r["entry_count"],
            }
            for r in rows
        ]


async def async_delete_batch(batch_id: str) -> bool:
    """Delete a batch and all its texts + embeddings (relies on CASCADE FK).

    Returns True if a row was deleted, False if the batch did not exist.
    """
    pool = await _get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "delete from reference_batch where id = $1::uuid;",
            batch_id,
        )
        # asyncpg returns "DELETE N" — check N > 0
        return result.endswith("1")


async def async_rename_batch(batch_id: str, new_name: str) -> bool:
    """Rename a batch. Returns True if the batch was found and updated."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "update reference_batch set name = $1 where id = $2::uuid;",
            new_name,
            batch_id,
        )
        return result.endswith("1")


async def async_get_batch_id_by_name(name: str) -> Optional[str]:
    """Return the UUID of the first batch with the given name, or None."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "select id from reference_batch where name = $1 limit 1;",
            name,
        )
        return str(row["id"]) if row else None


# ── Async CRUD — reference texts ──────────────────────────────────────────────

async def async_insert_reference_texts(
    batch_id: str,
    items: Iterable[Tuple[str, str, str, Optional[str], Optional[str]]],
) -> List[str]:
    """Bulk-insert reference texts into a batch. Returns list of inserted IDs."""
    rows = list(items)
    if not rows:
        return []
    pool = await _get_pool()
    async with pool.acquire() as conn:
        ids: List[str] = []
        insert_sql = (
            "insert into reference_text (batch_id, raw_text, cleaned_text, sha256, source, license) "
            "values ($1, $2, $3, $4, $5, $6) returning id;"
        )
        async with conn.transaction():
            for raw, cleaned, sha256, source, license_info in rows:
                ref_id = await conn.fetchval(
                    insert_sql,
                    batch_id, raw, cleaned, sha256, source, license_info,
                )
                ids.append(str(ref_id))
        return ids


async def async_fetch_hashes_by_batch(batch_id: str) -> List[str]:
    """Fetch SHA-256 hashes for all texts in a given batch."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "select sha256 from reference_text where batch_id = $1;",
            batch_id,
        )
        return [r["sha256"] for r in rows]


async def async_fetch_all_hashes() -> List[str]:
    """Fetch SHA-256 hashes for all stored texts."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("select sha256 from reference_text;")
        return [r["sha256"] for r in rows]


async def async_fetch_all_texts_by_batch(batch_id: Optional[str] = None) -> List[str]:
    """Fetch cleaned texts for a batch, or all if no batch provided."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        if batch_id:
            rows = await conn.fetch(
                "select cleaned_text from reference_text where batch_id = $1;",
                batch_id,
            )
        else:
            rows = await conn.fetch("select cleaned_text from reference_text;")
        return [r["cleaned_text"] for r in rows]


async def async_fetch_all_texts_with_batch_info() -> List[dict]:
    """Fetch every stored reference text with its batch id and name."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            select rt.raw_text, rt.cleaned_text, rt.batch_id, rb.name as batch_name
            from reference_text rt
            join reference_batch rb on rb.id = rt.batch_id
            order by rb.created_at desc, rt.id;
            """
        )
        return [
            {
                "raw_text": r["raw_text"],
                "cleaned_text": r["cleaned_text"],
                "batch_id": str(r["batch_id"]),
                "batch_name": r["batch_name"],
            }
            for r in rows
        ]


async def insert_reference_text_with_position(
    pool,
    batch_id,
    raw_text,
    cleaned_text,
    sha256,
    source_file,
    row_number,
    column_name,
    cell_ref,
    source=None,
    license=None,
) -> str:
    """Insert a reference text row with position metadata and return its UUID."""
    async with pool.acquire() as conn:
        ref_id = await conn.fetchval(
            ""
            "insert into reference_text "
            "(batch_id, raw_text, cleaned_text, sha256, source, license, "
            " source_file, row_number, column_name, cell_ref) "
            "values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) "
            "returning id;"
            "",
            batch_id,
            raw_text,
            cleaned_text,
            sha256,
            source,
            license,
            source_file,
            row_number,
            column_name,
            cell_ref,
        )
        return str(ref_id)


# ── Async CRUD — embeddings ───────────────────────────────────────────────────

async def async_insert_embeddings(pairs: Iterable[Tuple[str, Sequence[float]]]) -> None:
    """Upsert embeddings for reference texts."""
    data = list(pairs)
    if not data:
        return
    pool = await _get_pool()
    async with pool.acquire() as conn:
        values = [(ref_id, _vector_literal(vec)) for ref_id, vec in data]
        insert_sql = (
            "insert into reference_embedding (ref_id, embedding) values ($1, $2::vector) "
            "on conflict (ref_id) do update set embedding = excluded.embedding;"
        )
        async with conn.transaction():
            await conn.executemany(insert_sql, values)
