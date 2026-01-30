from __future__ import annotations

from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import sqlite3

from .models import Base


def create_sqlite_engine(db_path: str):
    return create_engine(f"sqlite:///{db_path}", echo=False, future=True)


def create_session_factory(engine):
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db(engine):
    Base.metadata.create_all(engine)
    _ensure_document_columns(engine)
    _ensure_document_trees_table(engine)


def _ensure_document_columns(engine):
    with engine.begin() as conn:
        rows = conn.exec_driver_sql("PRAGMA table_info(documents)").fetchall()
        existing = {row[1] for row in rows}
        columns = {
            "file_hash": "TEXT",
            "doc_type": "TEXT",
            "target_doc_id": "TEXT",
            "source_path": "TEXT",
            "last_step": "TEXT",
            "error_message": "TEXT",
            "updated_at": "TEXT",
        }
        for name, col_type in columns.items():
            if name not in existing:
                conn.exec_driver_sql(f"ALTER TABLE documents ADD COLUMN {name} {col_type}")


def _ensure_document_trees_table(engine):
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS document_trees (doc_id TEXT PRIMARY KEY, tree_json TEXT, updated_at TEXT)"
        )


@contextmanager
def session_scope(session_factory):
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
