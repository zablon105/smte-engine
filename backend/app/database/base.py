"""
base.py
Declarative base and database engine/session setup for SMTE.

Beginner note: SQLAlchemy's "declarative base" is the parent class
that all our table models inherit from. It's what lets SQLAlchemy
turn Python classes into real database tables.
"""

import os
from urllib.parse import quote_plus
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv, find_dotenv

# find_dotenv() searches the current directory AND parent directories
# for a .env file, so this works no matter where you run the script from.
load_dotenv(find_dotenv())

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5433")
DB_NAME = os.getenv("DB_NAME", "smart_money_engine")
DB_USER = os.getenv("DB_USER", "smte_admin")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

# quote_plus() safely encodes special characters (@, #, /, etc.) so a
# password containing them doesn't break the connection string.
DB_PASSWORD_ENCODED = quote_plus(DB_PASSWORD)
DB_USER_ENCODED = quote_plus(DB_USER)

DATABASE_URL = (
    f"postgresql+psycopg2://{DB_USER_ENCODED}:{DB_PASSWORD_ENCODED}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

# The engine manages the actual connection pool to Postgres.
engine = create_engine(DATABASE_URL, echo=False, future=True)

# SessionLocal is a factory for creating database sessions.
# Each request/task should open one session, use it, then close it.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base is the parent class every model in models.py inherits from.
Base = declarative_base()


def get_db():
    """
    Dependency function for FastAPI routes.
    Usage in a route:
        def my_route(db: Session = Depends(get_db)):
            ...
    Ensures the session is always closed after the request finishes,
    even if an error occurs.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()