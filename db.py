
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

def init_app(app):
    app.teardown_appcontext(close_db)
