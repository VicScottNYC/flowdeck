# FlowDeck frontend

React 19 + TypeScript + Vite. No UI framework: the design system lives in `src/index.css` (tokens for dark and light themes).

```bash
npm install
npm run dev     # http://localhost:5173, proxies /api, /fhir and /ws to the API on :8000
npm run build   # outputs dist/, which the API serves at http://localhost:8000
```

| Path | What it is |
|---|---|
| `src/api.ts` | Typed API client |
| `src/state.tsx` | Live WebSocket updates, replay time, shared data hook |
| `src/pages/` | One file per screen |
| `src/components.tsx` | Cards, KPI tiles, capacity bar, legends |
