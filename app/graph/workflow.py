from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Any, Dict, List, Literal, Optional, TypedDict

import chromadb
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langsmith import traceable
from pydantic import BaseModel, EmailStr, Field, create_model

from app.core.config import DomainConfig, load_domain_config
from app.core.settings import settings
from app.db.lead_store import LeadRepository
import dotenv

dotenv.load_dotenv()


class RouterDecision(BaseModel):
    intent: Literal["faq", "lead_capture", "general"]
    rationale: str = Field(default="")


class RewriteOutput(BaseModel):
    rewritten_query: str


class WorkflowState(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], add_messages]
    intent: str
    rewritten_query: str
    retrieval_language: str
    slot_data: Dict[str, str]
    slot_complete: bool


def _build_dynamic_slot_model(config: DomainConfig) -> type[BaseModel]:
    field_type_map: Dict[str, Any] = {"str": str, "EmailStr": EmailStr}
    model_fields: Dict[str, Any] = {}
    for field in config.lead_capture.slot_schema.required_fields:
        py_type = field_type_map.get(field.type, str)
        # Optional at extraction-time prevents model from fabricating required values.
        model_fields[field.name] = (
            Optional[py_type],
            Field(default=None, description=field.description),
        )
    return create_model(config.lead_capture.slot_schema.model_name, **model_fields)


def _get_llm(temperature: float = 0.0) -> ChatOpenAI:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    return ChatOpenAI(
        model=settings.openai_chat_model,
        temperature=temperature,
        api_key=settings.openai_api_key,
    )


@traceable(run_type="retriever", name="chroma_similarity_search")
def _similarity_search_documents(query: str, k: int) -> List[Document]:
    vectorstore = _build_vectorstore()
    return vectorstore.similarity_search(query, k=k)


@lru_cache(maxsize=1)
def _build_vectorstore() -> Chroma:
    config = load_domain_config()
    embeddings = OpenAIEmbeddings(
        model=settings.openai_embedding_model,
        api_key=settings.openai_api_key,
    )
    endpoint_candidates = [
        (settings.chroma_host, settings.chroma_port),  # env-configured endpoint
        ("localhost", 8001),  # docker-compose mapped host endpoint
        ("localhost", 8000),  # local chroma default endpoint
    ]

    for host, port in endpoint_candidates:
        try:
            client = chromadb.HttpClient(host=host, port=port)
            return Chroma(
                collection_name=config.rag.collection_name,
                client=client,
                embedding_function=embeddings,
            )
        except Exception:
            continue

    return Chroma(
        collection_name=config.rag.collection_name,
        persist_directory=config.rag.persist_directory,
        embedding_function=embeddings,
    )


@traceable(run_type="chain", name="graph_node_query_rewriter")
def query_rewriter_node(state: WorkflowState) -> Dict[str, Any]:
    config = load_domain_config()
    user_input = next(
        msg.content
        for msg in reversed(state["messages"])
        if isinstance(msg, HumanMessage)
    )
    target_lang = config.rag.languages.target_retrieval
    rewriter = _get_llm(temperature=0).with_structured_output(RewriteOutput)
    rewritten = rewriter.invoke(
        [
            SystemMessage(
                content=(
                    "Rewrite the user question into an optimized semantic-search query. "
                    f"Normalize to language='{target_lang}'. Keep only compact searchable text."
                )
            ),
            HumanMessage(content=user_input),
        ]
    )
    return {
        "rewritten_query": rewritten.rewritten_query,
        "retrieval_language": target_lang,
    }


@traceable(run_type="chain", name="graph_node_semantic_router")
def semantic_router_node(state: WorkflowState) -> Dict[str, str]:
    config = load_domain_config()
    router = _get_llm(temperature=0).with_structured_output(RouterDecision)
    decision = router.invoke(
        [
            SystemMessage(
                content=(
                    "Classify the latest user intent using conversation history.\n"
                    f"Allowed intents: {config.router.intents}\n"
                    f"Descriptions: {config.router.descriptions}"
                )
            ),
            *state["messages"],
        ],
    )
    return {"intent": decision.intent}


@traceable(run_type="chain", name="graph_node_faq_rag")
def faq_rag_node(state: WorkflowState) -> Dict[str, List[AIMessage]]:
    config = load_domain_config()
    query = state.get("rewritten_query") or state["messages"][-1].content
    docs = _similarity_search_documents(query, config.rag.top_k)
    context = "\n\n".join(doc.page_content for doc in docs) if docs else ""
    llm = _get_llm(temperature=0.2)
    response = llm.invoke(
        [
            SystemMessage(
                content=(
                    config.persona.system_prompt
                    + "\n\nUse only the retrieved context for factual answers.\n"
                    + "If context is empty, say you are unsure and offer human support.\n"
                    + f"Respond in {state.get('retrieval_language', 'en')}.\n\n"
                    + f"Retrieved context:\n{context}"
                )
            ),
            state["messages"][-1],
        ]
    )
    return {"messages": [AIMessage(content=response.content)]}


@traceable(run_type="chain", name="graph_node_lead_capture")
def lead_capture_node(state: WorkflowState) -> Dict[str, Any]:
    config = load_domain_config()
    dynamic_model = _build_dynamic_slot_model(config)
    extractor = _get_llm(temperature=0).with_structured_output(dynamic_model)
    extracted = extractor.invoke(
        [
            SystemMessage(
                content=(
                    "Extract lead fields from the latest user message and prior context. "
                    "Use best effort from available conversation text."
                )
            ),
            *state["messages"],
        ]
    )
    extracted_data = extracted.model_dump()
    missing = [
        name
        for name, value in extracted_data.items()
        if value is None or not str(value).strip()
    ]

    if missing:
        ask = _get_llm(temperature=0.3).invoke(
            [
                SystemMessage(
                    content=(
                        config.persona.system_prompt
                        + "\nAsk for missing lead fields in one concise sentence."
                    )
                ),
                HumanMessage(
                    content=f"Missing fields: {', '.join(missing)}. Ask user to provide them."
                ),
            ]
        )
        return {
            "slot_data": extracted_data,
            "slot_complete": False,
            "messages": [AIMessage(content=ask.content)],
        }

    repo = LeadRepository(config.lead_capture.storage.sqlite_path)
    repo.insert_lead({k: str(v) for k, v in extracted_data.items()})
    return {
        "slot_data": extracted_data,
        "slot_complete": True,
        "messages": [
            AIMessage(
                content="Thanks, your details are saved. A team member will contact you shortly."
            )
        ],
    }


@traceable(run_type="chain", name="graph_node_general")
def general_node(state: WorkflowState) -> Dict[str, List[AIMessage]]:
    config = load_domain_config()
    llm = _get_llm(temperature=0.5)
    response = llm.invoke(
        [SystemMessage(content=config.persona.system_prompt), *state["messages"]]
    )
    return {"messages": [AIMessage(content=response.content)]}


@traceable(run_type="chain", name="graph_route_intent")
def route_intent(state: WorkflowState) -> str:
    intent = state.get("intent", "general")
    if intent == "faq":
        return "faq_rag"
    if intent == "lead_capture":
        return "lead_capture"
    return "general"


def build_workflow():
    graph = StateGraph(WorkflowState)
    graph.add_node("query_rewriter", query_rewriter_node)
    graph.add_node("semantic_router", semantic_router_node)
    graph.add_node("faq_rag", faq_rag_node)
    graph.add_node("lead_capture", lead_capture_node)
    graph.add_node("general", general_node)

    graph.add_edge(START, "query_rewriter")
    graph.add_edge("query_rewriter", "semantic_router")
    graph.add_conditional_edges(
        "semantic_router",
        route_intent,
        {"faq_rag": "faq_rag", "lead_capture": "lead_capture", "general": "general"},
    )
    graph.add_edge("faq_rag", END)
    graph.add_edge("lead_capture", END)
    graph.add_edge("general", END)

    # MemorySaver enables multi-turn state when caller passes thread_id in config.
    return graph.compile(checkpointer=MemorySaver())
