
import os
import sqlite3
from pathlib import Path

from flask import g

DB_PATH = Path(__file__).parent / "personal.db"
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
USE_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))

if USE_POSTGRES:
    import psycopg
    from psycopg.rows import dict_row


class Database:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, query, params=()):
        if USE_POSTGRES:
            query = query.replace("?", "%s")
        return self.connection.execute(query, params)

    def commit(self):
        self.connection.commit()

    def close(self):
        self.connection.close()

def get_db():
    if "db" not in g:
        if USE_POSTGRES:
            g.db = Database(psycopg.connect(DATABASE_URL, row_factory=dict_row))
        else:
            connection = sqlite3.connect(DB_PATH)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            g.db = Database(connection)
    return g.db

def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    if USE_POSTGRES:
        schema = (Path(__file__).parent / "schema.postgres.sql").read_text(encoding="utf-8")
        with psycopg.connect(DATABASE_URL) as connection:
            with connection.cursor() as cursor:
                for statement in schema.split(";"):
                    statement = statement.strip()
                    if statement:
                        cursor.execute(statement)
    else:
        schema = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
        with sqlite3.connect(DB_PATH) as connection:
            connection.executescript(schema)
    migrate_db()


def migrate_db():
    db = get_db()
    if USE_POSTGRES:
        db.execute("ALTER TABLE areas ADD COLUMN IF NOT EXISTS parent_id INTEGER REFERENCES areas(id) ON DELETE CASCADE")
        db.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS stage TEXT NOT NULL DEFAULT 'inicio'")
    else:
        columns = {row[1] for row in db.execute("PRAGMA table_info(areas)").fetchall()}
        if "parent_id" not in columns:
            db.execute("ALTER TABLE areas ADD COLUMN parent_id INTEGER")
        columns = {row[1] for row in db.execute("PRAGMA table_info(tasks)").fetchall()}
        if "stage" not in columns:
            db.execute("ALTER TABLE tasks ADD COLUMN stage TEXT NOT NULL DEFAULT 'inicio'")
    db.execute("UPDATE tasks SET stage='concluido' WHERE status='done' AND (stage IS NULL OR stage='inicio')")
    db.execute("UPDATE tasks SET stage='inicio' WHERE status='pending' AND (stage IS NULL OR stage='concluido')")
    db.commit()

def init_app(app):
    app.teardown_appcontext(close_db)
