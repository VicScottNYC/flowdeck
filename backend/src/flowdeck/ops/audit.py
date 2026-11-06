"""Tamper-evident, hash-chained audit log.

Every human decision (approve/reject a suggestion, resolve a barrier) is
appended here. Each entry stores the hash of the previous one, so editing any
row breaks the chain from that point on, and ``verify`` finds it.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from flowdeck.store import Store

GENESIS = "GENESIS"


def _digest(entry: dict) -> str:
    body = {k: entry[k] for k in ("seq", "ts", "actor", "action", "payload", "prev_hash")}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def append(store: Store, actor: str, action: str, payload: dict, ts: datetime | None = None) -> dict:
    if not actor or not actor.strip():
        raise ValueError("Every audited action needs a named actor")
    last = store.query("SELECT seq, hash FROM audit_log ORDER BY seq DESC LIMIT 1")
    entry = {
        "seq": (last[0]["seq"] + 1) if last else 0,
        "ts": (ts or datetime.now()).isoformat(timespec="seconds"),
        "actor": actor.strip(),
        "action": action,
        "payload": json.dumps(payload, sort_keys=True, default=str),
        "prev_hash": last[0]["hash"] if last else GENESIS,
    }
    entry["hash"] = _digest(entry)
    store.execute("INSERT INTO audit_log VALUES (:seq,:ts,:actor,:action,:payload,:prev_hash,:hash)", entry)
    return entry


def entries(store: Store) -> list[dict]:
    return store.query("SELECT * FROM audit_log ORDER BY seq")


def verify(store: Store) -> dict:
    prev = GENESIS
    rows = entries(store)
    for row in rows:
        if row["prev_hash"] != prev or _digest(row) != row["hash"]:
            return {"valid": False, "entries": len(rows), "broken_at": row["seq"]}
        prev = row["hash"]
    return {"valid": True, "entries": len(rows), "broken_at": None}
