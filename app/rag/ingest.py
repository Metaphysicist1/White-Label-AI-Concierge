from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import List

import chromadb
from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFDirectoryLoader
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import load_domain_config
from app.core.settings import settings


def _validate_prerequisites() -> None:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for embedding generation.")


def _build_store(use_remote_chroma: bool) -> Chroma:
    cfg = load_domain_config()
    embeddings = OpenAIEmbeddings(
        model=settings.openai_embedding_model,
        api_key=settings.openai_api_key,
    )
    if use_remote_chroma:
        endpoint_candidates = [
            (settings.chroma_host, settings.chroma_port),  # env-configured endpoint
            ("localhost", 8001),  # docker-compose mapped host endpoint
            ("localhost", 8000),  # local chroma default endpoint
        ]
        for host, port in endpoint_candidates:
            try:
                client = chromadb.HttpClient(host=host, port=port)
                return Chroma(
                    collection_name=cfg.rag.collection_name,
                    client=client,
                    embedding_function=embeddings,
                )
            except Exception:
                continue

    return Chroma(
        collection_name=cfg.rag.collection_name,
        persist_directory=cfg.rag.persist_directory,
        embedding_function=embeddings,
    )


def _load_pdf_documents(pdf_dir: Path) -> List[Document]:
    if not pdf_dir.exists():
        return []
    return PyPDFDirectoryLoader(str(pdf_dir)).load()


def _load_web_documents(web_json_path: Path) -> List[Document]:
    if not web_json_path.exists():
        return []

    raw = json.loads(web_json_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"Expected list in {web_json_path}, got: {type(raw).__name__}")

    docs: List[Document] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url", "")).strip()
        title = str(item.get("title", "")).strip()
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        docs.append(
            Document(
                page_content=content,
                metadata={
                    "source_type": "web",
                    "source": url or str(web_json_path),
                    "title": title,
                },
            )
        )
    return docs


def ingest_knowledge(
    chunk_size: int = 1200,
    chunk_overlap: int = 150,
    use_remote_chroma: bool = True,
    include_pdfs: bool = True,
    include_web: bool = True,
) -> int:
    _validate_prerequisites()
    cfg = load_domain_config()
    documents: List[Document] = []

    if include_pdfs:
        documents.extend(_load_pdf_documents(Path(cfg.rag.document_path)))
    if include_web:
        documents.extend(_load_web_documents(Path(cfg.rag.web_data_path)))

    if not documents:
        return 0

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    chunks = splitter.split_documents(documents)

    store = _build_store(use_remote_chroma=use_remote_chroma)
    ids: List[str] = []
    for chunk in chunks:
        source = chunk.metadata.get("source", "unknown")
        page = chunk.metadata.get("page", 0)
        digest = hashlib.sha1(chunk.page_content.encode("utf-8")).hexdigest()[:12]
        safe_source = Path(str(source)).stem or "source"
        ids.append(f"{safe_source}-{page}-{digest}")

    store.add_documents(documents=chunks, ids=ids)
    return len(chunks)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest PDFs and scraped web JSON into Chroma."
    )
    parser.add_argument("--chunk-size", type=int, default=1200)
    parser.add_argument("--chunk-overlap", type=int, default=150)
    parser.add_argument("--only-pdfs", action="store_true", help="Ingest only PDFs.")
    parser.add_argument(
        "--only-web", action="store_true", help="Ingest only scraped web JSON."
    )
    parser.add_argument(
        "--local-chroma",
        action="store_true",
        help="Use local persistent Chroma instead of CHROMA_HOST/CHROMA_PORT.",
    )
    args = parser.parse_args()

    if args.only_pdfs and args.only_web:
        raise SystemExit("Use only one of --only-pdfs or --only-web.")

    include_pdfs = not args.only_web
    include_web = not args.only_pdfs

    chunk_count = ingest_knowledge(
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        use_remote_chroma=not args.local_chroma,
        include_pdfs=include_pdfs,
        include_web=include_web,
    )
    print(f"Ingestion complete. Indexed chunks: {chunk_count}")


if __name__ == "__main__":
    main()
