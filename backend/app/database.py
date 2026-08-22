from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _enforce_foreign_keys(dbapi_connection, _connection_record):
    """Make SQLite honour the foreign keys the models declare.

    SQLite ignores them per connection unless asked, which is why an
    ``ondelete="CASCADE"`` in models.py used to be decoration: deleting a user
    left their wardrobe, garments and verdicts behind pointing at a row that
    no longer existed. With this on, the database refuses to drift — a
    dangling reference becomes a loud error instead of silent wreckage.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
