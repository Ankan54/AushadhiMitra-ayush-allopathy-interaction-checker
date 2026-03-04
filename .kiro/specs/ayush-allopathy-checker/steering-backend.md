# Backend Steering File - AushadhiMitra

## Purpose
FastAPI backend with WebSocket streaming for real-time agent trace events. Orchestrates Bedrock Flow V4 execution with Pipeline Mode fallback.

## Key Responsibilities
- REST API endpoints for interaction checking
- WebSocket streaming of agent execution traces
- Bedrock Flow V4 orchestration with DoWhile validation loop
- Automatic fallback to Pipeline Mode on Flow timeout
- PostgreSQL integration for curated interactions and caching
- Request validation using Pydantic models

## Critical Implementation Details

### Execution Modes
1. **Flow Mode** (Primary): Invoke Bedrock Flow V4 with DoWhile loop
2. **Pipeline Mode** (Fallback): Direct sequential agent invocation when Flow times out
3. **Auto Mode**: Attempt Flow, fallback to Pipeline on timeout

### WebSocket Event Stream Order
```
status → trace → agent_complete → validation → response_chunk → complete
```

### Key Files
- `backend/app/main.py`: FastAPI app, endpoints, WebSocket handler
- `backend/app/agent_service.py`: Bedrock Flow/Pipeline orchestration
- `backend/app/config.py`: Environment config, agent IDs, Flow ID
- `backend/app/db.py`: PostgreSQL connection pool and queries
- `backend/app/models.py`: Pydantic request/response models

### API Endpoints
- `GET /api/health`: System status, agent IDs, Flow ID, DB config
- `POST /api/check-interaction`: Synchronous interaction check
- `WS /ws/check-interaction`: Asynchronous WebSocket stream
- `GET /api/interactions`: List recent 20 curated interactions
- `GET /`: Serve React frontend static files

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
1. **Bedrock Flow V4 Timeout**: Auto-fallback to Pipeline Mode
2. **Column Name Mismatch**: Use `response_data` not `interaction_data`
3. **Null Safety**: Handle None values in severity calculation

### Environment Variables
```
AWS_REGION=us-east-1
PLANNER_AGENT_ID=...
AYUSH_AGENT_ID=...
ALLOPATHY_AGENT_ID=...
REASONING_AGENT_ID=...
FLOW_ID=...
FLOW_ALIAS_ID=...
POSTGRES_HOST=scm-postgres.c2na6oc62pb7.us-east-1.rds.amazonaws.com
POSTGRES_DB=aushadhimitra
POSTGRES_USER=...
POSTGRES_PASSWORD=...
```

### Deployment
- Docker + Nginx reverse proxy
- `docker-compose.yml`: FastAPI app (port 8000) + Nginx (port 80/443)
- `Dockerfile`: Python 3.12-slim base image
- `nginx.conf`: Reverse proxy, static file serving

### Testing Priorities
1. WebSocket event streaming order
2. Flow timeout → Pipeline fallback
3. Curated DB lookup (Layer 0 instant response)
4. Null handling in agent responses
5. PostgreSQL connection pool under load
