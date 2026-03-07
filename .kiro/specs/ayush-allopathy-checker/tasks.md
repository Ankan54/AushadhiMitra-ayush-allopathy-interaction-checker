# Implementation Plan: AYUSH-Allopathy Interaction Checker

## Overview

This implementation plan builds AushadhiMitra, an AI-powered drug interaction checker using a **CO-MAS (Cooperative Multi-Agent System) pipeline** orchestrated directly by the FastAPI backend. Five specialized AWS Bedrock Agents (Planner, AYUSH, Allopathy, Research, Reasoning) collaborate across up to 3 self-improving iterations to gather evidence, reason over it, and produce interaction assessments with severity scoring, ADMET-based knowledge graph visualization, and full source citations.

The system uses Python 3.11 for all backend components, Lambda functions, and deployment scripts. The frontend uses React with Cytoscape.js for ADMET-focused knowledge graph visualization. A tiered response architecture provides instant responses from a PostgreSQL curated database (Layer 0) and real-time multi-agent CO-MAS analysis for novel queries.

## Tasks

- [x] 1. Set up AWS infrastructure and data stores
  - ✅ S3 bucket created: ausadhi-mitra-667736132441
  - ✅ Reference data files uploaded: name_mappings.json, cyp_enzymes.json, nti_drugs.json
  - ✅ DynamoDB table `ausadhi-imppat` created and populated
  - ✅ PostgreSQL database `aushadhimitra` with tables: curated_interactions, interaction_sources, allopathy_cache
  - ✅ Tavily API key stored in AWS Secrets Manager
  - _Requirements: 15, 16_

- [x] 2. Implement Lambda action groups for Planner Agent
  - [x] 2.1 Create `planner_tools/handler.py` with identify_substances, check_curated_interaction, and create_execution_plan functions
    - ✅ Implemented `identify_substances()` to extract AYUSH and allopathic medicine names from user input
    - ✅ Implemented `check_curated_interaction()` to query PostgreSQL curated_interactions table using `response_data` column
    - ✅ Implemented `create_execution_plan()` to persist structured execution plans with iteration-aware task lists
    - ✅ Uses interaction_key format: "ayush_name:allopathy_name" (lowercase with underscores)
    - _Requirements: 1.1, 2.1, 2.8, 4.1, 4.2, 4.3, 5.1, 5.2_
  
  - [ ]* 2.2 Write unit tests for planner_tools Lambda functions
    - ⚠️ NO TESTS FOUND - Test coverage missing
    - Test substance identification with various input formats
    - Test curated database lookup with hit/miss scenarios
    - Test execution plan creation with gap feedback
    - _Requirements: 4.1, 4.2, 5.1_

- [x] 3. Implement Lambda action groups for AYUSH Collaborator Agent
  - [x] 3.1 Create `ayush_data/handler.py` with name resolver, IMPPAT lookup, and CYP search functions
    - ✅ Implemented `ayush_name_resolver()` to normalize plant names using S3 name_mappings.json
    - ✅ Implemented `imppat_lookup()` to retrieve phytochemical and ADMET data from DynamoDB ausadhi-imppat table
    - ✅ Implemented `search_cyp_interactions()` to perform Tavily web search for CYP effects
    - ✅ Handles data source failures gracefully and reports data completeness
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 6.1_
  
  - [ ]* 3.2 Write unit tests for ayush_data Lambda functions
    - ⚠️ NO TESTS FOUND - Test coverage missing
    - Test name resolution with common names, brand names, and scientific names
    - Test IMPPAT lookup with mock DynamoDB responses
    - Test CYP search with mock Tavily responses
    - _Requirements: 5.1, 5.2, 5.3, 6.1_

- [x] 4. Implement Lambda action groups for Allopathy Collaborator Agent
  - [x] 4.1 Create `allopathy_data/handler.py` with drug lookup and NTI check functions
    - ✅ Implemented `allopathy_drug_lookup()` to retrieve drug data including DrugBank URL and ADMET properties
    - ✅ Implemented `check_nti_status()` to check if drug is on Narrow Therapeutic Index list from S3
    - ✅ Handles data source failures gracefully
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 7.1, 7.2, 7.3, 7.4_
  
  - [ ]* 4.2 Write unit tests for allopathy_data Lambda functions
    - ⚠️ NO TESTS FOUND - Test coverage missing
    - Test drug lookup with DrugBank URL extraction
    - Test NTI status check with known NTI drugs
    - Test ADMET property retrieval
    - _Requirements: 6.1, 6.2, 6.4, 7.1_

- [x] 5. Implement Lambda action groups for Research Agent
  - [x] 5.1 Create `research_tools/handler.py` with PubMed and clinical evidence search functions
    - ✅ Implemented `search_clinical_evidence()` to search PubMed and clinical databases for interaction evidence
    - ✅ Implemented source categorization (PubMed, clinical_study, review_article)
    - ✅ Extracts and returns source URLs with titles and snippets
    - _Requirements: 8.1, 8.2, 8.3_
  
  - [ ]* 5.2 Write unit tests for research_tools Lambda functions
    - ⚠️ NO TESTS FOUND - Test coverage missing
    - Test PubMed search with mock responses
    - Test source categorization logic
    - Test URL extraction
    - _Requirements: 8.1, 8.2_

- [x] 6. Implement web search Lambda action group
  - [x] 6.1 Create `web_search/handler.py` with Tavily API integration
    - ✅ Implemented `web_search()` function with source categorization (PubMed, DrugBank, FDA, research_paper, general)
    - ✅ Retrieves Tavily API key from AWS Secrets Manager
    - ✅ Handles API timeouts and rate limits gracefully
    - _Requirements: 8.3, 11.4, 17.7_
  
  - [ ]* 6.2 Write unit tests for web_search Lambda function
    - ⚠️ NO TESTS FOUND - Test coverage missing
    - Test source categorization logic
    - Test error handling for API failures
    - _Requirements: 8.3_

- [x] 7. Checkpoint - Ensure all Lambda functions deploy successfully
  - ✅ All Lambda functions deployed using deploy_lambdas.sh script (Python 3.11)
  - ✅ CloudWatch logs are being generated
  - ⚠️ Unit tests missing - no test suite found

- [x] 8. Implement Lambda action groups for Reasoning Collaborator Agent
  - [x] 8.1 Create `reasoning_tools/handler.py` with ADMET knowledge graph builder
    - ✅ Implemented `build_knowledge_graph()` to construct JSON graph with ADMET property nodes for BOTH drugs
    - ✅ Labels ADMET nodes with drug-name prefix (e.g., "Curcuma: Metabolism", "Metformin: Absorption")
    - ✅ Labels edges with "has \<property\>" format (e.g., "has Metabolism", "has Absorption")
    - ✅ Identifies CYP enzyme overlap nodes (enzymes affected by both medicines) with type `cyp_enzyme_overlap`
    - ✅ Handles incomplete data gracefully and returns valid graph structure
    - _Requirements: 7.2, 7.3, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 10.1, 10.2, 10.3, 17.6_
  
  - [x] 8.2 Implement CYP-based severity calculation in reasoning_tools
    - ✅ Implemented `calculate_severity()` with rule-based scoring: CYP overlap (weight × 2 for inhibition, × 1.5 for induction), NTI (+25)
    - ✅ Maps scores to severity levels: 0-14 NONE, 15-34 MINOR, 35-59 MODERATE, 60+ MAJOR
    - ✅ Added null guard for None or empty interactions_data input
    - ✅ Returns structured output with severity, severity_score, is_nti, scoring_factors
    - _Requirements: 7.4, 10.1, 10.2, 10.3, 10.4, 10.5, 11.1, 11.2, 11.3, 11.5, 11.6, 17.4_
  
  - [ ]* 8.3 Write unit tests for reasoning_tools Lambda functions
    - ⚠️ NO TESTS FOUND - Test coverage missing
    - Test ADMET knowledge graph construction with various data inputs
    - Test CYP-based severity calculation with different interaction scenarios
    - Test null guard for empty interactions_data
    - _Requirements: 7.2, 7.4, 9.1, 11.1_

- [x] 9. Implement shared utilities for Lambda functions
  - [x] 9.1 Create `shared/bedrock_utils.py` with Bedrock Agent event handling utilities
    - ✅ Implemented event parser for Bedrock Agent input format
    - ✅ Implemented response formatter for Bedrock Agent output format
    - _Requirements: 8.2_
  
  - [x] 9.2 Create `shared/db_utils.py` with database connection utilities
    - ✅ Implemented PostgreSQL connection helper with connection pooling
    - ✅ Implemented DynamoDB query helpers
    - ✅ Implemented S3 reference data loader
    - ✅ Consolidated schema constants to prevent column name drift
    - _Requirements: 8.2, 15.1_

- [x] 10. Create Bedrock Agents with action groups
  - [x] 10.1 Create `scripts/setup_agents.py` to configure all 5 Bedrock agents
    - ✅ Created Planner Agent (Claude 3 Sonnet) with planner_tools action group
    - ✅ Created AYUSH Agent (Claude 3 Haiku) with ayush_data and web_search action groups
    - ✅ Created Allopathy Agent (Claude 3 Haiku) with allopathy_data and web_search action groups
    - ✅ Created Research Agent (Claude 3 Haiku) with research_tools and web_search action groups
    - ✅ Created Reasoning Agent (Claude 3 Sonnet) with reasoning_tools and web_search action groups
    - ✅ Generated OpenAPI schemas for all action groups
    - _Requirements: 3.1, 3.8, 8.1, 8.3_
  
  - [ ]* 10.2 Write integration tests for Bedrock Agent setup
    - ⚠️ NO TESTS FOUND - Test coverage missing
    - Test agent creation and action group attachment
    - Test OpenAPI schema validation
    - _Requirements: 3.1, 8.1_

- [x] 11. Checkpoint - Verify AWS Bedrock infrastructure
  - ✅ All 5 agents deployed and can be invoked individually
  - ✅ Action groups correctly attached
  - ⚠️ Integration tests missing

- [x] 12. Implement FastAPI backend core
  - [x] 12.1 Create `backend/app/config.py` with environment-based configuration
    - ✅ Defined agent IDs and aliases for all 5 agents (Planner, AYUSH, Allopathy, Research, Reasoning)
    - ✅ Defined S3 bucket, PostgreSQL connection string
    - ✅ Defined input validation rules
    - ✅ Set MAX_COMAS_ITERATIONS = 3
    - _Requirements: 15.1_
  
  - [x] 12.2 Create `backend/app/models.py` with Pydantic validation models
    - ✅ Defined InteractionRequest model (ayush_medicine, allopathy_drug, user_type)
    - ✅ Defined HealthResponse model
    - _Requirements: 1.6_
  
  - [x] 12.3 Create `backend/app/db.py` with PostgreSQL connection pool
    - ✅ Implemented `lookup_curated()` for Layer 0 instant responses using `response_data` column
    - ✅ Implemented `get_sources()` to retrieve source URLs
    - ✅ Implemented `save_interaction()` to persist new results
    - ✅ Implemented `list_interactions()` to return recent 20 interactions
    - _Requirements: 2.1, 11.1, 11.2, 11.3_
  
  - [ ]* 12.4 Write unit tests for FastAPI database utilities
    - ⚠️ NO TESTS FOUND - Test coverage missing
    - Test curated lookup with various interaction keys
    - Test source retrieval
    - Test interaction persistence
    - _Requirements: 2.1_

- [x] 13. Implement FastAPI CO-MAS pipeline orchestration service
  - [x] 13.1 Create `backend/app/agent_service.py` with CO-MAS pipeline orchestrator
    - ✅ Implemented `run_comas_pipeline()` to orchestrate up to 3 iterations of the CO-MAS pipeline
    - ✅ Implemented `_invoke_planner()` with iteration-aware prompts (initial plan vs. gap-focused subsequent prompt)
    - ✅ Implemented `_invoke_proposers()` to run AYUSH, Allopathy, and Research agents in parallel
    - ✅ Implemented `_invoke_reasoning()` to run Reasoning (Evaluator) Agent with merged proposer context
    - ✅ Implemented `_score_output()` deterministic scorer (0-100 scale across 8 dimensions)
    - ✅ Implemented `_boost_severity_from_evidence()` to scan agent text for pharmacodynamic keywords and add PD boost
    - ✅ Implemented pipeline memory management to track successes and pass to Planner in subsequent iterations
    - ✅ Parses and formats agent trace events for WebSocket streaming
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 4.1, 4.2, 4.3, 4.4, 5.3, 5.4, 5.5, 11.3, 11.6, 17.2, 18.1, 18.2, 18.3_
  
  - [x] 13.2 Implement helper functions in agent_service.py
    - ✅ Implemented `_format_final_json()` to assemble final interaction_data dict from agent outputs
    - ✅ Implemented `_extract_drugbank_url()` to search all traces and response text for DrugBank URL patterns
    - ✅ Implemented `_extract_source_urls()` to parse URLs from all agent traces and responses
    - ✅ Implemented `_transform_graph_to_admet()` to post-process Lambda KG output and ensure ADMET node labels are drug-prefixed
    - ✅ Implemented `_call_severity_lambda()` as direct Lambda invocation fallback when Reasoning Agent doesn't call calculate_severity
    - _Requirements: 7.4, 9.8, 11.6, 12.2, 12.3_
  
  - [ ]* 13.3 Write integration tests for agent_service
    - ⚠️ NO TESTS FOUND - Test coverage missing
    - Test CO-MAS pipeline execution with 1-3 iterations
    - Test Scorer gap identification and iteration retry logic
    - Test pipeline memory propagation across iterations
    - Test severity boost from pharmacodynamic evidence
    - _Requirements: 3.2, 3.3, 3.6, 4.1, 11.3, 18.2_

- [x] 14. Implement FastAPI REST and WebSocket endpoints
  - [x] 14.1 Create `backend/app/main.py` with all API endpoints
    - ✅ Implemented `GET /api/health` endpoint for system status
    - ✅ Implemented `POST /api/check` to start CO-MAS pipeline and return session_id
    - ✅ Implemented `WS /ws/{session_id}` for WebSocket streaming of pipeline events
    - ✅ Implemented `GET /api/interactions` to list recent curated interactions
    - ✅ Implemented `GET /` and `GET /{path}` to serve React frontend static files
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 13.1, 13.2, 13.3, 13.4_
  
  - [x] 14.2 Implement WebSocket event streaming in main.py
    - ✅ Streams events in order: pipeline_status → llm_call → agent_thinking → tool_call → tool_result → llm_response → agent_complete → pipeline_status(gap_identified) → complete
    - ✅ Parses Bedrock Agent trace events and forwards to client
    - ✅ Handles iteration retry events with gap feedback
    - _Requirements: 12.2, 12.3, 13.2, 13.3_
  
  - [ ]* 14.3 Write integration tests for FastAPI endpoints
    - ⚠️ NO TESTS FOUND - Test coverage missing
    - Test health endpoint returns correct system status
    - Test POST /api/check returns session_id
    - Test WebSocket streaming with mock agent responses
    - Test interactions list endpoint
    - _Requirements: 12.1, 12.2, 13.1_

- [x] 15. Implement CloudWatch logging and monitoring
  - [x] 15.1 Add CloudWatch logging to all Lambda functions
    - ✅ Logs execution time, input parameters (sanitized), success/failure status
    - ✅ Logs data source access (DynamoDB, PostgreSQL, S3, Tavily)
    - _Requirements: 20.1_
  
  - [x] 15.2 Add CloudWatch logging to FastAPI backend
    - ✅ Logs CO-MAS pipeline execution ID, iteration count, validation status
    - ✅ Logs curated database hit/miss rate
    - ✅ Logs web search API response time and rate limit status
    - ✅ Logs errors with stack traces and context
    - ✅ Logs slow PostgreSQL queries (>1s)
    - ✅ Logs Scorer results (score, gaps, evidence_quality)
    - _Requirements: 20.2, 20.3, 20.4, 20.5, 20.6, 20.7_
  
  - [ ] 15.3 Create CloudWatch custom metrics
    - ⚠️ PARTIALLY IMPLEMENTED - Metrics defined but not all emitted
    - Emit IterationCount metric (1-3)
    - Emit CuratedDBHitRate metric
    - Emit ScorerPassRate metric
    - _Requirements: 20.6_
  
  - [ ]* 15.4 Create CloudWatch alarms
    - ⚠️ NOT IMPLEMENTED - No alarms configured
    - High Iteration Count alarm (>2.5 average)
    - Lambda Errors alarm (>5%)
    - Slow Queries alarm (>1s)
    - Low Cache Hit Rate alarm (<20%)
    - API Rate Limits alarm (429 errors)
    - _Requirements: 20.6_

- [x] 16. Checkpoint - Verify backend functionality
  - ✅ REST endpoints tested and working
  - ✅ WebSocket streaming functional
  - ✅ CloudWatch logs being generated
  - ✅ CO-MAS pipeline executes with 1-3 iterations
  - ⚠️ Automated test suite missing

- [x] 17. Implement data preparation scripts
  - [x] 17.1 Create `scripts/imppat_pipeline.py` to load IMPPAT data to DynamoDB
    - ✅ Parses IMPPAT CSV files
    - ✅ Transforms to DynamoDB schema (PK: plant_name, SK: record_key)
    - ✅ Loads METADATA and PHYTO records for 5 hero plants (Curcuma longa, Glycyrrhiza glabra, Zingiber officinale, Hypericum perforatum, Withania somnifera)
    - _Requirements: 16.2, 16.3_
  
  - [ ] 17.2 Create script to populate PostgreSQL curated_interactions table
    - ⚠️ PARTIALLY IMPLEMENTED - Schema exists but curated data not populated
    - Need to load 10-15 hero scenarios with pre-computed responses
    - Include ADMET knowledge graphs, severity assessments, clinical effects, research citations
    - Use correct column name: `response_data` (not `interaction_data`)
    - _Requirements: 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 16.4_
  
  - [x] 17.3 Create script to upload reference data to S3
    - ✅ Uploaded name_mappings.json with 5 AYUSH plants
    - ✅ Uploaded cyp_enzymes.json with 10 CYP450 enzymes and severity weights
    - ✅ Uploaded nti_drugs.json with ~20 NTI drugs
    - _Requirements: 16.1_
  
  - [ ]* 17.4 Write validation tests for data preparation
    - ⚠️ NO TESTS FOUND - Test coverage missing
    - Verify DynamoDB records are correctly formatted
    - Verify PostgreSQL curated interactions are queryable
    - Verify S3 reference files are accessible
    - _Requirements: 16.1, 16.2, 16.4_

- [x] 18. Implement Docker deployment configuration
  - [x] 18.1 Create `Dockerfile` for FastAPI application
    - ✅ Uses Python 3.11-slim base image
    - ✅ Installs dependencies from requirements.txt
    - ✅ Configures uvicorn server
    - _Requirements: 15.2_
  
  - [x] 18.2 Create `docker-compose.yml` for multi-container deployment
    - ✅ Defined aushadhimitra-app service (FastAPI, port 8000)
    - ✅ Defined aushadhimitra-nginx service (Nginx, port 80/443)
    - ✅ Configured networking and volumes
    - _Requirements: 15.2_
  
  - [x] 18.3 Create `nginx.conf` for reverse proxy
    - ✅ Configured reverse proxy to FastAPI backend
    - ✅ Configured static file serving for React frontend
    - ✅ Configured WebSocket upgrade headers
    - _Requirements: 15.2_

- [x] 19. Implement React frontend for professional users
  - [x] 19.1 Create React components for interaction check interface
    - ✅ Created input form for AYUSH and allopathic medicine names (DrugInputForm.tsx)
    - ✅ Created severity badge component with color coding (NONE/MINOR/MODERATE/MAJOR)
    - ✅ Created tabbed panel with: Summary, Drug Info, Mechanisms, Reasoning, Graph, Sources (ResultPanel.tsx)
    - _Requirements: 13.1, 13.3, 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7_
  
  - [x] 19.2 Implement Cytoscape.js ADMET knowledge graph visualization
    - ✅ Parses JSON graph from backend response (KnowledgeGraphView.tsx)
    - ✅ Renders interactive graph with color-coded nodes: green (AYUSH plant), blue (allopathy drug), orange (ADMET property), red (CYP overlap)
    - ✅ Displays ADMET property nodes for BOTH drugs with drug-prefixed labels
    - ✅ Highlights CYP enzyme overlap nodes
    - _Requirements: 9.5, 9.6, 9.7, 9.8, 13.2, 14.6_
  
  - [x] 19.3 Implement WebSocket client for real-time trace streaming
    - ✅ Connects to WS /ws/{session_id} endpoint
    - ✅ Displays status updates, agent traces, tool calls, and validation events (LiveActivitySidebar.tsx, AgentCard.tsx)
    - ✅ Displays iteration retry events with gap feedback
    - ✅ Handles complete event and renders final response
    - _Requirements: 12.2, 12.3, 13.2, 13.3_
  
  - [x] 19.4 Implement TextWithLinks component for clickable URLs
    - ✅ Auto-detects URLs in mechanism descriptions, reasoning steps, and evidence text
    - ✅ Renders URLs as clickable links
    - ✅ Displays DrugBank URL in Drug Info tab
    - _Requirements: 12.2, 12.3, 12.4, 14.3, 14.4, 14.5, 14.7_
  
  - [ ]* 19.5 Write frontend component tests
    - ⚠️ NO TESTS FOUND - Test coverage missing
    - Test input form validation
    - Test severity badge rendering
    - Test ADMET knowledge graph rendering with mock data
    - Test WebSocket event handling
    - _Requirements: 13.1, 13.2, 14.1_

- [ ] 20. Implement React frontend for patient users
  - [ ] 20.1 Create simple chat interface for patient interactions
    - ⚠️ NOT IMPLEMENTED - Patient interface not built
    - Create chat message components
    - Implement conversational response display (4-5 sentences)
    - Support multilingual responses (Hindi, English, Hinglish)
    - _Requirements: 14.1, 14.2_
  
  - [ ] 20.2 Implement severity-based actionable advice
    - ⚠️ NOT IMPLEMENTED - Patient-specific advice not implemented
    - Display clear recommendations for MODERATE/MAJOR severity
    - Include "consult a doctor" recommendation for MODERATE/MAJOR
    - _Requirements: 14.3, 14.4_
  
  - [ ]* 20.3 Write frontend tests for patient interface
    - ⚠️ NOT IMPLEMENTED - No patient interface to test
    - Test chat message rendering
    - Test multilingual response display
    - _Requirements: 14.1, 14.2_

- [x] 21. Implement error handling and graceful degradation
  - [x] 21.1 Add error handling to all Lambda functions
    - ✅ Returns structured error responses for agent-level handling
    - ✅ Logs errors to CloudWatch with context
    - _Requirements: 17.1_
  
  - [x] 21.2 Add graceful degradation to agent_service.py
    - ✅ Handles partial data availability and continues with analysis
    - ✅ Indicates missing information in final response as gaps
    - ✅ Handles agent invocation failures and continues with available outputs
    - _Requirements: 17.2, 17.3, 16.2_
  
  - [x] 21.3 Add null guards to severity calculation
    - ✅ Handles None or empty interactions_data without raising exceptions
    - ✅ Returns default NONE result for missing data
    - _Requirements: 17.4, 11.5_
  
  - [x] 21.4 Add error handling to knowledge graph builder
    - ✅ Returns valid graph structure even with incomplete data
    - ✅ Includes available nodes and edges only
    - _Requirements: 17.6_
  
  - [x] 21.5 Add error handling to curated database lookup
    - ✅ Falls through to full CO-MAS analysis on lookup failure
    - ✅ Logs failures without blocking request
    - _Requirements: 17.5, 16.5_
  
  - [x] 21.6 Add timeout handling to web search Lambda
    - ✅ Handles Tavily API timeouts gracefully
    - ✅ Continues with cached or database data on failure
    - _Requirements: 17.7_

- [x] 22. Final integration and deployment
  - [x] 22.1 Deploy all Lambda functions to AWS
    - ✅ Ran deploy_lambdas.sh script (Python 3.11)
    - ✅ All functions deployed and accessible
    - _Requirements: 15.1_
  
  - [x] 22.2 Create and configure Bedrock Agents
    - ✅ Ran setup_agents.py script
    - ✅ All 5 agents created with correct action groups
    - _Requirements: 3.1, 8.1_
  
  - [~] 22.3 Load reference data to S3, DynamoDB, and PostgreSQL
    - ✅ S3 reference data uploaded
    - ✅ DynamoDB IMPPAT data loaded
    - ⚠️ PostgreSQL curated interactions table empty - needs hero scenarios
    - _Requirements: 16.1, 16.2, 16.4_
  
  - [x] 22.4 Deploy FastAPI backend with Docker Compose
    - ✅ Built Docker images (Python 3.11)
    - ✅ Containers running with docker-compose
    - ✅ Backend accessible on EC2
    - _Requirements: 15.2_
  
  - [x] 22.5 Deploy React frontend
    - ✅ Built production bundle
    - ✅ Static files served by Nginx
    - ✅ Frontend loads and connects to backend
    - _Requirements: 13.1, 14.1_

- [~] 23. Final checkpoint - End-to-end testing
  - ✅ Layer 0 curated database lookup functional (but no curated data loaded yet)
  - ✅ Full CO-MAS pipeline executes with 1-3 iterations
  - ✅ Scorer gap identification and iteration retry working
  - ✅ Pipeline memory propagation across iterations functional
  - ✅ Professional UI with ADMET knowledge graph visualization working
  - ⚠️ Patient chat interface not implemented
  - ✅ CloudWatch logs and metrics being generated
  - ⚠️ Comprehensive automated test suite missing

## Implementation Status Summary

### ✅ Completed (Core Functionality)
- All 7 Lambda functions implemented and deployed
- All 5 Bedrock Agents configured with action groups
- FastAPI backend with CO-MAS pipeline orchestration
- WebSocket streaming for real-time agent traces
- React frontend with professional UI
- ADMET-focused knowledge graph visualization
- Docker deployment configuration
- Error handling and graceful degradation
- CloudWatch logging infrastructure

### ⚠️ Partially Complete
- CloudWatch custom metrics (defined but not all emitted)
- PostgreSQL curated interactions (schema exists, no data loaded)
- Data preparation scripts (IMPPAT loaded, curated DB empty)

### ❌ Not Implemented
- Comprehensive unit test suite (0 tests found)
- Integration test suite
- Frontend component tests
- CloudWatch alarms
- Patient-facing chat interface
- Multilingual support for patient interface
- Curated hero scenarios (10-15 pre-computed interactions)

### 🎯 Recommended Next Steps
1. **HIGH PRIORITY**: Populate curated_interactions table with 10-15 hero scenarios for instant Layer 0 responses
2. **HIGH PRIORITY**: Create comprehensive test suite (unit + integration tests)
3. **MEDIUM PRIORITY**: Implement CloudWatch alarms for production monitoring
4. **MEDIUM PRIORITY**: Emit all defined CloudWatch custom metrics
5. **LOW PRIORITY**: Build patient-facing chat interface with multilingual support

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Tasks marked with `[x]` are completed
- Tasks marked with `[~]` are partially completed
- Tasks marked with `⚠️` indicate issues or missing components
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at key milestones
- All Lambda functions use Python 3.11
- FastAPI backend uses Python 3.11 with uvicorn
- Frontend uses React with Cytoscape.js for ADMET-focused knowledge graph visualization
- CO-MAS pipeline orchestrated directly by FastAPI — NO Bedrock Flows or DoWhile nodes
- 5 agents: Planner, AYUSH, Allopathy, Research, Reasoning
- Up to 3 self-improving iterations with deterministic Scorer and Pipeline Memory
- Endpoint names: POST /api/check, WS /ws/{session_id}

## Current Deployment Status

**AWS Infrastructure:**
- Region: us-east-1
- Account: 667736132441
- EC2 Instance: i-0dd48f5462906bc03 (Public IP: 3.210.198.169)
- S3 Bucket: ausadhi-mitra-667736132441
- DynamoDB Table: ausadhi-imppat (populated with 5 plants)
- PostgreSQL: scm-postgres.c2na6oc62pb7.us-east-1.rds.amazonaws.com:5432/aushadhimitra
- All Lambda functions deployed and operational
- All 5 Bedrock Agents configured and operational

**Application Status:**
- Backend: Running in Docker on EC2 (aushadhi-comas:latest)
- Frontend: Built and served by Nginx on port 80
- WebSocket streaming: Functional
- CO-MAS pipeline: Operational with 1-3 iterations
- ADMET knowledge graph: Rendering correctly

**Known Gaps:**
- No automated test coverage
- Curated interactions database empty (Layer 0 not functional)
- CloudWatch alarms not configured
- Patient interface not implemented
