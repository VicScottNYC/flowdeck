# Threat model

| Area | Risk | Control in FlowDeck | Status |
|---|---|---|---|
| PHI in the feed | ADT messages carry MRN, name and DOB | The name is reduced to initials at parse time; the MRN is hashed for FHIR; the raw view masks PID-3/5/7 | ✅ Implemented + tested |
| Raw message archive | The archive contains full PHI | Kept server-side only, never sent to the AI or the browser unmasked | ✅ (encryption at rest planned for Azure) |
| AI data exposure | Model sees identifiers | Tools return bed IDs and initials only; an automated privacy check scans every prompt and answer | ✅ Tested on 110 questions |
| Prompt injection | Staff-entered barrier notes contain instructions | Tool output is wrapped as data; the system prompt forbids following it; an injection case runs in every evaluation | ✅ |
| Hallucinated numbers | The AI states a wrong figure | Grounding check flags any number not present in a tool result | ✅ |
| Unauthorized actions | Automation changes operations | No write tools for the AI; every decision needs a named person | ✅ |
| Audit tampering | A decision is edited after the fact | SHA-256 hash chain; verification on every load | ✅ Tested |
| Network | MLLP port exposed | Must be internal-only (private ingress or VPN to the hospital network) | ⏳ Azure deployment |
| Identity | Anyone can use the UI | Entra ID sign-in with role-based views | ⏳ Roadmap |
| Logs | Logs leak PHI | Logs record message status, never raw content | ✅ |
