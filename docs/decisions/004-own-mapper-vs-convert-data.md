# ADR 004: Own HL7→FHIR mapper now; Azure `$convert-data` for scale

**Status:** Accepted · 2026-11-06

## Context
FlowDeck emits FHIR R4 `Encounter` (with location history) and `Location` resources. Azure Health Data Services offers `$convert-data`, with Microsoft-maintained Liquid templates for ADT_A01–A60 and other message types.

## Decision
Ship a **small, readable mapper** (`fhir/mapper.py`) that builds an Encounter from the *whole visit history* (needed for location periods), validated in tests with `fhir.resources` (R4B). Use `$convert-data` when FlowDeck runs on Azure and needs broad message coverage.

## Trade-offs
| | Own mapper | `$convert-data` |
|---|---|---|
| Coverage | ADT subset FlowDeck uses | Dozens of message types |
| Visit-level history | ✅ joins all events for a visit | Per message; needs post-processing |
| Runs offline / in tests | ✅ | Needs an Azure FHIR service |
| Maintenance | Ours | Microsoft templates (customizable) |

## Consequences
FlowDeck works anywhere today. On Azure, the two can be compared on the same simulated feed.
