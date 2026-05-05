"""One-off probe: report ingestion + embedding coverage."""
from api.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

def q(sql):
    return db.execute(text(sql)).all()

print("docs:", q("SELECT count(*) FROM documents")[0][0])
print("docs_with_emb:", q("SELECT count(*) FROM documents WHERE embedding IS NOT NULL")[0][0])
print("chunks:", q("SELECT count(*) FROM document_chunks")[0][0])
print("chunks_with_emb:", q("SELECT count(*) FROM document_chunks WHERE embedding IS NOT NULL")[0][0])
print("by_status:", q("SELECT status, count(*) FROM documents GROUP BY status ORDER BY 2 DESC"))
print("by_source:", q("SELECT source_type, count(*) FROM documents GROUP BY source_type ORDER BY 2 DESC"))
print("recent_with_emb:", q("SELECT name, status, source_type FROM documents WHERE embedding IS NOT NULL ORDER BY created_at DESC LIMIT 5"))
print("emails:", q("SELECT count(*) FROM documents WHERE name ILIKE '%@%' OR name ILIKE '%.eml' OR name ILIKE '%.msg'")[0][0])
