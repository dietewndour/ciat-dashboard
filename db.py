"""Accès à la base SQLite."""
import sqlite3
from pathlib import Path

from flask import current_app, g

BASE_DIR = Path(__file__).resolve().parent


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(path):
    """Crée les tables à partir de schema.sql."""
    con = sqlite3.connect(path)
    con.executescript((BASE_DIR / "schema.sql").read_text(encoding="utf-8"))
    con.commit()
    con.close()
