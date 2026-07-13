"""
init_db.py
Run this once to create all 15 tables in your Postgres database
using the SQLAlchemy models (no need to manually run schema.sql).

Beginner note: `Base.metadata.create_all(engine)` looks at every
model class that inherits from Base (in models.py) and generates
the matching CREATE TABLE statements automatically.

Usage (from the SMTE/backend/ directory, with smte-env activated):
    python -m app.database.init_db
"""

from app.database.base import Base, engine
from app.models import models  # noqa: F401  (import so all model classes register with Base)


def init_db():
    print("Creating all tables defined in models.py ...")
    Base.metadata.create_all(bind=engine)
    print("Done. All 15 tables created (or already existed).")


if __name__ == "__main__":
    init_db()
