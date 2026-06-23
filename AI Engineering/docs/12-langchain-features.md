# 12 — LangChain: Complete Feature Reference (Single & Multi-Agent)

> A **feature-by-feature reference** for LangChain — the component library you compose into
> chains and agents. LangChain provides the *building blocks* (models, prompts, parsers,
> retrievers, tools, memory) and **LCEL** to wire them; LangGraph ([T11](11-langgraph-features.md))
> orchestrates them when control flow gets non-linear. Use both together.

---

## 1. The package layout (know where things live)

| Package | Contains |
|---------|----------|
| `langchain-core` | base abstractions: Runnable, messages, prompts, output parsers, tools |
| `langchain` | chains, agents, retrievers, higher-level orchestration |
| `langchain-<provider>` | integrations: `langchain-anthropic`, `langchain-openai`, `langchain-qdrant`, … |
| `langchain-community` | community integrations (loaders, vector stores, tools) |
| `langgraph` | stateful orchestration (separate, composes with the above) |

Rule: import models/vector stores from their **provider packages**, not `community`,
when an official one exists.

---

## 2. Models — chat, embeddings, structured output

```python
from langchain.chat_models import init_chat_model
llm = init_chat_model("anthropic:claude-sonnet-4-6", temperature=0)   # provider-agnostic init
```

Every chat model supports a common interface:
- **`invoke` / `ainvoke` / `stream` / `batch`** — sync, async, streaming, batched.
- **`.bind_tools([...])`** — attach tools for tool-calling (single-agent core).
- **`.with_structured_output(Schema)`** — force typed output (Pydantic/JSON schema).
- **`.with_retry()` / `.with_fallbacks([...])`** — resilience (retry, or fall back to
  another model on failure).
- **Multimodal** — pass images/files in message content for vision models.

```python
from pydantic import BaseModel
class Ticket(BaseModel):
    priority: str; summary: str
structured = llm.with_structured_output(Ticket)
structured.invoke("Customer can't log in, very urgent")    # → Ticket(priority='high', ...)
```

Embeddings share an interface too (`embed_documents`, `embed_query`) — see [T03](03-vector-search.md).

---

## 3. Messages & prompts

```python
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a {role}. Answer using the context."),
    MessagesPlaceholder("history"),          # slot for prior turns
    ("human", "Context:\n{context}\n\nQuestion: {question}"),
])
```

- **Message types:** `System`, `Human`, `AI` (may carry `tool_calls`), `Tool`, `Function`.
- **`MessagesPlaceholder`** injects a variable list of messages (chat history, scratchpad).
- **Few-shot templates** (`FewShotChatMessagePromptTemplate`) with optional **example
  selectors** that pick examples by similarity to the input.
- **Partial prompts**, template composition, and Hub-pulled prompts (`hub.pull(...)`).

---

## 4. LCEL — the composition layer

**LangChain Expression Language** composes Runnables with the `|` pipe into chains that
get streaming, async, batching, and retries *for free*.

```python
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

rag_chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt | llm | StrOutputParser()
)
rag_chain.invoke("How many leave days?")          # sync
await rag_chain.ainvoke(...)                       # async — same chain
rag_chain.batch([...])                             # batched
for tok in rag_chain.stream(...): ...              # streaming
```

Core Runnable primitives:
- **`RunnableSequence`** (`a | b | c`) — pipe output to input.
- **`RunnableParallel`** (`{ }`) — run branches concurrently, collect a dict.
- **`RunnablePassthrough`** — pass input through / `.assign()` to add keys.
- **`RunnableLambda`** — wrap any function as a Runnable.
- **`RunnableBranch`** — conditional routing between sub-chains.
- **`.with_config`, `.with_retry`, `.with_fallbacks`, `.bind`** — configure any Runnable.
- **`@chain`** decorator — turn a function into a Runnable.

> When a chain needs **loops, branches that revisit, or shared mutable state**, that's the
> signal to move orchestration to **LangGraph** (T11). LCEL is for *directed, acyclic* flows.

---

## 5. Output parsing & structured data

```python
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
# Prefer .with_structured_output (§2) for tool-calling models; parsers for text models.
```

Parsers: `StrOutputParser`, `JsonOutputParser`, `PydanticOutputParser` (validates against
a model), `CommaSeparatedListOutputParser`, and **`OutputFixingParser`/`RetryOutputParser`**
that re-ask the model to repair malformed output.

---

## 6. Retrieval & RAG components

LangChain provides the whole retrieval toolkit (the pieces behind [T01](01-rag-pipelines.md)):

- **Document loaders** — 100s: PDFs, web, Notion, SharePoint, S3, SQL (feeds [T02](02-document-ingestion.md)).
- **Text splitters** — `RecursiveCharacterTextSplitter`, `MarkdownHeaderTextSplitter`,
  `SemanticChunker`, token/code-aware splitters ([T01 §2](01-rag-pipelines.md), [T10 §1](10-rag-engineering.md)).
- **Vector stores** — Qdrant/Weaviate/OpenSearch/PGVector etc., unified `VectorStore` API ([T03](03-vector-search.md)).
- **Retrievers** — anything implementing `get_relevant_documents`:

```python
from langchain.retrievers import (EnsembleRetriever, ContextualCompressionRetriever,
                                   ParentDocumentRetriever, MultiQueryRetriever)
from langchain.retrievers.document_compressors import CohereRerank

# Hybrid via EnsembleRetriever (BM25 + dense, RRF) — T10 §2
hybrid = EnsembleRetriever(retrievers=[bm25_retriever, vector_retriever], weights=[0.4, 0.6])

# Reranking via compression retriever — T01 §4 / T10 §3
reranked = ContextualCompressionRetriever(
    base_retriever=hybrid, base_compressor=CohereRerank(model="rerank-v3.5", top_n=8))

# Multi-query expansion — T01 §5
mq = MultiQueryRetriever.from_llm(retriever=vector_retriever, llm=llm)
```

Built-in retrievers cover the entire Part-I RAG stack: ensemble (hybrid), compression
(rerank), parent-document (small-to-big), multi-query, self-query (LLM writes the metadata
filter), and time-weighted.

---

## 7. Tools — the agent's capabilities

```python
from langchain_core.tools import tool, StructuredTool

@tool
def get_weather(city: str) -> str:
    """Get current weather for a city."""        # docstring = the model's spec
    return weather_api(city)
```

Tool features:
- **`@tool`** decorator or **`StructuredTool.from_function`** (sync + async).
- **Pydantic `args_schema`** for rich, validated arguments.
- **`InjectedToolArg` / `InjectedState`** — hide internal args (db handle, state) from the
  model while passing them at runtime.
- **`ToolException` + `handle_tool_error`** — graceful failures the agent can recover from.
- **Toolkits** — bundled tool sets (SQL, Gmail, GitHub, file system, requests).
- **Built-in/community tools** — search, Python REPL, shell, API wrappers.
- **`response_format="content_and_artifact"`** — return both a model-visible string and a
  raw artifact for downstream code.

---

## 8. Single-agent in LangChain (and where it moved)

Tool-calling agents are the single-agent core. **Modern guidance: build agents on
LangGraph's `create_react_agent`** ([T11 §4](11-langgraph-features.md)) — the legacy
`AgentExecutor`/`initialize_agent` path is superseded because LangGraph gives durability,
streaming, and HITL for free.

```python
# Recommended single-agent path (LangGraph prebuilt, LangChain tools/model):
from langgraph.prebuilt import create_react_agent
agent = create_react_agent("anthropic:claude-sonnet-4-6", tools=[get_weather, search_kb])
```

You still use LangChain for everything *inside* the agent: the model, the tools, the
prompt, the parsers, the retrievers.

---

## 9. Memory

- **Short-term (conversation):** `RunnableWithMessageHistory` wraps a chain to persist and
  replay turns by session id; backends include Redis, Postgres, file, etc.

```python
from langchain_core.runnables.history import RunnableWithMessageHistory
chat = RunnableWithMessageHistory(rag_chain, get_session_history,
                                  input_messages_key="question", history_messages_key="history")
chat.invoke({"question": "..."}, config={"configurable": {"session_id": "u1"}})
```

- **Summarization / trimming** — `trim_messages` and summary helpers keep context within
  the window for long chats.
- **Long-term memory** — for cross-session memory and stateful agents, use LangGraph's
  **checkpointer + Store** (T11 §6–7); that's where persistent memory now lives.

---

## 10. Multi-agent in LangChain

LangChain supplies the **agents and tools**; **LangGraph supplies the orchestration**
(supervisor/network/swarm — [T14](14-multi-agent-orchestration.md)). The clean pattern:

```python
# Each specialist is a LangGraph agent built from LangChain tools/models...
researcher = create_react_agent(llm, [web_search, search_kb])
analyst    = create_react_agent(llm, [run_sql, query_analytics])
# ...orchestrated by a supervisor graph (T11 §11, T14 §2).
```

A simpler "agents-as-tools" pattern also works for shallow hierarchies: wrap an agent as a
tool the parent agent can call. Use full LangGraph orchestration when agents must share
state, hand off, or loop.

---

## 11. Streaming, async & batching

Built into every Runnable (no extra code):
- **`stream` / `astream`** — token/step streaming.
- **`astream_events`** — a fine-grained event stream (model start/stream/end, tool
  start/end, chain steps) for rich UIs.
- **`batch` / `abatch`** — concurrent processing of many inputs with `max_concurrency`.

---

## 12. Callbacks, tracing & caching (the ops layer)

- **Callbacks** — hooks on every event (LLM start/end, tool start/end, errors) for
  logging, metrics, streaming.
- **LangSmith** — tracing, datasets, evals, prompt management; set `LANGCHAIN_TRACING_V2`
  and runs are captured automatically (ties into [T16](16-evals-synthetic-data.md)).
- **LLM caching** — `set_llm_cache(...)` (in-memory, SQLite, Redis, semantic) to skip
  duplicate calls ([T07 §4](07-fastapi-microservices.md)).
- **Rate limiting** — `InMemoryRateLimiter` to stay under provider caps.

---

## 13. Indexing API (incremental ingestion)

LangChain's **Indexing API** keeps a vector store in sync with sources without
re-embedding unchanged content — it tracks document hashes and does insert/update/delete
(`cleanup="incremental"` or `"full"`). This is the LangChain-native way to implement the
incremental sync from [T08](08-enterprise-integration.md).

---

## 14. Feature → use-case cheat sheet

| You need… | Use |
|-----------|-----|
| Provider-agnostic model init | `init_chat_model` (§2) |
| Typed output | `.with_structured_output` (§2) |
| Compose a RAG chain | LCEL pipe `|` + `RunnableParallel` (§4) |
| Resilience | `.with_retry` / `.with_fallbacks` (§2) |
| Hybrid + rerank retrieval | `EnsembleRetriever` + `ContextualCompressionRetriever` (§6) |
| Validated tools | `@tool` + Pydantic `args_schema` (§7) |
| Build an agent | `create_react_agent` (LangGraph) with LangChain tools (§8) |
| Conversation memory | `RunnableWithMessageHistory` (§9) / LangGraph checkpointer |
| Incremental ingest | Indexing API (§13) |
| Tracing & evals | LangSmith callbacks (§12) |

**Key takeaway:** LangChain = compose the components (LCEL for linear flows); LangGraph =
orchestrate them when you need cycles, state, durability, or multiple agents.

**Next:** [13 — MCP Tools & Tool-Calling Workflows](13-mcp-tool-calling.md).
