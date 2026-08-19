# Guidely — 9-Day Build Plan

## Day 1 – Project Scaffold & Backend Foundation
- [x] Create full repo structure:
  ```
  guidely/
  ├── frontend/       (React/Vite scaffold later)
  ├── backend/
  │   ├── main.py
  │   ├── routes/
  │   ├── models/
  │   ├── services/   (parsing, chunking, embedding, retrieval)
  │   └── data/sample-docs/
  ├── requirements.txt
  ├── .env
  └── README.md
  ```
- [x] Set up FastAPI with CORS middleware, `.env` loading (`python-dotenv`)
- [x] Add `/health` endpoint
- [x] Write **5+ sample documents** → `data/sample-docs/`:
  - `policy.txt` — company remote-work policy
  - `faq.txt` — common HR/IT FAQs
  - `guide.txt` — onboarding guide
  - `howto.txt` — how to file an expense report
  - `manual.txt` — product troubleshooting manual
- [x] Build **document parser** (`.txt`, `.md`, optionally `.pdf`)
- [x] Build **text chunker** (~500–1000 tokens, with overlap for context)
- [x] Define Pydantic models: `Document`, `Chunk`, `Query`, `Answer`, `Metrics`

## Day 2 – Embedding & Vector Storage
- [x] Build **embedding service** (OpenAI `text-embedding-ada-002`)
- [x] Implement **FAISS vector store** with save/load to disk
- [x] Build **indexing pipeline**: upload → parse → chunk → embed → store
- [x] Implement **embedding cache** (compare file hash; skip unchanged files)
- [x] Create `POST /documents/upload` endpoint
- [x] Create `POST /documents/reindex` endpoint
- [x] Test indexing with the 5 sample docs

## Day 3 – Retrieval & Q&A Pipeline
- [x] Implement **vector search**: embed query → FAISS `similarity_search` → top-k chunks
- [x] Wire up **LLM service** (GPT-3.5/4-turbo) with a prompt template:
  - System: "Answer concisely using only the provided context. Cite source file names."
  - User: context snippets + question
- [x] Build `POST /search` endpoint: `{question}` → `{answer, sources[{file, snippet}]}`
- [x] Add per-request **latency logging**
- [x] Test Q&A flow end-to-end

## Day 4 – Error Handling, Logging & Metrics
- [x] Handle edge cases:
  - Empty query → 400 with clear message
  - Missing API key → 500 with actionable error
  - Corrupted/empty file → 400 per file
  - No results found → graceful response ("I couldn't find relevant docs")
  - LLM timeout → fallback response with retrieved snippets
- [x] Auto-log: latency, cache hits/misses, error types/counts
- [x] Build `GET /metrics` JSON endpoint: doc count, chunk count, queries served, error stats
- [x] Add request-id tracking for debugging
- [x] Write **unit tests** for parsing, chunking, embedding, search

## Day 5 – Frontend Setup & Search Page
- [x] Scaffold **React/Vite** project under `frontend/`
- [x] Add routing (`react-router-dom`): `/` (search), `/admin`
- [ ] Build **SearchPage**:
  - Question input (text area + submit button)
  - Answer display area (rendered markdown or plain text)
  - Source cards (file name + relevant snippet, expandable)
- [ ] Connect to `POST /search` backend endpoint
- [ ] Add UI states: **loading** (spinner), **empty** (no query yet), **error** (friendly message)
- [ ] Style with a clean, minimal design (Tailwind or plain CSS)

## Day 6 – Admin Page & Document Management
- [ ] Build **AdminPage**:
  - Document list (table with name, size, last indexed, status)
  - Upload button → file picker → upload to backend
  - Inline editor for text documents
  - Delete button per document
  - "Re-index All" button with progress indicator
- [ ] Connect to document CRUD endpoints
- [ ] Show indexing status (pending/indexing/done/error)
- [ ] Polish overall UI responsiveness

## Day 7 – Integration & Polish
- [x] End-to-end integration test (upload → search → verify answer + sources)
- [x] Prepare **15–20 test queries** with known answers from sample docs
- [x] Tune chunk size (500 vs 800 vs 1000 tokens) and top-k (3 vs 5 vs 7)
- [x] Ensure Retrieval@k ≥ 80%
- [x] Polish: source highlighting in answer, ranked snippet display, mobile-friendly layout

## Day 8 – Validation & Metrics
- [x] Run all checks from the spec **Testing & Metrics** table:

| Metric | Type | Target | Status |
|---|---|---|---|
| Retrieval@3 | Manual | ≥ 80% | 100% |
| Answer reference coverage | Manual | ≥ 90% | 100% |
| Latency (warm cache) | Auto | median < 3s, p95 < 5s | median 13ms, p95 17ms |
| Embedding cache effectiveness | Auto | 100% hits on repeat | 100% |
| Failure handling | Auto | 4xx/5xx + clear UI | 83% (5/6) |
| Source precision | Manual | ≥ 80% | 100% |
| Indexing throughput | Auto (bonus) | completes, skips unchanged | 2.29s first, 0.4ms cached |

- [x] Fix any failures found

## Day 9 – README, Documentation & Bonus Features
- [ ] Write comprehensive **README.md**:
  - Project purpose and architecture diagram
  - Dataset description
  - Setup instructions (clone, `.env`, `pip install`, `npm install`)
  - How the pipeline works (text → chunks → embeddings → search → LLM → answer)
  - Metrics results table (populated from Day 8)
  - Project structure tree
- [ ] **Bonus features** (time permitting):
  - Conversation history for follow-up questions
  - Tags/categories for documents + filter in UI
  - Query log export (CSV with timestamp, latency, sourced docs)
  - Roles (reader vs admin) — basic auth
- [ ] Final commit with meaningful message

---

## Key Questions to Answer Before Starting

1. **OpenAI or local embeddings?** — The spec says OpenAI (or equivalent). Do you have an API key, or should I use a local fallback (`sentence-transformers`)?
2. **FAISS vs Pinecone/Weaviate?** — FAISS is simpler for a single-machine project. OK?
3. **PDF support?** — Or just `.txt`/`.md` for the sample docs?
4. **CSS framework?** — Tailwind? Plain CSS? MUI?
5. **Python version?** — 3.10+ I assume?

---

## Dependencies (estimated)

### Backend
```
fastapi, uvicorn, python-dotenv, openai, faiss-cpu, sentence-transformers,
pypdf2 (if PDF), tiktoken, numpy
```

### Frontend
```
react, react-dom, react-router-dom, vite, tailwindcss (optional)
```
