# Guidely

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
| **Parsing** | Plain text, Markdown |

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
    ├── Parser    → reads .txt / .md files
    ├── Chunker   → splits into ~800-token chunks with overlap
    ├── Embedder  → generates vectors via OpenAI / sentence-transformers
    ├── Vector DB → FAISS index (saved to disk)
    ├── LLM       → summarizes retrieved chunks with source citations
    ├── Query Log → records every query for CSV export
    ├── Tags      → document categorization and filtering
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

## Setup Instructions

### Prerequisites

- Python 3.12+
- Node.js 18+ (for frontend)
- OpenAI API key (optional — uses sentence-transformers fallback without it)

### 1. Clone the repository

```bash
git clone <repo-url>
cd guidely
```

### 2. Set up the backend

```bash
# Create and activate a virtual environment
python3 -m venv backend/.venv
source backend/.venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure `.env`

Create a `.env` file in the repo root:

```
# Optional — without a key the embedder falls back to a local
# sentence-transformers model and answer generation is disabled.
OPENAI_API_KEY=sk-...
```

> Note: the key is read once at startup, so restart the server after changing it.

### 4. Run the backend

```bash
# From the repo root
backend/.venv/bin/python -m uvicorn backend.main:app --reload
```

The API is available at:

- Interactive docs: http://localhost:8000/docs
- Health check: `curl http://localhost:8000/health`
- Metrics: `curl http://localhost:8000/metrics`

### 5. Run the frontend

```bash
# Install frontend dependencies
cd frontend
npm install

# Start the dev server (make sure backend is running on port 8000)
npm run dev
```

The frontend opens at http://localhost:5173. It automatically proxies `/api/*` requests to the backend.

### 6. Build for production

```bash
cd frontend
npm run build        # outputs to frontend/dist/
npm run preview      # serves the production build locally
```

> **Note:** The backend must be running for search and document management to work.

## API Endpoints

### Search

```bash
# Ask a question
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"question": "How many remote work days per week are allowed?"}'
```

### Document Management

```bash
# List all documents
curl http://localhost:8000/api/documents/

# Upload a document
curl -X POST http://localhost:8000/api/documents/upload \
  -F "file=@path/to/document.txt"

# Re-index all documents
curl -X POST http://localhost:8000/api/documents/reindex

# Delete a document
curl -X DELETE http://localhost:8000/api/documents/<doc_id>
```

### Tags

```bash
# List all tags
curl http://localhost:8000/api/documents/tags

# Set tags for a document
curl -X POST http://localhost:8000/api/documents/<doc_id>/tags \
  -H "Content-Type: application/json" \
  -d '["policy", "hr"]'

# Add a single tag
curl -X POST http://localhost:8000/api/documents/<doc_id>/tags/policy

# Remove a tag
curl -X DELETE http://localhost:8000/api/documents/<doc_id>/tags/policy

# Filter documents by tag
curl "http://localhost:8000/api/documents/?tag=policy"
```

### Query Log

```bash
# View query log
curl http://localhost:8000/api/search/log

# Export query log as CSV
curl -o query_log.csv http://localhost:8000/api/search/log/export
```

## Running Tests

Each test suite is a standalone script run from the repo root:

```bash
# Run all tests
for t in test_parser test_chunker test_embedder test_llm test_search \
         test_retrieval test_indexing test_day4 test_metrics test_integration \
         test_validation; do
  backend/.venv/bin/python "backend/tests/$t.py"
done
```

## Validation Results

Formal validation run on Day 8 using sentence-transformers fallback (no OpenAI key):

| Metric | Type | Target | Result |
|---|---|---|---|
| Retrieval@3 | Auto | ≥ 80% | **100%** |
| Answer reference coverage | Auto | ≥ 90% | **100%** |
| Latency (warm cache) median | Auto | < 3s | **13.4ms** |
| Latency (warm cache) p95 | Auto | < 5s | **17.0ms** |
| Embedding cache effectiveness | Auto | 100% hits | **100%** |
| Failure handling | Auto | ≥ 80% | **83%** |
| Source precision | Auto | ≥ 80% | **100%** |
| Indexing throughput | Auto | completes | **2.29s** |
| Cache skip on re-index | Auto | 100% | **100%** |

To reproduce: `backend/.venv/bin/python backend/tests/test_validation.py`

## Sample Documents

The repository ships with 5 sample documents in `backend/data/sample-docs/`:

| File | Description |
|---|---|
| `policy.txt` | Company remote-work policy |
| `faq.txt` | Common HR/IT FAQs |
| `guide.txt` | Employee onboarding guide |
| `howto.txt` | How to file an expense report |
| `manual.txt` | Product troubleshooting manual |

## Project Structure

```
guidely/
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   │   ├── search.js         # Search API client
│   │   │   └── documents.js      # Document CRUD API client
│   │   ├── components/
│   │   │   ├── SourceCard.jsx    # Expandable source card
│   │   │   └── LoadingSpinner.jsx
│   │   ├── pages/
│   │   │   ├── SearchPage.jsx    # Main search UI
│   │   │   └── AdminPage.jsx     # Admin placeholder
│   │   ├── App.jsx               # Router + nav
│   │   ├── main.jsx              # Entry point
│   │   └── index.css             # Styles
│   ├── package.json
│   └── vite.config.js
├── backend/
│   ├── main.py              # FastAPI app entry point
│   ├── routes/
│   │   ├── documents.py     # Document CRUD + tag endpoints
│   │   └── search.py        # Q&A search + query log endpoints
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
│   │   ├── stats.py         # Metrics counters
│   │   ├── query_log.py     # Query log with CSV export
│   │   └── tags.py          # Document tag storage
│   ├── tests/
│   │   ├── test_parser.py
│   │   ├── test_chunker.py
│   │   ├── test_embedder.py
│   │   ├── test_search.py
│   │   ├── test_retrieval.py
│   │   ├── test_indexing.py
│   │   ├── test_llm.py
│   │   ├── test_day4.py
│   │   ├── test_metrics.py
│   │   ├── test_integration.py
│   │   └── test_validation.py
│   └── data/
│       ├── sample-docs/     # 5 sample documents
│       ├── uploads/         # User-uploaded documents
│       └── validation_report.json
├── requirements.txt
├── plan.md
├── .env
└── README.md
```

## Bonus Features

### Query Log Export

Every search query is logged with timestamp, latency, and sourced documents. Export as CSV for analysis:

```bash
curl -o query_log.csv http://localhost:8000/api/search/log/export
```

CSV columns: `timestamp`, `question`, `answer_preview`, `sources`, `source_count`, `latency_ms`, `status`

### Document Tags

Organize documents with tags for categorization and filtering:

```bash
# Tag a document
curl -X POST http://localhost:8000/api/documents/<doc_id>/tags/hr

# Filter by tag
curl "http://localhost:8000/api/documents/?tag=hr"
```

Tags are stored in `backend/data/tags.json` and survive server restarts.
