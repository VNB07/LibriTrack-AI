"""SQLite storage. Simple for version 1; move to PostgreSQL later with the same tables."""
import os
import sqlite3
from contextlib import closing
from pathlib import Path

DB_PATH = os.getenv("LIBRITRACK_DB", "libritrack.db")
PHOTO_DIR = os.getenv("LIBRITRACK_PHOTOS", "data/photos")
BOOK_DIR = os.getenv("LIBRITRACK_BOOKS", "data/books")
SNAPSHOT_DIR = os.getenv("LIBRITRACK_SNAPSHOTS", "data/snapshots")

SCHEMA = """
CREATE TABLE IF NOT EXISTS staff (
    id INTEGER PRIMARY KEY, email TEXT UNIQUE, name TEXT,
    password_hash TEXT, role TEXT DEFAULT 'librarian');
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY, student_code TEXT UNIQUE, name TEXT,
    email TEXT, consent_at TEXT, active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS photos (
    id INTEGER PRIMARY KEY, student_id INTEGER, uploaded_by INTEGER,
    path TEXT, embedding TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY, barcode TEXT UNIQUE, title TEXT,
    author TEXT, copies INTEGER DEFAULT 1, cover_path TEXT, features_path TEXT);
CREATE TABLE IF NOT EXISTS loans (
    id INTEGER PRIMARY KEY, barcode TEXT, student_id INTEGER,
    borrowed_at TEXT, due_at TEXT, returned_at TEXT, snapshot_path TEXT);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY, student_id INTEGER, kind TEXT,
    source TEXT, at TEXT);
CREATE TABLE IF NOT EXISTS unattended_books (
    id INTEGER PRIMARY KEY, barcode TEXT, detected_at TEXT,
    snapshot_path TEXT, status TEXT DEFAULT 'unreviewed');
"""


def init():
    Path(PHOTO_DIR).mkdir(parents=True, exist_ok=True)
    Path(BOOK_DIR).mkdir(parents=True, exist_ok=True)
    Path(SNAPSHOT_DIR).mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(DB_PATH)) as c:
        c.executescript(SCHEMA)
        # Safe schema migration for existing databases:
        cursor = c.cursor()
        cursor.execute("PRAGMA table_info(books)")
        cols = [col[1] for col in cursor.fetchall()]
        if "cover_path" not in cols:
            cursor.execute("ALTER TABLE books ADD COLUMN cover_path TEXT")
        if "features_path" not in cols:
            cursor.execute("ALTER TABLE books ADD COLUMN features_path TEXT")

        cursor.execute("PRAGMA table_info(loans)")
        loan_cols = [col[1] for col in cursor.fetchall()]
        if "snapshot_path" not in loan_cols:
            cursor.execute("ALTER TABLE loans ADD COLUMN snapshot_path TEXT")
        c.commit()


def _connect():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def query(sql, args=(), one=False):
    with closing(_connect()) as c:
        rows = [dict(r) for r in c.execute(sql, args).fetchall()]
    if one:
        return rows[0] if rows else None
    return rows


def execute(sql, args=()):
    with closing(_connect()) as c:
        cur = c.execute(sql, args)
        c.commit()
        return cur.lastrowid