# Lambda Functions Steering File - AushadhiMitra

## Purpose
AWS Lambda functions serving as Bedrock Agent Action Groups. All deterministic business logic is implemented in Lambda to keep agents focused on orchestration and reasoning.

## Architecture
- **12 Lambda functions** organized into 5 action groups
- **Python 3.12** runtime
- **Region**: us-east-1
- **Shared utilities**: `shared/bedrock_utils.py`, `shared/db_utils.py`

## Action Groups

### 1. planner_tools (Planner Agent)
**File**: `lambda/planner_tools/handler.py`

#### `identify_substances(user_input: str)`
- Extract AYUSH and allopathic medicine names from natural language
- Use local `name_mappings.json` for common name normalization
- Return: `{ayush_medicine, allopathy_drug, confidence}`

#### `check_curated_interaction(ayush_name: str, allopathy_name: str)`
- Query PostgreSQL `curated_interactions` table
- **CRITICAL**: Use `response_data` column, NOT `interaction_data`
- Return: `{found: bool, response_data: JSONB, knowledge_graph: JSONB}`
- Target: <500ms response time (Layer 0)

### 2. ayush_data (AYUSH Collaborator Agent)
**File**: `lambda/ayush_data/handler.py`

#### `ayush_name_resolver(common_name: str)`
- Normalize AYUSH names to scientific names
- Use S3 reference: `s3://ausadhi-mitra-667736132441/reference/name_mappings.json`
- Return: `{scientific_name, common_names[], key_phytochemicals[]}`

#### `imppat_lookup(scientific_name: str)`
- Query DynamoDB `ausadhi-imppat` table
- PK: `plant_name` (e.g., "curcuma_longa")
- SK: "METADATA" or "PHYTO#<imppat_id>"
- Return: `{phytochemicals[], admet_properties, cyp_effects}`

#### `search_cyp_interactions(plant_name: str)`
- Tavily web search for CYP inducer/inhibitor data
- Query: "{plant_name} CYP450 interaction phytochemical"
- Return: `{cyp_interactions[], sources[]}`

### 3. allopathy_data (Allopathy Collaborator Agent)
**File**: `lambda/allopathy_data/handler.py`

#### `allopathy_cache_lookup(drug_name: str)`
- Query PostgreSQL `allopathy_cache` table
- Check TTL: expires_at > NOW()
- Return: `{found: bool, drug_data: JSONB, sources[], cached_at}`

#### `allopathy_cache_save(drug_name: str, drug_data: dict, sources: list)`
- Save to PostgreSQL `allopathy_cache`
- Set expires_at = NOW() + 7 days
- Return: `{success: bool}`

#### `check_nti_status(drug_name: str)`
- Check against S3 reference: `s3://ausadhi-mitra-667736132441/reference/nti_drugs.json`
- NTI drugs: Warfarin, Cyclosporine, Digoxin, Theophylline, Lithium, etc.
- Return: `{is_nti: bool, clinical_concern: str, primary_cyp_substrates[]}`

### 4. web_search (Shared by all agents)
**File**: `lambda/web_search/handler.py`

#### `web_search(query: str, max_results: int = 5)`
- Tavily API wrapper
- Categorize sources: PubMed, DrugBank, FDA, research_paper, general
- Return: `{results: [{url, title, snippet, category, score}]}`
- Store in PostgreSQL `interaction_sources` table

### 5. reasoning_tools (Reasoning Collaborator Agent)
**File**: `lambda/reasoning_tools/handler.py`

#### `build_knowledge_graph(ayush_data: dict, allopathy_data: dict)`
- Construct JSON graph: nodes (Plant, Phytochemical, Drug, CYP_Enzyme) + edges
- Identify overlap_nodes (enzymes affected by both medicines)
- Return: `{nodes[], edges[], overlap_nodes[], interaction_points[]}`

#### `calculate_severity(interactions_data: dict, is_nti: bool)`
- **CRITICAL**: Handle None/empty `interactions_data` gracefully
- Rule-based scoring:
  - CYP overlap: +15 per enzyme
  - NTI drug: +25
  - Clinical evidence: +20
  - Pharmacodynamic overlap: +15
- Score → Severity: 0-20=NONE, 21-40=MINOR, 41-60=MODERATE, 61+=MAJOR
- Return: `{severity: str, score: int, factors[]}`

#### `format_professional_response(all_data: dict)`
- Assemble structured JSON response
- Include: severity, knowledge_graph, mechanisms, profiles, citations, disclaimer
- Return: Full professional response JSON

### 6. Supporting Functions

#### `imppat_loader/handler.py`
- Load IMPPAT CSV data to DynamoDB `ausadhi-imppat`
- Used by: `scripts/imppat_pipeline.py`

#### `validation_parser` (Inline Bedrock Flow node)
- Extract `validation_status: PASSED | NEEDS_MORE_DATA` from Reasoning Agent output
- Controls DoWhile loop exit condition

## Data Sources

### S3 Reference Files
```
s3://ausadhi-mitra-667736132441/reference/
  ├─ name_mappings.json      # 5 AYUSH plants with scientific/common/Hindi/brand names
  ├─ cyp_enzymes.json        # 10 CYP450 enzymes with severity weights
  └─ nti_drugs.json          # ~20 NTI drugs with clinical concerns
```

### DynamoDB Schema
```
Table: ausadhi-imppat
PK: plant_name (e.g., "curcuma_longa")
SK: record_key ("METADATA" or "PHYTO#<imppat_id>")

METADATA record:
  - scientific_name, common_name, family
  - phytochemical_count, last_updated

PHYTO#<id> record:
  - phytochemical_name, plant_part, imppat_id
  - smiles, molecular_weight, drug_likeness
  - admet_properties (dict)
  - cyp_interactions (inhibits[], induces[], substrates[])
```

### PostgreSQL Tables
- `curated_interactions`: Pre-computed high-impact pairs
- `allopathy_cache`: 7-day TTL drug data cache
- `interaction_sources`: Source URL citations

## Deployment

### Script: `scripts/deploy_lambdas.sh`
```bash
# Package and deploy each Lambda function
# Creates deployment packages with dependencies
# Updates Lambda function code
```

### IAM Permissions Required
- DynamoDB: GetItem, Query on `ausadhi-imppat`
- S3: GetObject on `ausadhi-mitra-667736132441/reference/*`
- RDS: Connect to PostgreSQL (via VPC security group)
- Secrets Manager: GetSecretValue for Tavily API key
- Bedrock: InvokeAgent (for Pipeline Mode fallback)

## Error Handling

### Graceful Degradation
1. **Data source failure**: Report gaps, continue with available data
2. **Null inputs**: Return safe defaults, never crash
3. **Cache miss**: Fall through to web search
4. **Web search timeout**: Return partial results

### Critical Null Guards
```python
# In calculate_severity()
if not interactions_data or interactions_data is None:
    return {
        "severity": "NONE",
        "score": 0,
        "factors": ["Insufficient data for severity assessment"]
    }
```

## Testing Priorities
1. Null/empty input handling in all functions
2. PostgreSQL column name alignment (`response_data` not `interaction_data`)
3. DynamoDB query performance for IMPPAT lookups
4. Tavily API rate limiting and timeout handling
5. S3 reference file caching (avoid repeated downloads)
6. Knowledge graph construction with missing data
7. Severity calculation edge cases (no overlaps, NTI only, etc.)

## Known Issues
1. **Column Name Mismatch**: `check_curated_interaction()` must use `response_data` column
2. **NoneType Error**: `calculate_severity()` crashes on None input - add null guard
3. **Empty Knowledge Graph**: Ensure `build_knowledge_graph()` always returns valid structure
