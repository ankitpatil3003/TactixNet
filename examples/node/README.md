# Node.js integration

Minimal example using `@tactixnet/client` against a running gateway.

## Prerequisites

- Node.js 18+
- TactixNet gateway: `uvicorn gateway.app:app --port 8000`

## Run

```bash
cd sdk/typescript
npm install
npm run build

cd ../../examples/node
npm install
npm start
```

Set `TACTIXNET_GATEWAY=http://localhost:8000` to override the default URL.

## What it does

1. Creates a 2-agent squad via `POST /squads`
2. Connects WebSocket and sends one `PerceptionFrame`
3. Waits for a `directive` response
4. Fetches recent events via `GET /squads/{id}/events`
