# Architecture

## Data flow
1. **Legacy HIS** sends HL7 v2 ADT messages over **MLLP** (TCP, port 2575 by default).
2. **Listener** (`hl7/mllp.py`) unframes each message and replies `ACK` (`MSA|AA`) or `NAK` (`MSA|AE`).
3. **Service** (`service.py`) archives the raw message (accepted, duplicate or rejected) and applies it to the census.
4. **Census** (`census/state.py`) updates the bed model idempotently and records conflicts instead of overwriting.
5. **API** (`main.py`) serves read models over REST and pushes changes to browsers over `/ws`.
6. **Forecast, rules, assistant and FHIR** all read through `service.py`, so every screen, AI answer and evaluation uses one code path.

## Key HL7 fields
| Field | Meaning |
|---|---|
| MSH-9 | Message type, e.g. `ADT^A02` |
| MSH-10 | Message control ID (idempotency key) |
| EVN-2 | Event time |
| PID-3 / PID-5 | MRN / name. The name is reduced to initials; the MRN is hashed for FHIR |
| PV1-2 | Patient class (I, E, O) |
| PV1-3 | Assigned location `unit^room^bed^facility` |
| PV1-6 | Prior location (transfers) |
| PV1-10 | Hospital service (the target unit on an A06 admit decision) |
| PV1-19 | Visit number |

## Events handled
| Trigger | Meaning | Census effect |
|---|---|---|
| A01 | Admit / ED arrival | Bed → occupied |
| A06 | Outpatient → inpatient (admit decision) | ED patient starts **boarding** |
| A02 | Transfer | Old bed → dirty, new bed → occupied |
| A03 | Discharge | Bed → dirty, then clean after the EVS turnaround |
| A11 / A13 | Cancel admit / cancel discharge | Reverse the effect |
| A08 | Update | No bed change |

## Bed lifecycle
`clean → occupied → dirty → clean`. Housekeeping can also post `POST /api/beds/{id}/status`.

## API
`/api/overview` · `/api/units/{u}/beds` · `/api/events` · `/api/boarding` · `/api/discharges` · `/api/barriers` · `/api/forecast` · `/api/assistant/ask` · `/api/brief` · `/api/suggestions` · `/api/audit` · `/fhir/Encounter/{visit}` · `/fhir/Location` · `/ws`

Most read endpoints accept `?at=<ISO time>` for time travel. Interactive docs: `http://localhost:8000/docs`.
