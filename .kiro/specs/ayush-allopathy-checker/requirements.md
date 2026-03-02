# Requirements Document

## Introduction

AushadhiMitra is an AI-powered interaction checker that identifies potential drug interactions between AYUSH (Ayurveda, Yoga & Naturopathy, Unani, Siddha, and Homeopathy) medicines and allopathic drugs. The system uses **AWS Bedrock Agents with a Bedrock Flow V4 (DoWhile validation loop)** to orchestrate a Planner Agent and three specialized Collaborator Agents that gather real-time data via Tavily web search and DynamoDB/PostgreSQL data stores, perform grounded reasoning on the gathered evidence, and produce interaction assessments with severity scoring, knowledge graph visualization, and full source citations.

The system supports two user personas: AYUSH practitioners who need detailed technical information (professional UI with interactive Cytoscape.js knowledge graph), and individual patients who need simple, conversational, multilingual explanations. The backend is a **FastAPI application with WebSocket streaming**, deployed via Docker + Nginx on AWS. The architecture uses a tiered approach: instant responses from a PostgreSQL curated database for high-impact interaction pairs (Layer 0), and real-time multi-agent analysis for other queries with Pipeline fallback when Bedrock Flow times out.

## Glossary

- **AYUSH**: Ayurveda, Yoga & Naturopathy, Unani, Siddha, and Homeopathy traditional medicine systems
- **Allopathic Drug**: Modern pharmaceutical medicine based on Western medical science
- **Amazon Bedrock Agents**: AWS managed service for building conversational AI agents with tool use capabilities
- **Bedrock Flow V4**: AWS Bedrock Flows with a DoWhile node for iterative validation-retry loops
- **DoWhile Loop**: A Bedrock Flow construct that repeats the agent pipeline until `validation_status == PASSED` or max 3 iterations
- **Planner Agent**: Entry-point Bedrock agent that identifies substances and checks the curated database
- **Collaborator Agent**: Specialized sub-agent handling specific domain tasks (AYUSH, Allopathy, Reasoning)
- **Action Group**: Collection of Lambda functions that define deterministic actions an agent can perform
- **Pipeline Mode**: Fallback execution mode where FastAPI directly invokes agents in sequence without using the Bedrock Flow node
- **IMPPAT**: Indian Medicinal Plants, Phytochemistry And Therapeutics database — primary source for AYUSH phytochemical data
- **DrugBank**: Comprehensive pharmaceutical database for allopathic drug ADMET properties
- **ADMET**: Absorption, Distribution, Metabolism, Excretion, Toxicity properties of a drug
- **CYP450 Pathway**: Cytochrome P450 enzyme system responsible for drug metabolism
- **CYP Inhibitor**: A compound that blocks CYP enzyme activity, potentially increasing drug levels
- **CYP Inducer**: A compound that increases CYP enzyme activity, potentially decreasing drug efficacy
- **CYP Substrate**: A drug that is metabolized by a specific CYP enzyme
- **Phytochemical**: Chemical compound produced by plants, the active ingredients in AYUSH medicines
- **Grounded Response**: AI response that is strictly based on provided evidence sources, not model's internal knowledge
- **Evidence Hierarchy**: Ranking of evidence quality: Clinical Study > In Vivo > In Vitro > Computational Prediction
- **Severity Level**: Classification of interaction risk as NONE, MINOR, MODERATE, or MAJOR
- **Knowledge Graph**: JSON-based graph structure mapping drugs, phytochemicals, enzymes, and their relationships
- **Curated Interaction Database**: PostgreSQL table of pre-computed high-confidence interaction pairs for instant responses
- **Narrow Therapeutic Index (NTI)**: Drugs where small changes in blood levels can cause serious toxicity
- **Hero Scenario**: Pre-tested, high-impact demo scenario showcasing dramatic clinical consequences
- **Validation Status**: Output of the DoWhile loop controller — `PASSED` exits the loop; `NEEDS_MORE_DATA` triggers another iteration
- **WebSocket Streaming**: Real-time event streaming from backend to frontend (status → trace → agent_complete → validation → response_chunk → complete)

## Requirements

### Requirement 1: Natural Language Medicine Input

**User Story:** As a patient taking both AYUSH and allopathic medicines, I want to input my medicines in natural language using common names or brand names, so that I can easily check for interactions without medical terminology.

#### Acceptance Criteria

1. WHEN a user sends a message containing medicine names THEN the Planner Agent SHALL extract and identify AYUSH and allopathic medicine references via `identify_substances()` Lambda
2. WHEN a user describes medicines using common names (e.g., "haldi" for Turmeric) THEN the system SHALL normalize names using the local `name_mappings.json` reference file
3. WHEN a user mentions an allopathic brand name (e.g., "Glycomet") THEN the Allopathy Collaborator Agent SHALL perform Tavily web search to find its generic name
4. WHEN a user mentions an AYUSH brand name (e.g., "Himalaya Ashwagandha") THEN the AYUSH Collaborator Agent SHALL identify the primary herb using local brand mapping
5. WHEN the system cannot identify a medicine with confidence THEN the Planner Agent SHALL request clarification from the user
6. WHEN input is received THEN the FastAPI backend SHALL validate it using Pydantic models before forwarding to Bedrock

### Requirement 2: Curated Interaction Database (Layer 0)

**User Story:** As a presenter, I want instant, reliable responses for high-impact interaction pairs, so that the demo is impressive and consistent.

#### Acceptance Criteria

1. WHEN a query matches a curated interaction pair THEN the system SHALL return the pre-computed response in under 500ms (Layer 0) via PostgreSQL lookup
2. WHEN preparing the curated database THEN it SHALL include at least 10-15 high-impact interaction pairs with dramatic clinical consequences
3. WHEN a curated pair is queried THEN the response SHALL include: pre-built knowledge graph, severity assessment, clinical effects, research citations, and AI summary
4. WHEN building curated entries THEN each SHALL include at least one research paper citation with PubMed link
5. WHEN the curated database contains an interaction THEN it SHALL be marked with evidence quality (clinical_study, case_report, in_vitro)
6. WHEN a curated pair includes NTI drugs (Warfarin, Cyclosporine, Digoxin) THEN it SHALL be flagged as high-priority
7. WHEN the curated DB Lambda references a column THEN it SHALL use `response_data` (not `interaction_data`) to match the PostgreSQL schema

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

### Requirement 3: AWS Bedrock Multi-Agent Architecture with Flow V4

**User Story:** As a system architect, I want to use AWS Bedrock's multi-agent collaboration and Bedrock Flow V4 with a DoWhile validation loop to orchestrate specialized agents, so that the system is scalable, self-correcting, and uses managed AWS services.

#### Acceptance Criteria

1. WHEN the system is deployed THEN it SHALL use Amazon Bedrock Agents with 1 Planner Agent and 3 Collaborator Agents (AYUSH, Allopathy, Reasoning)
2. WHEN a query is processed THEN it SHALL first attempt execution via Bedrock Flow V4 (DoWhile architecture)
3. WHEN Bedrock Flow V4 times out THEN the system SHALL automatically fall back to Pipeline Mode (direct agent invocation via FastAPI)
4. WHEN executing the DoWhile loop THEN the system SHALL run a maximum of 3 iterations
5. WHEN the Reasoning Agent completes analysis THEN the inline Validation Parser SHALL extract `validation_status` from the output
6. WHEN `validation_status == PASSED` THEN the DoWhile loop SHALL exit and return the final response
7. WHEN `validation_status == NEEDS_MORE_DATA` THEN the DoWhile loop SHALL re-invoke the AYUSH and Allopathy agents for another iteration
8. WHEN agents need LLM capabilities THEN the Planner and Reasoning Agents SHALL use Claude 3 Sonnet and the AYUSH and Allopathy Agents SHALL use Claude 3 Haiku via Amazon Bedrock

### Requirement 4: Planner Agent

**User Story:** As a system routing user requests, I want a Planner Agent to identify substances and check the curated database before triggering the full analysis pipeline.

#### Acceptance Criteria

1. WHEN the Planner Agent receives a query THEN it SHALL call `identify_substances()` to extract AYUSH and allopathic medicine names
2. WHEN substances are identified THEN the agent SHALL call `check_curated_interaction()` to check the PostgreSQL curated database
3. WHEN a curated match is found THEN the agent SHALL return the pre-computed response and exit the Flow without invoking collaborator agents
4. WHEN no curated match is found THEN the agent SHALL pass control to the DoWhile loop for full analysis

### Requirement 5: AYUSH Collaborator Agent

**User Story:** As a system processing AYUSH medicines, I want a specialized collaborator agent to gather comprehensive phytochemical and CYP data from DynamoDB and web search.

#### Acceptance Criteria

1. WHEN the AYUSH Collaborator Agent is invoked THEN it SHALL call `ayush_name_resolver()` to normalize plant names to scientific names
2. WHEN the scientific name is found THEN the agent SHALL call `imppat_lookup()` to retrieve phytochemical data from the DynamoDB `ausadhi-imppat` table
3. WHEN CYP inducer/inhibitor information is needed THEN the agent SHALL call `search_cyp_interactions()` using Tavily web search via Lambda
4. WHEN any data source fails THEN the agent SHALL report data gaps and continue with available data
5. WHEN data gathering is complete THEN the agent SHALL report a data_completeness assessment

### Requirement 6: Allopathy Collaborator Agent

**User Story:** As a system processing allopathic drugs, I want a specialized collaborator agent to gather CYP metabolism data via PostgreSQL cache and Tavily web search.

#### Acceptance Criteria

1. WHEN the Allopathy Collaborator Agent is invoked THEN it SHALL call `allopathy_cache_lookup()` to check PostgreSQL for previously gathered data
2. WHEN cached data exists and is fresh (< 7 days TTL) THEN the agent SHALL use cached data and skip web search
3. WHEN cache miss THEN the agent SHALL call `web_search()` via Lambda to perform Tavily search for DrugBank CYP data
4. WHEN the drug is a Narrow Therapeutic Index drug THEN `check_nti_status()` SHALL flag it for elevated severity scoring (+25 points)
5. WHEN web search succeeds THEN the agent SHALL call `allopathy_cache_save()` to persist data in PostgreSQL for future queries
6. WHEN web search fails THEN the agent SHALL report gaps and proceed with partial data

### Requirement 7: Reasoning Collaborator Agent

**User Story:** As a system analyzing drug interactions, I want a specialized reasoning agent to build knowledge graphs, detect conflicts, calculate severity, and format the final response.

#### Acceptance Criteria

1. WHEN the Reasoning Collaborator Agent receives merged data from AYUSH and Allopathy agents THEN it SHALL analyze ONLY the provided evidence
2. WHEN analyzing interactions THEN the agent SHALL call `build_knowledge_graph()` Lambda to construct a JSON graph
3. WHEN the knowledge graph is built THEN the agent SHALL identify overlap nodes (enzymes affected by both medicines)
4. WHEN overlap nodes are found THEN the agent SHALL call `calculate_severity()` Lambda for rule-based severity scoring
5. WHEN different sources provide conflicting information THEN the agent SHALL explicitly report the conflict
6. WHEN evidence is insufficient THEN the agent SHALL set `validation_status = NEEDS_MORE_DATA` to trigger another DoWhile iteration
7. WHEN analysis is complete and validated THEN the agent SHALL call `format_professional_response()` and set `validation_status = PASSED`
8. WHEN user_type is "patient" THEN the agent SHALL generate a simple 4-5 sentence response in the user's detected language instead of calling format_professional_response

### Requirement 8: Lambda Action Groups

**User Story:** As a developer, I want agent actions to be implemented as Lambda functions, so that business logic is deterministic, testable, and decoupled from the agent models.

#### Acceptance Criteria

1. WHEN defining action groups THEN each Lambda function SHALL have an OpenAPI schema defining its parameters
2. WHEN Lambda functions are invoked THEN they SHALL handle the Bedrock Agent event format and return proper response objects
3. WHEN implementing action groups THEN the following Lambda functions SHALL be deployed:
   - `identify_substances` (planner_tools) — Extract AYUSH and allopathic names from user input
   - `check_curated_interaction` (planner_tools) — Check PostgreSQL curated interaction database
   - `ayush_name_resolver` (ayush_data) — Normalize AYUSH names using local mappings
   - `imppat_lookup` (ayush_data) — Load phytochemical + ADMET data from DynamoDB `ausadhi-imppat`
   - `search_cyp_interactions` (ayush_data) — Web search for CYP effects of AYUSH plants
   - `allopathy_cache_lookup` (allopathy_data) — Check PostgreSQL for cached drug data
   - `allopathy_cache_save` (allopathy_data) — Save drug data to PostgreSQL cache (7-day TTL)
   - `check_nti_status` (allopathy_data) — Check if drug is on Narrow Therapeutic Index list
   - `web_search` (web_search) — Tavily API wrapper with source categorization
   - `build_knowledge_graph` (reasoning_tools) — Construct JSON graph and identify overlap nodes
   - `calculate_severity` (reasoning_tools) — Rule-based severity scoring (0–100)
   - `format_professional_response` (reasoning_tools) — Assemble structured JSON response for professional UI
4. WHEN Lambda functions fail THEN they SHALL return appropriate error responses for agent-level handling

### Requirement 9: Knowledge Graph Generation

**User Story:** As an AYUSH practitioner, I want to see a visual knowledge graph showing the interaction pathway between medicines.

#### Acceptance Criteria

1. WHEN both agents complete data gathering THEN the Reasoning Agent SHALL build a JSON knowledge graph via `build_knowledge_graph()` Lambda
2. WHEN building the knowledge graph THEN it SHALL include nodes for: Plant, Phytochemicals, Drug, CYP Enzymes, Transporters
3. WHEN building edges THEN it SHALL include relationships: CONTAINS, INHIBITS, INDUCES, SUBSTRATE_OF, METABOLIZED_BY
4. WHEN overlap nodes are found THEN they SHALL be marked as interaction points in the graph
5. WHEN displaying to professional users THEN the graph SHALL be rendered using Cytoscape.js in the frontend

### Requirement 10: Severity Classification

**User Story:** As a patient, I want to understand the severity of any interaction found.

#### Acceptance Criteria

1. WHEN an interaction is detected THEN the system SHALL classify severity as NONE, MINOR, MODERATE, or MAJOR
2. WHEN calculating severity THEN the `calculate_severity()` Lambda SHALL use rule-based scoring:
   - CYP pathway overlap: +15 points per shared enzyme
   - Narrow Therapeutic Index drug: +25 points
   - Clinical evidence (case reports, studies): +20 points
   - Pharmacodynamic overlap (shared effect category): +15 points
3. WHEN severity score is 0–20 THEN classify as NONE; 21–40 as MINOR; 41–60 as MODERATE; 61+ as MAJOR
4. WHEN severity is MAJOR THEN the response SHALL include urgent action recommendations
5. WHEN `interactions_data` is None or empty THEN `calculate_severity()` SHALL handle it gracefully without raising a NoneType error

### Requirement 11: Source Citation and Traceability

**User Story:** As an AYUSH practitioner, I want interaction results to cite all evidence sources with URLs.

#### Acceptance Criteria

1. WHEN any claim is made about an interaction THEN the system SHALL cite the specific source URL
2. WHEN data is from IMPPAT (DynamoDB) THEN the system SHALL include the IMPPAT URL
3. WHEN research articles support an interaction THEN the system SHALL include PubMed links
4. WHEN an interaction is inferred from CYP pathway THEN it SHALL be labeled as "Inferred from CYP mechanism"
5. WHEN Tavily web search returns results THEN sources SHALL be categorized (PubMed, DrugBank, FDA, research paper) and stored in the `interaction_sources` PostgreSQL table

### Requirement 12: FastAPI Backend with WebSocket Streaming

**User Story:** As a developer, I want the backend to support both REST and WebSocket endpoints so that the frontend can display real-time agent traces during analysis.

#### Acceptance Criteria

1. WHEN the backend is running THEN it SHALL expose the following endpoints:
   - `GET /api/health` — System status, agent IDs, Flow ID, DB config
   - `POST /api/check-interaction` — Synchronous interaction check
   - `WS /ws/check-interaction` — Asynchronous WebSocket stream of agent traces
   - `GET /api/interactions` — List recent 20 curated interactions
   - `GET /` — Serve React UI static files
2. WHEN a WebSocket connection is active THEN the backend SHALL stream events in order: status → trace → agent_complete → validation → response_chunk → complete
3. WHEN Bedrock Flow execution mode is used THEN flow trace events SHALL be parsed and forwarded to the WebSocket client
4. WHEN Pipeline fallback mode is used THEN the backend SHALL invoke agents sequentially and stream intermediate results

### Requirement 13: Professional User Interface (Web)

**User Story:** As an AYUSH practitioner, I want a detailed web interface showing comprehensive drug comparison and interactive knowledge graph.

#### Acceptance Criteria

1. WHEN a professional user submits medicines THEN the system SHALL display a detailed comparison view
2. WHEN displaying the knowledge graph THEN the interface SHALL render an interactive Cytoscape.js visualization using the JSON graph from `build_knowledge_graph()`
3. WHEN displaying sources THEN the interface SHALL show all clickable source URLs
4. WHEN conflicts exist in the evidence THEN the interface SHALL explicitly display conflicting information

### Requirement 14: Patient User Interface (Chat)

**User Story:** As a non-medical patient, I want to interact via a simple chat interface in my preferred language.

#### Acceptance Criteria

1. WHEN a patient sends a message THEN the system SHALL respond in conversational language (4-5 sentences)
2. WHEN the user writes in Hindi, English, or Hinglish THEN the system SHALL respond in the same language
3. WHEN severity is MODERATE or MAJOR THEN the response SHALL include clear actionable advice
4. WHEN severity is MODERATE or MAJOR THEN the response SHALL recommend consulting a doctor

### Requirement 15: AWS Infrastructure

**User Story:** As a developer, I want the system deployed on AWS using managed services for reliability and scalability.

#### Acceptance Criteria

1. WHEN deploying the system THEN it SHALL use the following AWS services:
   - Amazon Bedrock Agents for multi-agent orchestration (Claude 3 Sonnet, Claude 3 Haiku)
   - Amazon Bedrock Flows for DoWhile validation loop orchestration
   - AWS Lambda for action group functions (Python 3.12)
   - Amazon S3 for static reference data (`name_mappings.json`, `cyp_enzymes.json`, `nti_drugs.json`)
   - Amazon DynamoDB for IMPPAT phytochemical data (`ausadhi-imppat` table)
   - Amazon RDS PostgreSQL for curated interactions, allopathy cache, interaction sources
   - Amazon API Gateway (via FastAPI on Docker/Nginx)
   - AWS Secrets Manager for Tavily API key
2. WHEN deploying the FastAPI application THEN it SHALL run in a Docker container with Nginx reverse proxy
3. WHEN deploying Lambda functions THEN the `deploy_lambdas.sh` script SHALL package and deploy each function
4. WHEN creating Bedrock agents and flows THEN `setup_agents.py` and `create_flow_v4.py` SHALL be used

### Requirement 16: Data Preparation

**User Story:** As a developer preparing the system, I want reference data pre-loaded into all data stores before the system goes live.

#### Acceptance Criteria

1. WHEN preparing reference data THEN the following files SHALL be uploaded to S3:
   - `s3://ausadhi-mitra-667736132441/reference/name_mappings.json`
   - `s3://ausadhi-mitra-667736132441/reference/cyp_enzymes.json`
   - `s3://ausadhi-mitra-667736132441/reference/nti_drugs.json`
2. WHEN preparing AYUSH data THEN IMPPAT records SHALL be loaded to DynamoDB `ausadhi-imppat` for: Curcuma longa, Glycyrrhiza glabra, Zingiber officinale, Hypericum perforatum, Withania somnifera
3. WHEN loading IMPPAT data THEN the `imppat_loader` Lambda and `imppat_pipeline.py` script SHALL be used
4. WHEN preparing the curated database THEN all 10-15 hero scenarios SHALL be pre-loaded into the PostgreSQL `curated_interactions` table

### Requirement 17: Error Handling and Graceful Degradation

**User Story:** As a user, I want the system to handle errors gracefully so that partial information is still returned even when some data sources fail.

#### Acceptance Criteria

1. WHEN Lambda functions encounter errors THEN they SHALL return structured error responses for agent-level handling
2. WHEN Bedrock Flow V4 times out THEN the backend SHALL automatically switch to Pipeline Mode and continue processing
3. WHEN partial data is available THEN the system SHALL proceed with analysis and explicitly indicate missing information
4. WHEN `calculate_severity()` receives None or empty `interactions_data` THEN it SHALL return a default NONE/MINOR result without raising an exception
5. WHEN the curated DB lookup fails THEN it SHALL fall through to full agent analysis without error

### Requirement 18: Medical Disclaimers

**User Story:** As a user receiving health information, I want to see appropriate disclaimers so I understand the limitations of the system.

#### Acceptance Criteria

1. WHEN an interaction result is displayed THEN the response from `format_professional_response()` SHALL include a disclaimer field
2. WHEN severity is MODERATE or MAJOR THEN the response SHALL recommend consulting a doctor
3. WHEN the system cannot determine interaction status THEN it SHALL advise consulting a pharmacist

### Requirement 19: Pharmacodynamic Effect Analysis

**User Story:** As an Interaction Checker, I want to identify pharmacodynamic overlaps in addition to CYP pathway overlaps.

#### Acceptance Criteria

1. WHEN analyzing interactions THEN the Reasoning Agent SHALL check for overlapping pharmacodynamic effects (e.g., both anticoagulant, both hypoglycemic)
2. WHEN two medicines share the same effect category THEN the `calculate_severity()` Lambda SHALL add +15 points for additive interaction
3. WHEN both CYP and pharmacodynamic interactions are found THEN the agent SHALL report both in the final response
