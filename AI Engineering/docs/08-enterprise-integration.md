# 08 — Enterprise Integration & MCP (SharePoint, CRM, Databases, Tools)

> **Goal:** Connect your AI system to where enterprise data and actions actually live —
> SharePoint, CRMs (Salesforce/Dynamics), databases, and tools — using robust connectors
> and the **Model Context Protocol (MCP)** as a standard tool interface.

---

## 1. The integration problem

Enterprise knowledge is scattered across silos, each with its own auth, rate limits,
permission model, and update cadence:

```
  ┌────────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
  │ SharePoint │  │   CRM    │  │ Databases│  │  Email   │  │  SaaS    │
  │  / OneDrive│  │(SF/Dyn)  │  │(PG/MySQL)│  │(Exchange)│  │(Jira...) │
  └─────┬──────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘
        │ connectors (sync) ◄── ingest (T02)       │ tools (live) ──► agent (T04)
        └──────────────┴────────────┴──────────────┴─────────────┘
                                    │
                          AI system (RAG + agents)
```

Two integration modes — know which you need:

- **Sync/ingest (pull into your index):** for *search over* slow-changing content
  (documents, wikis, knowledge bases). Goes through ingestion (T02) → vector/graph store.
- **Live tools (query at request time):** for *fresh, transactional* data and **actions**
  (current ticket status, account balance, "create a case"). Goes through agent tools (T04).

Rule of thumb: **search-heavy + slow-changing → sync**; **fresh + transactional or
write → live tool**. Many systems use both.

---

## 2. The connector contract

Every connector — whatever the source — should implement the same interface so the rest
of the system doesn't care where data came from. **Crucially, connectors carry
permissions, not just content** (see [T09](09-security-governance.md)).

```python
from typing import Protocol, AsyncIterator
from dataclasses import dataclass

@dataclass
class SourceDoc:
    source_uri: str
    content: bytes | str
    mime_type: str
    metadata: dict            # title, author, modified, etc.
    acl: list[str]            # who can see it — carried from the SOURCE system
    etag: str                 # for incremental sync / change detection
    tenant_id: str

class Connector(Protocol):
    async def list_changes(self, since: str | None) -> AsyncIterator[SourceDoc]: ...  # incremental
    async def fetch(self, source_uri: str) -> SourceDoc: ...
```

Non-negotiables for every connector:
- **Incremental sync** via change tokens/`etag`/`modified` — never full re-crawl.
- **Carry source ACLs** so retrieval can enforce the *source system's* permissions, not a
  flattened "everyone." This is the heart of secure enterprise RAG.
- **Respect rate limits** with backoff + concurrency caps (T07 §6).
- **Resilient & resumable** — store a cursor; resume after failure.

---

## 3. SharePoint / OneDrive (Microsoft Graph)

The most common enterprise document source. Use **Microsoft Graph API** with an
app-registration (OAuth2 client-credentials or delegated flow).

```python
import httpx

class SharePointConnector:
    def __init__(self, token_provider, tenant_id):
        self.token_provider, self.tenant_id = token_provider, tenant_id

    async def list_changes(self, since=None):
        token = await self.token_provider()                  # MSAL: cache + refresh
        url = f"https://graph.microsoft.com/v1.0/sites/{SITE_ID}/drive/root/delta"
        async with httpx.AsyncClient() as http:
            while url:
                r = await http.get(url, headers={"Authorization": f"Bearer {token}"})
                data = r.json()
                for item in data.get("value", []):
                    if "file" in item:
                        yield SourceDoc(
                            source_uri=item["webUrl"],
                            content=await self._download(item, token),
                            mime_type=item["file"]["mimeType"],
                            metadata={"title": item["name"], "modified": item["lastModifiedDateTime"]},
                            acl=await self._fetch_permissions(item["id"], token),  # Graph permissions
                            etag=item["eTag"], tenant_id=self.tenant_id,
                        )
                url = data.get("@odata.deltaLink") or data.get("@odata.nextLink")
                # persist the deltaLink → next run is incremental
```

SharePoint specifics: use the **`/delta`** endpoint for incremental crawl; fetch
**permissions per item** and map SharePoint groups → your ACL groups; handle large files
via download URLs; respect Graph throttling (429 + `Retry-After`).

---

## 4. CRM (Salesforce / Dynamics)

CRM data is **structured and transactional** — usually better as **live tools** (T04) and
**ontology mapping** (T05 §6) than as ingested blobs (it changes constantly).

```python
from langchain_core.tools import tool
from simple_salesforce import Salesforce

sf = Salesforce(instance_url=..., session_id=...)   # OAuth; refresh tokens server-side

@tool
def get_account(account_name: str) -> dict:
    """Look up a Salesforce account and its open opportunities by name."""
    safe = account_name.replace("'", r"\'")          # escape — SOQL injection guard
    res = sf.query(f"SELECT Id, Name, AnnualRevenue, Tier__c FROM Account "
                   f"WHERE Name = '{safe}' LIMIT 1")
    return res["records"][0] if res["records"] else {"error": "not found"}

@tool
def create_case(account_id: str, subject: str, description: str) -> dict:
    """Open a support case. WRITE action — requires human approval (T04 §7.2)."""
    return sf.Case.create({"AccountId": account_id, "Subject": subject, "Description": description})
```

CRM specifics: prefer the official API/SOQL over scraping; **escape/parameterize** all
query inputs; **gate write actions** (create/update) behind approval; respect API call
limits (Salesforce has hard daily caps); sync large reference data (product catalogs) to
the knowledge layer, query live data per request.

---

## 5. Databases (SQL) — text-to-SQL safely

Letting an agent query the warehouse is powerful and dangerous. Make it **read-only and
sandboxed**.

```python
@tool
def query_analytics(question: str) -> dict:
    """Answer a data question by querying the analytics DB (read-only)."""
    sql = llm_to_sql(question, schema=ALLOWED_SCHEMA)        # generate from a curated schema
    if not is_safe_select(sql):                              # reject writes/DDL/multi-stmt
        return {"error": "Only single read-only SELECT statements are permitted."}
    return {"sql": sql, "rows": readonly_db.execute(sql)}    # connection with SELECT-only grants
```

Text-to-SQL safety rules (all required, not optional):
- **Read-only DB role** with privileges limited to whitelisted tables/views — the DB
  itself is the last line of defense, not the prompt.
- **Validate generated SQL**: single statement, `SELECT` only, no DDL/DML, parse with a
  SQL parser rather than regex where possible.
- **Row limits + statement timeouts** to prevent runaway/expensive queries.
- **Expose curated views**, not raw tables — narrows surface and hides sensitive columns.
- **Apply tenant_id / row-level security** in the view or `WHERE` clause (T09).
- **Return the SQL** to the user/log for transparency and audit.

---

## 6. Model Context Protocol (MCP) — the tool standard

**MCP** is an open standard (introduced by Anthropic) for connecting LLM applications to
tools, data, and prompts through a uniform client-server interface. Instead of writing a
bespoke integration per model and per app, you build an **MCP server** once and any
MCP-capable client (Claude, IDEs, your agent) can use it.

```
   ┌──────────────┐        MCP         ┌──────────────────┐
   │ MCP Client   │ ◄────────────────► │  MCP Server      │
   │ (your agent, │   tools/resources/ │  (SharePoint,    │
   │  Claude,IDE) │      prompts        │   CRM, DB, KB)   │
   └──────────────┘                     └──────────────────┘
```

MCP servers expose three primitives:
- **Tools** — callable functions (actions/queries) the model can invoke.
- **Resources** — readable data (files, records) the model can pull as context.
- **Prompts** — reusable prompt templates the server offers.

### 6.1 A minimal MCP server

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("enterprise-kb")

@mcp.tool()
def search_kb(query: str, tenant_id: str) -> str:
    """Search the enterprise knowledge base."""
    return rag_answer(query, filters={"tenant_id": tenant_id})["answer"]   # T01

@mcp.resource("contract://{contract_id}")
def get_contract(contract_id: str) -> str:
    """Expose a contract document as a readable resource."""
    return load_contract_text(contract_id)

if __name__ == "__main__":
    mcp.run(transport="stdio")     # or streamable HTTP for networked deployments
```

### 6.2 Consuming MCP tools from a LangGraph agent

```python
from langchain_mcp_adapters.client import MultiServerMCPClient

client = MultiServerMCPClient({
    "kb":  {"command": "python", "args": ["kb_server.py"], "transport": "stdio"},
    "crm": {"url": "https://crm-mcp.internal/mcp", "transport": "streamable_http"},
})
mcp_tools = await client.get_tools()
agent = create_react_agent(llm, mcp_tools)        # T04 — MCP tools used like any other tool
```

### 6.3 Why MCP matters in the enterprise

- **Write once, reuse everywhere** — one CRM MCP server serves every model/app/agent.
- **Decoupling** — swap the underlying model or app without rewriting integrations.
- **Governed surface** — centralize auth, rate limiting, and audit in the MCP server.
- **Security caveat** — an MCP server is a privileged gateway. Treat its tools with the
  same least-privilege, input-validation, and approval rules as any tool (T04/T09); only
  connect MCP servers you trust, and scope their credentials tightly.

---

## 7. Cross-cutting integration concerns

- **Auth & secrets:** OAuth2/service principals per source; store secrets in a vault
  (not env files in prod); rotate tokens; refresh server-side.
- **Permission propagation:** the user's *effective* permissions in the source system
  must constrain what RAG returns — sync ACLs and filter on them (T05/T09).
- **Sync orchestration:** schedule incremental syncs (cron/event-driven via webhooks);
  track per-source cursors; alert on sync failures and staleness.
- **Schema/format drift:** sources change fields and formats — validate on ingest and
  fail loudly, don't silently index garbage.
- **Cost & rate limits:** every external API has caps — centralize throttling and cache
  (T07) so one chatty agent doesn't exhaust a daily quota.

---

## 8. Checklist

- [ ] Decide sync-vs-live per source (search/slow → sync; fresh/transactional/write → tool).
- [ ] One connector contract: incremental sync, ACL capture, resumable cursor, backoff.
- [ ] SharePoint via Graph `/delta` + per-item permissions mapped to ACL groups.
- [ ] CRM via official API; escape inputs; gate writes behind approval; respect call caps.
- [ ] Text-to-SQL: read-only role, validated single SELECT, curated views, limits/timeouts, tenant RLS.
- [ ] Use MCP for reusable, governed tool/resource interfaces; trust + scope each server.
- [ ] Vaulted secrets, rotated tokens, propagated permissions, monitored syncs.

**Next:** [09 — Security, PII & Governance](09-security-governance.md) — the controls
that make all of this compliant and auditable.
