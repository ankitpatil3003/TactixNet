# tactixnet

Decentralized multi-agent coordination engine for real-time tactics games. LangGraph-orchestrated squad negotiation over Redis, served through an async FastAPI gateway.

## Features

- **Two-tier brain**: deterministic CNP reflex layer (<150ms p95) + optional LLM strategy layer via LangGraph
- **Contract Net Protocol**: decentralized role bidding from local perception only
- **Interrupt replanning**: mid-cycle ALERT triggers `compromised_replan` sub-graph
- **Redis message bus**: pub/sub fan-out + Streams event log
- **Simulation harness**: headless grid sim with benchmark rig

## Quickstart

```bash
pip install -r requirements.txt
cp .env.example .env
# Set GROQ_API_KEY for Tier-2 strategy (optional)

docker compose up -d redis
uvicorn gateway.app:app --reload --port 8000

# In another terminal
python -m engine.runner

# Run tests
pytest
```

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/squads` | POST | Create squad session |
| `/squads/{id}` | GET | Get squad state |
| `/squads/{id}/doctrine` | POST | Update strategy doctrine |
| `/ws/squads/{id}` | WS | Perception frames in, directives out |

## Environment

| Variable | Description |
|----------|-------------|
| `REDIS_URL` | Redis connection (default `redis://localhost:6379/0`) |
| `GROQ_API_KEY` | Groq API key for Tier-2 strategy layer |

## Architecture

```
Game Client → FastAPI Gateway → Redis Pub/Sub → LangGraph Orchestrator
                                      ↕                ↕
                                   Agents          Groq LLM (async)
```

See [docs/architecture.md](docs/architecture.md), [docs/protocol.md](docs/protocol.md), [docs/benchmark-methodology.md](docs/benchmark-methodology.md).

## Viewer

Open `viewer/index.html?squad=<squad-id>` while the gateway is running.

## Branching

- `main` — release
- `develop` — integration lifeline
- `feature/*` — milestone branches merged via PR into `develop`
