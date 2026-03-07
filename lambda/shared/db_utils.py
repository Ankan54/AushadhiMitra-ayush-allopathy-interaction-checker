"""
PostgreSQL database utilities for AushadhiMitra Lambda functions.
Modeled after SCM project's shared/db_utils.py pattern.
"""
import os
import json
import logging
from datetime import datetime, date
from typing import Optional

logger = logging.getLogger(__name__)

DB_HOST = os.environ.get("DB_HOST", "")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_NAME = os.environ.get("DB_NAME", "aushadhimitra")
DB_USER = os.environ.get("DB_USER", "")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_SSL = os.environ.get("DB_SSL", "require")

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None


def get_db():
    if psycopg2 is None:
        raise RuntimeError("psycopg2 not available")
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASSWORD, sslmode=DB_SSL,
        connect_timeout=10,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )
    conn.autocommit = False
    return conn


def _serialize(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    try:
        import decimal
        if isinstance(obj, decimal.Decimal):
            return float(obj)
    except ImportError:
        pass
    raise TypeError(f"Type {type(obj)} not serializable")


def row_to_dict(row) -> Optional[dict]:
    if row is None:
        return None
    return dict(row)


def rows_to_list(rows) -> list:
    return [dict(r) for r in rows]


def lookup_curated_interaction(ayush_name: str, allopathy_name: str) -> Optional[dict]:
    conn = get_db()
    try:
        cur = conn.cursor()
        key = f"{ayush_name.lower().strip()}#{allopathy_name.lower().strip()}"
        cur.execute(
            "SELECT * FROM curated_interactions WHERE interaction_key = %s", (key,)
        )
        row = cur.fetchone()
        if row:
            return row_to_dict(row)
        cur.execute(
            """SELECT * FROM curated_interactions
               WHERE LOWER(ayush_name) = %s AND LOWER(allopathy_name) = %s""",
            (ayush_name.lower().strip(), allopathy_name.lower().strip()),
        )
        return row_to_dict(cur.fetchone())
    finally:
        conn.close()


def get_interaction_sources(interaction_key: str) -> list:
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM interaction_sources WHERE interaction_key = %s",
            (interaction_key,),
        )
        return rows_to_list(cur.fetchall())
    finally:
        conn.close()


def cache_lookup_allopathy(drug_name: str) -> Optional[dict]:
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM allopathy_cache
               WHERE drug_name = %s AND expires_at > NOW()""",
            (drug_name.lower().strip(),),
        )
        return row_to_dict(cur.fetchone())
    finally:
        conn.close()


def cache_save_allopathy(drug_name: str, generic_name: str,
                          drug_data: dict, sources: list):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO allopathy_cache (drug_name, generic_name, drug_data, sources, cached_at, expires_at)
               VALUES (%s, %s, %s, %s, NOW(), NOW() + INTERVAL '7 days')
               ON CONFLICT (drug_name) DO UPDATE SET
                   generic_name = EXCLUDED.generic_name,
                   drug_data = EXCLUDED.drug_data,
                   sources = EXCLUDED.sources,
                   cached_at = NOW(),
                   expires_at = NOW() + INTERVAL '7 days'""",
            (drug_name.lower().strip(), generic_name,
             json.dumps(drug_data, default=_serialize),
             json.dumps(sources, default=_serialize)),
        )
        conn.commit()
    finally:
        conn.close()
