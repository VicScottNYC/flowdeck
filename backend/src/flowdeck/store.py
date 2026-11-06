"""SQLite event store (see ADR 002).

Every raw HL7 message is archived exactly as received, accepted or rejected.
The census is never stored as truth; it is rebuilt by replaying accepted
messages, which gives us an audit trail and time travel for free.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS adt_messages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    control_id    TEXT,
    received_at   TEXT NOT NULL,
    event_time    TEXT,
    trigger       TEXT,
    status        TEXT NOT NULL CHECK (status IN ('accepted','duplicate','rejected')),
    error         TEXT,
    raw           TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_adt_control ON adt_messages(control_id) WHERE status = 'accepted';
CREATE INDEX IF NOT EXISTS ix_adt_time ON adt_messages(event_time);

CREATE TABLE IF NOT EXISTS expected_discharges (
    visit_number  TEXT PRIMARY KEY,
    flagged_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS barriers (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_number  TEXT NOT NULL,
    type          TEXT NOT NULL,
    owner_dept    TEXT NOT NULL,
    note          TEXT,
    opened_at     TEXT NOT NULL,
    resolved_at   TEXT
);
CREATE INDEX IF NOT EXISTS ix_barrier_visit ON barriers(visit_number);

CREATE TABLE IF NOT EXISTS suggestions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    key           TEXT UNIQUE NOT NULL,
    created_at    TEXT NOT NULL,
    kind          TEXT NOT NULL,
    severity      TEXT NOT NULL,
    title         TEXT NOT NULL,
    detail        TEXT NOT NULL,
    evidence      TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',
    decided_by    TEXT,
    decided_at    TEXT,
    decision_note TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    seq           INTEGER PRIMARY KEY,
    ts            TEXT NOT NULL,
    actor         TEXT NOT NULL,
    action        TEXT NOT NULL,
    payload       TEXT NOT NULL,
    prev_hash     TEXT NOT NULL,
    hash          TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._lock = threading.Lock()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def execute(self, sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self.db.execute(sql, params)
            self.db.commit()
            return cur

    def query(self, sql: str, params: tuple | dict = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self.db.execute(sql, params).fetchall()]

    # ---- ADT archive ----------------------------------------------------
    def archive(self, raw: str, status: str, control_id: str | None = None, event_time: datetime | None = None,
                trigger: str | None = None, error: str | None = None) -> None:
        self.execute(
            "INSERT INTO adt_messages (control_id, received_at, event_time, trigger, status, error, raw) "
            "VALUES (?,?,?,?,?,?,?)",
            (control_id, datetime.now().isoformat(timespec="seconds"),
             event_time.isoformat() if event_time else None, trigger, status, error, raw),
        )

    def has_control_id(self, control_id: str) -> bool:
        return bool(self.query("SELECT 1 FROM adt_messages WHERE control_id=? AND status='accepted'",
                               (control_id,)))

    def accepted_messages(self, until: datetime | None = None) -> list[str]:
        sql = "SELECT raw FROM adt_messages WHERE status='accepted'"
        params: tuple = ()
        if until:
            sql += " AND event_time <= ?"
            params = (until.isoformat(),)
        return [r["raw"] for r in self.query(sql + " ORDER BY event_time, id", params)]

    def message_stats(self) -> dict:
        rows = self.query("SELECT status, COUNT(*) n FROM adt_messages GROUP BY status")
        return {r["status"]: r["n"] for r in rows}

    def is_empty(self) -> bool:
        return not self.query("SELECT 1 FROM adt_messages LIMIT 1")

    def event_bounds(self) -> tuple[str | None, str | None]:
        r = self.query("SELECT MIN(event_time) lo, MAX(event_time) hi FROM adt_messages WHERE status='accepted'")[0]
        return r["lo"], r["hi"]

    # ---- discharges & barriers ------------------------------------------
    def flag_expected_discharge(self, visit: str, at: datetime) -> None:
        self.execute("INSERT OR IGNORE INTO expected_discharges VALUES (?,?)", (visit, at.isoformat()))

    def expected_discharge_visits(self, at: datetime) -> set[str]:
        rows = self.query("SELECT visit_number FROM expected_discharges WHERE flagged_at <= ?", (at.isoformat(),))
        return {r["visit_number"] for r in rows}

    def add_barrier(self, visit: str, type_: str, dept: str, opened: datetime, note: str = "",
                    resolved: datetime | None = None) -> int:
        cur = self.execute(
            "INSERT INTO barriers (visit_number, type, owner_dept, note, opened_at, resolved_at) VALUES (?,?,?,?,?,?)",
            (visit, type_, dept, note, opened.isoformat(), resolved.isoformat() if resolved else None))
        return cur.lastrowid

    def resolve_barrier(self, barrier_id: int, at: datetime) -> None:
        self.execute("UPDATE barriers SET resolved_at=? WHERE id=? AND resolved_at IS NULL",
                     (at.isoformat(), barrier_id))

    def barriers_as_of(self, at: datetime) -> list[dict]:
        """Barriers that existed at ``at``, with open/resolved status as of that moment."""
        rows = self.query("SELECT * FROM barriers WHERE opened_at <= ? ORDER BY opened_at", (at.isoformat(),))
        for r in rows:
            r["is_open"] = r["resolved_at"] is None or r["resolved_at"] > at.isoformat()
            if r["is_open"]:
                r["resolved_at"] = None
        return rows

    # ---- suggestions ----------------------------------------------------
    def upsert_suggestion(self, s: dict) -> None:
        self.execute(
            "INSERT OR IGNORE INTO suggestions (key, created_at, kind, severity, title, detail, evidence) "
            "VALUES (:key,:created_at,:kind,:severity,:title,:detail,:evidence)",
            {**s, "evidence": json.dumps(s["evidence"])})

    def suggestions(self) -> list[dict]:
        rows = self.query(
            "SELECT * FROM suggestions ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, "
            "CASE severity WHEN 'high' THEN 0 ELSE 1 END, id DESC")
        for r in rows:
            r["evidence"] = json.loads(r["evidence"])
        return rows
