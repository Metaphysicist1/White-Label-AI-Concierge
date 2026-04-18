# White-Label AI Concierge (FastAPI + LangGraph + Chroma)

Production-ready, domain-agnostic AI assistant stack:

- **Backend:** FastAPI + LangGraph
- **Knowledge:** Web scraping JSON + PDF ingestion -> embeddings -> Chroma vector DB
- **Lead capture:** Dynamic slot filling -> SQLite
- **Frontend:** Floating website chat widget
- **Infra:** Docker, docker-compose, Azure Web App for Containers, GitHub Actions CI/CD

Main goal: clone this repo, update `config/domain_config.yaml`, add URLs/PDFs, deploy.

## System Components

- **Frontend (`app/static/index.html`)**
  - Foldable floating chat widget
  - Calls `POST /api/chat`
  - Persists `thread_id` in browser localStorage
  - Shows retrieval status text while waiting

- **Backend API (`app/main.py`, `app/api/routes.py`)**
  - Stateless REST endpoints
  - Passes `thread_id` into LangGraph checkpointer
  - Supports normal and streaming chat

- **Agent graph (`app/graph/workflow.py`)**
  - Query rewriter
  - Semantic router (`faq`, `lead_capture`, `general`)
  - RAG over Chroma
  - Lead capture + SQLite commit
  - MemorySaver for multi-turn conversation state

- **Knowledge ingestion (`app/rag/ingest.py`)**
  - Ingests both:
    - PDFs from `data/pdfs/`
    - scraped web JSON from `scraper/data/knowledge.json`
  - Chunk -> embed -> upsert into Chroma collection

- **Web crawler (`scraper/scraper_script.py`)**
  - Reads seed URLs from `scraper/data/urls.txt`
  - Crawls same-domain subpages (`/about`, `/contact`, etc.)
  - Writes normalized JSON knowledge file

- **Databases**
  - **Chroma** for vector retrieval
  - **SQLite** for leads (`db/leads.db`)

- **Infra**
  - `Dockerfile` (production-oriented)
  - `docker-compose.yml` (local app + chroma)
  - `.github/workflows/deploy.yml` (build + deploy container to Azure)

## Project Structure

```text
app/
  api/routes.py
  core/config.py
  core/settings.py
  db/lead_store.py
  graph/workflow.py
  rag/ingest.py
  schemas/chat.py
  static/index.html
config/
  domain_config.yaml
scraper/
  scraper_script.py
  data/urls.txt
  data/knowledge.json      # generated
data/pdfs/
db/
docker-compose.yml
Dockerfile
```

## 5-Minute Implementation Flow

1. **Set environment**
   - Create/update `.env`:

   ```env
   OPENAI_API_KEY=your_key_here
   OPENAI_CHAT_MODEL=gpt-4o-mini
   OPENAI_EMBEDDING_MODEL=text-embedding-3-small
   CHROMA_HOST=localhost
   CHROMA_PORT=8001
   APP_ENV=development
   ```

2. **Configure your domain**
   - Edit `config/domain_config.yaml`:
     - persona/system prompt
     - routing intents
     - lead slot fields
     - RAG paths/language

3. **Add company knowledge**
   - URLs -> `scraper/data/urls.txt`
   - PDFs -> `data/pdfs/`

4. **Run crawler**
   - `python scraper/scraper_script.py`

5. **Start app + chroma**
   - `docker compose up --build`

6. **Ingest knowledge**
   - `python -m app.rag.ingest`

7. **Test chat**
   - Open `http://localhost:8000`
   - Ask questions based on your URLs and PDFs

## Running Modes

- **Full Docker (recommended local):**
  - App in docker + Chroma in docker
  - `.env`: `CHROMA_HOST=chroma`, `CHROMA_PORT=8000`

- **App local, Chroma docker:**
  - `.env`: `CHROMA_HOST=localhost`, `CHROMA_PORT=8001`

- **Both local (no docker):**
  - `.env`: `CHROMA_HOST=localhost`, `CHROMA_PORT=8000`

The code tries multiple endpoints and falls back to local persistent Chroma if needed.

## Knowledge Pipeline (Web + PDF)

### Web crawl

- Input: `scraper/data/urls.txt`
- Output: `scraper/data/knowledge.json`
- Behavior:
  - same-domain crawl
  - BFS strategy
  - depth/page limits in `scraper/scraper_script.py`

### Ingestion commands

- Ingest all:
  - `python -m app.rag.ingest`
- Only web:
  - `python -m app.rag.ingest --only-web`
- Only pdf:
  - `python -m app.rag.ingest --only-pdfs`
- Local persistent chroma:
  - `python -m app.rag.ingest --local-chroma`

## API Contract

- `POST /api/chat`
  - body:

  ```json
  {
    "message": "Tell me about your services",
    "thread_id": "user-123"
  }
  ```

- `POST /api/chat/stream`
- `GET /health`

`thread_id` is required for multi-turn memory.

## Frontend Customization

Edit `app/static/index.html`:

- `CHAT_WIDGET_CONFIG.title`
- `CHAT_WIDGET_CONFIG.subtitle`
- `CHAT_WIDGET_CONFIG.welcomeMessage`
- primary colors (`:root` CSS variables)
- loading status messages

This is your white-label chat UI template.

## Azure CI/CD

- Workflow: `.github/workflows/deploy.yml`
- Flow:
  1. Build docker image
  2. Push to Azure Container Registry
  3. Deploy to Azure Web App for Containers

Required GitHub secrets/vars:

- `REGISTRY_LOGIN_SERVER`
- `REGISTRY_USERNAME`
- `REGISTRY_PASSWORD`
- `AZURE_WEBAPP_PUBLISH_PROFILE`
- `AZURE_WEBAPP_NAME` (repository variable)

## Quick Validation Before Deploy

1. `python -m app.rag.ingest --only-web`
2. `python -m app.rag.ingest --only-pdfs`
3. Chat asks:
   - web fact question
   - pdf fact question
   - mixed question
   - lead capture flow
4. Confirm lead saved in SQLite.

## Troubleshooting

- **Chroma connection fails locally**
  - set `.env` to `CHROMA_HOST=localhost`
  - use `CHROMA_PORT=8001` if chroma is via docker compose

- **Answers not grounded in your content**
  - re-run scraper
  - re-run ingestion
  - verify `domain_config.yaml` paths

- **Widget opens but no response**
  - verify backend is up
  - check `/health`
  - confirm API path in widget config is `/api/chat`
