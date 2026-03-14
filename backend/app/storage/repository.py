import asyncio
import os
from typing import Iterable, List, Optional, Sequence, Tuple

import asyncpg
import psycopg2
from psycopg2 import extras

try:  # pragma: no cover - optional convenience
	from dotenv import load_dotenv  # type: ignore

	load_dotenv()
except Exception:
	pass


def _vector_literal(vec: Sequence[float]) -> str:
	return "[" + ",".join(str(v) for v in vec) + "]"


def _get_conn():
	db_url = os.getenv("DATABASE_URL")
	if not db_url:
		raise RuntimeError("DATABASE_URL not set")
	return psycopg2.connect(db_url)


# Shared async connection pool

_pool: Optional[asyncpg.Pool] = None
_pool_lock = asyncio.Lock()


async def _get_pool() -> asyncpg.Pool:
	"""Lazy singleton pool — created once, reused by all async functions."""
	global _pool
	if _pool is not None:
		return _pool
	async with _pool_lock:
		# Re-check inside the lock in case another coroutine already created it.
		if _pool is None:
			db_url = os.getenv("DATABASE_URL")
			if not db_url:
				raise RuntimeError("DATABASE_URL not set")
			_pool = await asyncpg.create_pool(dsn=db_url, min_size=1, max_size=10)
	return _pool



# ----------------------- Sync helpers ----------------------- #

def fetch_hashes_by_batch(batch_id: str) -> List[str]:
	with _get_conn() as conn, conn.cursor() as cur:
		cur.execute(
			"select sha256 from reference_text where batch_id = %s;",
			(batch_id,),
		)
		return [r[0] for r in cur.fetchall()]


def fetch_all_hashes() -> List[str]:
	with _get_conn() as conn, conn.cursor() as cur:
		cur.execute("select sha256 from reference_text;")
		return [r[0] for r in cur.fetchall()]


# ----------------------- Async helpers ----------------------- #

async def async_create_batch(name: Optional[str] = None) -> str:
	pool = await _get_pool()
	async with pool.acquire() as conn:
		batch_id = await conn.fetchval(
			"insert into reference_batch (name) values ($1) returning id;",
			name,
		)
		return str(batch_id)


async def async_insert_reference_texts(
	batch_id: str,
	items: Iterable[Tuple[str, str, str, Optional[str], Optional[str]]],
) -> List[str]:
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
					batch_id,
					raw,
					cleaned,
					sha256,
					source,
					license_info,
				)
				ids.append(str(ref_id))
		return ids


async def async_insert_embeddings(pairs: Iterable[Tuple[str, Sequence[float]]]) -> None:
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


async def async_fetch_hashes_by_batch(batch_id: str) -> List[str]:
	pool = await _get_pool()
	async with pool.acquire() as conn:
		rows = await conn.fetch(
			"select sha256 from reference_text where batch_id = $1;",
			batch_id,
		)
		return [r["sha256"] for r in rows]


async def async_fetch_all_hashes() -> List[str]:
	pool = await _get_pool()
	async with pool.acquire() as conn:
		rows = await conn.fetch("select sha256 from reference_text;")
		return [r["sha256"] for r in rows]


async def async_get_batch_id_by_name(name: str) -> Optional[str]:
	pool = await _get_pool()
	async with pool.acquire() as conn:
		row = await conn.fetchrow(
			"select id from reference_batch where name = $1 limit 1;",
			name,
		)
		return str(row["id"]) if row else None


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


async def async_fetch_all_batches() -> List[dict]:
	"""Return a list of all stored batches as {id, name}."""
	pool = await _get_pool()
	async with pool.acquire() as conn:
		rows = await conn.fetch("select id, name from reference_batch order by created_at desc;")
		return [{"id": str(r["id"]), "name": r["name"]} for r in rows]


async def async_fetch_all_texts_with_batch_info() -> List[dict]:
	"""Fetch every stored reference text with its batch id and name.

	Returns a list of dicts:
		{
			"raw_text":    str,
			"cleaned_text": str,
			"batch_id":    str,
			"batch_name":  str | None,
		}
	"""
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
