# Backend Steering File - AushadhiMitra

## Purpose
FastAPI backend with WebSocket streaming for real-time agent trace events. Orchestrates CO-MAS (Cooperative Multi-Agent System) pipeline with up to 3 self-improving iterations.

## Key Responsibilities
- REST API endpoints for interaction checking
- WebSocket streaming of agent execution traces
- CO-MAS pipeline orchestration (Planner → Proposers → Evaluator → Scorer)
- PostgreSQL integration for curated interactions and caching
- Request validation using Pydantic models
- Pipeline memory management across iterations

## Critical Implementation Details

### CO-MAS Pipeline Architecture
1. **Layer 0**: Curated database lookup (instant <500ms response)
2. **CO-MAS Pipeline**: Up to 3 iterations with deterministic Scorer
   - Planner Agent (iteration-aware prompts)
   - Proposer Agents (AYUSH, Allopathy, Research in parallel)
   - Evaluator Agent (Reasoning)
   - Scorer (deterministic Python function)
3. **Pipeline Memory**: Tracks successes across iterations to avoid redundant work

### WebSocket Event Stream Order
```
pipeline_status → llm_call → agent_thinking → tool_call → tool_result → 
llm_response → agent_complete → pipeline_status(gap_identified) → complete
```

### Key Files
- `backend/app/main.py`: FastAPI app, endpoints, WebSocket handler
- `backend/app/agent_service.py`: CO-MAS pipeline orchestration
- `backend/app/config.py`: Environment config, 5 agent IDs, MAX_COMAS_ITERATIONS=3
- `backend/app/db.py`: PostgreSQL connection pool and queries
- `backend/app/models.py`: Pydantic request/response models
- `backend/app/cloudwatch_logger.py`: CloudWatch logging utilities

### API Endpoints
- `GET /api/health`: System status, agent IDs, DB config
- `POST /api/check`: Start CO-MAS pipeline, returns session_id
- `WS /ws/{session_id}`: Real-time stream of pipeline events
- `GET /api/interactions`: List recent 20 curated interactions
- `GET /` and `GET /{path}`: Serve React frontend static files

### Database Schema (PostgreSQL)
```sql
-- Curated interactions (Layer 0 instant responses)
curated_interactions (
  interaction_key VARCHAR PK,  -- "ayush_name:allopathy_name"
  ayush_name VARCHAR,
  allopathy_name VARCHAR,
  severity VARCHAR,
  response_data JSONB,  -- CRITICAL: Use response_data, not interaction_data
  knowledge_graph JSONB,
  created_at TIMESTAMP
)

-- Allopathy drug cache (7-day TTL)
allopathy_cache (
  drug_name VARCHAR PK,
  generic_name VARCHAR,
  drug_data JSONB,
  sources JSONB,
  cached_at TIMESTAMP,
  expires_at TIMESTAMP
)

-- Source citations
interaction_sources (
  source_id SERIAL PK,
  interaction_key VARCHAR FK,
  url TEXT,
  title TEXT,
  snippet TEXT,
  category VARCHAR
)
```

### Known Issues & Mitigations
1. **No Test Coverage**: Zero unit/integration tests - HIGH PRIORITY to add
2. **Curated DB Empty**: Layer 0 not functional - need to populate hero scenarios
3. **Column Name Alignment**: Use `response_data` not `interaction_data`
4. **Null Safety**: Handle None values in severity calculation

### Environment Variables
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
POSTGRES_HOST=scm-postgres.c2na6oc62pb7.us-east-1.rds.amazonaws.com
POSTGRES_DB=aushadhimitra
POSTGRES_USER=...
POSTGRES_PASSWORD=...
```

### Deployment
- Docker + Nginx reverse proxy
- `docker-compose.yml`: FastAPI app (port 8000) + Nginx (port 80)
- `Dockerfile`: Python 3.11-slim base image
- `nginx.conf`: Reverse proxy, static file serving, WebSocket upgrade headers
- EC2 Instance: i-0dd48f5462906bc03 (Public IP: 3.210.198.169)

### Testing Priorities
1. WebSocket event streaming order
2. CO-MAS pipeline execution with 1-3 iterations
3. Curated DB lookup (Layer 0 instant response) - BLOCKED: no curated data
4. Null handling in agent responses
5. PostgreSQL connection pool under load
6. Pipeline memory propagation across iterations
7. Scorer gap identification and iteration retry logic
