# 05 — Multi-Tenant, Ontology-Driven Knowledge Layers

> **Goal:** Move beyond a flat pile of chunks to a **knowledge layer**: a structured,
> ontology-driven, multi-tenant representation of enterprise data that agents and RAG can
> query precisely — with correct isolation, relationships, and governance baked in.

---

## 1. Why a knowledge layer?

Plain vector RAG answers "what does a document *say*?" It struggles with questions that
require **structure and relationships**:

- "Which contracts with *Acme* renew in Q3 and reference the *new indemnity clause*?"
- "Show all incidents caused by the *same root component* as ticket #4021."
- "What's the *reporting chain* from this employee to the CFO?"

These need **entities** (Contract, Customer, Component, Employee), **relationships**
(renews, caused-by, reports-to), and **attributes** — i.e. an **ontology** and often a
**knowledge graph**, layered over the documents. The knowledge layer is the semantic
contract between messy source data and the AI system.

```
  ┌───────────────────────────────────────────────────────────────┐
  │                     KNOWLEDGE LAYER                              │
  │  Ontology (classes, properties, relations)                      │
  │      │                                                          │
  │      ├── Knowledge graph (entities + edges)  ◄── extracted ──┐  │
  │      └── Vector index (chunks + entity links) ◄──────────────┤  │
  └──────────────────────────────────────────────────────────────│──┘
                                                                   │
        documents (T02) ──► entity/relation extraction ───────────┘
        structured data (T08: CRM, DB) ──► mapped to ontology
```

---

## 2. The ontology: a shared vocabulary

An **ontology** defines the *types of things* in your domain and how they relate. It is
the controlled vocabulary that keeps the system consistent across teams and sources.

A minimal, practical ontology spec:

```yaml
# ontology.yaml — keep it versioned in git; treat changes like schema migrations
classes:
  Customer:    { keys: [customer_id], attributes: [name, tier, region] }
  Contract:    { keys: [contract_id], attributes: [title, value, start, end, status] }
  Component:   { keys: [component_id], attributes: [name, team_owner] }
  Incident:    { keys: [incident_id], attributes: [severity, opened_at, status] }
relations:
  - { name: has_contract,   from: Customer,  to: Contract,  cardinality: 1:N }
  - { name: affects,        from: Incident,  to: Component, cardinality: N:N }
  - { name: caused_by,      from: Incident,  to: Component, cardinality: N:1 }
  - { name: references,     from: Contract,  to: Clause,    cardinality: N:N }
```

Design guidance:
- **Start small.** Model the entities your top queries actually need; grow iteratively.
- **Reuse standards** where they exist (schema.org, FIBO for finance, industry taxonomies)
  instead of inventing from scratch.
- **Version it.** Ontology changes ripple through extraction, indexing, and queries —
  manage them like database migrations with backfills.
- **Own it with SMEs.** Domain experts ([the SMEs you collaborate with](README.md))
  define the vocabulary; you encode and enforce it.

---

## 3. Building the knowledge graph

### 3.1 Entity & relation extraction from documents

Use an LLM with the ontology as the schema to extract structured triples from chunks.
Constrain it to your ontology types so output stays consistent.

```python
from pydantic import BaseModel
from langchain_anthropic import ChatAnthropic

class Entity(BaseModel):
    type: str        # must be one of the ontology classes
    name: str
    attributes: dict

class Relation(BaseModel):
    type: str        # must be one of the ontology relations
    source: str      # entity name
    target: str

class Extraction(BaseModel):
    entities: list[Entity]
    relations: list[Relation]

extractor = ChatAnthropic(model="claude-sonnet-4-6", temperature=0).with_structured_output(Extraction)

EXTRACT = """Extract entities and relations from the text using ONLY these types.
Classes: {classes}
Relations: {relations}
Do not invent types. If unsure, omit. Text:
{chunk}"""

result = extractor.invoke(EXTRACT.format(classes=CLASSES, relations=RELATIONS, chunk=chunk_text))
```

### 3.2 Entity resolution (the hard, essential part)

"Acme Corp", "ACME", and "Acme Corporation" are one entity. Without **entity
resolution**, your graph fragments and relationship queries break.

```python
# Strategy: blocking + embedding similarity + deterministic keys
def resolve_entity(candidate: Entity, store) -> str:
    if key := candidate.attributes.get("customer_id"):   # 1. exact key match wins
        return store.upsert_by_key("Customer", key, candidate)
    # 2. fuzzy: embed the name, search existing entities of same type, merge if > threshold
    matches = store.search_similar(candidate.type, candidate.name, threshold=0.92)
    return matches[0].id if matches else store.create(candidate)
```

### 3.3 Storing the graph

| Store | When |
|-------|------|
| **Neo4j** / property graph | rich traversal queries, mature tooling |
| **Postgres + edges table** | simpler ops, moderate graph needs |
| **Vector DB payload links** | lightweight: store entity ids in chunk metadata |
| **RDF triple store** | strict W3C ontology/SPARQL/reasoning requirements |

For most enterprise RAG, a pragmatic combo works: **Postgres/Neo4j for the graph** +
**vector DB for chunks**, with chunks carrying the entity ids they mention so you can hop
between text and structure.

---

## 4. GraphRAG: querying text + structure together

**GraphRAG** combines graph traversal with vector retrieval. The graph narrows *which*
entities/documents are relevant via relationships; vectors find the *passages*.

```python
def graph_rag(question: str, tenant_id: str):
    # 1. extract entities mentioned in the question
    seeds = extract_entities(question)                       # e.g. Customer "Acme"
    # 2. traverse the graph to gather the relevant neighborhood (tenant-scoped)
    subgraph = graph.neighborhood(seeds, hops=2, tenant_id=tenant_id)
    related_doc_ids = [n.doc_id for n in subgraph.nodes if n.doc_id]
    # 3. vector retrieve, RESTRICTED to those documents (precise + grounded)
    chunks = hybrid_retrieve(question, filters={"tenant_id": tenant_id,
                                                "doc_id": {"in": related_doc_ids}})
    # 4. give the LLM both the graph facts and the passages
    return llm.invoke(build_prompt_with_graph(question, subgraph, chunks))
```

This shines for **global/relational questions** ("themes across all incidents this
quarter", "all obligations Acme owes us") where flat RAG retrieves scattered, incomplete
context. For simple lookup questions, plain RAG ([T01](01-rag-pipelines.md)) is cheaper —
route by query type.

---

## 5. Multi-tenancy: isolation is the whole game

Enterprise = many tenants (customers, business units, regions) whose data **must not
leak** across boundaries. Tenancy must be enforced at *every* layer.

### 5.1 Isolation models

| Model | Vector DB | Graph | Isolation | Cost |
|-------|-----------|-------|-----------|------|
| **Shared + tenant_id filter** | one collection, `tenant_id` payload | `tenant_id` on every node | logical | lowest |
| **Namespace/native tenant** | Weaviate tenants / Qdrant partitions | graph per tenant label | strong | medium |
| **Silo (resource per tenant)** | collection/DB per tenant | DB per tenant | strongest | highest |

Choose by **count × sensitivity**: many small tenants → shared+filter; few regulated
tenants → silo; in between → native tenants. Document the choice; it's hard to change later.

### 5.2 The golden rule

```python
# tenant_id ALWAYS comes from the authenticated principal, NEVER from request body
def authorized_filter(principal) -> dict:
    return {
        "tenant_id": principal.tenant_id,           # server-derived, not client-supplied
        "acl": {"any": principal.groups},            # row/chunk-level ACL (T09)
    }
# every retrieval, graph traversal, and tool call passes this filter — no exceptions
```

A single code path that forgets the filter is a cross-tenant data breach. Centralize the
filter so it can't be omitted, and **test it** with a tenant-isolation eval ([T06](06-guardrails-evals.md)):
seed tenant A data, query as tenant B, assert zero leakage.

---

## 6. Mapping structured enterprise data

Not everything is a document. CRM rows, database tables, and tickets ([T08](08-enterprise-integration.md))
map directly onto ontology entities — often *more reliably* than LLM extraction.

```python
# Deterministic mapping beats LLM extraction for structured sources — use it when you can
def map_crm_account(row) -> Entity:
    return Entity(type="Customer", name=row["account_name"],
                  attributes={"customer_id": row["id"], "tier": row["tier"],
                              "region": row["region"], "tenant_id": row["org_id"]})
```

Result: a knowledge layer fed by **both** unstructured (documents → extraction) and
structured (systems → mapping) sources, unified under one ontology.

---

## 7. Keeping it fresh

- **Incremental updates.** When a source doc/row changes (T08 sync), re-extract only that
  item and reconcile entities — don't rebuild the graph.
- **Temporal validity.** Store `valid_from`/`valid_to` on facts so "what was true in
  March?" is answerable and stale facts don't pollute answers.
- **Provenance.** Every entity/edge records which source + extraction run produced it —
  essential for trust, debugging, and audit (T09).
- **Confidence.** Tag extracted (vs mapped) facts with a confidence score; low-confidence
  facts can require human review before they're trusted.

---

## 8. Checklist

- [ ] Define a small, versioned ontology with SMEs; reuse standards where possible.
- [ ] Extract entities/relations constrained to the ontology; resolve duplicates.
- [ ] Map structured sources deterministically; reserve LLM extraction for documents.
- [ ] Store graph (Neo4j/Postgres) + chunks (vector DB) with cross-links.
- [ ] Use GraphRAG for relational/global questions; plain RAG for lookups.
- [ ] Enforce tenant_id + ACL from the authenticated principal at every layer; centralize the filter.
- [ ] Add a cross-tenant isolation eval to CI (T06).
- [ ] Track provenance, temporal validity, and confidence on every fact.

**Next:** [06 — Guardrails, Hallucination Reduction & Evals](06-guardrails-evals.md) —
making sure the answers built on this knowledge layer are actually trustworthy.
