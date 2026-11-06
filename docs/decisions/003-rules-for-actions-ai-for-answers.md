# ADR 003: Rules propose actions; AI only answers questions

**Status:** Accepted · 2026-11-06

## Context
Operational recommendations ("open overflow," "add transport staff") affect patients and staff. They must be explainable, reproducible and approved by a person.

## Decision
- **Recommendations come from transparent rules** (`ops/suggestions.py`), each with its evidence attached. A named person must approve or dismiss each one, and every decision is written to a **hash-chained audit log**.
- **The language model is only used to answer questions**, through **read-only tools**. A deterministic **grounding check** flags any number in an answer that does not appear in a tool result.
- An **offline engine** (keyword routing over the same tools) is the default, so the product works with no cloud dependency. **Microsoft Foundry** is used automatically when `FOUNDRY_PROJECT_ENDPOINT` is set.

## Alternatives considered
- **Let the LLM generate actions:** harder to explain, harder to test, and it invites automation bias.
- **LLM-only assistant with no offline path:** demos and tests would depend on credentials and cost money per run.

## Consequences
- ✅ Every action is explainable and auditable. Every answer is checkable.
- ✅ The same evaluation harness scores either engine.
- ⚠️ The offline engine only understands a fixed set of question types. That's by design; Foundry handles open-ended phrasing.
