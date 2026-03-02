# AushadhiMitra V5 — Implementation Plan

## Context

The current 4-agent system works E2E but has gaps: no input validation (missing drug names pass through), no AYUSH DynamoDB validation, no structured agent output, no domain-restricted searches, no data accumulation across retries, inverted DoWhile condition, and no JSON schema validation. This overhaul creates a 5-agent pipeline with structured I/O, domain-restricted search, schema validation, and proper retry logic.

---

## Files Modified/Created

| # | File | Action |
|---|------|--------|
| 1 | `lambda/web_search/handler.py` | Modify: add `_load_domain_config()` + `include_domains`/`domain_preset` params |
| 2 | `lambda/research_tools/handler.py` | **NEW**: Research Agent Lambda (search_research_articles, search_clinical_evidence) |
| 3 | `lambda/planner_tools/handler.py` | Modify: add `validate_ayush_drug`, `generate_execution_plan` |
| 4 | `lambda/reasoning_tools/handler.py` | Modify: add `validate_and_format_output`, fix null guards |
| 5 | `scripts/setup_agents.py` | Modify: add Research Agent, update all agent prompts + function schemas |
| 6 | `scripts/create_flow_v5.py` | **NEW**: Complete Flow V5 rebuild |
| 7 | `backend/app/agent_service.py` | Modify: 5-agent pipeline, parallel execution, data accumulation |
| 8 | `backend/app/config.py` | Modify: add RESEARCH_AGENT_ID/ALIAS |
| 9 | `backend/app/main.py` | Modify: add research to health endpoint |
| 10 | `backend/docker-compose.yml` | Modify: add RESEARCH env vars |
| 11 | `scripts/deploy_lambdas.sh` | Modify: add research Lambda deployment |
| 12 | `reference/search_domains.json` | **NEW**: S3 domain config (local copy for reference) |

---

## Phase 1: Foundation (parallel, no deps)

### 1A. S3 Domain Config — `reference/search_domains.json`

Create local file + upload to `s3://ausadhi-mitra-667736132441/reference/search_domains.json`:

```json
{
  "version": "1.0",
  "presets": {
    "research": {
      "include_domains": [
        "pubmed.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov", "doi.org",
        "springer.com", "sciencedirect.com", "nature.com", "wiley.com",
        "academic.oup.com", "frontiersin.org", "mdpi.com",
        "biorxiv.org", "medrxiv.org", "cochranelibrary.com", "clinicaltrials.gov"
      ]
    },
    "allopathy": {
      "include_domains": [
        "go.drugbank.com", "drugbank.com", "drugs.com", "rxlist.com",
        "fda.gov", "ema.europa.eu", "medlineplus.gov", "uptodate.com",
        "pubmed.ncbi.nlm.nih.gov", "msdmanuals.com"
      ]
    },
    "ayush": {
      "include_domains": [
        "pubmed.ncbi.nlm.nih.gov", "examine.com", "cb.imsc.res.in",
        "ayush.gov.in", "sciencedirect.com", "springer.com",
        "herbalgram.org", "nccih.nih.gov"
      ]
    }
  }
}
```

### 1B. Web Search Domain Restriction — `lambda/web_search/handler.py`

- Add `_load_domain_config()` — loads from S3, cached in module global
- Modify `web_search()` signature: add `include_domains: str = None, domain_preset: str = None`
- In `lambda_handler`: extract `include_domains` and `domain_preset` from params
- Resolve domains: if `domain_preset` given, load from config; if `include_domains` given, parse JSON array or comma-sep
- Add `include_domains` to Tavily API payload

### 1C. New Research Lambda — `lambda/research_tools/handler.py`

Two functions:
- `search_research_articles(query, max_results=5)` — Tavily search with `domain_preset="research"`
- `search_clinical_evidence(ayush_name, allopathy_name, max_results=5)` — Auto-generates 2 targeted queries, deduplicates results

Reuses: `shared/bedrock_utils.py`, same Tavily key from Secrets Manager. Uses `_load_domain_config()` from S3.

---

## Phase 2: Planner Enhancement — `lambda/planner_tools/handler.py`

### New function: `validate_ayush_drug(plant_name)`
- Resolve via `name_mappings.json` (reuse existing `_load_name_mappings()`)
- Check DynamoDB METADATA record exists for resolved scientific name
- Return `{exists: true, scientific_name, dynamodb_key, total_phytochemicals}` or `{exists: false, message, available_plants: [5 random plants]}`

### New function: `generate_execution_plan(ayush_name, allopathy_name, ayush_exists, iteration, failure_feedback)`

**Input validation** — stops immediately if:
- `ayush_name` is empty/missing → `{plan_valid: false, inputs_valid: false, error: "AYUSH drug name is required"}`
- `allopathy_name` is empty/missing → `{plan_valid: false, inputs_valid: false, error: "Allopathy drug name is required"}`
- `ayush_exists` is false → `{plan_valid: false, inputs_valid: false, error: "AYUSH plant not found in database"}`

**Iteration 1 (initial)**: Returns plan for all 3 agents with tasks/queries:
```json
{
  "plan_valid": true,
  "inputs_valid": true,
  "iteration": 1,
  "ayush_name": "Curcuma longa",
  "allopathy_name": "warfarin",
  "agents": {
    "ayush": {"run": true, "tasks": ["Resolve name", "Get phytochemicals", "Search CYP interactions"]},
    "allopathy": {"run": true, "tasks": ["Check cache", "Get CYP metabolism", "Check NTI status"]},
    "research": {"run": true, "tasks": ["Search clinical evidence", "Find PubMed articles"]}
  }
}
```

**Iteration 2+ (retry)**: Planner Agent is re-invoked with failure feedback. It calls `generate_execution_plan` with the feedback text, which determines which agents need re-run. Keyword matching: "ayush"/"phytochemical"/"cyp" → run ayush; "allopathy"/"drug"/"nti" → run allopathy; "research"/"evidence"/"pubmed" → run research. Always runs at least `research` if nothing matches.

Add routing in `lambda_handler` for both new functions.

---

## Phase 3: Reasoning Agent Overhaul — `lambda/reasoning_tools/handler.py`

### 3A. Fix null guards
Add `if interactions is None or not isinstance(interactions, dict): interactions = {}` to:
- `calculate_severity()` (after json.loads)
- `build_knowledge_graph()` (after json.loads)
- `format_professional_response()` (all JSON parse blocks)

### 3B. New function: `validate_and_format_output(reasoning_output_str, iteration)`

Validates Reasoning Agent JSON against Success/Failed schema:
- If `iteration >= 3` and status != "Success" → force Success with partial data + `evidence_quality: "LOW"`
- If "Success": check required fields (`ayush_name`, `allopathy_name`, `severity`, `severity_score`, `knowledge_graph`, `sources`, `disclaimer`). Return `{valid: true/false, missing_fields: [...], output: {...}}`
- If "Failed": check `failure_reason` exists. Return `{valid: true/false, output: {...}}`

### 3C. Reasoning Agent Output Schemas

**Success Schema** (final output to UI):
```json
{
  "status": "Success",
  "interaction_data": {
    "interaction_key": "curcuma_longa#warfarin",
    "ayush_name": "Curcuma longa",
    "allopathy_name": "Warfarin",
    "interaction_exists": true,
    "interaction_summary": "Curcuma longa contains curcumin which inhibits CYP2C9...",
    "severity": "MAJOR",
    "severity_score": 72,
    "is_nti": true,
    "scoring_factors": ["CYP2C9 inhibition (+20)", "NTI drug status (+25)"],
    "mechanisms": {
      "pharmacokinetic": [{"type": "CYP_inhibition", "enzyme": "CYP2C9", "effect": "...", "clinical_significance": "..."}],
      "pharmacodynamic": [{"type": "additive_effect", "description": "...", "clinical_significance": "..."}]
    },
    "phytochemicals_involved": [{"name": "Curcumin", "cyp_effects": {"CYP2C9": "inhibitor"}, "relevance": "..."}],
    "clinical_effects": ["Increased bleeding risk", "Elevated INR"],
    "recommendations": ["Monitor INR closely", "Consider dose adjustment"],
    "evidence_quality": "HIGH|MODERATE|LOW",
    "knowledge_graph": {"nodes": [...], "edges": [...]},
    "sources": [{"url": "...", "title": "...", "snippet": "...", "category": "pubmed"}],
    "disclaimer": "This analysis is AI-generated for informational purposes only. Always consult qualified healthcare professionals before making clinical decisions about drug interactions.",
    "generated_at": "2026-03-02T10:30:00Z"
  }
}
```

**Failed Schema** (needs more data):
```json
{
  "status": "Failed",
  "failure_reason": "Insufficient CYP enzyme interaction data for the AYUSH plant",
  "data_gaps": [
    {
      "category": "ayush_cyp_data",
      "description": "No CYP interaction data found for key phytochemicals",
      "suggested_agent": "ayush",
      "suggested_query": "Search for withanolide CYP3A4 CYP2D6 interaction"
    },
    {
      "category": "clinical_evidence",
      "description": "No clinical case reports found",
      "suggested_agent": "research",
      "suggested_query": "Withania somnifera metformin clinical interaction"
    }
  ],
  "partial_data": {
    "ayush_data_quality": "LOW",
    "allopathy_data_quality": "HIGH",
    "research_data_quality": "NONE"
  },
  "iteration": 1
}
```

---

## Phase 4: Agent Setup — `scripts/setup_agents.py`

### New Research Agent
- Model: Haiku 3.5
- Action group: `ResearchToolsGroup` → Lambda `ausadhi-research-tools`
- Functions: `search_research_articles`, `search_clinical_evidence`
- Prompt: focused on PubMed/academic evidence gathering

### Updated Planner Agent Prompt
Key additions:
1. "You MUST call `identify_substances` first. If either AYUSH or allopathy drug is missing from user input, return error immediately."
2. "After identifying substances, call `validate_ayush_drug` to verify the AYUSH plant exists in DynamoDB."
3. "If AYUSH plant not found, return `{plan_valid: false, inputs_valid: false, error: ...}`"
4. "Call `generate_execution_plan` to produce structured JSON plan."
5. "Your response MUST be valid JSON matching the execution plan schema."
- New function schemas: `validate_ayush_drug`, `generate_execution_plan`
- Update existing `PlannerToolsGroup` to include all 4 functions

### Updated Allopathy Agent Prompt
- Add: "IMPORTANT: Always use `domain_preset: allopathy` when calling web_search"

### Updated Reasoning Agent Prompt (DETAILED)
Full decision-making instructions:

```
You are the Reasoning Agent for AushadhiMitra. You analyze drug interaction data
and produce a structured JSON verdict.

## Your Output Format

You MUST return ONLY valid JSON in one of two formats:

### If sufficient data exists → Status: Success
Return the complete interaction analysis JSON (see schema below).

### If insufficient data → Status: Failed
Return a failure JSON specifying what additional data is needed.

### On FINAL iteration (when told "FINAL ITERATION")
ALWAYS return Status: Success, even with partial data. Set evidence_quality to "LOW".

## How to Determine Drug Interaction

1. CHECK CYP OVERLAP: Do any AYUSH phytochemicals affect the same CYP enzymes
   that metabolize the allopathy drug?
   - If phytochemical INHIBITS a CYP enzyme that metabolizes the drug → interaction EXISTS
   - If phytochemical INDUCES a CYP enzyme that metabolizes the drug → interaction EXISTS

2. CHECK PHARMACODYNAMIC: Do both substances affect the same physiological pathway?
   - Both anticoagulant → additive bleeding risk
   - Both sedative → additive CNS depression
   - Both hypoglycemic → additive hypoglycemia risk

3. CHECK CLINICAL EVIDENCE: Are there published reports of this interaction?

4. DETERMINE SEVERITY using calculate_severity tool

5. BUILD knowledge graph using build_knowledge_graph tool

## Data Sufficiency Rules
- SUFFICIENT: At least 1 CYP overlap OR 1 pharmacodynamic overlap OR clinical evidence
- INSUFFICIENT: No CYP data for AYUSH plant AND no clinical evidence

## Severity Classification
- NONE (0-14): No known interaction pathway
- MINOR (15-34): Theoretical interaction, minimal clinical significance
- MODERATE (35-59): Clinically relevant, monitoring recommended
- MAJOR (60+): Significant risk, avoid or close monitoring required

## Success JSON Schema
{
  "status": "Success",
  "interaction_data": {
    "interaction_key": "<ayush>#<allopathy>",
    "ayush_name": "...",
    "allopathy_name": "...",
    "interaction_exists": true/false,
    "interaction_summary": "2-3 sentence summary",
    "severity": "NONE|MINOR|MODERATE|MAJOR",
    "severity_score": 0-100,
    "is_nti": true/false,
    "scoring_factors": ["factor1 (+score)", ...],
    "mechanisms": {
      "pharmacokinetic": [{"type": "...", "enzyme": "...", "effect": "...", "clinical_significance": "..."}],
      "pharmacodynamic": [{"type": "...", "description": "...", "clinical_significance": "..."}]
    },
    "phytochemicals_involved": [{"name": "...", "cyp_effects": {...}, "relevance": "..."}],
    "clinical_effects": ["effect1", "effect2"],
    "recommendations": ["rec1", "rec2"],
    "evidence_quality": "HIGH|MODERATE|LOW",
    "knowledge_graph": {"nodes": [...], "edges": [...]},
    "sources": [{"url": "...", "title": "...", "snippet": "...", "category": "..."}],
    "disclaimer": "This analysis is AI-generated...",
    "generated_at": "ISO timestamp"
  }
}

## Failed JSON Schema
{
  "status": "Failed",
  "failure_reason": "Human-readable explanation of what's missing",
  "data_gaps": [
    {"category": "...", "description": "...", "suggested_agent": "ayush|allopathy|research", "suggested_query": "..."}
  ],
  "partial_data": {"ayush_data_quality": "HIGH|MODERATE|LOW|NONE", ...},
  "iteration": 1
}
```

### Updated web_search function schema (all agents using WebSearchGroup)
Add parameters: `include_domains` (string, optional), `domain_preset` (string, optional)

---

## Phase 5: Flow V5 — `scripts/create_flow_v5.py`

New file (separate from `create_flow_v4.py`).

### Outer Flow Topology
```
FlowInput → PlannerAgent → PlannerOutputParser → InputValidationCheck
  ├── [invalid] → ErrorOutput (error JSON)
  └── [valid] → AnalysisLoop → FlowOutput
```

### Inner Loop (DoWhile, max 3)
```
LoopInput
  → [AYUSHAgent, AllopathyAgent, ResearchAgent] (parallel fan-out)
  → DataMergePrompt (3 inputs: ayush + allopathy + research)
  → DataAccumulator (InlineCode: append to previous iterations)
  → ReasoningAgent (receives accumulated data + iteration number)
  → SchemaValidator (InlineCode: check JSON schema validity)
  → SchemaFixCheck (Condition)
      ├── [invalid] → SchemaFixPrompt (Prompt: correct JSON) → StatusExtractor
      └── [valid] → StatusExtractor
  → StatusExtractor (InlineCode: extract status field)
  → LoopController (continue while status == "Failed")
```

### Key InlineCode Nodes

**PlannerOutputParser**: Extracts JSON from Planner response, outputs `{inputs_valid: "true"/"false", plan_json: "...", error: "..."}`

**DataAccumulator**: `accumulated = previous + "\n=== ITERATION DATA ===\n" + current`

**SchemaValidator**: Parses Reasoning JSON, checks required fields for Success/Failed. Outputs `{schema_valid: "true"/"false", output: "...", fix_instructions: "..."}`

**StatusExtractor**: Extracts `status` field from JSON. Default: `"Failed"` (FIXED from V4's `"PASSED"`)

**SchemaFixPrompt**: "Fix this invalid JSON: {{invalid_json}}. Issues: {{fix_instructions}}. Return ONLY corrected JSON."

### Critical Fix: DoWhile Condition
- V4 bug: `validationStatus == "PASSED"` (continues when passed — wrong!)
- V5 fix: `status == "Failed"` (continues while failed — correct!)

---

## Phase 6: Backend Pipeline — `backend/app/agent_service.py`

### Add Research Agent
```python
AGENTS["research"] = {"id": RESEARCH_AGENT_ID, "alias": RESEARCH_AGENT_ALIAS, "label": "Research Agent"}
NODE_TO_AGENT["ResearchAgent"] = "research"
# + other new node mappings
```

### Rewrite `run_interaction_pipeline()`

5-step pipeline with data accumulation:

1. **Planner** → validate inputs + plan. Short-circuit on error (missing names, AYUSH not found)
2. **Data Collection** (parallel via threading) → AYUSH + Allopathy + Research agents, routed by plan JSON
3. **Reasoning** → receives accumulated data, returns structured JSON
4. **Schema Validation** → check JSON validity, if invalid attempt correction
5. **Retry Loop** → if Failed, **re-invoke Planner Agent** with failure feedback text → Planner generates new targeted plan → selective agent re-run based on Planner's JSON output

New helpers: `_parse_planner_output()`, `_parse_reasoning_output()`

### Data Accumulation
```python
accumulated_ayush += "\n--- ADDITIONAL DATA ---\n" + new_ayush_data
accumulated_allopathy += "\n--- ADDITIONAL DATA ---\n" + new_allopathy_data
accumulated_research += "\n--- ADDITIONAL DATA ---\n" + new_research_data
```

---

## Phase 7: Config & Deployment

### `backend/app/config.py`
Add `RESEARCH_AGENT_ID` and `RESEARCH_AGENT_ALIAS` from env vars

### `backend/app/main.py`
Add `research: RESEARCH_AGENT_ID` to health endpoint agents dict

### `backend/docker-compose.yml`
Add `RESEARCH_AGENT_ID` and `RESEARCH_AGENT_ALIAS` env vars

### `scripts/deploy_lambdas.sh`
Add `ausadhi-research-tools` Lambda (timeout 60s, 256MB, same env vars as web_search)

---

## Execution Order

```
1. Phase 1A (S3 domain config)     ─┐
2. Phase 1B (web_search domains)    ├── Parallel foundation
3. Phase 1C (research Lambda)      ─┘
4. Phase 2 (planner_tools)
5. Phase 3 (reasoning_tools)
6. Phase 4 (setup_agents.py)
7. Phase 7 deploy_lambdas.sh
8. Phase 7 config.py + main.py + docker-compose.yml
9. Phase 6 (agent_service.py pipeline)
10. Phase 5 (create_flow_v5.py)
```

---

## Verification

1. **Missing drug name**: Send empty ayush_name → Planner returns error, flow stops
2. **AYUSH not found**: `validate_ayush_drug("random_herb")` → `{exists: false}` → flow stops with error
3. **Domain restriction**: web_search with `domain_preset=allopathy` → verify Tavily payload has `include_domains`
4. **Research Lambda**: search_research_articles → results from PubMed/academic only
5. **Reasoning Success**: turmeric + warfarin → `{status: "Success", interaction_data: {...}}`
6. **Reasoning Failed**: obscure herb + drug → `{status: "Failed", data_gaps: [...]}`
7. **Schema validation**: Malformed Reasoning JSON → SchemaFixPrompt corrects it
8. **Data accumulation**: Force retry → verify `--- ADDITIONAL DATA ---` markers
9. **Final iteration forced Success**: After 3 iterations → always returns Success
10. **E2E pipeline**: WebSocket test → all 5 agents invoked, structured JSON response
