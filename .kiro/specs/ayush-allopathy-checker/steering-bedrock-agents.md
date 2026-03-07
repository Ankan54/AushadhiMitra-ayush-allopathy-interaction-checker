# Bedrock Agents Steering File - AushadhiMitra

## Purpose
AWS Bedrock multi-agent CO-MAS (Cooperative Multi-Agent System) architecture with FastAPI orchestration for self-improving drug interaction analysis.

## Architecture Overview

### CO-MAS Pipeline (Orchestrated by FastAPI)
```
FastAPI Backend (agent_service.py)
  │
  ├─ Layer 0: lookup_curated() → PostgreSQL
  │     └─ Hit: return instantly (<500ms)
  │
  └─ CO-MAS Pipeline (max 3 iterations)
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
```

## Agent Specifications

### 1. Planner Agent
**Model**: Claude 3 Sonnet  
**Agent ID**: JRARFMAC40 / Alias: TSTALIASID  
**Role**: Entry point, substance identification, curated DB check, execution planning  
**Action Group**: `planner_tools`

**Instructions**:
```
You are the Planner Agent for AushadhiMitra drug interaction checker.

Your responsibilities:
1. Extract AYUSH and allopathic medicine names from user input using identify_substances()
2. Check the curated interaction database using check_curated_db()
3. If curated match found: Signal to return the pre-computed response immediately
4. If no match: Create a focused execution plan for the current iteration

ITERATION-AWARE PLANNING:
- Iteration 1: Create initial comprehensive plan
- Iteration 2+: Focus ONLY on remaining gaps from Scorer feedback
- Use pipeline memory to avoid re-fetching known data

Always normalize medicine names before checking the curated database.
Use the confidence score from identify_substances() to request clarification if needed.
```

**Lambda Functions**:
- `identify_substances(user_input: str)`
- `check_curated_db(ayush_name: str, allopathy_name: str)`
- `create_execution_plan(substances: dict, gaps: list, iteration: int)`

### 2. AYUSH Collaborator Agent
**Model**: Claude 3 Haiku  
**Agent ID**: 0SU1BHJ78L / Alias: TSTALIASID  
**Role**: Gather AYUSH phytochemical and CYP data  
**Action Groups**: `ayush_data`, `web_search`

**Instructions**:
```
You are the AYUSH Collaborator Agent specializing in traditional Indian medicine data.

Your responsibilities:
1. Normalize AYUSH medicine names to scientific names using ayush_name_resolver()
2. Retrieve phytochemical data from IMPPAT database using imppat_lookup()
3. Search for CYP450 interaction data using search_cyp_interactions()
4. Report data completeness and any gaps found

Focus on:
- Key phytochemicals (active ingredients)
- CYP450 enzyme effects (inhibitors, inducers, substrates)
- ADMET properties
- Plant part used (leaf, root, seed, etc.)

Always cite IMPPAT as the source for phytochemical data.
If data is incomplete, explicitly state what is missing.
```

**Lambda Functions**:
- `ayush_name_resolver(common_name: str)`
- `imppat_lookup(scientific_name: str)`
- `search_cyp_interactions(plant_name: str)`
- `web_search(query: str, max_results: int)`

### 3. Allopathy Collaborator Agent
**Model**: Claude 3 Haiku  
**Agent ID**: CNAZG8LA0H / Alias: TSTALIASID  
**Role**: Gather allopathic drug CYP metabolism data  
**Action Groups**: `allopathy_data`, `web_search`

**Instructions**:
```
You are the Allopathy Collaborator Agent specializing in pharmaceutical drug data.

Your responsibilities:
1. Perform web search for DrugBank CYP metabolism data
2. Check if drug is on Narrow Therapeutic Index (NTI) list using check_nti_status()
3. Extract DrugBank URL and include in response

Focus on:
- Generic drug name (if brand name provided)
- CYP450 substrates (which enzymes metabolize this drug)
- CYP450 inhibitors/inducers (does this drug affect enzymes)
- Narrow Therapeutic Index status
- Primary metabolism pathway
- ADMET properties

Always prioritize DrugBank and FDA sources.
Flag NTI drugs as high-priority for severity assessment.
```

**Lambda Functions**:
- `allopathy_drug_lookup(drug_name: str)`
- `check_nti_status(drug_name: str)`
- `web_search(query: str, max_results: int)`

### 4. Research Collaborator Agent
**Model**: Claude 3 Haiku  
**Agent ID**: 7DCGAF6N1A / Alias: TSTALIASID  
**Role**: Search PubMed and clinical evidence sources  
**Action Groups**: `web_search`, `research_tools`

**Instructions**:
```
You are the Research Agent specializing in clinical evidence gathering.

Your responsibilities:
1. Search PubMed for clinical interaction evidence
2. Search clinical trial databases
3. Extract and categorize source URLs
4. Summarize clinical significance

Focus on:
- Clinical case reports
- Randomized controlled trials
- Systematic reviews
- Pharmacokinetic studies

Always cite PubMed IDs when available.
Categorize evidence quality (clinical_study, case_report, in_vitro).
```

**Lambda Functions**:
- `web_search(query: str, max_results: int)`
- `search_clinical_evidence(ayush_name: str, allopathy_name: str)`

### 5. Reasoning Collaborator Agent
**Model**: Claude 3 Sonnet  
**Agent ID**: 03NGZ4CNF3 / Alias: TSTALIASID  
**Role**: Synthesize, build KG, score severity, format output  
**Action Groups**: `reasoning_tools`, `web_search`

**Instructions**:
```
You are the Reasoning Collaborator Agent responsible for interaction analysis.

Your responsibilities:
1. Build ADMET-focused knowledge graph using build_knowledge_graph()
2. Identify CYP enzyme overlap nodes (enzymes affected by both medicines)
3. Search for additional clinical evidence if needed using web_search()
4. Calculate severity using calculate_severity()
5. Detect conflicts in evidence sources
6. Format final structured output

Analysis Rules:
- ONLY use provided evidence from Lambda functions and Proposer agents
- Do NOT use your internal knowledge about drugs
- Explicitly report conflicts between sources
- Cite every claim with source URL
- Consider both CYP pathway and pharmacodynamic overlaps

Knowledge Graph Requirements:
- Include ADMET property nodes for BOTH drugs
- Label ADMET nodes with drug-name prefix (e.g., "Curcuma: Metabolism")
- Label edges with "has <property>" format
- Highlight CYP enzyme overlap nodes

For professional users: Provide full structured JSON with all fields
For patient users: Generate simple 4-5 sentence response in user's language
```

**Lambda Functions**:
- `build_knowledge_graph(ayush_name: str, allopathy_name: str, interactions_data_str: str)`
- `calculate_severity(interactions_data_str: str, allopathy_name: str)`
- `web_search(query: str, max_results: int)`

**Output Format**:
```json
{
  "ayush_name": "...",
  "allopathy_name": "...",
  "severity": "MODERATE",
  "severity_score": 51,
  "mechanisms": {...},
  "phytochemicals_involved": [...],
  "reasoning_chain": [...],
  "interaction_summary": "...",
  "knowledge_graph": {...}
}
```

## CO-MAS Pipeline Orchestration

### FastAPI Orchestrator (`agent_service.py`)

**Key Functions**:
- `run_comas_pipeline()`: Main orchestrator for up to 3 iterations
- `_invoke_planner()`: Invokes Planner with iteration-aware prompts
- `_invoke_proposers()`: Runs AYUSH, Allopathy, Research in parallel
- `_invoke_reasoning()`: Invokes Reasoning (Evaluator) Agent
- `_score_output()`: Deterministic scorer (0-100 scale)
- `_boost_severity_from_evidence()`: Adds PD boost to CYP-based severity
- `_format_final_json()`: Assembles final response
- `_extract_drugbank_url()`: Searches traces for DrugBank URL
- `_extract_source_urls()`: Parses all URLs from traces
- `_transform_graph_to_admet()`: Post-processes KG labels

### Scorer Dimensions (0-100 scale)
| Dimension | Points | Pass Condition |
|-----------|--------|----------------|
| ayush_name present | 10 | Not None/empty |
| allopathy_name present | 10 | Not None/empty |
| Severity (not NONE, score > 0) | 20 | severity != "NONE" AND severity_score > 0 |
| Knowledge graph (≥ 3 nodes) | 10 | len(nodes) >= 3 |
| Sources (≥ 2) | 10 | len(sources) >= 2 |
| Mechanisms (PK or PD) | 10 | pk or pd non-empty |
| Reasoning chain (≥ 2 steps) | 10 | len(reasoning_chain) >= 2 |
| Phytochemicals (≥ 1) | 10 | len(phytochemicals) >= 1 |
| Interaction summary (≥ 80 chars) | 10 | len(summary) >= 80 |

**Pass condition**: `(score >= 60 and has_substance) or iteration >= 3`

### Pipeline Memory Structure
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

## Deployment Scripts

### `scripts/setup_agents.py`
- Creates/updates 5 Bedrock agents (Planner, AYUSH, Allopathy, Research, Reasoning)
- Configures action groups with Lambda ARNs
- Sets agent instructions and model selection
- Generates agent aliases (TSTALIASID)

## Current Deployment Status

**All 5 agents deployed and operational:**
- Planner: JRARFMAC40 / TSTALIASID (Claude 3 Sonnet)
- AYUSH: 0SU1BHJ78L / TSTALIASID (Claude 3 Haiku)
- Allopathy: CNAZG8LA0H / TSTALIASID (Claude 3 Haiku)
- Research: 7DCGAF6N1A / TSTALIASID (Claude 3 Haiku)
- Reasoning: 03NGZ4CNF3 / TSTALIASID (Claude 3 Sonnet)

## Known Issues & Current Status

### ✅ Resolved Issues
1. **Bedrock Flow V4 timeout** → Replaced with CO-MAS direct orchestration
2. **Same error message in all iterations** → Planner uses gap-focused prompt in iteration N>1
3. **Information gaps showing status=Failed** → Gap events streamed as pipeline_status(gap_identified)
4. **Severity showing NONE (0/100)** → Added _call_severity_lambda() fallback
5. **DrugBank URL missing** → _extract_drugbank_url() searches all traces
6. **Sources list empty** → _extract_source_urls() parses all traces
7. **Pipeline not improving** → Pipeline memory passes successes + gaps to Planner

### ⚠️ Current Gaps
1. **No test coverage** → Zero unit/integration tests (HIGH PRIORITY)
2. **Curated DB empty** → Layer 0 not functional (HIGH PRIORITY)
3. **CloudWatch alarms not configured** → No proactive alerting (MEDIUM)
4. **Patient interface not implemented** → Only professional UI exists (LOW)

## Testing Priorities

1. **Layer 0 Fast Path**: Curated DB hit → instant response (<500ms) - BLOCKED: no curated data
2. **CO-MAS Iterations**: Pipeline executes 1-3 iterations based on Scorer feedback
3. **Max Iterations**: Pipeline stops after 3 iterations even if score < 60
4. **Pipeline Memory**: Successes passed to Planner in iteration N+1
5. **Grounded Reasoning**: Agent responses cite only Lambda-provided sources
6. **Null Handling**: Agents handle missing data gracefully
7. **WebSocket Streaming**: Trace events stream correctly during pipeline execution
8. **Parallel Proposers**: AYUSH, Allopathy, Research run concurrently

## Agent Model Selection Rationale

| Agent | Model | Reasoning |
|-------|-------|-----------|
| Planner | Claude 3 Sonnet | Needs strong reasoning for substance identification and iteration planning |
| AYUSH | Claude 3 Haiku | Data gathering task, cost-effective |
| Allopathy | Claude 3 Haiku | Data gathering task, cost-effective |
| Research | Claude 3 Haiku | Data gathering task, cost-effective |
| Reasoning | Claude 3 Sonnet | Complex analysis, synthesis, conflict resolution |

## Environment Variables
```
AWS_REGION=us-east-1
PLANNER_AGENT_ID=JRARFMAC40
PLANNER_AGENT_ALIAS=TSTALIASID
AYUSH_AGENT_ID=0SU1BHJ78L
AYUSH_AGENT_ALIAS=TSTALIASID
ALLOPATHY_AGENT_ID=CNAZG8LA0H
ALLOPATHY_AGENT_ALIAS=TSTALIASID
RESEARCH_AGENT_ID=7DCGAF6N1A
RESEARCH_AGENT_ALIAS=TSTALIASID
REASONING_AGENT_ID=03NGZ4CNF3
REASONING_AGENT_ALIAS=TSTALIASID
MAX_COMAS_ITERATIONS=3
```
