"""LangSmith / LangChain tracing bootstrap.

Why this module exists (AI architect mental model)
-------------------------------------------------
- LangChain and LangGraph read tracing flags from the process environment
  (``LANGCHAIN_TRACING_V2``, ``LANGCHAIN_API_KEY``, ``LANGCHAIN_PROJECT``).
- Your API imports ``app.api.routes`` at startup; that module builds the
  compiled LangGraph at import time (``graph = build_workflow()``). If tracing
  env vars are set *after* that import, some runs still trace, but startup
  ordering becomes fragile across workers and CLI tools.
- So: **one small module** that only sets env + documents the contract, called
  from **entrypoints** (``app/main.py``, ``app/rag/ingest`` main) *before*
  importing anything that constructs LLMs or the graph.

We do **not** put this logic inside ``workflow.py`` because that file should
stay pure graph/node logic; mixing global env side effects there makes the
graph hard to test and reuse. We do **not** scatter ``os.environ`` writes in
every node for the same reason.
"""
from __future__ import annotations

import os

from app.core.settings import settings


def configure_langsmith() -> bool:
    """
    Enable LangSmith when an API key is present.

    Returns True if tracing was turned on, False if skipped (no key).
    """
    if not settings.langsmith_api_key:
        return False

    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key

    if settings.langsmith_project:
        os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project

    if settings.langsmith_endpoint:
        os.environ["LANGCHAIN_ENDPOINT"] = settings.langsmith_endpoint

    return True
