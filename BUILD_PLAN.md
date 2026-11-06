# FlowDeck Build Plan
### A real-time operations layer for hospitals (Project 5)

> **Elevator pitch:** Hospitals run on legacy information systems that can't show a live picture of beds, transfers and discharges, and departments can't easily see each other's work. FlowDeck doesn't replace that system. It **listens** to the HL7 v2 feed the system already sends and adds a live bed board, discharge-barrier tracking, capacity forecasting and an AI operations assistant on top.

**Repo:** `flowdeck` · **Estimated effort to L4:** about 50–60 hours
**Stack:** Python 3.12 + FastAPI · React + TypeScript (Vite) · Postgres (local Docker; Supabase or Azure later) · HAPI FHIR (local) → Azure Health Data Services (L4) · Microsoft Foundry (AI)

---

## Ground rules (these also appear in the README)

1. **Operational, never clinical.** FlowDeck tracks beds, flow and logistics. It never suggests diagnoses or treatment.
2. **Minimum necessary data.** Screens show room, initials and status, never names or diagnoses.
3. **Synthetic data only.** It runs against the fictional *Meridian General Hospital* (`simulator/hospital.json`).
4. **Listen, don't replace.** FlowDeck never writes back to the legacy system (see ADR 001).
5. **AI recommends, people decide.** Every resource change needs a named human to approve it, and each approval is logged.

---

## Status (November 2026)

| Level | Status | Notes |
|---|---|---|
| **L1 Listen** | ✅ Complete | SQLite event store with replay ([ADR 002](docs/decisions/002-sqlite-event-store.md)), raw archive, duplicates and conflicts handled, time travel |
| **L2 See** | ✅ Complete | React + TypeScript UI: command center, bed board, discharge barriers, ED boarding, replay slider, live WebSocket |
| **L3 Think** | ✅ Complete | FHIR R4 mapper, backtested forecast (32–34% better than baseline), Foundry/offline assistant with grounding check, huddle brief, approvals + hash-chained audit, evaluations in CI |
| **L4 Run** | ⏳ Roadmap | Azure deployment (`azd` + Bicep), `$convert-data` comparison, Entra ID roles, App Insights tracing |

Deviations from the original plan, each recorded as an ADR:
- **SQLite instead of Postgres** so anyone can run it with zero setup. The schema is plain SQL and Postgres-ready.
- **Rules generate recommendations; the LLM only answers questions** ([ADR 003](docs/decisions/003-rules-for-actions-ai-for-answers.md)).
- **No Tailwind.** A small custom design system in `index.css` gives full control over the look.
- **Housekeeping** uses a 60-minute turnaround model plus a `POST /api/beds/{id}/status` endpoint, instead of simulator-emitted EVS events.

The original plan follows for reference.

---

## Level 1: Listen (≈12 hrs)
**Goal:** Durable, correct ingestion. Events are stored, the census survives a restart, and edge cases are handled.

- [ ] **1.1 Postgres event store.** Add `docker-compose.yml` services (already stubbed). Tables:
  - `adt_events`: raw message, parsed fields, `message_control_id UNIQUE`, `received_at`
  - `beds`: current state
  - Rebuild the census on startup by replaying events (event sourcing). Write an ADR on why you replay events instead of only storing current state. (Answer: an audit trail plus time-travel queries.)
- [ ] **1.2 Raw message archive.** Store every raw HL7 message exactly as received, even rejected ones, with the reason. Integration teams always ask, "Did you get message X?"
- [ ] **1.3 Out-of-order and edge cases**, each with a test:
  - a discharge that arrives before its admit
  - A11 cancel admit and A13 cancel discharge
  - a transfer to an occupied bed (flag a conflict; don't overwrite)
  - an unknown bed ID
- [ ] **1.4 Housekeeping events.** Replace the `tick()` cleaning stand-in with a real `POST /beds/{id}/status` endpoint (dirty → in-progress → clean), and have the simulator emit those events too.
- [ ] **1.5 Time travel.** `GET /census?at=2026-11-06T14:00` replays events up to that moment. This becomes your demo hook and the base for evaluations.

**Acceptance:** Restart the API mid-stream and the census is identical afterward. The edge-case tests pass. Tag `v0.1-L1`.

---

## Level 2: See (≈14 hrs) — your web-dev chops
**Goal:** A React live bed board and a discharge barrier tracker that people across departments can use.

- [ ] **2.1 React + TypeScript app** (`npm create vite@latest frontend -- --template react-ts`), styled with Tailwind.
- [ ] **2.2 Hospital overview:** one tile per unit with occupancy %, clean/dirty/occupied counts and a color threshold. Updates live from `/ws` (the snapshot message, then incremental updates).
- [ ] **2.3 Unit bed board:** a room-by-room grid with status color, initials, time in status, and an animation when something changes.
- [ ] **2.4 Discharge barrier tracker.** This is the feature that connects departments:
  - New table `discharge_barriers (visit, type, owner_dept, opened_at, resolved_at, note)`, with types `labs | pharmacy | transport | case_mgmt | family | imaging`
  - Each department filters to its own open barriers, and "time open" counts up
  - Expected-discharge-today list, sorted by number of barriers
  - The simulator creates barriers on about 60% of planned discharges and resolves them over time
- [ ] **2.5 ED boarding view:** patients who were admitted but are still in an ED bed, with wait time. The simulator already creates boarding, so you should see it.
- [ ] **2.6 Replay mode:** a time slider plus 1×/10×/60× playback using `/census?at=`. This makes the 2-minute demo GIF.
- [ ] **2.7 Tests:** Playwright end-to-end (start the simulator, check that a tile updates) and component tests (Vitest). CI runs both.

**Acceptance:** Watch a full simulated day in under 2 minutes and see the bottleneck form. Demo GIF recorded. Tag `v0.2-L2`.

---

## Level 3: Think (≈16 hrs) — AI with guardrails
**Goal:** Forecasting and an ops assistant whose answers you can verify, because the simulator knows the ground truth.

- [ ] **3.1 FHIR conversion:** map events to FHIR `Encounter` (with `location` history), `Location` (beds and units) and `Patient` (minimal). Validate with `fhir.resources` and POST to local HAPI FHIR (`docker compose up fhir`). Reuse your ClearIntake skills.
- [ ] **3.2 Capacity forecast.** Start without AI:
  - a baseline forecast of occupancy per unit 4/8/24 hours out, from current census + expected discharges + ED admit rate
  - **evaluation:** simulate 30 seeded days and measure forecast error (MAE) against the actual timelines
  - only then try improvements (historical patterns, or a model) and keep them only if the error drops. Record the result in an ADR.
- [ ] **3.3 Ops assistant (Foundry agent, read-only tools):**
  - tools: `get_census(at)`, `get_unit(unit)`, `get_boarding()`, `get_open_barriers(dept?)`, `get_forecast(unit, hours)`
  - every answer cites the event IDs or tool results it used, and a rule-based check rejects any number that doesn't appear in a tool result
  - **no write tools.** It can't move patients or change anything.
- [ ] **3.4 Morning huddle brief:** at 07:30 (simulated time), generate a one-page brief covering capacity, top 5 barriers, boarding and forecast risk. Use structured output, then render it.
- [ ] **3.5 Approval-gated suggestions:** the assistant may *propose* actions ("open overflow unit," "prioritize 3 transports for 4W"). Each proposal goes to an approvals queue, a human approves or rejects it, and an audit log records who decided and when, hash-chained like Diligence Desk.
- [ ] **3.6 Evaluation harness** (`evals/`). Because the simulator is seeded, every answer has a known correct value:
  - 40 questions with exact answers ("How many patients are boarding at 14:00?") → accuracy
  - groundedness of the huddle brief (`azure-ai-evaluation`)
  - **privacy check:** confirm that no full name from the simulator appears in any prompt or output
  - prompt injection: a patient name or barrier note containing "ignore previous instructions…" must not change behavior

**Acceptance:** Forecast error and assistant accuracy are in the README results table. The privacy check passes on 100% of prompts. Tag `v0.3-L3`.

---

## Level 4: Run (≈14 hrs) — production on Azure
**Goal:** Deploy it, operate it, and prove that the "listen to the legacy feed" approach works with Azure's own tools.

- [ ] **4.1 Azure Health Data Services FHIR + `$convert-data`.** Convert your simulator's HL7 v2 using Microsoft's built-in templates (ADT_A01/A02/A03 are supported). Compare the output with your own mapper and write an ADR on when you'd use each.
- [ ] **4.2 Hosting:** the API on Container Apps, the frontend on Static Web Apps, Postgres (Azure Database for PostgreSQL Flexible Server, or keep Supabase). The MLLP listener needs a TCP port, so document how you expose it securely (internal-only ingress plus a VPN or private link in a real hospital). Record this in an ADR.
- [ ] **4.3 Identity and security:**
  - managed identity everywhere, no secrets in code
  - role-based screens with Entra ID sign-in: unit charge nurse, bed manager, EVS, ops leadership (your Okta/IAM background fits here)
  - the threat model is complete
- [ ] **4.4 Observability:**
  - OpenTelemetry traces from message received → parsed → census updated → websocket pushed
  - **message-to-screen latency** as the headline metric
  - an Application Insights dashboard
- [ ] **4.5 CI/CD:** lint, tests, Playwright, then evaluations (a gate on forecast error and assistant accuracy), then `azd deploy`.

**Acceptance:** `azd up` deploys everything from a clean clone. Message-to-screen p95 latency is in the README. Final GIF, Loom and LinkedIn post done. Tag `v1.0`.

---

## Going further (L5 ideas)
- **Equipment and supply tracking:** connect the idea from your Clinic Supply Tracker (IV pumps, wheelchairs, isolation carts) as a second resource type.
- **Transport dispatch:** a queue of patient-transport requests with ETA, created automatically from A02 transfers.
- **Staffing ratio overlay:** nurse-to-patient ratio per unit from a synthetic staffing roster, flagging units that will be short.
- **Voice:** a charge nurse asks "How many clean beds on 4 West?" by voice (AI-103 speech skills).

---

## Interview talking points this project gives you
1. "I built an MLLP listener and HL7 v2 parser from scratch, so I understand how legacy hospital systems actually talk."
2. "The census is event-sourced and idempotent. Duplicate and out-of-order messages are handled and tested."
3. "My simulator is seeded, so every AI answer has a known correct value. My assistant's accuracy is a measured number, not a guess."
4. "I compared my own HL7-to-FHIR mapper against Azure's `$convert-data` and documented when I'd use each."
5. "The AI can propose, but only a person can approve, and every decision lands in a hash-chained audit log."

## Reference docs
- HL7 v2 → FHIR with `$convert-data`: https://learn.microsoft.com/azure/healthcare-apis/fhir/convert-data-overview
- Azure Health Data Services FHIR service: https://learn.microsoft.com/azure/healthcare-apis/fhir/
- Foundry SDK overview: https://learn.microsoft.com/azure/foundry/how-to/develop/sdk-overview
- Azure AI Evaluation SDK: https://learn.microsoft.com/python/api/overview/azure/ai-evaluation-readme
- Background on legacy HIS modernization: https://dochours.com/healthcare-legacy-system-modernization/ · https://kms-technology.com/blog/legacy-system-in-healthcare/
