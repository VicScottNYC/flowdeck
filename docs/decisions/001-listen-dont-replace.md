# ADR 001: Listen to the legacy feed; don't replace or write back

**Status:** Accepted · 2026-11-06

## Context
Hospital information systems are expensive to replace and risky to change. Most of them already send HL7 v2 ADT messages (admit, transfer, discharge) to other systems over MLLP. Modernization guides call wrapping a legacy system with a modern layer **encapsulation**.

## Decision
FlowDeck is a **read-only subscriber** to the HIS's ADT feed. It never writes back to the HIS. Anything FlowDeck adds (discharge barriers, approvals, forecasts) lives in FlowDeck's own store.

## Alternatives considered
- **Poll the HIS database directly.** Fragile, often against vendor terms, and it adds load to a system that can't take it.
- **Two-way integration (write orders/updates back).** Much higher clinical and regulatory risk; out of scope for a portfolio and for a first deployment.
- **Wait for a FHIR API from the vendor.** Many legacy systems have none, or only a partial one.

## Consequences
- ✅ No change is required to the legacy system. A hospital only needs to add FlowDeck as one more destination on its interface engine.
- ✅ The event log doubles as an audit trail and makes time-travel replay possible.
- ⚠️ FlowDeck is only as accurate as the feed. Duplicates, out-of-order and missing messages must be handled (see the L1 edge-case tests).
- ⚠️ Data FlowDeck owns (barriers, approvals) won't appear in the HIS unless a later integration is added.
