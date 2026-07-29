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
│   │   ├── parser.py        # File parsing (txt, md, pdf)
│   │   ├── chunker.py       # Token-aware text chunking
│   │   ├── embedder.py      # Embedding generation
│   │   └── retriever.py     # Vector search + LLM
│   └── data/sample-docs/    # 5 sample documents
├── requirements.txt
├── plan.md
├── .env
└── README.md
```
