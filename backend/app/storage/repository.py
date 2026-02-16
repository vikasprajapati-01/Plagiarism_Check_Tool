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


async def _get_async_conn():
	db_url = os.getenv("DATABASE_URL")
	if not db_url:
		raise RuntimeError("DATABASE_URL not set")
	return await asyncpg.connect(dsn=db_url)


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
	conn = await _get_async_conn()
	try:
		batch_id = await conn.fetchval(
			"insert into reference_batch (name) values ($1) returning id;",
			name,
		)
		return str(batch_id)
	finally:
		await conn.close()


async def async_insert_reference_texts(
	batch_id: str,
	items: Iterable[Tuple[str, str, str, Optional[str], Optional[str]]],
) -> List[str]:
	rows = list(items)
	if not rows:
		return []
	conn = await _get_async_conn()
	try:
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
	finally:
		await conn.close()


async def async_insert_embeddings(pairs: Iterable[Tuple[str, Sequence[float]]]) -> None:
	data = list(pairs)
	if not data:
		return
	conn = await _get_async_conn()
	try:
		values = [(ref_id, _vector_literal(vec)) for ref_id, vec in data]
		insert_sql = (
			"insert into reference_embedding (ref_id, embedding) values ($1, $2::vector) "
			"on conflict (ref_id) do update set embedding = excluded.embedding;"
		)
		async with conn.transaction():
			await conn.executemany(insert_sql, values)
	finally:
		await conn.close()


async def async_fetch_hashes_by_batch(batch_id: str) -> List[str]:
	conn = await _get_async_conn()
	try:
		rows = await conn.fetch(
			"select sha256 from reference_text where batch_id = $1;",
			batch_id,
		)
		return [r["sha256"] for r in rows]
	finally:
		await conn.close()


async def async_fetch_all_hashes() -> List[str]:
	conn = await _get_async_conn()
	try:
		rows = await conn.fetch("select sha256 from reference_text;")
		return [r["sha256"] for r in rows]
	finally:
		await conn.close()

async def async_fetch_all_texts_by_batch(batch_id: str) -> List[str]:
    """
    Fetch all text entries for a given batch ID.
    
    This is used by fuzzy matching to compare against existing texts.
    """
    # TODO: Implement based on your database schema
    # Example with SQLite:
    query = "SELECT text_content FROM texts WHERE batch_id = ?"
    cursor = await db.execute(query, (batch_id,))
    rows = await cursor.fetchall()
    return [row[0] for row in rows]