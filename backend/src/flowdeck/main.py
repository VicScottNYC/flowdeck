"""FlowDeck API: HL7 listener + live operations read models over REST and WebSocket.

Run locally:
    cd backend && uv run uvicorn flowdeck.main:app --reload
The demo hospital loads automatically (FLOWDECK_DEMO=1, default). To stream new
traffic into a fresh database instead:
    FLOWDECK_DEMO=0 uv run uvicorn flowdeck.main:app
    python simulator/simulate_day.py --send --speed 60
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from flowdeck.assistant.brief import huddle_brief
from flowdeck.assistant.engine import default_engine
from flowdeck.census.state import CLEAN, DIRTY
from flowdeck.fhir import mapper
from flowdeck.hl7 import mllp
from flowdeck.ops import audit
from flowdeck.service import FlowDeck
from flowdeck.store import Store

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("flowdeck")

ROOT = Path(__file__).resolve().parents[3]
HOSPITAL_CONFIG = Path(os.getenv("FLOWDECK_HOSPITAL_CONFIG", ROOT / "simulator" / "hospital.json"))
DB_PATH = os.getenv("FLOWDECK_DB", ":memory:")
MLLP_PORT = int(os.getenv("FLOWDECK_MLLP_PORT", "2575"))
DEMO = os.getenv("FLOWDECK_DEMO", "1") == "1"
FRONTEND_DIST = ROOT / "frontend" / "dist"

fd = FlowDeck(HOSPITAL_CONFIG, Store(DB_PATH))
engine = default_engine()


class Hub:
    """Fan-out of census changes to every connected browser."""

    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()

    async def broadcast(self, payload: dict) -> None:
        for ws in list(self.clients):
            try:
                await ws.send_json(payload)
            except Exception:
                self.clients.discard(ws)


hub = Hub()


async def handle_message(raw: str) -> None:
    status, changed, event = fd.ingest(raw)  # raises on malformed input -> NAK
    if changed:
        await hub.broadcast({"type": "census", "event": event, "beds": [asdict(b) for b in changed],
                             "overview": fd.overview()})


@asynccontextmanager
async def lifespan(app: FastAPI):
    if DEMO and fd.store.is_empty():
        from flowdeck.demo import seed_demo
        log.info("Seeded demo hospital: %s", seed_demo(fd))
    server = await mllp.serve(handle_message, port=MLLP_PORT)
    task = asyncio.create_task(server.serve_forever())
    yield
    server.close()
    task.cancel()


app = FastAPI(title="FlowDeck", version="1.0.0", lifespan=lifespan,
              description="Real-time operations layer on top of legacy HIS HL7 v2 feeds.")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


def _at(at: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(at) if at else None
    except ValueError as exc:
        raise HTTPException(422, "at must be an ISO timestamp") from exc


# ---- system -----------------------------------------------------------------
@app.get("/api/health")
def health() -> dict:
    lo, hi = fd.store.event_bounds()
    return {"status": "ok", "beds": len(fd.census.beds), "mllp_port": MLLP_PORT, "assistant": engine.name,
            "messages": fd.store.message_stats(), "first_event": lo, "last_event": hi,
            "as_of": fd.now.isoformat(), "conflicts": len(fd.census.conflicts)}


@app.get("/api/hospital")
def hospital() -> dict:
    return {"units": list(fd.census.units.values()), "as_of": fd.now.isoformat()}


# ---- census & flow ------------------------------------------------------------
@app.get("/api/overview")
def overview(at: str | None = None) -> dict:
    return fd.overview(_at(at))


@app.get("/api/units/{unit}/beds")
def unit_beds(unit: str, at: str | None = None) -> list[dict]:
    beds = fd.census_at(_at(at)).beds_json(unit.upper())
    if not beds:
        raise HTTPException(404, f"Unknown unit {unit}")
    return beds


@app.get("/api/events")
def events(limit: int = 40, at: str | None = None) -> list[dict]:
    return fd.recent_events(min(limit, 200), _at(at))


@app.get("/api/boarding")
def boarding(at: str | None = None) -> list[dict]:
    return fd.census_at(_at(at)).boarding()


@app.get("/api/discharges")
def discharges(at: str | None = None) -> list[dict]:
    return fd.discharges(_at(at))


@app.get("/api/barriers")
def barriers(dept: str | None = None, at: str | None = None) -> list[dict]:
    return fd.open_barriers(dept, _at(at))


@app.get("/api/forecast")
def forecast(hours: int = 8, at: str | None = None) -> list[dict]:
    return fd.forecast(max(1, min(hours, 24)), _at(at))


@app.get("/api/conflicts")
def conflicts() -> list[dict]:
    return [asdict(c) for c in fd.census.conflicts]


class BedStatus(BaseModel):
    status: str = Field(pattern=f"^({CLEAN}|{DIRTY})$")
    actor: str = Field(min_length=1)


@app.post("/api/beds/{bed_id}/status")
async def set_bed_status(bed_id: str, body: BedStatus) -> dict:
    if bed_id not in fd.census.beds:
        raise HTTPException(404, "Unknown bed")
    try:
        bed = fd.census.mark_status(bed_id, body.status, fd.now)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    audit.append(fd.store, body.actor, "bed.status", {"bed_id": bed_id, "status": body.status}, fd.now)
    await hub.broadcast({"type": "census", "event": None, "beds": [asdict(bed)], "overview": fd.overview()})
    return asdict(bed)


class Actor(BaseModel):
    actor: str = Field(min_length=1)
    note: str = ""


@app.post("/api/barriers/{barrier_id}/resolve")
def resolve_barrier(barrier_id: int, body: Actor) -> dict:
    fd.resolve_barrier(barrier_id, body.actor)
    return {"ok": True}


# ---- AI: assistant, brief, suggestions --------------------------------------
class Question(BaseModel):
    question: str = Field(min_length=2, max_length=500)


@app.post("/api/assistant/ask")
def ask(body: Question) -> dict:
    return asdict(engine.ask(fd, body.question))


@app.get("/api/brief")
def brief() -> dict:
    return huddle_brief(fd)


@app.get("/api/suggestions")
def suggestions() -> list[dict]:
    return fd.refresh_suggestions()


@app.post("/api/suggestions/{sid}/{decision}")
def decide(sid: int, decision: str, body: Actor) -> dict:
    try:
        return fd.decide(sid, {"approve": "approved", "reject": "rejected"}.get(decision, decision),
                         body.actor, body.note)
    except KeyError as exc:
        raise HTTPException(404, "Unknown suggestion") from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/api/audit")
def audit_log() -> dict:
    return {"verification": audit.verify(fd.store), "entries": audit.entries(fd.store)[::-1]}


@app.get("/api/messages/latest")
def latest_message(trigger: str | None = None) -> dict:
    """Most recent raw HL7 message plus the FHIR Encounter FlowDeck derives from it."""
    sql = "SELECT raw, received_at, status FROM adt_messages WHERE status='accepted'"
    params: tuple = ()
    if trigger:
        sql += " AND trigger=?"
        params = (trigger.upper(),)
    rows = fd.store.query(sql + " ORDER BY event_time DESC, id DESC LIMIT 1", params)
    if not rows:
        raise HTTPException(404, "No messages yet")
    from flowdeck.hl7.parser import parse_adt

    ev = parse_adt(rows[0]["raw"])
    enc = {k: v for k, v in mapper.encounter(fd, ev.visit_number).items() if v is not None}
    # Mask identifiers in the raw message before it reaches a browser.
    masked = "\r".join(
        "|".join(f if i not in (3, 5, 7) else "***" for i, f in enumerate(seg.split("|")))
        if seg.startswith("PID") else seg for seg in rows[0]["raw"].split("\r"))
    return {"raw": masked, "status": rows[0]["status"], "event": asdict(ev) | {"mrn": "***"}, "fhir": enc,
            "stats": fd.store.message_stats()}


@app.get("/api/evals")
def evals() -> dict:
    """Latest evaluation results committed under evals/results/."""
    out = {}
    for f in (ROOT / "evals" / "results").glob("*.json"):
        data = json.loads(f.read_text())
        data.pop("failures", None)
        out[f.stem] = data
    return out


# ---- FHIR -------------------------------------------------------------------
@app.get("/fhir/Encounter/{visit}")
def fhir_encounter(visit: str) -> dict:
    try:
        return {k: v for k, v in mapper.encounter(fd, visit).items() if v is not None}
    except KeyError as exc:
        raise HTTPException(404, "Unknown visit") from exc


@app.get("/fhir/Location")
def fhir_locations() -> dict:
    return mapper.bundle(mapper.locations(fd))


# ---- live updates --------------------------------------------------------------
@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    await websocket.accept()
    hub.clients.add(websocket)
    await websocket.send_json({"type": "snapshot", "overview": fd.overview()})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        hub.clients.discard(websocket)


# ---- serve the built React app (production / single-process demo) ---------------
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        file = FRONTEND_DIST / path
        return FileResponse(file if path and file.is_file() else FRONTEND_DIST / "index.html")
