"""PostgreSQL connection pool and helpers for the FastAPI backend."""
import json
import logging
from datetime import datetime, date
from contextlib import contextmanager
from typing import Optional

import psycopg2
import psycopg2.extras
import psycopg2.pool

from app.config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, DB_SSL

logger = logging.getLogger(__name__)

_pool = None


def get_pool():
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1, maxconn=5,
            host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
            user=DB_USER, password=DB_PASSWORD, sslmode=DB_SSL,
            cursor_factory=psycopg2.extras.RealDictCursor,
            connect_timeout=5,  # 5 second timeout
            options="-c statement_timeout=5000",
        )
    return _pool


@contextmanager
def get_conn():
    pool = get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def _serialize(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def lookup_curated(ayush: str, allopathy: str) -> Optional[dict]:
    key = f"{ayush.lower().strip()}#{allopathy.lower().strip()}"
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM curated_interactions WHERE interaction_key = %s", (key,))
        row = cur.fetchone()
        if row:
            return dict(row)
        cur.execute(
            "SELECT * FROM curated_interactions WHERE LOWER(ayush_name) LIKE %s AND LOWER(allopathy_name) LIKE %s",
            (f"%{ayush.lower().strip()}%", f"%{allopathy.lower().strip()}%"),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def get_sources(interaction_key: str) -> list:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM interaction_sources WHERE interaction_key = %s", (interaction_key,))
        return [dict(r) for r in cur.fetchall()]


def save_interaction(data: dict, sources: list):
    """Save a completed interaction analysis to the curated DB."""
    key = data.get("interaction_key", "")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO curated_interactions
               (interaction_key, ayush_name, allopathy_name, severity, severity_score,
                response_data, knowledge_graph, created_at, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
               ON CONFLICT (interaction_key) DO UPDATE SET
                   severity = EXCLUDED.severity,
                   severity_score = EXCLUDED.severity_score,
                   response_data = EXCLUDED.response_data,
                   knowledge_graph = EXCLUDED.knowledge_graph,
                   updated_at = NOW()""",
            (
                key,
                data.get("ayush_name", ""),
                data.get("allopathy_name", ""),
                data.get("severity", ""),
                data.get("severity_score", 0),
                json.dumps(data, default=_serialize),
                json.dumps(data.get("knowledge_graph", {}), default=_serialize),
            ),
        )
        for src in sources:
            cur.execute(
                """INSERT INTO interaction_sources
                   (interaction_key, source_url, source_title, source_snippet, source_type, relevance_score)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    key,
                    src.get("url", ""),
                    src.get("title", ""),
                    src.get("snippet", ""),
                    src.get("source_type", "tavily_search"),
                    src.get("score", 0),
                ),
            )


def list_interactions(limit: int = 20) -> list:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT interaction_key, ayush_name, allopathy_name, severity, severity_score, created_at
               FROM curated_interactions ORDER BY created_at DESC LIMIT %s""",
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]
