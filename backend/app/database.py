from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _configure_connection(dbapi_connection, _connection_record):
    """Two pragmas SQLite will not apply on its own, set per connection.

    ``foreign_keys`` makes SQLite honour the keys the models declare. It ignores
    them unless asked, which is why an ``ondelete="CASCADE"`` in models.py used
    to be decoration: deleting a user left their wardrobe, garments and verdicts
    behind pointing at a row that no longer existed. With this on, the database
    refuses to drift — a dangling reference becomes a loud error instead of
    silent wreckage.

    ``journal_mode=WAL`` lets readers carry on while something is being written.
    The default rollback journal blocks them, and this app holds one genuinely
    long read: a full backup or an export walks every garment and every photo.
    Without WAL, your partner swiping while you export waits for the export to
    finish. WAL is persistent — set once per database, not per connection — but
    asking for it every time is harmless and survives the file being replaced by
    a restored backup.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    # Wait rather than fail when another connection is mid-write; the default is
    # to give up immediately with "database is locked".
    cursor.execute("PRAGMA busy_timeout=5000")
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
