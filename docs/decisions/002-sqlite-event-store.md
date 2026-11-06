# ADR 002: SQLite event store with replay (Postgres-ready)

**Status:** Accepted · 2026-11-06

## Context
FlowDeck needs to archive every raw HL7 message, survive restarts and answer "what did the hospital look like at 10:00?" A reviewer should be able to run it with no infrastructure.

## Decision
Use **SQLite** (Python standard library) as an append-only event store. The census is **never stored as truth**: it is rebuilt by replaying accepted messages in event-time order. Time travel (`?at=`) is the same replay with a cutoff.

## Alternatives considered
- **Postgres from day one:** production-grade, but every reviewer would need Docker first.
- **Store only current bed state:** simpler, but loses the audit trail, replay and the ability to backtest the forecast.

## Consequences
- ✅ Zero setup (`FLOWDECK_DB=flowdeck.db` for a file; in-memory by default).
- ✅ Replay powers time travel, restart recovery and the evaluation harness.
- ⚠️ A single-writer database. The schema is plain SQL, so moving to Postgres is a connection-string change plus a migration tool. Planned with the Azure deployment.
- ⚠️ Full replay is O(messages). Fine for days of data; add periodic snapshots for months.
