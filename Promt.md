## Role
Act as a Senior Microsoft Sentinel Architect and CCF (Codeless Connector Framework) Expert with deep experience in:
- Azure Function–based data connectors (Python)
- Microsoft Sentinel ingestion pipelines
- REST API & Webhook integrations
- Security data engineering and schema design

---

## Background
I am a senior developer with 3–4 years of experience building Microsoft Sentinel integrations.

Previously, we developed data connectors using Azure Functions (Python), handling:
- API polling and webhook ingestion
- Authentication handling
- Pagination and checkpointing
- Data transformation and ingestion

These connectors are production-ready and compliant with Microsoft certification standards.

However, Microsoft has introduced **Codeless Connector Framework (CCF)** and is:
- Strongly recommending it for all new integrations
- Encouraging migration from Azure Function–based connectors

---

## Current Integration Approach (Function-Based)
For each integration, we:
1. Analyze API documentation or webhook mechanism
2. Identify:
   - Authentication type
   - API structure (single vs multiple endpoints)
   - Pagination (offset, cursor, next link)
   - Checkpointing (timestamp, ID, hash)
   - Data processing needs (filtering, merging, normalization)
3. Implement logic in Python:
   - Iterative data fetching
   - Stateful checkpointing
   - Data transformation
4. Send processed data to Microsoft Sentinel ingestion pipeline

---

## CCF Transition Goal
Now, we want to **fully automate the creation of CCF-based connectors**, replacing the above logic using:
- JSON/ARM templates
- Built-in CCF capabilities (auth, pagination, transformations, chaining APIs)

---

## Your Task (Phase 1 – Prompt + Guidance)

### 1. Define Ideal Input Requirements
Explain clearly:
- What inputs are required from the user to generate a CCF connector
  (e.g., OpenAPI spec, sample responses, schema, auth details, use cases)

### 2. Create a “Perfect Prompt Template”
Design a **single, high-quality Claude prompt** that:
- Takes API details as input
- Generates a **fully working CCF connector configuration**
- Covers:
  - Pull (polling) connectors
  - Push (webhook) connectors
  - Authentication setup
  - Pagination handling
  - Checkpointing strategy
  - Dependent API chaining
  - Data transformation (KQL if needed)

---

## Your Task (Phase 2 – Intelligence & Pattern Extraction)

I will provide:
- Existing CCF connector examples (e.g., BigID)
- Official Microsoft documentation

You must:
- Identify common reusable patterns:
  - API chaining
  - Pagination strategies
  - Auth mappings
  - Schema handling
- Extract reusable “design templates” for automation

---

## Your Task (Phase 3 – Agent Design)

Design an **Agentic AI System** that can:

### Input:
- OpenAPI spec / API documentation / README
- Sample response JSON
- Use case description

### Output:
- Fully working CCF connector JSON (single-shot)

### Agent Responsibilities:
1. API Analysis Agent
   - Understand endpoints, auth, pagination, dependencies

2. Schema Agent
   - Generate normalized schema for ingestion

3. Transformation Agent
   - Create KQL transformations if required

4. Connector Generator Agent
   - Build final CCF JSON template

5. Validation Agent
   - Ensure correctness and completeness

---

## Expected Output from You

Provide:

1. ✅ Feasibility confirmation (is full automation possible?)
2. ✅ Required input checklist for users
3. ✅ Best-in-class Claude prompt (ready-to-use)
4. ✅ Pattern extraction from CCF connectors
5. ✅ Agentic architecture (step-by-step)
6. ✅ Risks, limitations, and edge cases
7. ✅ Best practices aligned with Microsoft standards

---

## Reference Documentation
- https://learn.microsoft.com/en-us/azure/sentinel/create-codeless-connector  
- https://learn.microsoft.com/en-us/azure/sentinel/data-connector-ui-definitions-reference  
- https://learn.microsoft.com/en-us/azure/sentinel/create-push-codeless-connector  

---

## Important Constraints
- Output must be production-grade and accurate  
- Avoid assumptions; explicitly call out uncertainties  
- Follow Microsoft CCF standards strictly  
- Ensure generated connectors are logically correct and deployable  
