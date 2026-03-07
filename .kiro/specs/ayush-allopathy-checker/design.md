# Design Document

## Overview

AushadhiMitra is a multi-agent AI system that checks for drug interactions between AYUSH (traditional Indian medicine) and allopathic (modern pharmaceutical) medicines. The system uses a **CO-MAS (Cooperative Multi-Agent System) pipeline** orchestrated directly by the FastAPI backend — five specialized AWS Bedrock Agents collaborate across up to 3 self-improving iterations to gather evidence, reason over it, and produce a structured interaction analysis.

A tiered response strategy is used: instant responses from a PostgreSQL curated database (Layer 0) for known high-impact pairs, and real-time CO-MAS analysis for novel queries. Results are streamed to the frontend via WebSocket and rendered in a tabbed React UI with an ADMET-focused Cytoscape.js knowledge graph.

**Key Design Principles:**
- **CO-MAS Orchestration**: FastAPI orchestrates all 5 agents directly — no Bedrock Flows or DoWhile nodes
- **Iterative Self-Improvement**: Deterministic Scorer identifies gaps; Planner adapts its plan each iteration
- **Pipeline Memory**: What worked in iteration N is passed to the Planner in iteration N+1 to avoid redundant re-fetching
- **ADMET Knowledge Graph**: Both drugs visualized with Absorption/Distribution/Metabolism/Excretion/Toxicity nodes; CYP overlaps highlighted
- **Two-Stage Severity**: CYP-based Lambda scoring + pharmacodynamic boost from agent text evidence
- **Full Source Traceability**: URLs extracted from all agent traces and response text; rendered as clickable links
- **WebSocket Streaming**: Every agent action streamed in real time to the frontend

**Architecture Summary:**
- **5 Bedrock Agents**: Planner (Claude 3 Sonnet), AYUSH (Claude 3 Haiku), Allopathy (Claude 3 Haiku), Research (Claude 3 Haiku), Reasoning (Claude 3 Sonnet)
- **7 Lambda Functions**: Deterministic tool implementations
- **Data Storage**: S3 (reference data), DynamoDB (IMPPAT phytochemicals), RDS PostgreSQL (curated DB + allopathy cache)
- **FastAPI Backend**: `POST /api/check` + `WS /ws/{session_id}`, Docker + Nginx on EC2

---

## System Architecture

### Architecture Diagram

```
User (Browser)
      │
      ▼
[Nginx (port 80)] ──► [React SPA / static files]
      │
      ▼ /api/* and /ws/*
[FastAPI backend (port 8000)]
  ├─ POST /api/check  → start CO-MAS pipeline (returns session_id)
  ├─ WS   /ws/{session_id} → stream real-time events
  └─ GET  /api/health, /api/interactions
      │
      ▼
[agent_service.py — CO-MAS Orchestrator]
  │
  ├─ Layer 0: lookup_curated(ayush, allopathy) → PostgreSQL
  │     └─ Hit: return instantly (<500ms)
  │
  └─ Cache miss: CO-MAS Pipeline (max 3 iterations)
       │
       ▼
  ┌─────────────────────────────────────────────────────┐
  │  CO-MAS Iteration (repeated up to 3x)               │
  │                                                     │
  │  1. PLANNER PHASE                                   │
  │     PlannerAgent (Claude 3 Sonnet)                  │
  │       ├─ identify_substances() Lambda               │
  │       ├─ check_curated_db() Lambda                  │
  │       └─ create_execution_plan() Lambda             │
  │     [Iter 2+: prompt includes pipeline memory       │
  │      + remaining gaps, NOT the initial prompt]      │
  │                                                     │
  │  2. PROPOSER PHASE (parallel)                       │
  │     AYUSHAgent (Claude 3 Haiku)                     │
  │       ├─ ayush_name_resolver() Lambda               │
  │       ├─ imppat_lookup() Lambda (DynamoDB)          │
  │       └─ search_cyp_interactions() Lambda (Tavily)  │
  │     AllopathyAgent (Claude 3 Haiku)                 │
  │       ├─ allopathy_drug_lookup() Lambda             │
  │       └─ check_nti_status() Lambda                  │
  │     ResearchAgent (Claude 3 Haiku)                  │
  │       └─ web_search() Lambda (Tavily/PubMed)        │
  │                                                     │
  │  3. EVALUATOR PHASE                                 │
  │     ReasoningAgent (Claude 3 Sonnet)                │
  │       ├─ build_knowledge_graph() Lambda             │
  │       ├─ calculate_severity() Lambda                │
  │       └─ web_search() Lambda (if more evidence      │
  │          needed)                                    │
  │                                                     │
  │  4. SCORER PHASE (deterministic Python)             │
  │     _score_output() → 0–100 score + gap list        │
  │     _boost_severity_from_evidence() → PD boost      │
  │     pipeline_memory updated with successes          │
  │                                                     │
  │  score ≥ 60 AND has_substance? → EXIT               │
  │  else iteration < 3?           → NEXT ITERATION     │
  │  else iteration == 3?          → EXIT (best effort) │
  └─────────────────────────────────────────────────────┘
      │
      ▼
  _format_final_json()
  _extract_drugbank_url()
  _extract_source_urls()
  _transform_graph_to_admet()
      │
      ▼
  WebSocket "complete" event → Frontend
```

---

## Component Details

### Backend (FastAPI)

**File: `backend/app/main.py`**
- `POST /api/check`: Validates request (Pydantic), starts CO-MAS pipeline in background thread, returns `{session_id}`
- `WS /ws/{session_id}`: Reads from session queue and streams pipeline events to the connected browser client
- `GET /api/health`: Returns system status, agent IDs, DB config
- `GET /api/interactions`: Lists recent 20 curated interactions from PostgreSQL
- `GET /` and `GET /{path}`: Serves React SPA static files from `/app/static/`

**File: `backend/app/agent_service.py`**
- `run_comas_pipeline()`: Main orchestrator — runs up to 3 CO-MAS iterations, manages pipeline memory, streams events to session queue
- `_invoke_planner()`: Invokes Planner Agent with iteration-aware prompt (initial plan vs. gap-focused subsequent prompt)
- `_invoke_proposers()`: Runs AYUSH, Allopathy, Research agents in parallel (ThreadPoolExecutor)
- `_invoke_reasoning()`: Invokes Reasoning (Evaluator) Agent with merged proposer context
- `_score_output()`: Deterministic scorer — awards 0–100 points across 8 dimensions; returns `(passes, gaps, score, evidence_quality)`
- `_boost_severity_from_evidence()`: Scans agent response text for pharmacodynamic keywords; adds PD boost (capped at +25) to CYP base score
- `_format_final_json()`: Assembles final `interaction_data` dict from agent outputs
- `_extract_drugbank_url()`: Searches all traces + response text for DrugBank URL patterns
- `_extract_source_urls()`: Parses URLs from all agent traces and responses; deduplicates into structured `sources` list
- `_transform_graph_to_admet()`: Post-processes Lambda KG output to ensure ADMET nodes have drug-prefixed labels (e.g., "Curcuma: Metabolism") and edges use "has \<property\>" format
- `_call_severity_lambda()`: Direct Lambda invocation fallback when the Reasoning Agent doesn't call `calculate_severity()`

**File: `backend/app/config.py`**
- Environment-based configuration: 5 agent IDs + aliases, S3 bucket, PostgreSQL DSN
- Agent model mapping (Sonnet for Planner/Reasoning, Haiku for AYUSH/Allopathy/Research)
- `MAX_COMAS_ITERATIONS = 3`

**File: `backend/app/db.py`**
- PostgreSQL connection pool (psycopg2)
- `lookup_curated(ayush_name, allopathy_name)` — Layer 0 instant response using `response_data` column
- `get_sources(interaction_key)` — Source URLs for curated interactions
- `save_interaction(...)` — Persist new interaction results
- `list_interactions()` — Returns 20 most recent interactions

**Deployment:**
- `Dockerfile`: Python 3.11-slim, installs requirements, copies all app files
- `docker-compose.yml`: `aushadhi-comas:latest` app container (port 8000) + Nginx (port 80)
- `nginx.conf`: Reverse proxy, WebSocket upgrade headers, static file serving

---

### Bedrock Agents

| Agent | Model | Role | Action Groups |
|-------|-------|------|---------------|
| **Planner** | Claude 3 Sonnet | Plan iteration; identify substances; check curated DB | `planner_tools` |
| **AYUSH** | Claude 3 Haiku | Gather plant phytochemical + ADMET + CYP data | `ayush_data`, `web_search` |
| **Allopathy** | Claude 3 Haiku | Gather drug ADMET, NTI status, DrugBank URL | `allopathy_data`, `web_search` |
| **Research** | Claude 3 Haiku | Search PubMed and clinical evidence sources | `web_search`, `research_tools` |
| **Reasoning** | Claude 3 Sonnet | Synthesize, build KG, score severity, format output | `reasoning_tools`, `web_search` |

All agents use alias `TSTALIASID` (routes to latest DRAFT version).

---

### Lambda Action Groups

#### `ausadhi-planner-tools`
| Function | Input | Output |
|----------|-------|--------|
| `identify_substances` | Raw query text | `{ayush_name, allopathy_name, confidence}` |
| `check_curated_db` | ayush_name, allopathy_name | `{found: bool, response_data, knowledge_graph}` |
| `create_execution_plan` | substances, gaps, iteration | `{plan_version, tasks[]}` |

#### `ausadhi-ayush-data`
| Function | Input | Output |
|----------|-------|--------|
| `ayush_name_resolver` | Common/brand name | `{scientific_name, common_names, key_phytochemicals}` |
| `imppat_lookup` | scientific_name | `{phytochemicals[], admet_properties, cyp_effects}` from DynamoDB |
| `search_cyp_interactions` | plant_name | `{cyp_interactions[], sources[]}` via Tavily |

#### `ausadhi-allopathy-data`
| Function | Input | Output |
|----------|-------|--------|
| `allopathy_drug_lookup` | drug_name | `{drug_data, drugbank_url, admet_properties, sources[]}` |
| `check_nti_status` | drug_name | `{is_nti: bool, clinical_concern, primary_cyp_substrates}` |

#### `ausadhi-web-search`
| Function | Input | Output |
|----------|-------|--------|
| `web_search` | query, max_results | `{results: [{url, title, snippet, category, score}]}` |

Source categories: PubMed, DrugBank, FDA, research_paper, general

#### `ausadhi-reasoning-tools`
| Function | Input | Output |
|----------|-------|--------|
| `build_knowledge_graph` | ayush_name, allopathy_name, interactions_data_str | `{nodes[], edges[]}` — ADMET + CYP overlap nodes |
| `calculate_severity` | interactions_data_str, allopathy_name | `{severity, severity_score, is_nti, scoring_factors}` |

#### `ausadhi-check-curated-db`
- Provides `check_curated_db` as a callable action group tool for agents
- Queries PostgreSQL `curated_interactions` table using `response_data` column

#### `ausadhi-research-tools`
- Provides research-specific search capabilities (PubMed, clinical trial databases)

---

### Knowledge Graph Design

The knowledge graph is **ADMET-focused** — it shows the pharmacokinetic/toxicological profile of both drugs side by side, with CYP enzyme overlap nodes where the two drugs share the same metabolic pathway.

**Node types:**

| Type | Label Format | Color |
|------|-------------|-------|
| `ayush_plant` | Scientific name (e.g., "Curcuma longa") | Green |
| `allopathy_drug` | Drug name (e.g., "Metformin") | Blue |
| `admet_property` | "DrugShortName: Category" (e.g., "Curcuma: Metabolism") | Orange |
| `cyp_enzyme_overlap` | Enzyme name (e.g., "CYP3A4") | Red (highlighted) |
| `cyp_enzyme` | Enzyme name | Yellow |

**Edge label format:**
- Drug → ADMET node: `"has Absorption"`, `"has Metabolism"`, etc.
- Drug → CYP node: `"Inhibits"`, `"Induces"`, `"Metabolized by"`

**Schema:**
```json
{
  "nodes": [
    {"data": {"id": "ayush", "label": "Curcuma longa", "type": "ayush_plant"}},
    {"data": {"id": "allopathy", "label": "Metformin", "type": "allopathy_drug"}},
    {"data": {"id": "ayush_absorption", "label": "Curcuma: Absorption", "type": "admet_property"}},
    {"data": {"id": "allo_absorption", "label": "Metformin: Absorption", "type": "admet_property"}},
    {"data": {"id": "ayush_metabolism", "label": "Curcuma: Metabolism", "type": "admet_property"}},
    {"data": {"id": "allo_metabolism", "label": "Metformin: Metabolism", "type": "admet_property"}},
    {"data": {"id": "cyp_CYP3A4", "label": "CYP3A4", "type": "cyp_enzyme_overlap"}}
  ],
  "edges": [
    {"data": {"source": "ayush", "target": "ayush_absorption", "label": "has Absorption"}},
    {"data": {"source": "allopathy", "target": "allo_absorption", "label": "has Absorption"}},
    {"data": {"source": "ayush", "target": "cyp_CYP3A4", "label": "Inhibits"}},
    {"data": {"source": "allopathy", "target": "cyp_CYP3A4", "label": "Metabolized by"}}
  ]
}
```

**Post-processing (`_transform_graph_to_admet`):**
After the Lambda returns the graph, the orchestrator applies label fixes:
- ADMET nodes without drug-name prefix → prefixed with `"DrugShort: Category"`
- Edge labels that are bare category names → prefixed with `"has "`
- This ensures correct labeling even if the Lambda returned generic labels

---

### Severity Scoring Algorithm

**Stage 1 — CYP-based (`calculate_severity` Lambda):**
```
base_score = 0

For each CYP enzyme in interactions_data.cyp_enzymes:
  weight = cyp_ref[enzyme].severity_weight  (from S3 cyp_enzymes.json)
  if effect == inhibit/inhibitor:  base_score += weight × 2
  elif effect == induce/inducer:   base_score += weight × 1.5
  else:                            base_score += weight

if allopathy_drug in nti_drugs:    base_score += 25

Thresholds (from cyp_enzymes.json):
  NONE     < 15
  MINOR    15–34
  MODERATE 35–59
  MAJOR    ≥ 60
```

**Stage 2 — PD boost (`_boost_severity_from_evidence` in agent_service.py):**
```
Scan all agent response text for PD keyword groups (each group counts once):
  - Hypoglycemic risk keywords → +8 to +10
  - Synergistic/additive effect → +7 to +8
  - AMPK pathway → +5
  - Insulin sensitization → +5
  - Potentiation → +7
  - Bioavailability change → +6
  - Hepatotoxicity / Nephrotoxicity → +6
  - Bleeding / Anticoagulant → +7
  ... etc.

pd_boost = min(total_pd_points, 25)  ← hard cap

final_score = min(cyp_base + pd_boost, 100)
final_severity = reclassified by threshold
```

**Example (Turmeric + Metformin):**
- Metformin is not NTI, not primarily CYP-metabolized → CYP base ≈ 15 (MINOR)
- PD boost from "blood glucose"/"synergistic" keywords → +15 to +21
- Final score: 30–36 → **MINOR to MODERATE** (varies by LLM response content)

**Example (Turmeric + Warfarin):**
- CYP2C9 overlap (weight×2): +20
- NTI boost: +25
- PD: anticoagulant synergy: +7
- Total: 52+ → **MODERATE to MAJOR**

---

### Scorer (`_score_output`)

Deterministic Python function awarding 0–100 points:

| Dimension | Points | Pass Condition |
|-----------|--------|----------------|
| `ayush_name` present | 10 | Not None/empty |
| `allopathy_name` present | 10 | Not None/empty |
| Severity (not NONE, score > 0) | 20 | `severity != "NONE"` AND `severity_score > 0` |
| Knowledge graph (≥ 3 nodes) | 10 | `len(nodes) >= 3` |
| Sources (≥ 2) | 10 | `len(sources) >= 2` |
| Mechanisms (PK or PD) | 10 | `pk or pd` non-empty |
| Reasoning chain (≥ 2 steps) | 10 | `len(reasoning_chain) >= 2` |
| Phytochemicals (≥ 1) | 10 | `len(phytochemicals) >= 1` |
| Interaction summary (≥ 80 chars) | 10 | `len(summary) >= 80` |

**Pass condition:**
```python
has_substance = bool(pk or pd or len(phytos) >= 1 or len(rc) >= 2)
passes = (score >= 60 and has_substance) or iteration >= MAX_COMAS_ITERATIONS
```

---

### Pipeline Memory

Maintained as a per-session dict, updated after each scored iteration:

```python
pipeline_memory = {
    "successes": [
        "AYUSH drug identification confirmed: Curcuma longa",
        "Found 3 phytochemicals (curcumin, demethoxycurcumin, bisdemethoxycurcumin)",
        "Severity assessed as MODERATE (51/100)",
        "KG built with 12 nodes"
    ],
    "data_collected": {
        "ayush_name": "Curcuma longa",
        "allopathy_name": "Metformin",
        "phytochemicals": ["curcumin"],
        "cyp_enzymes": ["CYP3A4"]
    },
    "source_urls": ["https://pubmed.ncbi.nlm.nih.gov/..."]
}
```

Passed to the Planner in iteration N+1 as:
```
WHAT WORKED WELL (do NOT re-fetch):
  - AYUSH drug identification confirmed: Curcuma longa
  - Found 3 phytochemicals...

REMAINING GAPS (focus on these):
  - Need detailed reasoning chain with evidence (at least 2 steps)
  - Need interaction summary (at least 80 characters)
```

---

### WebSocket Streaming Protocol

```
Client: POST /api/check  {"ayush_name": "Turmeric", "allopathy_name": "Metformin"}
Server: {"session_id": "uuid"}

Client: WS /ws/{session_id}

Server streams:
  {"type": "pipeline_status", "status": "name_resolution", "message": "Resolving 'Turmeric'..."}
  {"type": "pipeline_status", "status": "iteration_start", "iteration": 1}
  {"type": "pipeline_status", "status": "phase_proposer", "iteration": 1}
  {"type": "llm_call",        "agent": "Planner", "iteration": 1}
  {"type": "agent_thinking",  "agent": "Planner", "iteration": 1, "message": "..."}
  {"type": "tool_call",       "agent": "Planner", "iteration": 1, "message": "Calling identify_substances"}
  {"type": "tool_result",     "agent": "Planner", "iteration": 1, "message": "Tool returned: ..."}
  {"type": "llm_response",    "agent": "Planner", "iteration": 1}
  {"type": "agent_complete",  "agent": "Planner", "iteration": 1}
  ...  (similar for AYUSH, Allopathy, Research, Reasoning agents)
  {"type": "pipeline_status", "status": "phase_scorer", "iteration": 1}
  {"type": "pipeline_status", "status": "gap_identified", "iteration": 1, "gap": "Need phytochemicals..."}
  {"type": "pipeline_status", "status": "iteration_retry", "iteration": 1, "message": "Score=60. Retrying..."}
  {"type": "pipeline_status", "status": "iteration_start", "iteration": 2}
  ...
  {"type": "pipeline_status", "status": "formatting", "message": "Formatting final output..."}
  {"type": "complete", "result": { "status": "Success", "interaction_data": {...} }}
```

---

### Final Output Structure

The `result` object in the `complete` WebSocket event:

```json
{
  "status": "Success",
  "interaction_data": {
    "interaction_key": "curcuma_longa:metformin",
    "ayush_name": "Curcuma longa",
    "allopathy_name": "Metformin",
    "interaction_exists": true,
    "interaction_summary": "Curcumin from Curcuma longa may enhance metformin's glucose-lowering effect...",
    "severity": "MODERATE",
    "severity_score": 51,
    "is_nti": false,
    "scoring_factors": ["CYP3A4 interaction (+10)", "Blood glucose effect (+8)", "Synergistic effect (+7)"],
    "mechanisms": {
      "pharmacokinetic": [
        {"mechanism": "CYP3A4 inhibition by curcumin", "evidence": "https://pubmed.ncbi.nlm.nih.gov/...", "confidence": "HIGH"}
      ],
      "pharmacodynamic": [
        {"mechanism": "Additive glucose-lowering effect", "evidence": "AMPK pathway activation", "confidence": "MODERATE"}
      ]
    },
    "phytochemicals_involved": ["curcumin", "demethoxycurcumin"],
    "clinical_effects": ["Enhanced hypoglycemic effect", "Possible blood glucose reduction"],
    "recommendations": ["Monitor blood glucose levels", "Consult physician before combining"],
    "evidence_quality": "MODERATE",
    "reasoning_chain": [
      {"step": 1, "reasoning": "Curcumin is a known CYP3A4 inhibitor...", "evidence": "PubMed 29518605"},
      {"step": 2, "reasoning": "Metformin activates AMPK; curcumin also activates AMPK...", "evidence": "In vitro studies"}
    ],
    "knowledge_graph": {
      "nodes": [
        {"data": {"id": "ayush", "label": "Curcuma longa", "type": "ayush_plant"}},
        {"data": {"id": "allopathy", "label": "Metformin", "type": "allopathy_drug"}},
        {"data": {"id": "ayush_metabolism", "label": "Curcuma: Metabolism", "type": "admet_property"}},
        {"data": {"id": "allo_metabolism", "label": "Metformin: Metabolism", "type": "admet_property"}}
      ],
      "edges": [
        {"data": {"source": "ayush", "target": "ayush_metabolism", "label": "has Metabolism"}},
        {"data": {"source": "allopathy", "target": "allo_metabolism", "label": "has Metabolism"}}
      ]
    },
    "sources": [
      {"url": "https://pubmed.ncbi.nlm.nih.gov/29518605/", "title": "Curcumin and metformin interaction", "category": "PubMed"},
      {"url": "https://go.drugbank.com/drugs/DB00331", "title": "Metformin — DrugBank", "category": "DrugBank"}
    ],
    "drugbank_url": "https://go.drugbank.com/drugs/DB00331",
    "imppat_url": "https://imppat.iith.ac.in/...",
    "disclaimer": "This tool provides informational analysis only. Consult a licensed healthcare professional before making any medication decisions.",
    "generated_at": "2026-03-04T07:57:00Z"
  }
}
```

---

## Deployment Architecture

```
AWS Account: 667736132441  |  Region: us-east-1

EC2 Instance: i-0dd48f5462906bc03  |  Public IP: 3.210.198.169
  IAM Role: AusadhiEC2Role
    └─ Permissions: bedrock:*, lambda:InvokeFunction, s3:*, logs:PutLogEvents
  Docker Compose:
    ├─ ausadhi-app   (aushadhi-comas:latest, port 8000) ← FastAPI
    └─ ausadhi-nginx (nginx:alpine, port 80)            ← Reverse proxy

Bedrock Agents (us-east-1):
  ├─ Planner:    JRARFMAC40 / TSTALIASID
  ├─ AYUSH:      0SU1BHJ78L / TSTALIASID
  ├─ Allopathy:  CNAZG8LA0H / TSTALIASID
  ├─ Reasoning:  03NGZ4CNF3 / TSTALIASID
  └─ Research:   7DCGAF6N1A / TSTALIASID

Lambda Functions (us-east-1, Python 3.11):
  ├─ ausadhi-planner-tools      (last deployed: 2026-03-04)
  ├─ ausadhi-ayush-data         (last deployed: 2026-03-04)
  ├─ ausadhi-allopathy-data     (last deployed: 2026-03-04)
  ├─ ausadhi-web-search         (last deployed: 2026-03-04)
  ├─ ausadhi-reasoning-tools    (last deployed: 2026-03-04)
  ├─ ausadhi-check-curated-db   (last deployed: 2026-03-04)
  └─ ausadhi-research-tools     (last deployed: 2026-03-03)

S3: ausadhi-mitra-667736132441
  ├─ /reference/name_mappings.json
  ├─ /reference/cyp_enzymes.json
  └─ /reference/nti_drugs.json

DynamoDB: ausadhi-imppat
  └─ Plants: curcuma_longa, glycyrrhiza_glabra, zingiber_officinale,
             hypericum_perforatum, withania_somnifera

RDS PostgreSQL: scm-postgres.c2na6oc62pb7.us-east-1.rds.amazonaws.com:5432/aushadhimitra
  ├─ curated_interactions (response_data JSONB column)
  ├─ interaction_sources
  └─ allopathy_cache
```

### Deployment Scripts

| Script | Purpose |
|--------|---------|
| `scripts/deploy_lambdas.sh` | Package and deploy all Lambda functions |
| `scripts/setup_agents.py` | Create/update 5 Bedrock agents with action groups |
| `scripts/imppat_pipeline.py` | Load IMPPAT CSV data to DynamoDB |

### Rebuilding the EC2 Docker Image

Since the compose file uses `image: aushadhi-comas:latest` (pre-built tag), code changes require a manual rebuild:
```bash
# Via SSM (no SSH needed):
cd /home/ec2-user/aushadhimitra
docker build -t aushadhi-comas:latest .
docker-compose down && docker-compose up -d
```

---

## Known Issues and Current Status

### ✅ Resolved Issues (Previously Documented)

| # | Issue | Status | Resolution |
|---|-------|--------|------------|
| 1 | Bedrock Flow V4 timeout | ✅ Resolved | Replaced by CO-MAS direct orchestration — Flows no longer used |
| 2 | Same error message in all iterations | ✅ Resolved | Planner uses gap-focused prompt in iteration N>1, not initial prompt |
| 3 | Information gaps showing status=Failed in UI | ✅ Resolved | Gap events streamed as `pipeline_status(gap_identified)` separate from errors |
| 4 | Severity showing NONE (0/100) | ✅ Resolved | Added direct `_call_severity_lambda()` fallback; fixed `_score_output` treating `0` as present |
| 5 | DrugBank URL missing from Drug Info tab | ✅ Resolved | `_extract_drugbank_url()` searches all traces + agent response text |
| 6 | Evidence mentions but no clickable links | ✅ Resolved | `TextWithLinks` React component auto-detects URLs in any text field |
| 7 | KG showing "Contains" edges for AYUSH / "Induces" for allopathy | ✅ Resolved | `build_knowledge_graph()` Lambda now generates ADMET nodes; `_transform_graph_to_admet()` ensures prefix labels |
| 8 | KG node and edge labels both named "Metabolism" etc. | ✅ Resolved | ADMET nodes prefixed: "Curcuma: Metabolism"; edges: "has Metabolism" |
| 9 | Sources list empty | ✅ Resolved | `_extract_source_urls()` parses all agent traces and responses |
| 10 | Pipeline not improving across iterations | ✅ Resolved | Pipeline memory passes successes + gaps to Planner each iteration |
| 11 | Severity inconsistent (MINOR vs MAJOR across runs) | ✅ Known / Inherent | LLM non-determinism affects PD boost; CYP-base score is deterministic; acceptable variance |
| 12 | EC2 image not updated on code change | ✅ Process | Must run `docker build` manually after deploying new files — compose uses pre-built `image:` tag |

### ⚠️ Current Implementation Gaps

| # | Gap | Impact | Priority | Recommendation |
|---|-----|--------|----------|----------------|
| 1 | No curated interactions data | Layer 0 instant responses not functional; every query triggers full CO-MAS analysis (30-60s) | 🔴 HIGH | Populate curated_interactions table with 10-15 hero scenarios from requirements (St. John's Wort + Cyclosporine, Turmeric + Warfarin, etc.) |
| 2 | Zero test coverage | No automated validation; regression risk on changes | 🔴 HIGH | Create test suite: Lambda unit tests, agent_service integration tests, API endpoint tests |
| 3 | CloudWatch alarms not configured | No proactive alerting on failures or performance degradation | 🟡 MEDIUM | Configure alarms for: Lambda errors >5%, slow queries >1s, low cache hit rate <20%, high iteration count >2.5 |
| 4 | Custom metrics partially implemented | Limited observability into pipeline performance | 🟡 MEDIUM | Emit all defined metrics: IterationCount, CuratedDBHitRate, ScorerPassRate |
| 5 | Patient interface not implemented | Only professional UI available; no simplified patient experience | 🟢 LOW | Build chat interface with conversational responses and multilingual support (Hindi/English/Hinglish) |
| 6 | No frontend tests | UI regression risk | 🟢 LOW | Add component tests for: DrugInputForm, KnowledgeGraphView, ResultPanel, WebSocket handling |

### 🎯 Production Readiness Checklist

**Before Production Launch:**
- [ ] Populate curated_interactions with 10-15 hero scenarios
- [ ] Implement comprehensive test suite (unit + integration)
- [ ] Configure CloudWatch alarms for critical metrics
- [ ] Load test CO-MAS pipeline (target: handle 10 concurrent requests)
- [ ] Document API endpoints and error codes
- [ ] Create runbook for common operational issues
- [ ] Set up automated backup for PostgreSQL curated_interactions
- [ ] Implement rate limiting on /api/check endpoint
- [ ] Add API authentication/authorization (if needed)
- [ ] Configure SSL/TLS certificates for production domain

**Nice to Have:**
- [ ] Patient-facing chat interface
- [ ] Multilingual support (Hindi, English, Hinglish)
- [ ] Frontend component test suite
- [ ] Performance monitoring dashboard
- [ ] A/B testing framework for severity scoring improvements

---

## Monitoring and Observability

### CloudWatch Logs

**Log Groups**:
- `/aws/lambda/planner_tools` - Planner Agent Lambda logs
- `/aws/lambda/ayush_data` - AYUSH Agent Lambda logs
- `/aws/lambda/allopathy_data` - Allopathy Agent Lambda logs
- `/aws/lambda/reasoning_tools` - Reasoning Agent Lambda logs
- `/aws/lambda/web_search` - Web search Lambda logs
- `/ecs/aushadhimitra-backend` - FastAPI application logs

**Key Metrics to Log**:
- Lambda execution time (target: <3s per function)
- Curated DB hit rate (target: >30% for common queries)
- Web search API response time (target: <2s)
- CO-MAS pipeline execution time (target: <60s)
- Pipeline iteration count (target: 1-2 iterations average)

### CloudWatch Metrics

**Custom Metrics** (Partially Implemented):
```python
# In agent_service.py
cloudwatch.put_metric_data(
    Namespace='AushadhiMitra',
    MetricData=[
        {
            'MetricName': 'IterationCount',
            'Value': iterations,
            'Unit': 'Count'
        },
        {
            'MetricName': 'CuratedDBHitRate',
            'Value': hit_rate,
            'Unit': 'Percent'
        },
        {
            'MetricName': 'ScorerPassRate',
            'Value': pass_rate,
            'Unit': 'Percent'
        }
    ]
)
```

### Alarms (Not Yet Configured)

1. **High Iteration Count**: Alert if >2.5 average iterations per query
2. **Lambda Errors**: Alert if error rate >5% for any Lambda function
3. **Slow Queries**: Alert if PostgreSQL queries >1s
4. **Low Cache Hit Rate**: Alert if curated DB hit rate <20%
5. **API Rate Limits**: Alert if Tavily API returns 429 errors

### Performance Targets

| Component | Target | Acceptable | Critical |
|-----------|--------|------------|----------|
| Layer 0 (Curated) | <500ms | <1s | >2s |
| Full Analysis (Flow) | <30s | <45s | >60s |
| Lambda Execution | <3s | <5s | >10s |
| PostgreSQL Query | <100ms | <500ms | >1s |
| Web Search API | <2s | <5s | >10s |

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

