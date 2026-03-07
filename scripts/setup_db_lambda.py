"""Temporary Lambda handler to create the aushadhimitra database and tables."""
import json
import os
import psycopg2
import psycopg2.extras

DB_HOST = os.environ.get("DB_HOST", "")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_USER = os.environ.get("DB_USER", "")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")


def lambda_handler(event, context):
    results = []

    # Step 1: Create database (connect to 'postgres' default DB)
    try:
        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT, dbname="postgres",
            user=DB_USER, password=DB_PASSWORD, sslmode="require",
            connect_timeout=10
        )
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SELECT datname FROM pg_database WHERE datname='aushadhimitra'")
        if cur.fetchone():
            results.append("DB aushadhimitra already exists")
        else:
            cur.execute("CREATE DATABASE aushadhimitra")
            results.append("DB aushadhimitra created")
        conn.close()
    except Exception as e:
        results.append(f"DB creation error: {e}")
        return {"statusCode": 500, "body": json.dumps(results)}

    # Step 2: Create tables (connect to aushadhimitra DB)
    try:
        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT, dbname="aushadhimitra",
            user=DB_USER, password=DB_PASSWORD, sslmode="require",
            connect_timeout=10
        )
        conn.autocommit = False
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS curated_interactions (
            interaction_key VARCHAR(255) PRIMARY KEY,
            ayush_name VARCHAR(255) NOT NULL,
            allopathy_name VARCHAR(255) NOT NULL,
            ayush_scientific_name VARCHAR(255),
            allopathy_generic_name VARCHAR(255),
            severity VARCHAR(20),
            severity_score INTEGER,
            response_data JSONB NOT NULL,
            knowledge_graph JSONB,
            patient_summary_en TEXT,
            patient_summary_hi TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS interaction_sources (
            id SERIAL PRIMARY KEY,
            interaction_key VARCHAR(255) REFERENCES curated_interactions(interaction_key),
            source_url TEXT NOT NULL,
            source_title TEXT,
            source_snippet TEXT,
            source_type VARCHAR(50),
            relevance_score FLOAT,
            retrieved_at TIMESTAMP DEFAULT NOW()
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS allopathy_cache (
            drug_name VARCHAR(255) PRIMARY KEY,
            generic_name VARCHAR(255),
            drug_data JSONB NOT NULL,
            sources JSONB,
            cached_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP DEFAULT NOW() + INTERVAL '7 days'
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id VARCHAR(255) PRIMARY KEY,
            telegram_chat_id VARCHAR(100),
            agent_session_id VARCHAR(255),
            context JSONB DEFAULT '{}',
            messages JSONB DEFAULT '[]',
            last_message TEXT,
            source VARCHAR(20) DEFAULT 'web',
            title VARCHAR(255) DEFAULT 'New Conversation',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP DEFAULT NOW() + INTERVAL '24 hours'
        )
        """)

        # Create indexes
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_sessions_telegram ON sessions(telegram_chat_id)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at)",
            "CREATE INDEX IF NOT EXISTS idx_curated_ayush ON curated_interactions(ayush_name)",
            "CREATE INDEX IF NOT EXISTS idx_curated_allopathy ON curated_interactions(allopathy_name)",
            "CREATE INDEX IF NOT EXISTS idx_sources_interaction ON interaction_sources(interaction_key)",
            "CREATE INDEX IF NOT EXISTS idx_allopathy_cache_expires ON allopathy_cache(expires_at)",
        ]
        for idx_sql in indexes:
            cur.execute(idx_sql)

        conn.commit()
        results.append("All tables and indexes created successfully")
        conn.close()
    except Exception as e:
        results.append(f"Table creation error: {e}")
        return {"statusCode": 500, "body": json.dumps(results)}

    # Step 3: Verify
    try:
        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT, dbname="aushadhimitra",
            user=DB_USER, password=DB_PASSWORD, sslmode="require",
            connect_timeout=10
        )
        cur = conn.cursor()
        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' ORDER BY table_name
        """)
        tables = [r[0] for r in cur.fetchall()]
        results.append(f"Tables in aushadhimitra: {tables}")
        conn.close()
    except Exception as e:
        results.append(f"Verify error: {e}")

    return {"statusCode": 200, "body": json.dumps(results)}
