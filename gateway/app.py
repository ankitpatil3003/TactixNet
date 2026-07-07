"""FastAPI gateway placeholder for M0 scaffold."""

from fastapi import FastAPI

app = FastAPI(title="TactixNet Gateway", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
