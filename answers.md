# Internship Preliminary Test — Answers

---

## Part 2 — Code Review

### Problem 1 — SQL Injection (Critical)

**What's wrong:**
Both `search_documents` and `save_answer` build SQL queries by directly concatenating
user input into the string:
```python
"SELECT ... WHERE content LIKE '%" + question + "%'"
"INSERT INTO answers ... VALUES ('" + question + "', '" + answer + "')"
```

**Why it matters:**
An attacker can input something like `'; DROP TABLE documents; --` and destroy the
database, or extract any data they want. This is the most dangerous vulnerability
possible in a database-facing app.

**Fix:**
Always use parameterised queries (placeholders):
```python
cursor.execute("SELECT id, title, content FROM documents WHERE content LIKE ?", (f"%{question}%",))
conn.execute("INSERT INTO answers (question, answer) VALUES (?, ?)", (question, answer))
```

---

### Problem 2 — Hardcoded API Key (Security)

**What's wrong:**
```python
API_KEY = "sk-prod-abc123xyz"  # hardcoded
```
The production API key is written directly in the source code.

**Why it matters:**
If this file is pushed to GitHub (even a private repo), or shared with anyone, the key
is compromised. Attackers can run up massive API bills or access sensitive data.

**Fix:**
Load secrets from environment variables or a secrets manager:
```python
import os
API_KEY = os.environ["LLM_API_KEY"]
```

---

### Problem 3 — LLM API Called Twice (Waste + Inconsistency)

**What's wrong:**
```python
print(ask_llm(q, docs))
save_answer(q, ask_llm(q, docs))  # called twice
```
`ask_llm` is called two times with the same inputs.

**Why it matters:**
- Doubles the API cost for every query.
- The two calls may return *different* answers (LLMs are non-deterministic), so the
  printed answer and the saved answer could be different — a silent data inconsistency.

**Fix:**
Call it once and reuse the result:
```python
answer = ask_llm(q, docs)
print(answer)
save_answer(q, answer)
```

---

### Problem 4 — No Error Handling on the LLM API Call

**What's wrong:**
```python
return response.json()["response"]
```
There is no check that the HTTP request succeeded, and no handling if the JSON does
not contain a `"response"` key.

**Why it matters:**
Any network error, rate limit (429), server error (500), or model change that alters
the response shape will cause an unhandled exception and crash the entire script.

**Fix:**
```python
response.raise_for_status()  # raises HTTPError for 4xx/5xx
data = response.json()
if "response" not in data:
    raise ValueError(f"Unexpected API response shape: {data}")
return data["response"]
```

---

### Problem 5 (bonus) — Database Connection Never Closed on Error

**What's wrong:**
`conn.close()` is only called on the happy path. If an exception is raised before it,
the connection leaks.

**Fix:**
Use a context manager so the connection always closes:
```python
with sqlite3.connect(DB_PATH) as conn:
    cursor = conn.cursor()
    cursor.execute(...)
    return cursor.fetchall()
```

---

## Part 3 — Short Written Questions

### Q1 — SQLite LIKE search → Postgres at 1 million rows

The first thing that becomes slow is the full-table scan caused by the leading
wildcard: `LIKE '%keyword%'` cannot use a standard B-tree index because the pattern
does not start with a fixed prefix, so Postgres reads every row on every query.

**Fix:** Switch to Postgres full-text search. Add a `tsvector` column (or generated
column) and a GIN index on it:
```sql
ALTER TABLE documents ADD COLUMN search_vector tsvector
    GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;
CREATE INDEX idx_documents_fts ON documents USING GIN (search_vector);
```
Then query with `search_vector @@ plainto_tsquery('english', $1)`, which is fast
even at millions of rows. For more advanced semantic search, pgvector embeddings
would be the next step.

---

### Q2 — Why sending all documents to the LLM is a bad idea + basic RAG

Once the document set grows, concatenating everything into one prompt quickly hits
the model's context window limit (e.g. 8k–128k tokens), causing truncation or outright
rejection of the request. Even before the limit is reached, longer prompts cost
significantly more, take longer to process, and often produce worse answers because
the model is overwhelmed with irrelevant content.

**Basic RAG fix:**
1. **Chunk** documents into smaller pieces (e.g. 300–500 tokens each).
2. **Embed** each chunk with an embedding model (e.g. OpenAI `text-embedding-3-small`
   or a local sentence-transformer) and store the vectors in a vector store (pgvector,
   Pinecone, Chroma, etc.).
3. At query time, embed the user's question and retrieve the **top-k most similar
   chunks** (e.g. k=5) using cosine similarity.
4. Send only those k chunks as context to the LLM.

This keeps the prompt small, cheap, and focused — the model only sees content that is
actually relevant to the question.

---

### Q3 — 3 things that can go wrong with LLM API calls + production handling

**1. Rate limiting (HTTP 429)**
The API provider throttles requests when you exceed your quota.
*Handling:* Catch 429 responses and retry with exponential backoff + jitter
(e.g. wait 1s, 2s, 4s…). Libraries like `tenacity` make this easy. Also queue
requests and monitor usage against the rate limit in a dashboard.

**2. Network timeout / connectivity error**
The request hangs or the connection drops before a response arrives.
*Handling:* Always set a `timeout` parameter on `requests.post()` (e.g. 30s).
Catch `requests.exceptions.Timeout` and `requests.exceptions.ConnectionError`,
log the error, and return a graceful fallback message to the user.

**3. Unexpected response shape / model deprecation**
The API changes its response format, or the model name becomes invalid, causing
`KeyError` or `ValueError` when parsing the JSON.
*Handling:* Validate the response structure before accessing keys (e.g. check
`"response" in data`). Log the full raw response on unexpected shapes. Set up
alerts so the team knows immediately when parsing fails in production, and pin the
model version in the request payload to avoid surprise changes.

---

### Q4 (bonus) — Postgres schema for a chatbot with user history

```sql
-- One row per conversation session
CREATE TABLE conversations (
    id         SERIAL PRIMARY KEY,
    user_id    TEXT        NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per message (user or assistant) within a conversation
CREATE TABLE messages (
    id              SERIAL PRIMARY KEY,
    conversation_id INTEGER     NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT        NOT NULL CHECK (role IN ('user', 'assistant')),
    content         TEXT        NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_messages_conversation ON messages(conversation_id, created_at);
```

**Why this structure:**
- Separating `conversations` from `messages` lets you load a full history for one
  session by querying `WHERE conversation_id = $1 ORDER BY created_at` — exactly
  the list you pass back to the LLM as prior context.
- The `role` column mirrors the `{"role": "user"/"assistant"}` format expected by
  most LLM APIs, so you can feed the rows directly into the messages array with
  minimal transformation.
- If memory needs to be capped (to avoid overflowing the context window), you can
  simply take the last N rows per conversation.

---

## Time spent
~55 minutes total (Part 1: ~20 min, Part 2: ~20 min, Part 3: ~15 min).