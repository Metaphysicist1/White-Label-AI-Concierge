from __future__ import annotations

import json
from typing import Any, AsyncGenerator, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from langsmith import traceable

from app.graph.workflow import build_workflow
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/api", tags=["chat"])
graph = build_workflow()


def _run_config(request: ChatRequest, endpoint: str) -> Dict[str, Any]:
    """LangGraph/LangSmith-friendly config: thread + tags + metadata for traces."""
    return {
        "configurable": {"thread_id": request.thread_id},
        "run_name": f"concierge_{endpoint.strip('/')}",
        "tags": ["concierge", "langgraph", endpoint],
        "metadata": {
            "thread_id": request.thread_id,
            "endpoint": endpoint,
        },
    }


@router.post("/chat", response_model=ChatResponse)
@traceable(run_type="chain", name="api_post_chat")
async def chat(request: ChatRequest) -> ChatResponse:
    if not request.thread_id.strip():
        raise HTTPException(status_code=400, detail="thread_id is required")

    try:
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=request.message)]},
            config=_run_config(request, "/api/chat"),
        )
        final_message = result["messages"][-1]
        return ChatResponse(
            thread_id=request.thread_id,
            intent=result.get("intent", "general"),
            response=final_message.content,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Chat processing failed: {exc}"
        ) from exc


@router.post("/chat/stream")
@traceable(run_type="chain", name="api_post_chat_stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    if not request.thread_id.strip():
        raise HTTPException(status_code=400, detail="thread_id is required")

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            async for event in graph.astream_events(
                {"messages": [HumanMessage(content=request.message)]},
                config=_run_config(request, "/api/chat/stream"),
                version="v2",
            ):
                payload = {"event": event.get("event"), "data": event.get("data", {})}
                yield f"data: {json.dumps(payload)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'event': 'error', 'data': str(exc)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
