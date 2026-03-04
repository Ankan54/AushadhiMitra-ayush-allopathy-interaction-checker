# Requirements Document

## Introduction

AushadhiMitra is an AI-powered drug interaction checker that identifies potential interactions between AYUSH (Ayurveda, Yoga & Naturopathy, Unani, Siddha, and Homeopathy) medicines and allopathic drugs. The system uses a **CO-MAS (Cooperative Multi-Agent System) pipeline** orchestrated directly by a FastAPI backend, running up to 3 self-improving iterations. Five specialized AWS Bedrock Agents (Planner, AYUSH, Allopathy, Research, Reasoning) collaborate to gather evidence, reason over it, and produce interaction assessments with severity scoring, ADMET-based knowledge graph visualization, and full source citations.

The backend is a **FastAPI application with WebSocket streaming**, deployed via Docker + Nginx on an AWS EC2 instance. AWS Lambda functions implement all deterministic tool logic. The architecture uses a tiered approach: instant responses from a PostgreSQL curated database (Layer 0), and real-time multi-agent CO-MAS analysis for novel queries.

## Glossary

- **AYUSH**: Ayurveda, Yoga & Naturopathy, Unani, Siddha, and Homeopathy traditional medicine systems
- **Allopathic Drug**: Modern pharmaceutical medicine based on Western medical science
- **Amazon Bedrock Agents**: AWS managed service for building conversational AI agents with tool-use capabilities
- **CO-MAS**: Cooperative Multi-Agent System — the orchestration pattern where multiple specialized agents collaborate within a shared iteration loop
- **CO-MAS Iteration**: A single pass of the pipeline: Planner → Proposers (AYUSH + Allopathy + Research) → Evaluator (Reasoning) → Scorer
- **Planner Agent**: Bedrock agent that reads gap feedback and plans which data to collect in the current iteration
- **Proposer Agents**: AYUSH, Allopathy, and Research agents that gather domain-specific evidence
- **Evaluator Agent**: Reasoning agent that synthesizes evidence, builds the KG, scores severity, and produces the final structured output
- **Scorer**: Deterministic Python function (`_score_output`) that evaluates output completeness and determines if another iteration is needed
- **Pipeline Memory**: Per-session dictionary tracking what worked well across iterations; passed to the Planner on subsequent iterations
- **Action Group**: Collection of Lambda functions defining deterministic tools an agent can call
- **IMPPAT**: Indian Medicinal Plants, Phytochemistry And Therapeutics database — primary source for AYUSH phytochemical data
- **DrugBank**: Comprehensive pharmaceutical database for allopathic drug data and ADMET properties
- **ADMET**: Absorption, Distribution, Metabolism, Excretion, Toxicity — the five pharmacokinetic/toxicological dimensions shown in the knowledge graph
- **CYP450 Pathway**: Cytochrome P450 enzyme system responsible for drug metabolism
- **CYP Inhibitor**: A compound that blocks CYP enzyme activity, potentially increasing co-administered drug levels
- **CYP Inducer**: A compound that increases CYP enzyme activity, potentially decreasing drug efficacy
- **NTI Drug**: Narrow Therapeutic Index drug — a drug where small concentration changes cause serious harm (e.g., Warfarin, Digoxin)
- **Phytochemical**: Chemical compound produced by plants — the active ingredients in AYUSH medicines
- **Knowledge Graph**: Cytoscape.js-compatible JSON graph showing ADMET properties for both drugs and CYP enzyme overlap nodes
- **Severity Level**: Classification of interaction risk as NONE, MINOR, MODERATE, or MAJOR
- **Curated Interaction Database**: PostgreSQL table of pre-computed high-confidence interaction pairs for instant Layer 0 responses
- **WebSocket Streaming**: Real-time event streaming from backend to frontend during pipeline execution
- **Information Gap**: A field identified by the Scorer as missing or insufficient, fed back to the Planner for the next iteration
- **PD Boost**: Pharmacodynamic severity boost added on top of the CYP-based severity score when agent responses mention known PD interaction keywords

## Requirements

### Requirement 1: Natural Language Medicine Input

**User Story:** As a patient taking both AYUSH and allopathic medicines, I want to input my medicines in natural language using common names or brand names, so that I can easily check for interactions without needing medical terminology.

#### Acceptance Criteria

1. WHEN a user enters an AYUSH drug name THEN the backend SHALL resolve it to a scientific name using the local `name_mappings.json` (e.g., "Turmeric" → "Curcuma longa", "haldi" → "Curcuma longa")
2. WHEN a user enters a common AYUSH name THEN the AYUSH Agent SHALL further confirm and resolve it via the `ayush_name_resolver` Lambda
3. WHEN a user enters an allopathic brand name THEN the Allopathy Agent SHALL resolve it to a generic name via the `allopathy_drug_lookup` Lambda
4. WHEN the system cannot identify a medicine THEN the pipeline SHALL return a structured error with `status: "Failed"` and a descriptive message
5. WHEN input is received THEN the FastAPI backend SHALL validate it using Pydantic models before processing

### Requirement 2: Curated Interaction Database (Layer 0)

**User Story:** As a presenter, I want instant, reliable responses for high-impact interaction pairs, so that the demo is impressive and consistent.

#### Acceptance Criteria

1. WHEN a query matches a curated interaction pair THEN the system SHALL return the pre-computed response under 500ms via PostgreSQL lookup
2. WHEN a curated pair is queried THEN the response SHALL include: knowledge graph, severity, clinical effects, research citations, and AI summary
3. WHEN building curated entries THEN each SHALL include at least one research paper citation with a PubMed link
4. WHEN a curated pair includes NTI drugs (e.g., Warfarin, Cyclosporine, Digoxin) THEN it SHALL be flagged as high-priority
5. WHEN the curated DB Lambda queries the database THEN it SHALL use the `response_data` column (not `interaction_data`)

**Curated Hero Scenarios (Minimum Set):**

| AYUSH | Allopathic | Severity | Demo Impact |
|-------|------------|----------|-------------|
| St. John's Wort | Cyclosporine | MAJOR | Organ rejection risk in transplant patients |
| St. John's Wort | Oral Contraceptives | MAJOR | Contraceptive failure |
| Turmeric (Curcumin) | Warfarin | MAJOR | Bleeding risk, INR elevation |
| Licorice (Glycyrrhiza) | Digoxin | MAJOR | Potassium depletion, fatal arrhythmia |
| Ginger | Warfarin | MODERATE | Enhanced bleeding risk |
| Turmeric | Metformin | MODERATE | Additive hypoglycemia |
| Ginger | Aspirin | MODERATE | Additive antiplatelet effect |
| Licorice | Furosemide | MODERATE | Severe potassium depletion |

### Requirement 3: CO-MAS Multi-Agent Pipeline

**User Story:** As a system architect, I want the system to run a self-improving cooperative multi-agent loop so that analysis quality improves across iterations and information gaps are filled systematically.

#### Acceptance Criteria

1. WHEN a query is not found in the curated database THEN the system SHALL run the CO-MAS pipeline with up to 3 iterations
2. WHEN starting an iteration THEN the Planner Agent SHALL run first to create a focused execution plan
3. WHEN the Planner completes THEN AYUSH, Allopathy, and Research agents SHALL run in parallel as the Proposer phase
4. WHEN all Proposers complete THEN the Reasoning (Evaluator) Agent SHALL synthesize their outputs
5. WHEN the Evaluator completes THEN the deterministic Scorer SHALL evaluate output completeness (0–100 scale)
6. WHEN the Scorer identifies gaps THEN it SHALL pass them as targeted feedback to the Planner for the next iteration
7. WHEN the score is ≥60 AND substantive data is present (mechanisms, phytochemicals, or reasoning chain) THEN the pipeline SHALL accept the output and exit
8. WHEN the maximum iteration count (3) is reached THEN the pipeline SHALL return the best available output regardless of score
9. WHEN subsequent iterations are started THEN the Planner SHALL receive both the information gaps AND the pipeline memory (what worked well), not the same generic initial prompt

### Requirement 4: Pipeline Memory

**User Story:** As a system managing multi-iteration pipelines, I want to maintain memory of what was successfully collected in earlier iterations, so that the Planner can avoid re-fetching known data and focus only on remaining gaps.

#### Acceptance Criteria

1. WHEN an iteration completes THEN the system SHALL record successful data points in a pipeline memory dict (e.g., "AYUSH drug identification confirmed", "Found 3 phytochemicals", "KG built with 12 nodes")
2. WHEN starting iteration N>1 THEN the Planner prompt SHALL include a "WHAT WORKED WELL (do NOT re-fetch)" section from pipeline memory
3. WHEN starting iteration N>1 THEN the Planner prompt SHALL include a "REMAINING GAPS" section with only the unresolved gaps
4. WHEN all gaps are resolved THEN the Planner SHALL instruct agents to refine and validate existing data rather than re-collecting it

### Requirement 5: Planner Agent

**User Story:** As the pipeline orchestrator, I want a Planner Agent that creates targeted, iteration-aware execution plans so that each agent knows exactly what to do.

#### Acceptance Criteria

1. WHEN the Planner Agent runs in iteration 1 THEN it SHALL call `identify_substances()` and `check_curated_db()` before generating a plan
2. WHEN the Planner generates a plan THEN it SHALL call `create_execution_plan()` Lambda to persist the structured plan
3. WHEN the Planner runs in iteration N>1 THEN it SHALL use a different system prompt focused on remaining gaps only — NOT the same initial system prompt
4. WHEN the Planner completes THEN it SHALL return a structured plan with specific instructions for each Proposer agent
5. WHEN a curated match is found THEN the Planner SHALL signal pipeline exit without invoking Proposer agents

### Requirement 6: AYUSH Proposer Agent

**User Story:** As a system processing AYUSH medicines, I want a specialized agent to gather comprehensive phytochemical, ADMET, and CYP data.

#### Acceptance Criteria

1. WHEN invoked THEN the AYUSH Agent SHALL call `ayush_name_resolver()` to normalize the plant name to a scientific name
2. WHEN the scientific name is resolved THEN the agent SHALL call `imppat_lookup()` to retrieve phytochemical and ADMET data from DynamoDB
3. WHEN CYP data is needed THEN the agent SHALL call `search_cyp_interactions()` via Tavily web search
4. WHEN data is available THEN the agent SHALL report ADMET properties (Absorption, Distribution, Metabolism, Excretion, Toxicity) for the plant
5. WHEN any data source fails THEN the agent SHALL continue with available data and report the gap

### Requirement 7: Allopathy Proposer Agent

**User Story:** As a system processing allopathic drugs, I want a specialized agent to gather CYP metabolism, ADMET, and NTI data with a DrugBank URL.

#### Acceptance Criteria

1. WHEN invoked THEN the Allopathy Agent SHALL call `allopathy_drug_lookup()` to retrieve drug data including the DrugBank URL
2. WHEN the drug is a Narrow Therapeutic Index drug THEN the agent SHALL flag it for elevated severity scoring
3. WHEN the drug data is retrieved THEN it SHALL include ADMET properties (Absorption, Distribution, Metabolism, Excretion, Toxicity)
4. WHEN the DrugBank URL is found THEN it SHALL be included in the agent's response and extracted by `_extract_drugbank_url()` in the orchestrator
5. WHEN the agent completes THEN its traces and response text SHALL be scanned for URLs to populate the sources list

### Requirement 8: Research Proposer Agent

**User Story:** As a system requiring clinical evidence, I want a dedicated Research agent to search PubMed and clinical databases for interaction evidence.

#### Acceptance Criteria

1. WHEN invoked THEN the Research Agent SHALL perform targeted web searches for clinical interaction evidence between the two drugs
2. WHEN search results are found THEN the agent SHALL extract and return source URLs (PubMed, clinical studies, review articles)
3. WHEN evidence is found THEN the agent SHALL summarize the clinical significance for the Reasoning agent
4. WHEN no evidence is found THEN the agent SHALL report the gap for the next iteration

### Requirement 9: Reasoning Evaluator Agent

**User Story:** As a system synthesizing drug interaction analysis, I want a Reasoning agent to build the knowledge graph, calculate severity, and produce structured output.

#### Acceptance Criteria

1. WHEN invoked THEN the Reasoning Agent SHALL synthesize outputs from AYUSH, Allopathy, and Research agents
2. WHEN synthesizing THEN the agent SHALL call `build_knowledge_graph()` Lambda to construct the ADMET-focused graph
3. WHEN the knowledge graph is built THEN it SHALL show ADMET property nodes for BOTH drugs and CYP enzyme overlap nodes
4. WHEN the agent produces a severity assessment THEN it SHALL call `calculate_severity()` Lambda with the CYP enzyme data
5. WHEN the Reasoning Agent does not call `calculate_severity()` THEN the orchestrator SHALL call it directly as a fallback
6. WHEN analysis is complete THEN the agent SHALL produce a structured JSON output including: `severity`, `severity_score`, `mechanisms`, `phytochemicals_involved`, `reasoning_chain`, `interaction_summary`, and `knowledge_graph`
7. WHEN sources are mentioned in the response THEN they SHALL be extractable from agent traces and response text

### Requirement 10: Knowledge Graph Visualization

**User Story:** As an AYUSH practitioner, I want to see a visual ADMET-focused knowledge graph comparing both drugs side by side with any CYP enzyme overlaps highlighted.

#### Acceptance Criteria

1. WHEN the knowledge graph is built THEN it SHALL contain ADMET property nodes for BOTH the AYUSH drug and the allopathy drug
2. WHEN labeling ADMET nodes THEN each SHALL be prefixed with the drug name (e.g., "Curcuma: Metabolism", "Metformin: Absorption") to distinguish the two drugs
3. WHEN labeling edges from drug to ADMET nodes THEN they SHALL use the format "has \<property\>" (e.g., "has Metabolism", "has Absorption")
4. WHEN both drugs share a CYP enzyme pathway THEN a CYP enzyme overlap node SHALL be added with type `cyp_enzyme_overlap` and highlighted distinctly
5. WHEN CYP enzymes are present for only one drug THEN a regular `cyp_enzyme` node SHALL be added
6. WHEN no CYP overlap exists THEN no CYP nodes SHALL appear — only ADMET nodes for both drugs
7. WHEN the graph is rendered THEN it SHALL use Cytoscape.js in the frontend with color-coded node types
8. WHEN the `_transform_graph_to_admet()` orchestrator function runs THEN it SHALL ensure all ADMET nodes are properly prefixed, even if the Lambda returned generic labels

### Requirement 11: Severity Classification

**User Story:** As a patient, I want to understand how serious any detected interaction is.

#### Acceptance Criteria

1. WHEN an interaction is detected THEN the system SHALL classify severity as NONE, MINOR, MODERATE, or MAJOR
2. WHEN calculating severity THEN the `calculate_severity()` Lambda SHALL use rule-based CYP-based scoring:
   - For each CYP enzyme in the data: add `weight × 2` for inhibition, `weight × 1.5` for induction, `weight × 1` for generic interaction
   - NTI drug detected: add +25 points
   - Thresholds: NONE < 15, MINOR 15–34, MODERATE 35–59, MAJOR ≥ 60
3. WHEN the CYP-based score is computed THEN the `_boost_severity_from_evidence()` function SHALL scan agent response text for pharmacodynamic keywords and add a PD boost (capped at +25)
4. WHEN severity is MAJOR THEN the response SHALL include urgent action recommendations
5. WHEN `calculate_severity()` receives None or empty input THEN it SHALL return a default NONE result without raising an exception
6. WHEN the Reasoning Agent does not invoke `calculate_severity()` THEN the backend orchestrator SHALL invoke it directly

### Requirement 12: Source Citation and Evidence Links

**User Story:** As an AYUSH practitioner, I want all interaction claims to cite specific clickable source URLs.

#### Acceptance Criteria

1. WHEN any interaction claim is made THEN the system SHALL cite the source URL
2. WHEN the Allopathy Agent response contains a DrugBank URL THEN it SHALL appear in the Drug Info tab
3. WHEN agent traces and response text contain URLs THEN `_extract_source_urls()` SHALL parse and deduplicate them into the `sources` list
4. WHEN sources are displayed in the Sources tab THEN they SHALL be rendered as clickable links
5. WHEN mechanism or reasoning text contains a URL THEN it SHALL be rendered as a clickable link via the `TextWithLinks` component

### Requirement 13: FastAPI Backend with WebSocket Streaming

**User Story:** As a developer, I want the backend to support REST and WebSocket endpoints so that the frontend can display real-time agent traces during analysis.

#### Acceptance Criteria

1. WHEN the backend is running THEN it SHALL expose:
   - `GET /api/health` — System status, agent IDs, DB config
   - `POST /api/check` — Start CO-MAS pipeline; returns `{session_id}`
   - `WS /ws/{session_id}` — Real-time stream of pipeline events for the given session
   - `GET /api/interactions` — List recent curated interactions
   - `GET /` and `GET /{path}` — Serve React SPA static files
2. WHEN a WebSocket connection is active THEN the backend SHALL stream events in this sequence: `pipeline_status` → `llm_call` → `agent_thinking` → `tool_call` → `tool_result` → `llm_response` → `agent_complete` → `pipeline_status(gap_identified)` → `complete`
3. WHEN an iteration fails its score THEN the backend SHALL emit `pipeline_status` events with `status: "gap_identified"` for each gap before starting the next iteration
4. WHEN the pipeline completes THEN the backend SHALL emit a `complete` event with `result` containing the full structured output

### Requirement 14: Professional User Interface

**User Story:** As an AYUSH practitioner, I want a detailed tabbed interface showing all analysis dimensions.

#### Acceptance Criteria

1. WHEN a result is returned THEN the frontend SHALL display a tabbed panel with: Summary, Drug Info, Mechanisms, Reasoning, Graph, Sources
2. WHEN displaying the Summary tab THEN it SHALL show severity badge (color-coded), severity score, interaction summary, and phytochemicals involved
3. WHEN displaying the Drug Info tab THEN it SHALL show AYUSH drug details (scientific name, IMPPAT URL) and Allopathy drug details with a clickable DrugBank link
4. WHEN displaying the Mechanisms tab THEN each mechanism SHALL show description, evidence with clickable link, and confidence level
5. WHEN displaying the Reasoning tab THEN reasoning steps and evidence SHALL render URLs as clickable links via `TextWithLinks`
6. WHEN displaying the Graph tab THEN the Cytoscape.js graph SHALL render with color-coded nodes: green (AYUSH plant), blue (allopathy drug), orange (ADMET property), red (CYP overlap)
7. WHEN displaying the Sources tab THEN all URLs SHALL be clickable links with title and category labels

### Requirement 15: AWS Infrastructure

**User Story:** As a developer, I want the system deployed on AWS using managed services.

#### Acceptance Criteria

1. WHEN deploying the system THEN it SHALL use the following AWS services:
   - Amazon Bedrock Agents (Claude 3 Sonnet / Haiku) — 5 agents: Planner, AYUSH, Allopathy, Research, Reasoning
   - AWS Lambda — 7 deployed functions (Python 3.11): `ausadhi-planner-tools`, `ausadhi-ayush-data`, `ausadhi-allopathy-data`, `ausadhi-web-search`, `ausadhi-reasoning-tools`, `ausadhi-check-curated-db`, `ausadhi-research-tools`
   - Amazon S3 — `ausadhi-mitra-667736132441` for reference data and static files
   - Amazon DynamoDB — `ausadhi-imppat` table for AYUSH phytochemical data
   - Amazon RDS PostgreSQL — curated interactions + allopathy cache
   - AWS IAM — `AusadhiEC2Role` with permissions for Bedrock, Lambda, S3, CloudWatch
2. WHEN deploying the FastAPI application THEN it SHALL run as Docker container `aushadhi-comas:latest` behind Nginx on EC2 (port 80)
3. WHEN deploying Lambda functions THEN `scripts/deploy_lambdas.sh` SHALL package and deploy each function to us-east-1
4. WHEN the EC2 container restarts THEN the IAM role credentials SHALL grant `lambda:InvokeFunction` and `logs:PutLogEvents` permissions

### Requirement 16: Error Handling and Graceful Degradation

**User Story:** As a user, I want the system to handle errors gracefully so that partial information is returned even when some data sources fail.

#### Acceptance Criteria

1. WHEN Lambda functions encounter errors THEN they SHALL return structured error responses for agent-level handling
2. WHEN partial data is available THEN the system SHALL proceed and explicitly indicate missing information as gaps
3. WHEN `calculate_severity()` receives None or empty `interactions_data` THEN it SHALL return a default NONE result without raising an exception
4. WHEN the curated DB lookup fails THEN it SHALL fall through to full CO-MAS analysis without error
5. WHEN an agent call fails THEN the orchestrator SHALL log the error and continue with available outputs from other agents

### Requirement 17: Medical Disclaimers

**User Story:** As a user receiving health information, I want appropriate disclaimers so I understand the system's limitations.

#### Acceptance Criteria

1. WHEN an interaction result is displayed THEN the response SHALL include a disclaimer field
2. WHEN severity is MODERATE or MAJOR THEN the response SHALL recommend consulting a licensed healthcare professional
3. WHEN the system cannot determine interaction status THEN it SHALL advise consulting a pharmacist

### Requirement 18: Pharmacodynamic Effect Analysis

**User Story:** As an Interaction Checker, I want to identify pharmacodynamic overlaps in addition to CYP pathway overlaps.

#### Acceptance Criteria

1. WHEN analyzing interactions THEN the system SHALL check for overlapping pharmacodynamic effects (e.g., both hypoglycemic, both anticoagulant)
2. WHEN pharmacodynamic keywords are found in agent responses THEN `_boost_severity_from_evidence()` SHALL add a PD boost (capped at +25 points) to the CYP-based severity score
3. WHEN both CYP and pharmacodynamic interactions are found THEN both SHALL be reported in the mechanisms and reasoning sections
