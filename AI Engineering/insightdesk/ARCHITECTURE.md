# InsightDesk — Architecture & Design Notes

This document explains *how the pieces fit* and *why they were chosen*, for a
reader evaluating the design (e.g. an interviewer).

## 1. Layered view

```
┌──────────────────────────────────────────────────────────────────┐
│ Entry points          cli.py · examples/*.py                       │
├──────────────────────────────────────────────────────────────────┤
│ Orchestration         single_agent.py  ·  multi_agent.py           │
│   (LangGraph)         create_react_agent · StateGraph + supervisor │
├──────────────────────────────────────────────────────────────────┤
│ Capabilities          tools.py                                     │
│   - RAG tool ─────────────────────────────▶ retriever.py → Chroma  │
│   - calculate (local)                                              │
│   - MCP tools ────────────────────────────▶ mcp_server/server.py   │
├──────────────────────────────────────────────────────────────────┤
│ State                 memory.py  (SqliteSaver + InMemoryStore)     │
├──────────────────────────────────────────────────────────────────┤
│ Models                llm.py → langchain-anthropic → Claude        │
│ Config                config.py                                    │
└──────────────────────────────────────────────────────────────────┘
```

## 2. RAG data flow

```
data/knowledge_base/*.md
        │  DirectoryLoader
        ▼
   Documents
        │  RecursiveCharacterTextSplitter (chunk_size=800, overlap=120)
        ▼
    Chunks
        │  HuggingFaceEmbeddings (all-MiniLM-L6-v2)  → vectors
        ▼
   Chroma collection  (persisted at .chroma/)        ← ingest.py writes here
        ▲
        │  similarity_search(query, k=4)              ← retriever.py reads here
        │
  knowledge_base_search tool  ← called by agents
```

Re-running `python -m insightdesk.ingest` clears and rebuilds the collection so
chunks never duplicate.

## 3. Single-agent control flow (ReAct)

```
HumanMessage ─▶ [LLM] ──tool_calls?──▶ [Tools] ──results──▶ [LLM] ──▶ AIMessage
                  ▲                                            │
                  └────────────────── loop ────────────────────┘
```

`create_react_agent` builds exactly this graph and (optionally) attaches a
checkpointer so the loop's state is persisted per `thread_id`.

## 4. Multi-agent control flow (supervisor)

```
START ─▶ supervisor ──route──▶ researcher ─┐
            ▲   │                          │
            │   ├──route──▶ support ───────┤
            │   │                          │
            │   ├──route──▶ calculator ────┤
            │   │                          │
            │   └─ workers report back ────┘
            │
            └─ FINISH ─▶ synthesize ─▶ END
```

- The supervisor uses `with_structured_output(Route)` so routing is a typed,
  validated decision rather than free-text parsing.
- Workers are independent ReAct agents with **narrow** tool sets — this is the
  main lever for reliability: a worker that can only search the KB rarely
  misuses a ticket tool.
- Shared state is a single `messages` list (LangGraph's `add_messages` reducer),
  so each worker sees the running conversation.

## 5. Memory model

| Layer | Backed by | Scope | Use |
|---|---|---|---|
| Short-term | `SqliteSaver` checkpointer | one `thread_id` | resume a conversation, recall earlier turns |
| Long-term | `InMemoryStore` | namespace (e.g. per user) | durable facts across conversations |

Swap `InMemoryStore` for `PostgresStore` and `SqliteSaver` for `PostgresSaver`
to make both layers production-grade — no other code changes.

## 6. Model strategy

- **Supervisor & synthesis**: `claude-opus-4-8` — the hardest reasoning/routing.
- **Workers**: `claude-sonnet-4-6` — fast and cheap for narrow jobs.
- Sampling params and `budget_tokens` are intentionally left unset; on Claude
  4.7+/Opus 4.8 they error. To enable extended thinking, pass
  `thinking={"type": "adaptive"}` rather than a token budget.

## 7. Extension points

- **Add a worker**: write a ReAct agent in `multi_agent.py`, add its name to
  `WORKERS`, and the supervisor can route to it.
- **Add a tool**: a `@tool` function in `tools.py`, or expose it from the MCP
  server to share it with any MCP client.
- **Swap the vector DB**: `ingest.py`/`retriever.py` are the only files that
  touch Chroma; replace with pgvector/Pinecone there.
- **Add streaming/UI**: every graph supports `.astream()` (see
  `examples/03_multi_agent.py`).
