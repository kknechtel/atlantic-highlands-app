"""DELETE every music event written by the scrapers — used to recover
from a bad parser run that polluted the table with junk titles.

Only deletes rows where source LIKE 'html:%' or 'squarespace:%' or
'tribe:%' (the prefixes the scraper adapters write). Hand-entered or
borough-calendar rows are untouched.
"""
import sys
from sqlalchemy import text
from database import SessionLocal


def main() -> int:
    db = SessionLocal()
    try:
        for prefix in ("html:", "squarespace:", "tribe:"):
            n = db.execute(text(
                "DELETE FROM calendar_events WHERE source LIKE :p"
            ), {"p": f"{prefix}%"}).rowcount
            print(f"  deleted {n} rows with source LIKE '{prefix}%'")
        db.commit()
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
