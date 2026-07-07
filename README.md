# tactixnet

Decentralized multi-agent coordination engine for real-time tactics games. LangGraph-orchestrated squad negotiation over Redis, served through an async FastAPI gateway.

## Quickstart

```bash
# Clone and install
pip install -r requirements.txt
cp .env.example .env

# Start Redis + services
docker compose up -d redis

# Run gateway locally
uvicorn gateway.app:app --reload

# Run tests
pytest
```

## Architecture

See [docs/architecture.md](docs/architecture.md) (added in M7).

## Environment

| Variable | Description |
|----------|-------------|
| `REDIS_URL` | Redis connection string |
| `GROQ_API_KEY` | Groq API key for Tier-2 strategy layer |

## Branching

- `main` — release
- `develop` — integration lifeline
- `feature/*` — milestone branches merged via PR into `develop`
