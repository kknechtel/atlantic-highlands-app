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
        # 1. Add per-row missing columns
        for table, column, col_type in new_columns:
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
