"""
Atlantic Highlands - Database setup
PostgreSQL with SQLAlchemy ORM. Inline migrations run on startup.
"""
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from config import DATABASE_URL

logger = logging.getLogger(__name__)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

EMBEDDING_DIM = 1024  # voyage-3-lite / hash fallback


def get_db():
    """Dependency for FastAPI routes to get a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables and run inline migrations."""
    Base.metadata.create_all(bind=engine)
    _migrate()
    logger.info("Database initialized")
    _log_rag_health_banner()


def rag_health() -> dict:
    """
    Inspect the live database and return a status dict for the RAG pipeline.

    Used by:
      - the startup banner (so an operator notices a degraded mode)
      - GET /health/rag (so a uptime check can alert)
      - tests / diagnostic scripts

    Three independent axes:
      1. pgvector extension installed              → semantic search possible
      2. embedding columns exist on docs + chunks  → ingestion can write vectors
      3. VOYAGE_API_KEY set                        → vectors will be SEMANTIC
                                                     (otherwise hash-vector fallback)
    """
    import os

    status = {
        "pgvector_extension": False,
        "pgvector_version": None,
        "documents_embedding_column": False,
        "chunks_embedding_column": False,
        "voyage_api_key_set": bool(os.environ.get("VOYAGE_API_KEY", "").strip()),
        "ready_for_semantic_search": False,
        "degraded_mode": None,  # None | "no_pgvector" | "no_voyage_key"
        "documents_total": 0,
        "documents_embedded": 0,
        "chunks_total": 0,
        "chunks_embedded": 0,
    }

    try:
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
            )).fetchone()
            if row:
                status["pgvector_extension"] = True
                status["pgvector_version"] = row[0]

            # Embedding columns
            for table in ("documents", "document_chunks"):
                exists = conn.execute(text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = :t AND column_name = 'embedding'"
                ), {"t": table}).fetchone()
                key = "documents_embedding_column" if table == "documents" else "chunks_embedding_column"
                status[key] = bool(exists)

            # Coverage (only meaningful if embedding column exists)
            if status["documents_embedding_column"]:
                status["documents_total"] = conn.execute(text("SELECT count(*) FROM documents")).scalar() or 0
                status["documents_embedded"] = conn.execute(text(
                    "SELECT count(*) FROM documents WHERE embedding IS NOT NULL"
                )).scalar() or 0
            if status["chunks_embedding_column"]:
                status["chunks_total"] = conn.execute(text("SELECT count(*) FROM document_chunks")).scalar() or 0
                status["chunks_embedded"] = conn.execute(text(
                    "SELECT count(*) FROM document_chunks WHERE embedding IS NOT NULL"
                )).scalar() or 0
    except Exception as exc:
        logger.warning("rag_health: query failed: %s", exc)

    has_pgvector = (
        status["pgvector_extension"]
        and status["documents_embedding_column"]
        and status["chunks_embedding_column"]
    )

    if not has_pgvector:
        status["degraded_mode"] = "no_pgvector"
    elif not status["voyage_api_key_set"]:
        status["degraded_mode"] = "no_voyage_key"

    status["ready_for_semantic_search"] = has_pgvector and status["voyage_api_key_set"]
    return status


def _log_rag_health_banner() -> None:
    """Print a hard-to-miss multi-line banner about the RAG pipeline state.
    Helps operators notice when the system is silently running in a degraded
    mode (keyword-only search, hash-vector fallback)."""
    s = rag_health()
    rule = "=" * 72

    if s["ready_for_semantic_search"]:
        logger.info("\n%s\nRAG: READY (semantic + keyword)\n  pgvector v%s · voyage embeddings · %d/%d chunks embedded\n%s",
                    rule, s["pgvector_version"], s["chunks_embedded"], s["chunks_total"], rule)
        return

    lines = [rule, "RAG PIPELINE: DEGRADED MODE"]

    if s["degraded_mode"] == "no_pgvector":
        lines += [
            "",
            "  pgvector extension is NOT available on this Postgres instance.",
            "  Semantic search is OFF. Chat will fall back to tsvector keyword search.",
            "",
            f"  pgvector_extension:        {s['pgvector_extension']}",
            f"  documents.embedding col:   {s['documents_embedding_column']}",
            f"  document_chunks.embedding: {s['chunks_embedding_column']}",
            "",
            "  Fix:",
            "    RDS:        parameter group → shared_preload_libraries += pgvector → reboot",
            "    Docker:     image must be `pgvector/pgvector:pgN`, not stock postgres",
            "    Self-host:  apt-get install postgresql-{16,15,...}-pgvector",
            "",
            "  Then restart the API — the inline migration will create the extension",
            "  and add the embedding columns. Re-run ingestion to populate vectors.",
        ]
    elif s["degraded_mode"] == "no_voyage_key":
        lines += [
            "",
            "  pgvector is installed, but VOYAGE_API_KEY is not set.",
            "  Embeddings will use the SHA-512 hash fallback (deterministic, NOT semantic).",
            "  Keyword search via tsvector still works; chat recall will be okay but not great.",
            "",
            f"  pgvector v{s['pgvector_version']} · {s['chunks_embedded']}/{s['chunks_total']} chunks embedded (hash)",
            "",
            "  Fix:",
            "    Set VOYAGE_API_KEY (free tier covers AH's corpus). Get a key at",
            "      https://dash.voyageai.com",
            "    Restart the API and re-run ingestion to overwrite hash vectors with",
            "    real embeddings.",
        ]
    else:
        lines.append("  Unknown state — see status: %s" % s)

    lines.append(rule)
    logger.warning("\n%s", "\n".join(lines))


def _migrate():
    """
    Inline migrations. Adds columns/indexes/extensions create_all won't add
    to existing tables. Idempotent — safe to run on every startup.
    """
    new_columns = [
        ("users", "must_change_password", "BOOLEAN DEFAULT FALSE"),
        # Financial statement upgrades (Phase 1)
        ("financial_statements", "extraction_pass", "INTEGER DEFAULT 0"),
        ("financial_statements", "reconcile_status", "VARCHAR DEFAULT 'not_attempted'"),
        ("financial_statements", "reconcile_details", "JSONB DEFAULT '{}'::jsonb"),
        ("financial_statements", "anomaly_flags", "JSONB DEFAULT '[]'::jsonb"),
        ("financial_statements", "drill_results", "JSONB DEFAULT '{}'::jsonb"),
        ("financial_statements", "accounting_basis", "VARCHAR"),
        ("financial_statements", "fiscal_calendar", "VARCHAR"),
        ("financial_statements", "predecessor_entity", "VARCHAR"),
        # Financial line item upgrades — fund + NJ account codes
        ("financial_line_items", "fund", "VARCHAR"),
        ("financial_line_items", "account_code", "VARCHAR"),
        ("financial_line_items", "program_code", "VARCHAR"),
        ("financial_line_items", "function_code", "VARCHAR"),
        ("financial_line_items", "object_code", "VARCHAR"),
        ("financial_line_items", "is_total_row", "BOOLEAN DEFAULT FALSE"),
        ("financial_line_items", "yoy_change_pct", "FLOAT"),
        ("financial_line_items", "variance_pct", "FLOAT"),
        ("financial_line_items", "anomaly_flags", "JSONB DEFAULT '[]'::jsonb"),
    ]

    with engine.connect() as conn:
        def _table_exists(t: str) -> bool:
            return bool(conn.execute(text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = :t"
            ), {"t": t}).fetchone())

        # 1. Add per-row missing columns. Skip silently if the table doesn't
        # exist yet (can happen mid-deploy if models haven't been imported).
        for table, column, col_type in new_columns:
            if not _table_exists(table):
                continue
            exists = conn.execute(text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :table AND column_name = :column"
            ), {"table": table, "column": column}).fetchone()
            if not exists:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                logger.info(f"Added column {table}.{column}")

        # 2. Enable pgvector + tsvector for hybrid RAG
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        except Exception as e:
            logger.warning(f"pgvector extension not available — semantic search will fall back to keyword-only: {e}")

        # 3. Add embedding + fts_vector columns + chunk-level pgvector cols
        rag_columns = [
            ("documents", "embedding", f"vector({EMBEDDING_DIM})"),
            ("documents", "fts_vector", "tsvector"),
            ("document_chunks", "embedding", f"vector({EMBEDDING_DIM})"),
            ("document_chunks", "fts_vector", "tsvector"),
        ]
        for table, column, col_type in rag_columns:
            if not _table_exists(table):
                continue
            exists = conn.execute(text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :table AND column_name = :column"
            ), {"table": table, "column": column}).fetchone()
            if exists:
                continue
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                logger.info(f"Added column {table}.{column} ({col_type})")
            except Exception as e:
                # Most likely pgvector wasn't installable — keep the keyword-only path working
                logger.warning(f"Failed to add {table}.{column}: {e}")

        # 4. Indexes for fast hybrid search
        rag_indexes = [
            # GIN over tsvector for keyword
            ("ix_documents_fts", "CREATE INDEX IF NOT EXISTS ix_documents_fts ON documents USING gin(fts_vector)"),
            ("ix_chunks_fts", "CREATE INDEX IF NOT EXISTS ix_chunks_fts ON document_chunks USING gin(fts_vector)"),
            # IVFFLAT for vector cosine. Lists=100 is fine up to ~100K chunks; bump later.
            ("ix_documents_vec", "CREATE INDEX IF NOT EXISTS ix_documents_vec ON documents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"),
            ("ix_chunks_vec", "CREATE INDEX IF NOT EXISTS ix_chunks_vec ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"),
        ]
        for name, sql in rag_indexes:
            try:
                conn.execute(text(sql))
            except Exception as e:
                logger.warning(f"Index {name} skipped: {e}")

        conn.commit()
