# ruff: noqa: E402, F403
from __future__ import annotations
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

import os

from app.core.tracing import configure_langsmith

configure_langsmith()

from app.api.routes import router as api_router

current_dir = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(current_dir, "static")

app = FastAPI(
    title="White-Label Multi-Agent Backend",
    version="1.0.0",
    description="Config-driven FastAPI + LangGraph backend for domain-agnostic deployments.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/")
async def root() -> HTMLResponse:
    return HTMLResponse(
        content=open(
            os.path.join(static_dir, "index.html"), "r", encoding="utf-8"
        ).read()
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
