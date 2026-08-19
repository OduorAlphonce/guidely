# guidely

An internal knowledge assistant that answers questions in plain language and cites where the answer came from. Users upload company docs (policies, guides, FAQs), the system indexes them into vector embeddings, and then answers questions by retrieving relevant chunks and summarizing them via an LLM.

## Problem

Teams waste hours digging through scattered documents — policies in PDFs, FAQs in wikis, guides in shared drives — to find simple answers. New hires, support engineers, and even tenured employees struggle to locate accurate information quickly.

## Solution

Guidely combines **semantic search** with **LLM-powered answer generation**. Upload your documents once, then ask natural-language questions. Every answer includes source citations so users can verify and explore further.

## Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | React + Vite |
| **Backend** | FastAPI (Python 3.12) |
| **Embeddings** | OpenAI `text-embedding-ada-002` (with sentence-transformers fallback) |
| **Vector Store** | FAISS (local, disk-persisted) |
| **LLM** | OpenAI GPT-3.5/4-turbo |
| **Chunking** | tiktoken-based token-aware splitting |
| **Auth / Config** | python-dotenv (`.env`) |
| **Parsing** | Plain text, Markdown, PDF (via PyPDF2) |

## Architecture

```
User (Frontend)
    │
    ▼
[ React/Vite UI ]
    │  POST /api/search
    ▼
[ FastAPI Backend ]
    │
    ├── Parser    → reads .txt / .md / .pdf files
    ├── Chunker   → splits into ~800-token chunks with overlap
    ├── Embedder  → generates vectors via OpenAI / sentence-transformers
    ├── Vector DB → FAISS index (saved to disk)
    ├── LLM       → summarizes retrieved chunks with source citations
    └── Logger    → tracks latency, cache hits, error counts
```

### Data Flow

```
Upload Docs → Parse → Chunk → Embed → Store in FAISS
                                              │
Ask Question ──► Embed Query ──► FAISS Search ──► Top-k Chunks
                                                    │
                                              LLM generates answer
                                                    │
                                          {answer, sources[snippet, file]}
```

## Running the Backend

### 1. Set up the environment

```bash
# Create and activate a virtual environment
python3 -m venv backend/.venv
source backend/.venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure `.env`

Create a `.env` file in the repo root (a template already ships as `.env`):

```
# Optional — without a key the embedder falls back to a local
# sentence-transformers model and answer generation is disabled.
OPENAI_API_KEY=sk-...
```

> Note: the key is read once at startup, so restart the server after changing it.

### 3. Run the API

```bash
# From the repo root
backend/.venv/bin/python -m uvicorn backend.main:app --reload
```

The API is then available at:

- Interactive docs: http://localhost:8000/docs
- Health check: `curl http://localhost:8000/health`
- Metrics: `curl http://localhost:8000/metrics`
- Root: `curl http://localhost:8000/`

### 4. Useful endpoint calls

```bash
# Index the sample documents (and anything in data/uploads)
curl -X POST http://localhost:8000/api/documents/reindex

# Ask a question
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"question": "How many remote work days per week are allowed?"}'
```

### 5. Run the tests

Each suite is a standalone script run from the repo root (all pass without an OpenAI API key):

```bash
for t in test_llm test_parser test_chunker test_embedder test_search \
         test_retrieval test_indexing test_day4 test_metrics test_integration; do
  backend/.venv/bin/python "backend/tests/$t.py"
done
```

## Running the Frontend

The frontend is a React + Vite app that proxies API requests to the backend at `localhost:8000`.

### 1. Install dependencies

```bash
cd frontend
npm install
```

### 2. Start the dev server

Make sure the backend is already running on port 8000, then:

```bash
npm run dev
```

The frontend opens at http://localhost:5173. It automatically proxies `/api/*` requests to the backend.

### 3. Build for production

```bash
npm run build        # outputs to frontend/dist/
npm run preview      # serves the production build locally
```

> **Note:** The backend must be running for search and document management to work. Without it the UI will show network errors.

## Metrics

Measured by running `python backend/tests/test_indexing.py` (sentence-transformers fallback, CPU). Artifacts written to `backend/data/`.

| Metric | Value |
|---|---|
| Number of files indexed | 5 |
| Total chunks created | 63 |
| Total time taken (first-time indexing) | 2.59 s |
| Cache hit rate on re-index | 100% (all 5 files skipped, 0.3 ms) |
| Embedding vectors in FAISS | 63 |
| Embedding dimension | 384 (all-MiniLM-L6-v2 fallback) |
| Re-embedding on modified file | Yes (only the changed file) |
| Edge cases handled | Empty file, unsupported type, large file |

To reproduce: `backend/.venv/bin/python backend/tests/test_indexing.py`

## Project Structure

```
guidely/
├── frontend/
│   ├── public/
│   └── src/
│       ├── components/
│       ├── pages/
│       └── App.jsx
├── backend/
│   ├── main.py              # FastAPI app entry point
│   ├── routes/
│   │   ├── documents.py     # Document CRUD endpoints
│   │   └── search.py        # Q&A search endpoint
│   ├── models/
│   │   └── record.py        # Pydantic data models
│   ├── services/
│   │   ├── parser.py        # File parsing (txt, md)
│   │   ├── chunker.py       # Token-aware text chunking
│   │   ├── embedder.py      # Embedding generation
│   │   ├── indexing.py      # Indexing pipeline orchestration
│   │   ├── retrieval.py     # Vector search + LLM
│   │   ├── cache.py         # Embedding cache (skip unchanged files)
│   │   ├── vector_store.py  # FAISS persistence
│   │   ├── llm.py           # OpenAI answer generation
│   │   └── stats.py         # Metrics counters
│   ├── tests/
│   │   ├── test_parser.py       # Parser unit tests
│   │   ├── test_chunker.py      # Chunker unit tests
│   │   ├── test_embedder.py     # Embedder unit tests
│   │   ├── test_search.py       # Search endpoint tests
│   │   ├── test_retrieval.py    # Retrieval verification
│   │   ├── test_indexing.py     # Indexing verification
│   │   ├── test_llm.py          # LLM service tests
│   │   ├── test_day4.py         # Edge cases, logging, stats
│   │   └── test_metrics.py      # /metrics + request-id tests
│   └── data/sample-docs/    # 5 sample documents
├── requirements.txt
├── plan.md
├── .env
└── README.md
```
