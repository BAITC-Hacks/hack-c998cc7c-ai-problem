"""SQLite-хранилище: совещания, статусы этапов, поручения, саммари."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import config


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def conn() -> sqlite3.Connection:
    c = sqlite3.connect(config.DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL;")
    return c


def init_db() -> None:
    with conn() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS meetings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            original_path TEXT,
            status TEXT NOT NULL DEFAULT 'queued',
            stage TEXT DEFAULT '—',
            created_at TEXT NOT NULL,
            finished_at TEXT,
            result_json TEXT,
            extract_mode TEXT,
            summary_mode TEXT,
            error TEXT
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id INTEGER NOT NULL,
            ts TEXT NOT NULL,
            stage TEXT,
            message TEXT
        );
        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id INTEGER NOT NULL,
            position INTEGER NOT NULL,
            task TEXT NOT NULL,
            owner TEXT,
            deadline_raw TEXT,
            deadline TEXT,
            priority TEXT DEFAULT 'medium',
            speaker_label TEXT,
            status TEXT NOT NULL DEFAULT 'в работе',
            created_at TEXT NOT NULL
        );
        """)


def create_meeting(filename: str, path: str) -> int:
    with conn() as db:
        cur = db.execute(
            "INSERT INTO meetings(filename, original_path, status, created_at) VALUES (?,?,?,?)",
            (filename, path, "queued", _now()))
        return int(cur.lastrowid)


def log_event(meeting_id: int, stage: str, message: str) -> None:
    with conn() as db:
        db.execute("INSERT INTO events(meeting_id, ts, stage, message) VALUES (?,?,?,?)",
                   (meeting_id, _now(), stage, message))


def set_stage(meeting_id: int, status: str, stage: str) -> None:
    with conn() as db:
        db.execute("UPDATE meetings SET status=?, stage=? WHERE id=?", (status, stage, meeting_id))


def finish_meeting(meeting_id: int, result: dict, extract_mode: str, summary_mode: str) -> None:
    with conn() as db:
        db.execute("""
            UPDATE meetings SET status='done', finished_at=?, result_json=?,
                   extract_mode=?, summary_mode=? WHERE id=?
        """, (_now(), json.dumps(result, ensure_ascii=False), extract_mode, summary_mode, meeting_id))
        for i, a in enumerate(result.get("assignments", []), 1):
            db.execute("""
                INSERT INTO assignments(meeting_id, position, task, owner, deadline_raw,
                                        deadline, priority, speaker_label, created_at)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (meeting_id, i, a.get("task", ""), a.get("owner"), a.get("deadline_raw"),
                  a.get("deadline"), a.get("priority", "medium"), a.get("speaker_label"), _now()))


def fail_meeting(meeting_id: int, error: str) -> None:
    with conn() as db:
        db.execute("UPDATE meetings SET status='error', error=?, finished_at=? WHERE id=?",
                   (error[:2000], _now(), meeting_id))


def get_meeting(meeting_id: int) -> dict | None:
    with conn() as db:
        row = db.execute("SELECT * FROM meetings WHERE id=?", (meeting_id,)).fetchone()
        if not row:
            return None
        m = dict(row)
        m["result"] = json.loads(m.pop("result_json")) if m.get("result_json") else None
        m["events"] = [dict(r) for r in db.execute(
            "SELECT ts, stage, message FROM events WHERE meeting_id=? ORDER BY id",
            (meeting_id,))]
        m["assignments"] = [dict(r) for r in db.execute(
            "SELECT * FROM assignments WHERE meeting_id=? ORDER BY position", (meeting_id,))]
        return m


def list_meetings() -> list[dict]:
    with conn() as db:
        return [dict(r) for r in db.execute(
            "SELECT id, filename, status, stage, created_at, finished_at, error, "
            "       extract_mode, summary_mode FROM meetings ORDER BY id DESC")]


def set_assignment_status(assignment_id: int, status: str) -> None:
    with conn() as db:
        db.execute("UPDATE assignments SET status=? WHERE id=?", (status, assignment_id))


def assignment_overdue(iso_deadline: str | None) -> bool:
    if not iso_deadline:
        return False
    try:
        return datetime.fromisoformat(iso_deadline).date() < datetime.now().date()
    except ValueError:
        return False