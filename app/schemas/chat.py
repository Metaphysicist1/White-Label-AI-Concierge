from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    thread_id: str = Field(min_length=1, max_length=200)
    metadata: Optional[Dict[str, Any]] = None


class ChatResponse(BaseModel):
    thread_id: str
    intent: str
    response: str
