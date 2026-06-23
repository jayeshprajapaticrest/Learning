# InsightDesk — an agentic AI assistant (LangGraph + Claude)

A compact, **interview-ready** project that demonstrates a full modern agent
stack in one coherent product: an AI **support & research assistant** that
answers from a knowledge base, looks up support tickets, and routes hard
requests across a team of specialist agents.

It is deliberately small enough to read end-to-end in 20 minutes, but covers
every component an interviewer is likely to probe:

| Concept | Where it lives | Read this |
|---|---|---|
| **Single agent** (ReAct loop) | [single_agent.py](insightdesk/src/insightdesk/single_agent.py) | one LLM + tools, looping until done |
| **Multi-agent** (supervisor/orchestrator) | [multi_agent.py](insightdesk/src/insightdesk/multi_agent.py) | a supervisor routes to specialist workers |
| **RAG** (retrieval-augmented generation) | [ingest.py](insightdesk/src/insightdesk/ingest.py) + [retriever.py](insightdesk/src/insightdesk/retriever.py) | load → chunk → embed → search |
| **Vector storing & searching** | [ingest.py](insightdesk/src/insightdesk/ingest.py) (Chroma) | persisted embeddings, similarity search |
| **MCP tool** | [mcp_server/server.py](insightdesk/mcp_server/server.py) + [tools.py](insightdesk/src/insightdesk/tools.py) | external tools over the Model Context Protocol |
| **Memory & context** | [memory.py](insightdesk/src/insightdesk/memory.py) | short-term (checkpointer) + long-term (store) |
| **LLM config / model IDs** | [llm.py](insightdesk/src/insightdesk/llm.py) + [config.py](insightdesk/src/insightdesk/config.py) | `claude-opus-4-8` + `claude-sonnet-4-6` |
| **Orchestration framework** | LangGraph throughout | `StateGraph`, `create_react_agent`, checkpointer |

---

## Architecture at a glance

```
                ┌───────────────────────────── SUPERVISOR (Claude Opus 4.8) ─────────────────────────────┐
   user ───▶    │  routes each turn to one specialist worker, then synthesizes the final answer          │
                └───────┬───────────────────────┬───────────────────────────┬───────────────────────────┘
                        ▼                        ▼                           ▼
                ┌───────────────┐      ┌──────────────────┐        ┌──────────────────┐
                │  researcher   │      │     support      │        │   calculator     │
                │  (RAG)        │      │   (MCP tools)    │        │  (arithmetic)    │
                └──────┬────────┘      └────────┬─────────┘        └──────────────────┘
                       ▼                        ▼
              ┌─────────────────┐      ┌──────────────────────┐
              │  Chroma vector  │      │  MCP server (stdio)  │
              │  store (RAG)    │      │  support tickets     │
              └─────────────────┘      └──────────────────────┘

       Memory: every graph run is checkpointed per thread_id (short-term);
               durable user facts live in a cross-thread store (long-term).
```

A deeper write-up of the data flow and design choices is in
[ARCHITECTURE.md](insightdesk/ARCHITECTURE.md).

---

## Where to start (reading order)

Follow the files in this order — each builds on the last:

1. **[config.py](insightdesk/src/insightdesk/config.py)** — every knob in one place (models, paths, RAG settings).
2. **[llm.py](insightdesk/src/insightdesk/llm.py)** — how a Claude model is constructed via `langchain-anthropic`.
3. **[ingest.py](insightdesk/src/insightdesk/ingest.py)** — RAG ingestion: load → chunk → embed → persist to Chroma.
4. **[retriever.py](insightdesk/src/insightdesk/retriever.py)** — RAG retrieval: semantic search over the vectors.
5. **[tools.py](insightdesk/src/insightdesk/tools.py)** — the three tool flavours (RAG tool, local calc, MCP loader).
6. **[mcp_server/server.py](insightdesk/mcp_server/server.py)** — the MCP server the agents connect to.
7. **[single_agent.py](insightdesk/src/insightdesk/single_agent.py)** — the simplest agent (ReAct).
8. **[memory.py](insightdesk/src/insightdesk/memory.py)** — short- and long-term memory.
9. **[multi_agent.py](insightdesk/src/insightdesk/multi_agent.py)** — composing single agents into a supervised team.
10. **[cli.py](insightdesk/src/insightdesk/cli.py)** — ties it together for interactive use.

The [examples/](insightdesk/examples) folder has one runnable script per concept.

---

## Quickstart

```bash
cd insightdesk

# 1. Install (editable, uses pyproject.toml)
python -m venv .venv && source .venv/bin/activate
pip install -e .

# 2. Add your key
cp .env.example .env        # then edit .env and set ANTHROPIC_API_KEY

# 3. Build the vector store from the sample knowledge base (RAG)
python -m insightdesk.ingest

# 4. Run the examples
python examples/02_rag.py            # RAG retrieval only (no LLM call)
python examples/01_single_agent.py   # single ReAct agent
python examples/03_multi_agent.py    # supervisor multi-agent team
python examples/04_memory.py         # short + long-term memory

# 5. Or chat interactively
python -m insightdesk.cli                 # single agent
python -m insightdesk.cli --mode multi    # multi-agent team
```

> The embedding model (`all-MiniLM-L6-v2`) runs **locally** — no embedding API
> key needed. Only `ANTHROPIC_API_KEY` is required (for the chat models).

---

## How each component works (the 60-second version)

**RAG.** `ingest.py` reads the markdown in [data/knowledge_base/](insightdesk/data/knowledge_base),
splits it into overlapping chunks, embeds them with a sentence-transformer, and
stores the vectors in a persisted **Chroma** collection. At query time
`retriever.py` embeds the question and returns the nearest chunks, which the
agent cites. This is what keeps answers grounded and auditable.

**Single agent.** `create_react_agent` (LangGraph prebuilt) wires an LLM to a
tool node in a loop: the model emits tool calls, tools run, results return to
the model, and it repeats until it produces a final answer.

**Multi-agent.** A `StateGraph` with a **supervisor** node that uses Claude with
structured output to choose the next worker (`researcher` / `support` /
`calculator`) or `FINISH`. Each worker is itself a small ReAct agent — so the
team is just single agents composed. The supervisor then synthesizes a final
answer. This is the standard orchestrator pattern for decomposing hard tasks.

**MCP tool.** `mcp_server/server.py` is a real MCP server (FastMCP) exposing
support-ticket tools. `tools.load_mcp_tools()` launches it and converts its
tools into LangChain tools via `langchain-mcp-adapters` — the same mechanism
works for remote HTTP/SSE MCP servers.

**Memory.** Two layers, both native to LangGraph. A **checkpointer** (SQLite)
persists graph state per `thread_id` → short-term conversational memory that
survives restarts. A **store** holds durable, cross-thread facts about a user →
long-term memory.

---

## Talking points for an interview

- *Why a supervisor instead of one big agent?* Smaller, focused tool sets per
  worker → better tool selection, cheaper models for narrow jobs
  (`claude-sonnet-4-6` workers, `claude-opus-4-8` supervisor), and a clear
  place to add guardrails/routing logic.
- *Why RAG over fine-tuning?* Grounding + citations + instant updates (re-run
  ingest) without retraining.
- *Why MCP?* A standard tool interface — the same agent can consume first-party
  and third-party tools without bespoke glue.
- *Why a checkpointer?* Statelessness of the API means memory must be explicit;
  the checkpointer makes conversations resumable and auditable.
