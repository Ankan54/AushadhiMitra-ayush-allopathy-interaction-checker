# Implementation Plan: AYUSH-Allopathy Interaction Checker

## Overview

This implementation plan builds AushadhiMitra, an AI-powered drug interaction checker using a **CO-MAS (Cooperative Multi-Agent System) pipeline** orchestrated directly by the FastAPI backend. Five specialized AWS Bedrock Agents (Planner, AYUSH, Allopathy, Research, Reasoning) collaborate across up to 3 self-improving iterations to gather evidence, reason over it, and produce interaction assessments with severity scoring, ADMET-based knowledge graph visualization, and full source citations.

The system uses Python 3.11 for all backend components, Lambda functions, and deployment scripts. The frontend uses React with Cytoscape.js for ADMET-focused knowledge graph visualization. A tiered response architecture provides instant responses from a PostgreSQL curated database (Layer 0) and real-time multi-agent CO-MAS analysis for novel queries.

## Tasks

- [ ] 1. Set up AWS infrastructure and data stores
  - Create S3 bucket and upload reference data files (name_mappings.json, cyp_enzymes.json, nti_drugs.json)
  - Create DynamoDB table `ausadhi-imppat` with appropriate schema
  - Create PostgreSQL database `aushadhimitra` with tables: curated_interactions, interaction_sources, allopathy_cache
  - Store Tavily API key in AWS Secrets Manager
  - _Requirements: 15, 16_

- [ ] 2. Implement Lambda action groups for Planner Agent
  - [ ] 2.1 Create `planner_tools/handler.py` with identify_substances, check_curated_interaction, and create_execution_plan functions
    - Implement `identify_substances()` to extract AYUSH and allopathic medicine names from user input
    - Implement `check_curated_interaction()` to query PostgreSQL curated_interactions table using `response_data` column
    - Implement `create_execution_plan()` to persist structured execution plans with iteration-aware task lists
    - Use interaction_key format: "ayush_name:allopathy_name" (lowercase with underscores)
    - _Requirements: 1.1, 2.1, 2.8, 4.1, 4.2, 4.3, 5.1, 5.2_
  
  - [ ]* 2.2 Write unit tests for planner_tools Lambda functions
    - Test substance identification with various input formats
    - Test curated database lookup with hit/miss scenarios
    - Test execution plan creation with gap feedback
    - _Requirements: 4.1, 4.2, 5.1_

- [ ] 3. Implement Lambda action groups for AYUSH Collaborator Agent
  - [ ] 3.1 Create `ayush_data/handler.py` with name resolver, IMPPAT lookup, and CYP search functions
    - Implement `ayush_name_resolver()` to normalize plant names using S3 name_mappings.json
    - Implement `imppat_lookup()` to retrieve phytochemical and ADMET data from DynamoDB ausadhi-imppat table
    - Implement `search_cyp_interactions()` to perform Tavily web search for CYP effects
    - Handle data source failures gracefully and report data completeness
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 6.1_
  
  - [ ]* 3.2 Write unit tests for ayush_data Lambda functions
    - Test name resolution with common names, brand names, and scientific names
    - Test IMPPAT lookup with mock DynamoDB responses
    - Test CYP search with mock Tavily responses
    - _Requirements: 5.1, 5.2, 5.3, 6.1_

- [ ] 4. Implement Lambda action groups for Allopathy Collaborator Agent
  - [ ] 4.1 Create `allopathy_data/handler.py` with drug lookup and NTI check functions
    - Implement `allopathy_drug_lookup()` to retrieve drug data including DrugBank URL and ADMET properties
    - Implement `check_nti_status()` to check if drug is on Narrow Therapeutic Index list from S3
    - Handle data source failures gracefully
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 7.1, 7.2, 7.3, 7.4_
  
  - [ ]* 4.2 Write unit tests for allopathy_data Lambda functions
    - Test drug lookup with DrugBank URL extraction
    - Test NTI status check with known NTI drugs
    - Test ADMET property retrieval
    - _Requirements: 6.1, 6.2, 6.4, 7.1_

- [ ] 5. Implement Lambda action groups for Research Agent
  - [ ] 5.1 Create `research_tools/handler.py` with PubMed and clinical evidence search functions
    - Implement `search_clinical_evidence()` to search PubMed and clinical databases for interaction evidence
    - Implement source categorization (PubMed, clinical_study, review_article)
    - Extract and return source URLs with titles and snippets
    - _Requirements: 8.1, 8.2, 8.3_
  
  - [ ]* 5.2 Write unit tests for research_tools Lambda functions
    - Test PubMed search with mock responses
    - Test source categorization logic
    - Test URL extraction
    - _Requirements: 8.1, 8.2_

- [ ] 6. Implement web search Lambda action group
  - [ ] 6.1 Create `web_search/handler.py` with Tavily API integration
    - Implement `web_search()` function with source categorization (PubMed, DrugBank, FDA, research_paper, general)
    - Retrieve Tavily API key from AWS Secrets Manager
    - Handle API timeouts and rate limits gracefully
    - _Requirements: 8.3, 11.4, 17.7_
  
  - [ ]* 6.2 Write unit tests for web_search Lambda function
    - Test source categorization logic
    - Test error handling for API failures
    - _Requirements: 8.3_

- [ ] 7. Checkpoint - Ensure all Lambda functions deploy successfully
  - Deploy all Lambda functions using deploy_lambdas.sh script (Python 3.11)
  - Verify CloudWatch logs are being generated
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Implement Lambda action groups for Reasoning Collaborator Agent
  - [ ] 8.1 Create `reasoning_tools/handler.py` with ADMET knowledge graph builder
    - Implement `build_knowledge_graph()` to construct JSON graph with ADMET property nodes for BOTH drugs
    - Label ADMET nodes with drug-name prefix (e.g., "Curcuma: Metabolism", "Metformin: Absorption")
    - Label edges with "has \<property\>" format (e.g., "has Metabolism", "has Absorption")
    - Identify CYP enzyme overlap nodes (enzymes affected by both medicines) with type `cyp_enzyme_overlap`
    - Handle incomplete data gracefully and return valid graph structure
    - _Requirements: 7.2, 7.3, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 10.1, 10.2, 10.3, 17.6_
  
  - [ ] 8.2 Implement CYP-based severity calculation in reasoning_tools
    - Implement `calculate_severity()` with rule-based scoring: CYP overlap (weight × 2 for inhibition, × 1.5 for induction), NTI (+25)
    - Map scores to severity levels: 0-14 NONE, 15-34 MINOR, 35-59 MODERATE, 60+ MAJOR
    - Add null guard for None or empty interactions_data input
    - Return structured output with severity, severity_score, is_nti, scoring_factors
    - _Requirements: 7.4, 10.1, 10.2, 10.3, 10.4, 10.5, 11.1, 11.2, 11.3, 11.5, 11.6, 17.4_
  
  - [ ]* 8.3 Write unit tests for reasoning_tools Lambda functions
    - Test ADMET knowledge graph construction with various data inputs
    - Test CYP-based severity calculation with different interaction scenarios
    - Test null guard for empty interactions_data
    - _Requirements: 7.2, 7.4, 9.1, 11.1_

- [ ] 9. Implement shared utilities for Lambda functions
  - [ ] 9.1 Create `shared/bedrock_utils.py` with Bedrock Agent event handling utilities
    - Implement event parser for Bedrock Agent input format
    - Implement response formatter for Bedrock Agent output format
    - _Requirements: 8.2_
  
  - [ ] 9.2 Create `shared/db_utils.py` with database connection utilities
    - Implement PostgreSQL connection helper with connection pooling
    - Implement DynamoDB query helpers
    - Implement S3 reference data loader
    - Consolidate schema constants to prevent column name drift
    - _Requirements: 8.2, 15.1_

- [ ] 10. Create Bedrock Agents with action groups
  - [ ] 10.1 Create `scripts/setup_agents.py` to configure all 5 Bedrock agents
    - Create Planner Agent (Claude 3 Sonnet) with planner_tools action group
    - Create AYUSH Agent (Claude 3 Haiku) with ayush_data and web_search action groups
    - Create Allopathy Agent (Claude 3 Haiku) with allopathy_data and web_search action groups
    - Create Research Agent (Claude 3 Haiku) with research_tools and web_search action groups
    - Create Reasoning Agent (Claude 3 Sonnet) with reasoning_tools and web_search action groups
    - Generate OpenAPI schemas for all action groups
    - _Requirements: 3.1, 3.8, 8.1, 8.3_
  
  - [ ]* 10.2 Write integration tests for Bedrock Agent setup
    - Test agent creation and action group attachment
    - Test OpenAPI schema validation
    - _Requirements: 3.1, 8.1_

- [ ] 11. Checkpoint - Verify AWS Bedrock infrastructure
  - Test all 5 agents can be invoked individually
  - Verify action groups are correctly attached
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 12. Implement FastAPI backend core
  - [ ] 12.1 Create `backend/app/config.py` with environment-based configuration
    - Define agent IDs and aliases for all 5 agents (Planner, AYUSH, Allopathy, Research, Reasoning)
    - Define S3 bucket, PostgreSQL connection string
    - Define input validation rules
    - Set MAX_COMAS_ITERATIONS = 3
    - _Requirements: 15.1_
  
  - [ ] 12.2 Create `backend/app/models.py` with Pydantic validation models
    - Define InteractionRequest model (ayush_medicine, allopathy_drug, user_type)
    - Define HealthResponse model
    - _Requirements: 1.6_
  
  - [ ] 12.3 Create `backend/app/db.py` with PostgreSQL connection pool
    - Implement `lookup_curated()` for Layer 0 instant responses using `response_data` column
    - Implement `get_sources()` to retrieve source URLs
    - Implement `save_interaction()` to persist new results
    - Implement `list_interactions()` to return recent 20 interactions
    - _Requirements: 2.1, 11.1, 11.2, 11.3_
  
  - [ ]* 12.4 Write unit tests for FastAPI database utilities
    - Test curated lookup with various interaction keys
    - Test source retrieval
    - Test interaction persistence
    - _Requirements: 2.1_

- [ ] 13. Implement FastAPI CO-MAS pipeline orchestration service
  - [ ] 13.1 Create `backend/app/agent_service.py` with CO-MAS pipeline orchestrator
    - Implement `run_comas_pipeline()` to orchestrate up to 3 iterations of the CO-MAS pipeline
    - Implement `_invoke_planner()` with iteration-aware prompts (initial plan vs. gap-focused subsequent prompt)
    - Implement `_invoke_proposers()` to run AYUSH, Allopathy, and Research agents in parallel
    - Implement `_invoke_reasoning()` to run Reasoning (Evaluator) Agent with merged proposer context
    - Implement `_score_output()` deterministic scorer (0-100 scale across 8 dimensions)
    - Implement `_boost_severity_from_evidence()` to scan agent text for pharmacodynamic keywords and add PD boost
    - Implement pipeline memory management to track successes and pass to Planner in subsequent iterations
    - Parse and format agent trace events for WebSocket streaming
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 4.1, 4.2, 4.3, 4.4, 5.3, 5.4, 5.5, 11.3, 11.6, 17.2, 18.1, 18.2, 18.3_
  
  - [ ] 13.2 Implement helper functions in agent_service.py
    - Implement `_format_final_json()` to assemble final interaction_data dict from agent outputs
    - Implement `_extract_drugbank_url()` to search all traces and response text for DrugBank URL patterns
    - Implement `_extract_source_urls()` to parse URLs from all agent traces and responses
    - Implement `_transform_graph_to_admet()` to post-process Lambda KG output and ensure ADMET node labels are drug-prefixed
    - Implement `_call_severity_lambda()` as direct Lambda invocation fallback when Reasoning Agent doesn't call calculate_severity
    - _Requirements: 7.4, 9.8, 11.6, 12.2, 12.3_
  
  - [ ]* 13.3 Write integration tests for agent_service
    - Test CO-MAS pipeline execution with 1-3 iterations
    - Test Scorer gap identification and iteration retry logic
    - Test pipeline memory propagation across iterations
    - Test severity boost from pharmacodynamic evidence
    - _Requirements: 3.2, 3.3, 3.6, 4.1, 11.3, 18.2_

- [ ] 14. Implement FastAPI REST and WebSocket endpoints
  - [ ] 14.1 Create `backend/app/main.py` with all API endpoints
    - Implement `GET /api/health` endpoint for system status
    - Implement `POST /api/check` to start CO-MAS pipeline and return session_id
    - Implement `WS /ws/{session_id}` for WebSocket streaming of pipeline events
    - Implement `GET /api/interactions` to list recent curated interactions
    - Implement `GET /` and `GET /{path}` to serve React frontend static files
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 13.1, 13.2, 13.3, 13.4_
  
  - [ ] 14.2 Implement WebSocket event streaming in main.py
    - Stream events in order: pipeline_status → llm_call → agent_thinking → tool_call → tool_result → llm_response → agent_complete → pipeline_status(gap_identified) → complete
    - Parse Bedrock Agent trace events and forward to client
    - Handle iteration retry events with gap feedback
    - _Requirements: 12.2, 12.3, 13.2, 13.3_
  
  - [ ]* 14.3 Write integration tests for FastAPI endpoints
    - Test health endpoint returns correct system status
    - Test POST /api/check returns session_id
    - Test WebSocket streaming with mock agent responses
    - Test interactions list endpoint
    - _Requirements: 12.1, 12.2, 13.1_

- [ ] 15. Implement CloudWatch logging and monitoring
  - [ ] 15.1 Add CloudWatch logging to all Lambda functions
    - Log execution time, input parameters (sanitized), success/failure status
    - Log data source access (DynamoDB, PostgreSQL, S3, Tavily)
    - _Requirements: 20.1_
  
  - [ ] 15.2 Add CloudWatch logging to FastAPI backend
    - Log CO-MAS pipeline execution ID, iteration count, validation status
    - Log curated database hit/miss rate
    - Log web search API response time and rate limit status
    - Log errors with stack traces and context
    - Log slow PostgreSQL queries (>1s)
    - Log Scorer results (score, gaps, evidence_quality)
    - _Requirements: 20.2, 20.3, 20.4, 20.5, 20.6, 20.7_
  
  - [ ] 15.3 Create CloudWatch custom metrics
    - Emit IterationCount metric (1-3)
    - Emit CuratedDBHitRate metric
    - Emit ScorerPassRate metric
    - _Requirements: 20.6_
  
  - [ ]* 15.4 Create CloudWatch alarms
    - High Iteration Count alarm (>2.5 average)
    - Lambda Errors alarm (>5%)
    - Slow Queries alarm (>1s)
    - Low Cache Hit Rate alarm (<20%)
    - API Rate Limits alarm (429 errors)
    - _Requirements: 20.6_

- [ ] 16. Checkpoint - Verify backend functionality
  - Test REST endpoints with curl or Postman
  - Test WebSocket streaming with a WebSocket client
  - Verify CloudWatch logs are being generated
  - Test CO-MAS pipeline with 1-3 iterations
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 17. Implement data preparation scripts
  - [ ] 17.1 Create `scripts/imppat_pipeline.py` to load IMPPAT data to DynamoDB
    - Parse IMPPAT CSV files
    - Transform to DynamoDB schema (PK: plant_name, SK: record_key)
    - Load METADATA and PHYTO records for 5 hero plants (Curcuma longa, Glycyrrhiza glabra, Zingiber officinale, Hypericum perforatum, Withania somnifera)
    - _Requirements: 16.2, 16.3_
  
  - [ ] 17.2 Create script to populate PostgreSQL curated_interactions table
    - Load 10-15 hero scenarios with pre-computed responses
    - Include ADMET knowledge graphs, severity assessments, clinical effects, research citations
    - Use correct column name: `response_data` (not `interaction_data`)
    - _Requirements: 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 16.4_
  
  - [ ] 17.3 Create script to upload reference data to S3
    - Upload name_mappings.json with 5 AYUSH plants
    - Upload cyp_enzymes.json with 10 CYP450 enzymes and severity weights
    - Upload nti_drugs.json with ~20 NTI drugs
    - _Requirements: 16.1_
  
  - [ ]* 17.4 Write validation tests for data preparation
    - Verify DynamoDB records are correctly formatted
    - Verify PostgreSQL curated interactions are queryable
    - Verify S3 reference files are accessible
    - _Requirements: 16.1, 16.2, 16.4_

- [ ] 18. Implement Docker deployment configuration
  - [ ] 18.1 Create `Dockerfile` for FastAPI application
    - Use Python 3.11-slim base image
    - Install dependencies from requirements.txt
    - Configure uvicorn server
    - _Requirements: 15.2_
  
  - [ ] 18.2 Create `docker-compose.yml` for multi-container deployment
    - Define aushadhimitra-app service (FastAPI, port 8000)
    - Define aushadhimitra-nginx service (Nginx, port 80/443)
    - Configure networking and volumes
    - _Requirements: 15.2_
  
  - [ ] 18.3 Create `nginx.conf` for reverse proxy
    - Configure reverse proxy to FastAPI backend
    - Configure static file serving for React frontend
    - Configure WebSocket upgrade headers
    - _Requirements: 15.2_

- [ ] 19. Implement React frontend for professional users
  - [ ] 19.1 Create React components for interaction check interface
    - Create input form for AYUSH and allopathic medicine names
    - Create severity badge component with color coding (NONE/MINOR/MODERATE/MAJOR)
    - Create tabbed panel with: Summary, Drug Info, Mechanisms, Reasoning, Graph, Sources
    - _Requirements: 13.1, 13.3, 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7_
  
  - [ ] 19.2 Implement Cytoscape.js ADMET knowledge graph visualization
    - Parse JSON graph from backend response
    - Render interactive graph with color-coded nodes: green (AYUSH plant), blue (allopathy drug), orange (ADMET property), red (CYP overlap)
    - Display ADMET property nodes for BOTH drugs with drug-prefixed labels
    - Highlight CYP enzyme overlap nodes
    - _Requirements: 9.5, 9.6, 9.7, 9.8, 13.2, 14.6_
  
  - [ ] 19.3 Implement WebSocket client for real-time trace streaming
    - Connect to WS /ws/{session_id} endpoint
    - Display status updates, agent traces, tool calls, and validation events
    - Display iteration retry events with gap feedback
    - Handle complete event and render final response
    - _Requirements: 12.2, 12.3, 13.2, 13.3_
  
  - [ ] 19.4 Implement TextWithLinks component for clickable URLs
    - Auto-detect URLs in mechanism descriptions, reasoning steps, and evidence text
    - Render URLs as clickable links
    - Display DrugBank URL in Drug Info tab
    - _Requirements: 12.2, 12.3, 12.4, 14.3, 14.4, 14.5, 14.7_
  
  - [ ]* 19.5 Write frontend component tests
    - Test input form validation
    - Test severity badge rendering
    - Test ADMET knowledge graph rendering with mock data
    - Test WebSocket event handling
    - _Requirements: 13.1, 13.2, 14.1_

- [ ] 20. Implement React frontend for patient users
  - [ ] 20.1 Create simple chat interface for patient interactions
    - Create chat message components
    - Implement conversational response display (4-5 sentences)
    - Support multilingual responses (Hindi, English, Hinglish)
    - _Requirements: 14.1, 14.2_
  
  - [ ] 20.2 Implement severity-based actionable advice
    - Display clear recommendations for MODERATE/MAJOR severity
    - Include "consult a doctor" recommendation for MODERATE/MAJOR
    - _Requirements: 14.3, 14.4_
  
  - [ ]* 20.3 Write frontend tests for patient interface
    - Test chat message rendering
    - Test multilingual response display
    - _Requirements: 14.1, 14.2_

- [ ] 21. Implement error handling and graceful degradation
  - [ ] 21.1 Add error handling to all Lambda functions
    - Return structured error responses for agent-level handling
    - Log errors to CloudWatch with context
    - _Requirements: 17.1_
  
  - [ ] 21.2 Add graceful degradation to agent_service.py
    - Handle partial data availability and continue with analysis
    - Indicate missing information in final response as gaps
    - Handle agent invocation failures and continue with available outputs
    - _Requirements: 17.2, 17.3, 16.2_
  
  - [ ] 21.3 Add null guards to severity calculation
    - Handle None or empty interactions_data without raising exceptions
    - Return default NONE result for missing data
    - _Requirements: 17.4, 11.5_
  
  - [ ] 21.4 Add error handling to knowledge graph builder
    - Return valid graph structure even with incomplete data
    - Include available nodes and edges only
    - _Requirements: 17.6_
  
  - [ ] 21.5 Add error handling to curated database lookup
    - Fall through to full CO-MAS analysis on lookup failure
    - Log failures without blocking request
    - _Requirements: 17.5, 16.5_
  
  - [ ] 21.6 Add timeout handling to web search Lambda
    - Handle Tavily API timeouts gracefully
    - Continue with cached or database data on failure
    - _Requirements: 17.7_

- [ ] 22. Final integration and deployment
  - [ ] 22.1 Deploy all Lambda functions to AWS
    - Run deploy_lambdas.sh script (Python 3.11)
    - Verify all functions are deployed and accessible
    - _Requirements: 15.1_
  
  - [ ] 22.2 Create and configure Bedrock Agents
    - Run setup_agents.py script
    - Verify all 5 agents are created with correct action groups
    - _Requirements: 3.1, 8.1_
  
  - [ ] 22.3 Load reference data to S3, DynamoDB, and PostgreSQL
    - Run data preparation scripts
    - Verify all data stores are populated
    - _Requirements: 16.1, 16.2, 16.4_
  
  - [ ] 22.4 Deploy FastAPI backend with Docker Compose
    - Build Docker images (Python 3.11)
    - Start containers with docker-compose up
    - Verify backend is accessible
    - _Requirements: 15.2_
  
  - [ ] 22.5 Deploy React frontend
    - Build production bundle
    - Copy static files to Nginx serve directory
    - Verify frontend loads and connects to backend
    - _Requirements: 13.1, 14.1_

- [ ] 23. Final checkpoint - End-to-end testing
  - Test Layer 0 curated database responses (<500ms)
  - Test full CO-MAS pipeline with 1-3 iterations
  - Test Scorer gap identification and iteration retry
  - Test pipeline memory propagation across iterations
  - Test professional UI with ADMET knowledge graph visualization
  - Test patient chat interface with multilingual responses
  - Verify CloudWatch logs and metrics are being generated
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at key milestones
- All Lambda functions use Python 3.11 (changed from 3.12)
- FastAPI backend uses Python 3.11 with uvicorn
- Frontend uses React with Cytoscape.js for ADMET-focused knowledge graph visualization
- CO-MAS pipeline orchestrated directly by FastAPI — NO Bedrock Flows or DoWhile nodes
- 5 agents: Planner, AYUSH, Allopathy, Research (new), Reasoning
- Up to 3 self-improving iterations with deterministic Scorer and Pipeline Memory
- Endpoint names: POST /api/check, WS /ws/{session_id}
