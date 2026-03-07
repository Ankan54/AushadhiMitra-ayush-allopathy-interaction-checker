# AushadhiMitra

**AI-powered drug interaction checker between AYUSH (traditional Indian medicine) and allopathic drugs.**

AushadhiMitra uses a Cooperative Multi-Agent System (CO-MAS) built on Amazon Bedrock to analyze potential interactions between Ayurvedic/traditional Indian herbal medicines and conventional pharmaceutical drugs. The system streams a live analysis trace to the user via WebSocket while running up to 5 specialized AI agents in parallel.

---

## Table of Contents

- [What It Does](#what-it-does)
- [How It Works](#how-it-works)
  - [CO-MAS Pipeline](#co-mas-pipeline)
  - [Agent Roles](#agent-roles)
  - [WebSocket Streaming](#websocket-streaming)
  - [Severity Scoring](#severity-scoring)
- [Architecture](#architecture)
  - [Infrastructure Overview](#infrastructure-overview)
  - [Data Sources](#data-sources)
  - [Database Schema](#database-schema)
- [Project Structure](#project-structure)
- [Setup & Deployment](#setup--deployment)
  - [Prerequisites](#prerequisites)
  - [1. AWS Infrastructure](#1-aws-infrastructure)
  - [2. Environment Variables](#2-environment-variables)
  - [3. Deploy Lambda Functions](#3-deploy-lambda-functions)
  - [4. Configure Bedrock Agents](#4-configure-bedrock-agents)
  - [5. Run the Backend](#5-run-the-backend)
- [API Reference](#api-reference)
- [Author](#author)

---

## What It Does

AYUSH medicine (Ayurveda, Yoga & Naturopathy, Unani, Siddha, Homeopathy) is widely used alongside allopathic drugs in India, yet drug interaction data for these combinations is scarce and scattered. AushadhiMitra bridges this gap by:

- Resolving plant common names / Hindi names to scientific names via IMPPAT
- Fetching phytochemical CYP enzyme data for AYUSH herbs from DynamoDB
- Looking up allopathic drug metabolism pathways and NTI (Narrow Therapeutic Index) status
- Searching clinical and pharmacological literature via Tavily web search
- Running a multi-iteration reasoning loop to score evidence completeness
- Producing a structured JSON result with severity classification, a knowledge graph, and cited sources
- Caching analyzed interactions in PostgreSQL to serve repeat queries instantly

---

## How It Works

### CO-MAS Pipeline

Every interaction check runs through a **Cooperative Multi-Agent System** pipeline with up to 3 refinement iterations:

```
[POST /api/check]
       │
       ▼
Layer 0: Curated DB lookup (PostgreSQL)
  ├─ HIT  → return cached result instantly via WebSocket
  └─ MISS → start background CO-MAS pipeline thread
               │
               ▼
          ┌─────────────────────────────────────────────┐
          │  Iteration 1..3 (DoWhile loop)             │
          │                                             │
          │  1. PLANNER  — Generate execution plan      │
          │  2. PROPOSER — Parallel agent research:     │
          │     ├─ AYUSH Agent  (phytochemicals/CYP)   │
          │     ├─ Allopathy Agent (drug metabolism)   │
          │     └─ Research Agent (clinical evidence)  │
          │  3. EVALUATOR — Reasoning Agent synthesizes │
          │  4. SCORER   — Deterministic quality check  │
          │     ├─ PASS (score ≥ 60) → FORMAT & save   │
          │     └─ FAIL → identify gaps, loop back     │
          └─────────────────────────────────────────────┘
               │
               ▼
          [WebSocket /ws/{session_id}]
          Streams: status → thinking → tool_call → tool_result
                   → agent_complete → complete
```

### Agent Roles

| Agent | Model | Purpose | Lambda Action Group |
|-------|-------|---------|---------------------|
| **Planner** | Claude 3 Sonnet | Validates inputs, checks curated DB, generates per-iteration execution plan | `planner_tools` |
| **AYUSH** | Claude 3 Haiku | Resolves plant names, retrieves IMPPAT phytochemicals and CYP interactions from DynamoDB | `ayush_data` |
| **Allopathy** | Claude 3 Haiku | Looks up drug CYP metabolism and NTI status from PostgreSQL cache | `allopathy_data` |
| **Research** | Claude 3 Haiku | Domain-restricted web search via Tavily API for PubMed/clinical evidence | `web_search` |
| **Reasoning** | Claude 3 Sonnet | Synthesizes findings into interaction analysis, builds knowledge graph, scores severity | `reasoning_tools` |

### WebSocket Streaming

The frontend connects to `/ws/{session_id}` after POSTing to `/api/check`. Events emitted:

| Event Type | Description |
|------------|-------------|
| `pipeline_status` | Pipeline phase transitions (name_resolution, iteration_start, gap_identified, …) |
| `agent_thinking` | Agent reasoning step |
| `llm_call` | LLM invocation with prompt preview |
| `llm_response` | Token counts from model response |
| `tool_call` | Lambda function called with parameters |
| `tool_result` | Lambda function returned result |
| `agent_complete` | Individual agent finished |
| `complete` | Final interaction result (or cached hit) |
| `error` | Pipeline or validation failure |

### Severity Scoring

Severity is calculated deterministically by the `calculate_severity` Lambda, not by the LLM:

| Factor | Score Added |
|--------|-------------|
| CYP enzyme overlap (per enzyme) | +5–15 (weighted by enzyme clinical importance) |
| Strong CYP inhibitor | weight × 2 |
| Strong CYP inducer | weight × 1.5 |
| NTI drug (Warfarin, Digoxin, Cyclosporine, etc.) | +25 |

| Threshold | Severity |
|-----------|----------|
| 0–14 | NONE |
| 15–34 | MINOR |
| 35–59 | MODERATE |
| 60+ | MAJOR |

---

## Architecture

### Infrastructure Overview

```
┌─────────────────────────────────────────────────────────────┐
│  EC2 Instance (us-east-1)                                   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Docker Compose                                      │   │
│  │  ┌──────────┐    ┌──────────────────────────────┐  │   │
│  │  │  Nginx   │───▶│  FastAPI + Uvicorn  (8000)   │  │   │
│  │  │  (80)    │    │  app/main.py                 │  │   │
│  │  └──────────┘    └──────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
         │                         │
         │ Bedrock Agent Invoke     │ psycopg2
         ▼                         ▼
┌──────────────────┐    ┌─────────────────────────────────┐
│  Amazon Bedrock  │    │  RDS PostgreSQL (us-east-1)     │
│  5 Agents        │    │  DB: aushadhimitra               │
│  Claude 3 Haiku  │    │  curated_interactions           │
│  Claude 3 Sonnet │    │  allopathy_cache                │
└──────────────────┘    │  interaction_sources            │
         │               └─────────────────────────────────┘
         │ Lambda Invoke
         ▼
┌──────────────────────────────────────────────────────────────┐
│  Lambda Functions                                            │
│  ┌──────────────────┐  ┌────────────────┐  ┌─────────────┐ │
│  │ ausadhi-planner- │  │ ausadhi-ayush- │  │ ausadhi-    │ │
│  │ tools            │  │ data           │  │ allopathy-  │ │
│  └──────────────────┘  └────────────────┘  │ data        │ │
│  ┌──────────────────┐  ┌────────────────┐  └─────────────┘ │
│  │ ausadhi-web-     │  │ ausadhi-       │                   │
│  │ search           │  │ reasoning-     │                   │
│  └──────────────────┘  │ tools          │                   │
│                        └────────────────┘                   │
└──────────────────────────────────────────────────────────────┘
         │                         │
         │ DynamoDB                │ S3
         ▼                         ▼
┌──────────────────┐    ┌─────────────────────────────────┐
│  ausadhi-imppat  │    │  ausadhi-mitra-667736132441     │
│  IMPPAT plant /  │    │  reference/name_mappings.json   │
│  phytochemical   │    │  reference/cyp_enzymes.json     │
│  data            │    │  reference/nti_drugs.json       │
└──────────────────┘    │  reference/search_domains.json  │
                        └─────────────────────────────────┘
```

### Data Sources

| Source | Access | Content |
|--------|--------|---------|
| **IMPPAT** (Indian Medicinal Plants, Phytochemistry And Therapeutics) | DynamoDB (`ausadhi-imppat`) | Phytochemicals, CYP interactions, ADMET properties |
| **DrugBank / RxList** | Web search (Tavily) | Allopathy drug metabolism, CYP substrates |
| **PubMed / Clinical Trials** | Web search (Tavily) | Clinical evidence for herb-drug interactions |
| **NTI Drug Reference** | S3 JSON | Narrow Therapeutic Index drugs requiring elevated severity |
| **CYP Enzyme Reference** | S3 JSON | CYP enzyme weights and severity thresholds |

### Database Schema

```sql
-- Curated interaction cache
curated_interactions (
    interaction_key     TEXT PRIMARY KEY,     -- "{ayush}#{allopathy}"
    ayush_name          TEXT,
    allopathy_name      TEXT,
    severity            TEXT,                 -- NONE/MINOR/MODERATE/MAJOR
    severity_score      INTEGER,
    response_data       JSONB,                -- full interaction JSON
    knowledge_graph     JSONB,                -- Cytoscape.js graph data
    created_at          TIMESTAMPTZ,
    updated_at          TIMESTAMPTZ
)

-- Source citations
interaction_sources (
    source_id           SERIAL PRIMARY KEY,
    interaction_key     TEXT REFERENCES curated_interactions,
    url                 TEXT,
    title               TEXT,
    snippet             TEXT,
    category            TEXT,                 -- pubmed/clinical_trial/etc.
    relevance_score     FLOAT
)

-- Allopathy drug data cache (7-day TTL)
allopathy_cache (
    drug_name           TEXT PRIMARY KEY,
    generic_name        TEXT,
    drug_data           JSONB,               -- CYP metabolism info
    sources             JSONB,
    cached_at           TIMESTAMPTZ,
    expires_at          TIMESTAMPTZ
)
```

---

## Project Structure

```
.
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI REST + WebSocket endpoints
│   │   ├── agent_service.py     # CO-MAS pipeline orchestrator
│   │   ├── config.py            # Agent IDs, aliases, DB config
│   │   ├── db.py                # PostgreSQL connection pool
│   │   └── models.py            # Pydantic request/response models
│   ├── static/                  # Built SPA frontend (served by FastAPI)
│   ├── Dockerfile
│   ├── nginx.conf
│   └── requirements.txt
│
├── lambda/
│   ├── planner_tools/           # identify_substances, check_curated, generate_plan
│   ├── ayush_data/              # ayush_name_resolver, imppat_lookup, search_cyp
│   ├── allopathy_data/          # allopathy_cache_lookup/save, check_nti_status
│   ├── reasoning_tools/         # build_knowledge_graph, calculate_severity, validate
│   ├── web_search/              # Tavily web search with domain presets
│   ├── check_curated_db/        # Direct DB interaction checker
│   └── shared/
│       ├── bedrock_utils.py     # Bedrock agent response format helper
│       └── db_utils.py          # PostgreSQL connection helper for Lambdas
│
├── scripts/
│   ├── setup_agents.py          # Create/update Bedrock agents
│   ├── create_flow_v4.py        # Build Bedrock Flow V4 with DoWhile loop
│   ├── deploy_lambdas.sh        # Package and deploy all Lambda functions
│   ├── imppat_pipeline.py       # Load IMPPAT phytochemical data to DynamoDB
│   └── run_check_streaming.py   # Local test script for the pipeline
│
└── data/
    └── reference/
        ├── cyp_enzymes.json     # CYP enzyme severity weights
        └── nti_drugs.json       # Narrow Therapeutic Index drug list
```

---

## Setup & Deployment

### Prerequisites

- AWS account with access to: Bedrock (Claude 3 Haiku + Sonnet), Lambda, RDS PostgreSQL, DynamoDB, S3, Secrets Manager
- AWS CLI configured (`aws configure`)
- Docker and Docker Compose
- Python 3.12
- Tavily API key (for web search)

### 1. AWS Infrastructure

#### S3 Bucket

```bash
aws s3 mb s3://ausadhi-mitra-<ACCOUNT_ID> --region us-east-1

# Upload reference data
aws s3 cp data/reference/cyp_enzymes.json s3://ausadhi-mitra-<ACCOUNT_ID>/reference/
aws s3 cp data/reference/nti_drugs.json   s3://ausadhi-mitra-<ACCOUNT_ID>/reference/
# Also upload name_mappings.json and search_domains.json if available
```

#### RDS PostgreSQL

Create a PostgreSQL 14+ instance in `us-east-1`. Then run:

```sql
CREATE DATABASE aushadhimitra;

CREATE TABLE curated_interactions (
    interaction_key TEXT PRIMARY KEY,
    ayush_name TEXT,
    allopathy_name TEXT,
    severity TEXT,
    severity_score INTEGER,
    response_data JSONB,
    knowledge_graph JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE interaction_sources (
    source_id SERIAL PRIMARY KEY,
    interaction_key TEXT REFERENCES curated_interactions(interaction_key),
    url TEXT,
    title TEXT,
    snippet TEXT,
    category TEXT,
    relevance_score FLOAT
);

CREATE TABLE allopathy_cache (
    drug_name TEXT PRIMARY KEY,
    generic_name TEXT,
    drug_data JSONB,
    sources JSONB,
    cached_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);
```

#### DynamoDB

```bash
aws dynamodb create-table \
  --table-name ausadhi-imppat \
  --attribute-definitions \
      AttributeName=plant_name,AttributeType=S \
      AttributeName=record_key,AttributeType=S \
  --key-schema \
      AttributeName=plant_name,KeyType=HASH \
      AttributeName=record_key,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1
```

Load IMPPAT data:

```bash
python scripts/imppat_pipeline.py
```

#### Secrets Manager (Tavily API Key)

```bash
aws secretsmanager create-secret \
  --name ausadhi-mitra/tavily-api-key \
  --secret-string '{"api_key":"tvly-YOUR_KEY_HERE"}' \
  --region us-east-1
```

### 2. Environment Variables

Create `backend/.env` (or set on EC2 / ECS):

```env
AWS_REGION=us-east-1

# Bedrock Agent IDs (from setup_agents.py output)
PLANNER_AGENT_ID=JRARFMAC40
PLANNER_AGENT_ALIAS=TSTALIASID
AYUSH_AGENT_ID=0SU1BHJ78L
AYUSH_AGENT_ALIAS=TSTALIASID
ALLOPATHY_AGENT_ID=CNAZG8LA0H
ALLOPATHY_AGENT_ALIAS=TSTALIASID
REASONING_AGENT_ID=03NGZ4CNF3
REASONING_AGENT_ALIAS=TSTALIASID
RESEARCH_AGENT_ID=7DCGAF6N1A
RESEARCH_AGENT_ALIAS=TSTALIASID

# S3
S3_BUCKET=ausadhi-mitra-667736132441

# PostgreSQL
DB_HOST=your-rds-endpoint.us-east-1.rds.amazonaws.com
DB_PORT=5432
DB_NAME=aushadhimitra
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_SSL=require

# Pipeline tuning (optional)
MAX_COMAS_ITERATIONS=3
AGENT_INVOKE_MAX_RETRIES=2
AGENT_RETRY_BASE_WAIT=3
```

### 3. Deploy Lambda Functions

```bash
export DB_PASSWORD=your_db_password
export AWS_REGION=us-east-1

bash scripts/deploy_lambdas.sh
```

This packages and deploys 8 Lambda functions with Bedrock invoke permissions. A `psycopg2` Lambda Layer must already exist (see `PSYCOPG2_LAYER_ARN` in the script).

### 4. Configure Bedrock Agents

```bash
# Create all 5 Bedrock agents with their action groups
python scripts/setup_agents.py
```

This creates the Planner, AYUSH, Allopathy, Research, and Reasoning agents in Amazon Bedrock and attaches the corresponding Lambda action groups.

### 5. Run the Backend

#### With Docker (recommended)

```bash
cd backend
docker-compose up --build
```

The API will be available at `http://localhost:80` (Nginx → Uvicorn on 8000).

#### Without Docker (development)

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### Test the pipeline

```bash
python scripts/run_check_streaming.py
```

---

## API Reference

### `GET /api/health`
Returns agent IDs and database name.

### `GET /api/interactions`
Lists the 20 most recent curated interactions from PostgreSQL.

### `POST /api/check`
Start an interaction analysis.

**Request body:**
```json
{
  "ayush_name": "Curcuma longa",
  "allopathy_name": "warfarin"
}
```

**Response:**
```json
{ "session_id": "550e8400-e29b-41d4-a716-446655440000" }
```

### `WebSocket /ws/{session_id}`
Connect after POSTing to `/api/check`. Receives streaming events until a `complete` or `error` message.

**Final `complete` payload:**
```json
{
  "type": "complete",
  "cached": false,
  "result": {
    "interaction_key": "curcuma longa#warfarin",
    "ayush_name": "Curcuma longa",
    "allopathy_name": "warfarin",
    "severity": "MAJOR",
    "severity_score": 72,
    "interaction_summary": "...",
    "mechanisms": { "pharmacokinetic": [...], "pharmacodynamic": [...] },
    "phytochemicals_involved": [...],
    "clinical_effects": [...],
    "recommendations": [...],
    "knowledge_graph": { "nodes": [...], "edges": [...] },
    "sources": [...],
    "reasoning_chain": [...],
    "disclaimer": "..."
  }
}
```

---

## Author

**Ankan** — [github.com/Ankan54](https://github.com/Ankan54)