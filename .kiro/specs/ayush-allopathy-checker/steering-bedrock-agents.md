# Bedrock Agents & Flow Steering File - AushadhiMitra

## Purpose
AWS Bedrock multi-agent architecture with Flow V4 DoWhile validation loop for self-correcting drug interaction analysis.

## Architecture Overview

### Agent Hierarchy
```
Bedrock Flow V4 (DoWhile Loop)
  ├─ Planner Agent (Entry Point)
  │    └─ Action Group: planner_tools
  │
  └─ DoWhile Loop (max 3 iterations)
       ├─ AYUSH Collaborator Agent
       │    └─ Action Groups: ayush_data, web_search
       │
       ├─ Allopathy Collaborator Agent
       │    └─ Action Groups: allopathy_data, web_search
       │
       ├─ Data Merge Prompt (Amazon Nova Pro)
       │
       ├─ Reasoning Collaborator Agent
       │    └─ Action Groups: reasoning_tools, web_search
       │
       ├─ Validation Parser (inline code node)
       │    └─ Extract validation_status
       │
       └─ Loop Controller
            ├─ PASSED → Exit loop
            └─ NEEDS_MORE_DATA → Re-run (max 3x)
```

## Agent Specifications

### 1. Planner Agent
**Model**: Claude 3 Sonnet  
**Role**: Entry point, substance identification, curated DB check  
**Action Group**: `planner_tools`

**Instructions**:
```
You are the Planner Agent for AushadhiMitra drug interaction checker.

Your responsibilities:
1. Extract AYUSH and allopathic medicine names from user input using identify_substances()
2. Check the curated interaction database using check_curated_interaction()
3. If curated match found: Return the pre-computed response immediately
4. If no match: Pass control to the DoWhile loop for full analysis

Always normalize medicine names before checking the curated database.
Use the confidence score from identify_substances() to request clarification if needed.
```

**Lambda Functions**:
- `identify_substances(user_input: str)`
- `check_curated_interaction(ayush_name: str, allopathy_name: str)`

### 2. AYUSH Collaborator Agent
**Model**: Claude 3 Haiku  
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
**Role**: Gather allopathic drug CYP metabolism data  
**Action Groups**: `allopathy_data`, `web_search`

**Instructions**:
```
You are the Allopathy Collaborator Agent specializing in pharmaceutical drug data.

Your responsibilities:
1. Check cache for previously gathered drug data using allopathy_cache_lookup()
2. If cache miss, perform web search for DrugBank CYP metabolism data
3. Check if drug is on Narrow Therapeutic Index (NTI) list using check_nti_status()
4. Save new data to cache using allopathy_cache_save()

Focus on:
- Generic drug name (if brand name provided)
- CYP450 substrates (which enzymes metabolize this drug)
- CYP450 inhibitors/inducers (does this drug affect enzymes)
- Narrow Therapeutic Index status
- Primary metabolism pathway

Always prioritize DrugBank and FDA sources.
Flag NTI drugs as high-priority for severity assessment.
```

**Lambda Functions**:
- `allopathy_cache_lookup(drug_name: str)`
- `allopathy_cache_save(drug_name: str, drug_data: dict, sources: list)`
- `check_nti_status(drug_name: str)`
- `web_search(query: str, max_results: int)`

### 4. Reasoning Collaborator Agent
**Model**: Claude 3 Sonnet  
**Role**: Analyze interactions, build knowledge graph, validate completeness  
**Action Groups**: `reasoning_tools`, `web_search`

**Instructions**:
```
You are the Reasoning Collaborator Agent responsible for interaction analysis.

Your responsibilities:
1. Build knowledge graph from AYUSH and Allopathy data using build_knowledge_graph()
2. Identify overlap nodes (enzymes affected by both medicines)
3. Search for clinical evidence using web_search() targeting PubMed
4. Calculate severity using calculate_severity()
5. Detect conflicts in evidence sources
6. Validate data completeness and set validation_status

Validation Logic:
- If critical data is missing (e.g., no CYP data for either medicine): validation_status = NEEDS_MORE_DATA
- If conflicting evidence exists without resolution: validation_status = NEEDS_MORE_DATA
- If analysis is complete and grounded in evidence: validation_status = PASSED

Analysis Rules:
- ONLY use provided evidence from Lambda functions
- Do NOT use your internal knowledge about drugs
- Explicitly report conflicts between sources
- Cite every claim with source URL
- Consider both CYP pathway and pharmacodynamic overlaps

For professional users: Call format_professional_response() with full structured data
For patient users: Generate simple 4-5 sentence response in user's language
```

**Lambda Functions**:
- `build_knowledge_graph(ayush_data: dict, allopathy_data: dict)`
- `calculate_severity(interactions_data: dict, is_nti: bool)`
- `format_professional_response(all_data: dict)`
- `web_search(query: str, max_results: int)`

**Output Format**:
```json
{
  "analysis": "...",
  "validation_status": "PASSED",  // or "NEEDS_MORE_DATA"
  "response": { ... }
}
```

## Bedrock Flow V4 Structure

### Flow Nodes

1. **FlowInput**
   - Receives: `{ayush_medicine, allopathy_drug, user_type}`

2. **PlannerAgent** (Agent Node)
   - Invokes: Planner Agent
   - Output: `{substances, curated_result}`
   - Condition: If curated_result.found → FlowOutput (Layer 0 exit)

3. **DoWhileLoop** (DoWhile Node)
   - Max iterations: 3
   - Exit condition: `validation_status == "PASSED"`

4. **AYUSHAgent** (Agent Node, inside loop)
   - Invokes: AYUSH Collaborator Agent
   - Output: `{ayush_data, data_completeness}`

5. **AllopathyAgent** (Agent Node, inside loop)
   - Invokes: Allopathy Collaborator Agent
   - Output: `{allopathy_data, data_completeness}`

6. **DataMergePrompt** (Prompt Node, inside loop)
   - Model: Amazon Nova Pro
   - Consolidates AYUSH + Allopathy data
   - Output: `{merged_data}`

7. **ReasoningAgent** (Agent Node, inside loop)
   - Invokes: Reasoning Collaborator Agent
   - Output: `{analysis, validation_status, response}`

8. **ValidationParser** (Inline Code Node, inside loop)
   - Extracts `validation_status` from ReasoningAgent output
   - Returns: `"PASSED"` or `"NEEDS_MORE_DATA"`

9. **LoopController** (Condition Node)
   - If `validation_status == "PASSED"` → Exit loop
   - Else → Re-run loop (up to 3 times)

10. **FlowOutput**
    - Returns: Final response JSON

### Flow Configuration
```python
{
    "name": "AushadhiMitra-DoWhile-Flow-V4",
    "description": "Multi-agent drug interaction checker with DoWhile validation loop",
    "executionRoleArn": "arn:aws:iam::667736132441:role/BedrockFlowExecutionRole",
    "definition": {
        "nodes": [...],
        "connections": [...]
    }
}
```

## Deployment Scripts

### `scripts/setup_agents.py`
- Creates/updates 4 Bedrock agents
- Configures action groups with Lambda ARNs
- Sets agent instructions and model selection
- Generates agent aliases

### `scripts/create_flow_v4.py`
- Builds Bedrock Flow V4 with DoWhile node
- Configures validation parser and loop controller
- Creates flow alias for production use

## Known Issues & Mitigations

### Issue 1: Bedrock Flow V4 Timeout
**Symptom**: "Read timed out" error during Flow execution  
**Impact**: Flow fails to complete  
**Mitigation**: Auto-fallback to Pipeline Mode in `agent_service.py`

### Issue 2: DoWhile Loop Infinite Retry
**Symptom**: Loop runs 3 times even when data is sufficient  
**Mitigation**: Ensure Reasoning Agent explicitly sets `validation_status = PASSED`

### Issue 3: Agent Hallucination
**Symptom**: Agent makes claims not supported by Lambda data  
**Mitigation**: Strong instructions to use ONLY provided evidence

## Testing Priorities

1. **Layer 0 Fast Path**: Curated DB hit → instant response (<500ms)
2. **DoWhile Validation**: Loop exits on PASSED, re-runs on NEEDS_MORE_DATA
3. **Max Iterations**: Loop stops after 3 iterations even if not PASSED
4. **Pipeline Fallback**: Flow timeout → automatic Pipeline Mode
5. **Grounded Reasoning**: Agent responses cite only Lambda-provided sources
6. **Null Handling**: Agents handle missing data gracefully
7. **WebSocket Streaming**: Trace events stream correctly during Flow execution

## Agent Model Selection Rationale

| Agent | Model | Reasoning |
|-------|-------|-----------|
| Planner | Claude 3 Sonnet | Needs strong reasoning for substance identification and routing |
| AYUSH | Claude 3 Haiku | Data gathering task, cost-effective |
| Allopathy | Claude 3 Haiku | Data gathering task, cost-effective |
| Reasoning | Claude 3 Sonnet | Complex analysis, validation logic, conflict resolution |
| DataMerge | Amazon Nova Pro | Simple consolidation task, AWS-native |

## Environment Variables
```
AWS_REGION=us-east-1
PLANNER_AGENT_ID=<agent-id>
PLANNER_AGENT_ALIAS=<alias-id>
AYUSH_AGENT_ID=<agent-id>
AYUSH_AGENT_ALIAS=<alias-id>
ALLOPATHY_AGENT_ID=<agent-id>
ALLOPATHY_AGENT_ALIAS=<alias-id>
REASONING_AGENT_ID=<agent-id>
REASONING_AGENT_ALIAS=<alias-id>
FLOW_ID=<flow-id>
FLOW_ALIAS_ID=<alias-id>
```
