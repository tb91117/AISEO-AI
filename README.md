# AEGIS — Answer Engine & Generative Intelligence Suite

A Python FastAPI service implementing two AI-powered content intelligence features:

| Feature | Endpoint |
|---|---|
| **AEO Content Scorer** — three NLP checks, 0–100 readiness score | `POST /api/aeo/analyze` |
| **Query Fan-Out Engine** — LLM query decomposition + semantic gap analysis | `POST /api/fanout/generate` |

---

## Setup

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Download the spaCy model

```bash
# Minimum (faster):
python -m spacy download en_core_web_sm

# Preferred (better dependency parsing for Check A):
python -m spacy download en_core_web_lg
```

The service automatically falls back to `en_core_web_sm` if `en_core_web_lg` is not installed.

### 3. Set environment variables

Create a `.env` file in the project root (it is `.gitignore`d):

```env
# Use one — Gemini is preferred (faster free tier)
GOOGLE_API_KEY=your_gemini_api_key_here

# Fallback if Gemini key is absent
OPENAI_API_KEY=your_openai_api_key_here
```

The service checks `GOOGLE_API_KEY` / `GEMINI_API_KEY` first, then `OPENAI_API_KEY`.  
The AEO scorer requires no API key — only the fan-out endpoint does.

### 4. Run the server

```bash
uvicorn app.main:app --reload
```

Interactive API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Quick API Examples

### AEO Scorer

```bash
# Analyse a live URL
curl -X POST http://localhost:8000/api/aeo/analyze \
  -H "Content-Type: application/json" \
  -d '{"input_type": "url", "input_value": "https://example.com/article"}'

# Analyse raw HTML or plain text
curl -X POST http://localhost:8000/api/aeo/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "input_type": "text",
    "input_value": "<h1>What is Python?</h1><p>Python is a high-level language.</p>"
  }'
```

### Fan-Out Engine

```bash
# Sub-queries only (no gap analysis)
curl -X POST http://localhost:8000/api/fanout/generate \
  -H "Content-Type: application/json" \
  -d '{"target_query": "best AI writing tool for SEO"}'

# Sub-queries + gap analysis
curl -X POST http://localhost:8000/api/fanout/generate \
  -H "Content-Type: application/json" \
  -d '{
    "target_query": "best AI writing tool for SEO",
    "existing_content": "Paste your article text here..."
  }'
```

---

## Running Tests

```bash
pytest tests/ -v
```

The test suite runs entirely without an API key — all LLM calls are mocked.

---

## What Was Completed

| Item | Status | Notes |
|---|---|---|
| Check A — Direct Answer Detection | Complete | spaCy dep parser for declarative detection |
| Check B — H-tag Hierarchy | Complete | All 3 rules, exact spec scoring |
| Check C — Readability Scorer | Complete | textstat FK grade, top-3 complex sentences |
| AEO score aggregation + bands | Complete | Normalised 0–100 |
| `POST /api/aeo/analyze` | Complete | URL fetch (httpx) + raw text/HTML |
| Fan-out LLM generation | Complete | Gemini 1.5 Flash + GPT-4o-mini fallback |
| Retry logic with exponential back-off | Complete | 3 attempts, 1 s / 2 s / 4 s delays |
| Semantic gap analysis | Complete | sentence-transformers cosine similarity |
| `POST /api/fanout/generate` | Complete | Gap summary only when content provided |
| Pydantic models for all I/O | Complete | Typed request + response + error models |
| Unit tests — all 3 AEO checks | Complete | Pass + fail case per check |
| Mocked LLM test (JSON parsing) | Complete | 9 scenarios including retry + 503 |
| `PROMPT_LOG.md` | Complete | 4-draft iteration log |

Nothing was deliberately skipped.  
Known limitations: FK grade accuracy degrades on very short texts (<100 words); JS-rendered pages that return empty HTML will produce a low-scoring (but non-crashing) response.

---

## Prompt Design Decisions

See `PROMPT_LOG.md` for the full iteration log. Summary of key decisions:

**Fixed count (12 queries, 2 per type)**  
Early drafts said "10–15 sub-queries." The model routinely produced 4 comparatives and 1 definitional.  Fixing the count to exactly 12 with the type order enforced in the example resolved the distribution problem completely.

**Separate example with a different topic**  
The worked example deliberately uses "best project management tool for startups" rather than an SEO tool example.  This prevents the model from paraphrasing the example instead of reasoning about the new query.

**Type definitions, not just names**  
The first draft listed only the 6 type names.  Adding one-sentence definitions for each type improved semantic quality significantly — the model generated genuine use-case queries instead of keyword-stuffed phrases.

**Defensive parser**  
Despite the explicit "no markdown fences" instruction, ~5 % of Gemini responses still included them.  `_parse_llm_response()` strips fences before parsing, and any `ValueError` or `JSONDecodeError` triggers a retry with exponential back-off.

---

## Gap Analysis Threshold

The threshold is set to **0.72** as specified.

**Why 0.72 is reasonable:**  
`all-MiniLM-L6-v2` cosine similarities for topically related but non-identical sentences typically cluster in 0.55–0.80.  A threshold of 0.72 sits solidly in the "strong semantic overlap" zone — it requires genuine content coverage, not just shared vocabulary.

**Would I tune it?**  
Yes.  In production I would collect labeled (content, sub-query, covered: true/false) examples and optimise the threshold by maximising F1 on that dataset.  For an SEO diagnostic tool, false positives (claiming coverage that doesn't exist) are more harmful than false negatives, so I would bias toward a slightly higher threshold (~0.75–0.78) after empirical validation.

---

## Embedding Model Choice

**Chosen: `all-MiniLM-L6-v2`** (not `all-mpnet-base-v2`)

| | MiniLM-L6-v2 | mpnet-base-v2 |
|---|---|---|
| Encoding speed (CPU) | ~22 ms/sentence | ~110 ms/sentence |
| RAM | ~80 MB | ~420 MB |
| STS accuracy | good | ~3–4 % higher |

For a per-request operation that encodes potentially hundreds of article sentences, the 5× latency difference is user-facing.  The small accuracy trade-off is acceptable given threshold flexibility.

**Production consideration:** If accuracy proved critical, I would switch to an embedding API (`text-embedding-3-small`) to offload compute and get both speed and quality.

---

## Concurrency Model

Both endpoints are sync `def` functions.  FastAPI automatically runs sync endpoints in a thread pool (`anyio.to_thread`), which is appropriate because:

- spaCy and textstat are **CPU-bound** — they would block the event loop inside `async def` without `asyncio.to_thread`.
- sentence-transformers encoding is also **CPU-bound**.
- The Gemini/OpenAI HTTP call is **I/O-bound** but wrapping it in `asyncio.to_thread` adds complexity for marginal gain at this scale.

**Production improvement:** Convert LLM calls to true async using the async Gemini/OpenAI clients, and run sentence-transformer encoding in a thread pool executor to allow concurrent requests.

---

## What I Would Improve With More Time

1. **Async LLM calls** — use the async Gemini client so multiple fan-out requests can run concurrently without blocking each other.
2. **spaCy sentence chunking** in the gap analyser — currently splits on punctuation which loses context at clause boundaries.  spaCy's sentence boundary detection would be more robust.
3. **Model warm-up on startup** — spaCy and the sentence-transformer model currently load on first request.  A FastAPI `lifespan` handler would pre-warm them, eliminating cold-start latency.
4. **Threshold calibration** — run the gap analyser against a labeled dataset to choose 0.72 empirically rather than accepting it as a given.
5. **Streaming response** for `/api/fanout/generate` — the LLM + embedding step can take 5–10 s; streaming the sub-queries as they are generated would improve perceived performance significantly.
