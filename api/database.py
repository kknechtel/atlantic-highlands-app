"""
Atlantic Highlands - Database setup
PostgreSQL with SQLAlchemy ORM.
"""
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from config import DATABASE_URL

logger = logging.getLogger(__name__)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency for FastAPI routes to get a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables and add any missing columns."""
    Base.metadata.create_all(bind=engine)
    _migrate()
    logger.info("Database initialized")


def _migrate():
    """Add columns that create_all won't add to existing tables."""
    new_columns = [
        ("users", "must_change_password", "BOOLEAN DEFAULT FALSE"),
    ]
    with engine.connect() as conn:
        for table, column, col_type in new_columns:
            exists = conn.execute(text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :table AND column_name = :column"
            ), {"table": table, "column": column}).fetchone()
            if not exists:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                logger.info(f"Added column {table}.{column}")
        conn.commit()
