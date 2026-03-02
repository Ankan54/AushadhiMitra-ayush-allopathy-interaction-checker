# Design Document

## Overview

AushadhiMitra is a multi-agent AI system that checks for drug interactions between AYUSH (traditional Indian medicine) and allopathic (modern pharmaceutical) medicines. The system uses **Amazon Bedrock Agents with Bedrock Flow V4** to orchestrate a tiered, self-validating pipeline: instant responses from a PostgreSQL curated database for high-impact pairs (Layer 0), and real-time multi-agent analysis with a DoWhile validation loop for other queries. A Pipeline Mode fallback handles Bedrock Flow timeouts.

The backend is a **FastAPI application** with WebSocket streaming, deployed on Docker + Nginx. AWS Lambda functions serve as Action Groups for all deterministic operations. A dynamic JSON knowledge graph maps interaction pathways and is rendered on the frontend via Cytoscape.js.

**Key Design Principles:**
- **AWS Managed Services**: Bedrock Agents, Bedrock Flows, Lambda, S3, DynamoDB, RDS PostgreSQL
- **Bedrock Flow V4 + DoWhile**: Self-validating agent loop (max 3 iterations) with inline validation parser
- **Pipeline Fallback**: FastAPI-orchestrated direct agent invocation when Flow times out
- **Tiered Response**: Layer 0 (curated instant, <500ms) → Real-time multi-agent analysis → Graceful degradation
- **Grounded Reasoning**: LLM uses ONLY provided evidence from Lambda data sources
- **WebSocket Streaming**: Real-time agent trace events streamed to frontend
- **Full Source Citation**: Clickable URLs for every claim (PubMed, DrugBank, IMPPAT, Tavily)

**Architecture Summary:**
- **1 Planner Agent** (Claude 3 Sonnet): Routes requests, checks curated DB
- **3 Collaborator Agents**: AYUSH Agent (Claude 3 Haiku), Allopathy Agent (Claude 3 Haiku), Reasoning Agent (Claude 3 Sonnet)
- **12 Lambda Action Groups**: Deterministic business logic functions
- **Data Storage**: S3 (reference data), DynamoDB (IMPPAT phytochemicals), RDS PostgreSQL (curated DB + allopathy cache)
- **FastAPI Backend**: REST + WebSocket API, Docker + Nginx deployment

---

## AWS Architecture

### System Architecture Diagram

```
User (Browser/Chat)
        │
        ▼
[FastAPI + Nginx (Docker on EC2)]
   REST POST /api/check-interaction
   WS   /ws/check-interaction  ◄── Real-time trace streaming
        │
        ▼
[agent_service.py]
   ├─ mode=flow → Bedrock Flow V4 (DoWhile)
   └─ mode=pipeline (fallback) → Direct agent invocation
        │
        ▼
[Amazon Bedrock Flow V4]
   ┌────────────────────────────────────────────────────────┐
   │  FlowInput                                             │
   │     ↓                                                  │
   │  PlannerAgent (Claude 3 Sonnet)                        │
   │     ├─ identify_substances() Lambda                    │
   │     ├─ check_curated_interaction() Lambda ──► Layer 0  │
   │     │        (PostgreSQL hit → instant return)         │
   │     └─ Cache miss → enter DoWhile loop                 │
   │                                                        │
   │  DoWhile Loop (max 3 iterations)                       │
   │  ┌──────────────────────────────────────────────────┐  │
   │  │  AYUSHAgent (Claude 3 Haiku)                     │  │
   │  │     ├─ ayush_name_resolver() Lambda              │  │
   │  │     ├─ imppat_lookup() Lambda (DynamoDB)         │  │
   │  │     └─ search_cyp_interactions() Lambda (Tavily) │  │
   │  │                    +                             │  │
   │  │  AllopathyAgent (Claude 3 Haiku)                 │  │
   │  │     ├─ allopathy_cache_lookup() Lambda (PG)      │  │
   │  │     ├─ web_search() Lambda (Tavily)              │  │
   │  │     ├─ check_nti_status() Lambda                 │  │
   │  │     └─ allopathy_cache_save() Lambda (PG)        │  │
   │  │                    ↓                             │  │
   │  │  DataMergePrompt (Amazon Nova Pro)               │  │
   │  │     └─ Consolidate AYUSH + Allopathy data        │  │
   │  │                    ↓                             │  │
   │  │  ReasoningAgent (Claude 3 Sonnet)                │  │
   │  │     ├─ build_knowledge_graph() Lambda            │  │
   │  │     ├─ web_search() Lambda (research articles)   │  │
   │  │     ├─ calculate_severity() Lambda               │  │
   │  │     └─ format_professional_response() Lambda     │  │
   │  │                    ↓                             │  │
   │  │  ValidationParser (inline code node)            │  │
   │  │     └─ Extract validation_status from output     │  │
   │  │                    ↓                             │  │
   │  │  ValidationLoopController                        │  │
   │  │     ├─ PASSED → Exit DoWhile                     │  │
   │  │     └─ NEEDS_MORE_DATA → Re-run loop (max 3x)    │  │
   │  └──────────────────────────────────────────────────┘  │
   │                    ↓                                    │
   │  FlowOutput                                             │
   └────────────────────────────────────────────────────────┘
        │
        ▼
[FastAPI: format + stream response]
        │
        ▼
[Frontend: Cytoscape.js KG + Severity + Sources + Disclaimer]
```

---

## Component Details

### Backend (FastAPI)

**File: `backend/app/main.py`**
- REST endpoint `POST /api/check-interaction`: Synchronous interaction check
- WebSocket endpoint `WS /ws/check-interaction`: Streams agent trace events to frontend
- `GET /api/health`: Returns system status, agent IDs, Flow ID, DB config
- `GET /api/interactions`: Lists recent 20 curated interactions from PostgreSQL
- `GET /`: Serves React frontend static files

**File: `backend/app/agent_service.py`**
- Orchestrates Bedrock Flow V4 or Pipeline Mode execution
- Parses Bedrock Flow trace events for WebSocket streaming
- Handles Flow timeout → automatic Pipeline Mode fallback
- Supports `mode="auto|flow|pipeline"` parameter

**File: `backend/app/config.py`**
- Environment-based configuration for 4 agent IDs and aliases, Flow ID
- PostgreSQL connection string, input validation rules
- Agent model mapping (Sonnet for Planner/Reasoning, Haiku for AYUSH/Allopathy)

**File: `backend/app/db.py`**
- PostgreSQL connection pool (psycopg2)
- `lookup_curated(ayush_name, allopathy_name)` — Layer 0 instant response
- `get_sources(interaction_key)` — Retrieve source URLs for curated interactions
- `save_interaction(...)` — Persist new interaction results
- `list_interactions()` — Returns 20 most recent interactions

**File: `backend/app/models.py`**
- Pydantic `InteractionRequest`: validates `ayush_medicine`, `allopathy_drug`, `user_type`
- Pydantic `HealthResponse`: system status schema

**Deployment:**
- `Dockerfile`: Python 3.12-slim image
- `docker-compose.yml`: FastAPI app + Nginx reverse proxy
- `nginx.conf`: Reverse proxy config, static file serving

---

### Bedrock Agents

| Agent | Model | Role | Action Groups |
|-------|-------|------|---------------|
| **Planner Agent** | Claude 3 Sonnet | Entry point; identify substances, check curated DB | `planner_tools` |
| **AYUSH Agent** | Claude 3 Haiku | Gather plant phytochemical + CYP data | `ayush_data`, `web_search` |
| **Allopathy Agent** | Claude 3 Haiku | Gather drug CYP/metabolism data via cache + web | `allopathy_data`, `web_search` |
| **Reasoning Agent** | Claude 3 Sonnet | Build KG, score severity, validate, format response | `reasoning_tools`, `web_search` |

---

### Lambda Action Groups

#### `planner_tools/handler.py`
| Function | Input | Output |
|----------|-------|--------|
| `identify_substances` | Raw user text | `{ayush_medicine, allopathy_drug, confidence}` |
| `check_curated_interaction` | ayush_name, allopathy_name | `{found: bool, response_data, knowledge_graph}` (uses `response_data` column) |

#### `ayush_data/handler.py`
| Function | Input | Output |
|----------|-------|--------|
| `ayush_name_resolver` | Common/brand name | `{scientific_name, common_names, key_phytochemicals}` |
| `imppat_lookup` | scientific_name | `{phytochemicals[], admet_properties, cyp_effects}` from DynamoDB |
| `search_cyp_interactions` | plant_name | `{cyp_interactions[], sources[]}` via Tavily |

#### `allopathy_data/handler.py`
| Function | Input | Output |
|----------|-------|--------|
| `allopathy_cache_lookup` | drug_name | `{found: bool, drug_data, sources[], cached_at}` |
| `allopathy_cache_save` | drug_name, drug_data, sources | `{success: bool}` — 7-day TTL |
| `check_nti_status` | drug_name | `{is_nti: bool, clinical_concern, primary_cyp_substrates}` |

#### `web_search/handler.py`
| Function | Input | Output |
|----------|-------|--------|
| `web_search` | query, max_results | `{results: [{url, title, snippet, category, score}]}` |

Source categories: PubMed, DrugBank, FDA, research_paper, general

#### `reasoning_tools/handler.py`
| Function | Input | Output |
|----------|-------|--------|
| `build_knowledge_graph` | ayush_data, allopathy_data | `{nodes[], edges[], overlap_nodes[]}` |
| `calculate_severity` | interactions_data, is_nti | `{severity: NONE/MINOR/MODERATE/MAJOR, score: 0-100, factors[]}` |
| `format_professional_response` | all_data | Full structured JSON response |

#### `validation_parser/handler.py`
- Inline code node in Bedrock Flow
- Extracts `validation_status: PASSED | NEEDS_MORE_DATA` from Reasoning Agent output
- Controls DoWhile loop exit condition

#### Supporting Lambda Functions
- `imppat_loader/handler.py`: Loads IMPPAT phytochemical records to DynamoDB `ausadhi-imppat`
- `check_curated_db/handler.py`: Legacy S3-based curated check (replaced by PostgreSQL version)
- `shared/bedrock_utils.py`, `shared/db_utils.py`: Shared utilities

---

### Data Architecture

#### PostgreSQL (RDS) — `aushadhimitra` database
```
curated_interactions
  ├─ interaction_key       VARCHAR (PK, format: "ayush_name:allopathy_name")
  ├─ ayush_name            VARCHAR
  ├─ allopathy_name        VARCHAR
  ├─ severity              VARCHAR (NONE/MINOR/MODERATE/MAJOR)
  ├─ response_data         JSONB  ← NOTE: Lambda must use this column name
  ├─ knowledge_graph       JSONB
  └─ created_at            TIMESTAMP

interaction_sources
  ├─ source_id             SERIAL (PK)
  ├─ interaction_key       VARCHAR (FK → curated_interactions)
  ├─ url                   TEXT
  ├─ title                 TEXT
  ├─ snippet               TEXT
  └─ category              VARCHAR

allopathy_cache
  ├─ drug_name             VARCHAR (PK)
  ├─ generic_name          VARCHAR
  ├─ drug_data             JSONB
  ├─ sources               JSONB
  ├─ cached_at             TIMESTAMP
  └─ expires_at            TIMESTAMP (TTL: 7 days)
```

#### DynamoDB — `ausadhi-imppat` table
```
PK: plant_name (e.g., "curcuma_longa")
SK: record_key ("METADATA" or "PHYTO#<imppat_id>")

METADATA record:
  ├─ scientific_name, common_name, family
  └─ phytochemical_count, last_updated

PHYTO#<id> record:
  ├─ phytochemical_name, plant_part, imppat_id
  ├─ smiles, molecular_weight, drug_likeness
  ├─ admet_properties (dict)
  └─ cyp_interactions (inhibits[], induces[], substrates[])
```

#### S3 — `ausadhi-mitra-667736132441` bucket
```
/reference/name_mappings.json    — 5 AYUSH plants with scientific/common/Hindi/brand names
/reference/cyp_enzymes.json      — 10 CYP450 enzymes with severity weights
/reference/nti_drugs.json        — ~20 NTI drugs with clinical concerns
```

---

### Knowledge Graph Schema

```json
{
  "nodes": [
    {"id": "plant_1", "label": "Turmeric", "type": "Plant"},
    {"id": "phyto_1", "label": "Curcumin", "type": "Phytochemical"},
    {"id": "drug_1",  "label": "Warfarin",  "type": "Drug"},
    {"id": "cyp_1",   "label": "CYP2C9",    "type": "CYP_Enzyme", "is_overlap": true},
    {"id": "cyp_2",   "label": "CYP3A4",    "type": "CYP_Enzyme"}
  ],
  "edges": [
    {"source": "plant_1",  "target": "phyto_1", "relationship": "CONTAINS"},
    {"source": "phyto_1",  "target": "cyp_1",   "relationship": "INHIBITS"},
    {"source": "drug_1",   "target": "cyp_1",   "relationship": "METABOLIZED_BY"}
  ],
  "overlap_nodes": ["cyp_1"],
  "interaction_points": [
    {"enzyme": "CYP2C9", "effect": "Curcumin inhibits; Warfarin substrate → increased Warfarin levels"}
  ]
}
```

---

### Severity Scoring Algorithm

```
Base score: 0

+ 15 points × (number of shared CYP enzymes)
+ 25 points   (if allopathic drug is NTI)
+ 20 points   (if clinical evidence: case report or study found)
+ 15 points   (if pharmacodynamic overlap: shared effect category)

Score → Severity:
  0–20  → NONE
  21–40 → MINOR
  41–60 → MODERATE
  61+   → MAJOR
```

**Example (Turmeric + Warfarin):**
- CYP2C9 overlap: +15
- NTI (Warfarin): +25
- Anticoagulant PD overlap: +15
- Case report evidence: +20
- Total: 75 → **MAJOR**

---

### WebSocket Streaming Protocol

```
Client connects: WS /ws/check-interaction
Client sends: {"ayush_medicine": "turmeric", "allopathy_drug": "warfarin", "user_type": "professional"}

Server streams events:
  {"type": "status",         "message": "Starting interaction check..."}
  {"type": "trace",          "message": "PlannerAgent: Identifying substances", "data": {...}}
  {"type": "trace",          "message": "AYUSHAgent: Looking up IMPPAT data", "data": {...}}
  {"type": "trace",          "message": "AllopathyAgent: Web search in progress", "data": {...}}
  {"type": "agent_complete", "message": "ReasoningAgent: Analysis complete"}
  {"type": "validation",     "message": "Validation: PASSED", "loop_iterations": 1}
  {"type": "response_chunk", "message": "...response text chunk..."}
  {"type": "complete",       "full_response": {...}, "execution_mode": "flow", "loop_iterations": 1, "final_validation": "PASSED"}
```

---

### Professional Response Structure

```json
{
  "query": {"ayush_medicine": "...", "allopathy_drug": "..."},
  "severity": {
    "level": "MAJOR",
    "score": 75,
    "contributing_factors": ["CYP2C9 overlap", "NTI drug", "Anticoagulant PD overlap", "Case report evidence"]
  },
  "knowledge_graph": { "nodes": [...], "edges": [...], "overlap_nodes": [...] },
  "mechanisms": [
    {"type": "CYP", "enzyme": "CYP2C9", "effect": "Curcumin inhibits CYP2C9; Warfarin is CYP2C9 substrate → elevated Warfarin levels → bleeding risk"}
  ],
  "ayush_profile": {
    "plant": "Curcuma longa",
    "phytochemicals": ["Curcumin", "Demethoxycurcumin"],
    "cyp_effects": ["CYP2C9 inhibitor", "CYP3A4 inhibitor"],
    "sources": [{"url": "...", "title": "IMPPAT entry", "category": "database"}]
  },
  "allopathy_profile": {
    "drug": "Warfarin",
    "generic_name": "Warfarin sodium",
    "is_nti": true,
    "cyp_substrate": ["CYP2C9"],
    "sources": [{"url": "...", "title": "DrugBank: Warfarin", "category": "DrugBank"}]
  },
  "research_citations": [
    {"url": "https://pubmed.ncbi.nlm.nih.gov/...", "title": "Curcumin-warfarin interaction...", "category": "PubMed"}
  ],
  "conflicts": [],
  "ai_summary": "Turmeric (Curcumin) significantly inhibits CYP2C9, the primary enzyme metabolizing Warfarin...",
  "disclaimer": "This tool provides informational analysis only. Consult a licensed healthcare professional before making any medication decisions.",
  "execution_mode": "flow",
  "loop_iterations": 1
}
```

---

### Pipeline Fallback Mode

When Bedrock Flow V4 times out (known issue), `agent_service.py` falls back to Pipeline Mode:

```
FastAPI agent_service.py (Pipeline Mode)
  ↓
invoke_agent(planner_agent_id, query)
  ↓
invoke_agent(ayush_agent_id, substances)       ─┐ parallel
invoke_agent(allopathy_agent_id, substances)   ─┘
  ↓
invoke_agent(reasoning_agent_id, merged_data)
  ↓
Return formatted response
```

---

## Deployment Architecture

```
AWS Account: 667736132441  |  Region: us-east-1

EC2 Instance
  └─ Docker Compose
       ├─ aushadhimitra-app (FastAPI, port 8000)
       └─ aushadhimitra-nginx (Nginx, port 80/443)

AWS Services:
  ├─ Bedrock Agents (4 agents: Planner, AYUSH, Allopathy, Reasoning)
  ├─ Bedrock Flows (Flow V4 with DoWhile)
  ├─ Lambda (12 functions, Python 3.12, us-east-1)
  ├─ S3 Bucket: ausadhi-mitra-667736132441
  ├─ DynamoDB: ausadhi-imppat
  ├─ RDS PostgreSQL: scm-postgres.c2na6oc62pb7.us-east-1.rds.amazonaws.com:5432/aushadhimitra
  └─ Secrets Manager: Tavily API key
```

### Deployment Scripts
| Script | Purpose |
|--------|---------|
| `scripts/create_flow_v4.py` | Build Bedrock Flow V4 with DoWhile node |
| `scripts/setup_agents.py` | Create/update 4 Bedrock agents with action groups |
| `scripts/deploy_lambdas.sh` | Package and deploy Lambda functions |
| `scripts/imppat_pipeline.py` | Load IMPPAT CSV data to DynamoDB |
| `scripts/plant_details_extractor.py` | Extract IMPPAT plant metadata |
| `scripts/plant_specific_extractor.py` | Deep extract phytochemical data per plant |

---

## Known Issues and Mitigations

| # | Issue | Impact | Mitigation |
|---|-------|--------|-----------|
| 1 | Bedrock Flow V4 timeout (Read timed out) | Flow execution fails | Auto-fallback to Pipeline Mode in `agent_service.py` |
| 2 | Curated DB Lambda uses `interaction_data` column but DB has `response_data` | Layer 0 instant responses always fail; every query triggers full analysis | Fix Lambda to use `response_data` column |
| 3 | `calculate_severity()` NoneType error when `interactions_data` is None | Severity Lambda crashes on null input | Add null guard: `if not interactions_data: return default_result` |
| 4 | `db.py` backend vs Lambda schema alignment | Potential column name drift | Consolidate schema constants in `shared/db_utils.py` |
| 5 | Empty `knowledge_graph` in some final responses | KG visualization fails silently | Ensure `build_knowledge_graph()` always returns a valid graph structure |

---

## Data Flow: Example Query

**Input:** "Check interaction between turmeric and warfarin" (user_type: professional)

```
1. FastAPI validates request (Pydantic)
2. agent_service.py → attempt Bedrock Flow V4
3. PlannerAgent:
   - identify_substances() → {ayush: "Curcuma longa", allopathy: "Warfarin"}
   - check_curated_interaction() → {found: false} [Issue #2: may fail]
4. DoWhile Iteration 1:
   a. AYUSHAgent:
      - ayush_name_resolver("turmeric") → scientific_name: "Curcuma longa"
      - imppat_lookup("Curcuma longa") → {Curcumin: CYP2C9/3A4 inhibitor, Demethoxycurcumin: ...}
      - search_cyp_interactions("Curcuma longa") → Tavily results with PubMed links
   b. AllopathyAgent:
      - allopathy_cache_lookup("Warfarin") → {found: false} (first run)
      - web_search("Warfarin CYP metabolism DrugBank") → {CYP2C9 substrate, NTI drug}
      - check_nti_status("Warfarin") → {is_nti: true, clinical_concern: "Bleeding risk"}
      - allopathy_cache_save("Warfarin", data) → cached for 7 days
   c. DataMergePrompt (Nova Pro) → consolidated data object
   d. ReasoningAgent:
      - build_knowledge_graph() → {nodes: [Turmeric, Curcumin, Warfarin, CYP2C9], edges: [...], overlap: [CYP2C9]}
      - web_search("Curcumin warfarin interaction PubMed") → research citations
      - calculate_severity() → {score: 75, level: MAJOR, factors: [CYP2C9, NTI, PD, evidence]}
      - format_professional_response() → full JSON
      - validation_status: PASSED
   e. ValidationParser → extract "PASSED"
   f. Loop exits
5. FlowOutput → FastAPI formats and streams response
6. WebSocket: streams trace events → "complete" event with full_response JSON
7. Frontend: renders Cytoscape.js graph + severity badge + source URLs + disclaimer
```
