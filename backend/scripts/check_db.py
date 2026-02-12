"""Quick connectivity check to Supabase Postgres.

Run after setting .env in this directory:
    python scripts/check_db.py
"""
import os
import sys

import psycopg2
from psycopg2 import sql

from dotenv import load_dotenv  # type: ignore

load_dotenv()


def main() -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL not set. Ensure .env is loaded.")
        return 1

    try:
        with psycopg2.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(sql.SQL("select 1;"))
                row = cur.fetchone()
                print("DB connection OK, select 1 ->", row)
        return 0
    except Exception as exc: 
        print("DB connection failed:", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
