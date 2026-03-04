# AushadhiMitra - AYUSH-Allopathy Drug Interaction Checker

## Overview

AushadhiMitra is an AI-powered drug interaction checker that identifies potential interactions between AYUSH (traditional Indian medicine) and allopathic (modern pharmaceutical) medicines. The system uses AWS Bedrock Agents with a Bedrock Flow V4 DoWhile validation loop to orchestrate multi-agent analysis with real-time data gathering and grounded reasoning.

## Key Features

- **Instant Responses**: Layer 0 curated database for high-impact interactions (<500ms)
- **Real-Time Analysis**: Multi-agent system with web search and database lookups
- **Self-Validating**: DoWhile loop ensures data completeness (max 3 iterations)
- **Interactive Knowledge Graph**: Cytoscape.js visualization of interaction pathways
- **Dual UX**: Professional UI for practitioners, simple chat for patients
- **Multilingual**: Hindi, English, and Hinglish support
- **Full Citations**: Every claim backed by source URLs (PubMed, DrugBank, IMPPAT)
- **Graceful Degradation**: Auto-fallback to Pipeline Mode on Flow timeout

## Architecture

### AWS Services
- **Amazon Bedrock Agents**: 4 agents (Planner, AYUSH, Allopathy, Reasoning)
- **Amazon Bedrock Flows**: DoWhile validation loop orchestration
- **AWS Lambda**: 12 functions for deterministic business logic
- **Amazon S3**: Reference data (name mappings, CYP enzymes, NTI drugs)
- **Amazon DynamoDB**: IMPPAT phytochemical database
- **Amazon RDS PostgreSQL**: Curated interactions, allopathy cache, sources
- **FastAPI + Docker**: Backend with WebSocket streaming
- **React + Cytoscape.js**: Frontend with interactive graph visualization

### Agent Models
- **Planner Agent**: Claude 3 Sonnet (routing and substance identification)
- **AYUSH Agent**: Claude 3 Haiku (phytochemical data gathering)
- **Allopathy Agent**: Claude 3 Haiku (drug metabolism data gathering)
- **Reasoning Agent**: Claude 3 Sonnet (analysis, validation, response formatting)
- **Data Merge**: Amazon Nova Pro (data consolidation)

## Document Structure

### Core Specification
- **requirements.md**: EARS-compliant requirements with INCOSE quality rules
- **design.md**: Technical architecture and component details
- **.config.kiro**: Workflow configuration (requirements-first, feature spec)

### Steering Files
- **steering-backend.md**: FastAPI backend, WebSocket streaming, execution modes
- **steering-lambda.md**: Lambda functions, action groups, data sources
- **steering-bedrock-agents.md**: Agent configuration, Flow V4 structure, DoWhile loop
- **steering-frontend.md**: React UI, Cytoscape.js, WebSocket integration
- **steering-data-preparation.md**: S3, DynamoDB, PostgreSQL data loading
- **steering-deployment.md**: Deployment steps, monitoring, operations, troubleshooting

## Quick Start

### Prerequisites
- AWS Account (ID: 667736132441)
- Bedrock model access (Claude 3 Sonnet, Haiku, Nova Pro)
- Python 3.12+
- Node.js 18+
- Docker & Docker Compose
- PostgreSQL client

### Deployment (5-Day Plan)

**Day 1: Data Preparation**
```bash
# Upload S3 reference files
aws s3 cp reference/ s3://ausadhi-mitra-667736132441/reference/ --recursive

# Load DynamoDB IMPPAT data
python scripts/imppat_pipeline.py --plant curcuma_longa

# Initialize PostgreSQL
psql -h scm-postgres... -d aushadhimitra -f scripts/create_tables.sql
python scripts/load_curated_interactions.py
```

**Day 2: Lambda Deployment**
```bash
cd lambda
./deploy_lambdas.sh
```

**Day 3: Bedrock Agents Setup**
```bash
python scripts/setup_agents.py
python scripts/create_flow_v4.py
```

**Day 4: Backend Deployment**
```bash
cd backend
docker-compose up -d
```

**Day 5: Frontend Deployment**
```bash
cd frontend
npm install && npm run build
cp -r dist/* ../backend/static/
```

### Testing
```bash
# Health check
curl http://localhost/api/health

# Test interaction check
curl -X POST http://localhost/api/check-interaction \
  -H "Content-Type: application/json" \
  -d '{"ayush_medicine": "turmeric", "allopathy_drug": "warfarin", "user_type": "professional"}'
```

## Key Design Decisions

### 1. Tiered Response Architecture
- **Layer 0**: Curated database for instant responses (<500ms)
- **Layer 1**: Real-time multi-agent analysis with DoWhile validation
- **Fallback**: Pipeline Mode when Bedrock Flow times out

### 2. DoWhile Validation Loop
- Self-correcting: Re-runs analysis if data is incomplete
- Max 3 iterations to prevent infinite loops
- Validation status: PASSED (exit) or NEEDS_MORE_DATA (retry)

### 3. Grounded Reasoning
- Agents use ONLY Lambda-provided evidence
- No hallucination from model's internal knowledge
- Every claim cited with source URL

### 4. Severity Scoring Algorithm
```
Base score: 0
+ 15 points × (shared CYP enzymes)
+ 25 points (NTI drug)
+ 20 points (clinical evidence)
+ 15 points (pharmacodynamic overlap)

0-20 = NONE | 21-40 = MINOR | 41-60 = MODERATE | 61+ = MAJOR
```

### 5. WebSocket Streaming
Real-time event stream: `status → trace → agent_complete → validation → response_chunk → complete`

## Known Issues & Mitigations

| Issue | Mitigation |
|-------|-----------|
| Bedrock Flow V4 timeout | Auto-fallback to Pipeline Mode |
| Column name mismatch (interaction_data vs response_data) | Use `response_data` in Lambda |
| NoneType error in calculate_severity() | Add null guard |
| Empty knowledge graph | Ensure valid structure always returned |

## Performance Targets

| Component | Target | Acceptable | Critical |
|-----------|--------|------------|----------|
| Layer 0 (Curated) | <500ms | <1s | >2s |
| Full Analysis (Flow) | <30s | <45s | >60s |
| Lambda Execution | <3s | <5s | >10s |
| PostgreSQL Query | <100ms | <500ms | >1s |

## Hero Scenarios (Curated Database)

High-impact interaction pairs pre-loaded for instant responses:

1. **Turmeric + Warfarin** (MAJOR): CYP2C9 inhibition → bleeding risk
2. **St. John's Wort + Cyclosporine** (MAJOR): CYP3A4 induction → organ rejection
3. **Licorice + Digoxin** (MAJOR): Potassium depletion → arrhythmia
4. **Ginger + Warfarin** (MODERATE): Additive anticoagulant effect
5. **Turmeric + Metformin** (MODERATE): Additive hypoglycemia
6. **St. John's Wort + Oral Contraceptives** (MAJOR): Contraceptive failure
7. **Licorice + Furosemide** (MODERATE): Severe potassium depletion
8. **Ginger + Aspirin** (MODERATE): Additive antiplatelet effect

## Monitoring

### CloudWatch Metrics
- Flow timeout rate (alert if >20%)
- Curated DB hit rate (target >30%)
- Lambda error rate (alert if >5%)
- DoWhile loop iterations (average 1-2)

### CloudWatch Logs
- `/aws/lambda/planner_tools`
- `/aws/lambda/ayush_data`
- `/aws/lambda/allopathy_data`
- `/aws/lambda/reasoning_tools`
- `/ecs/aushadhimitra-backend`

## Data Sources

### IMPPAT (Indian Medicinal Plants Database)
- 5 key plants loaded: Turmeric, Licorice, Ginger, St. John's Wort, Ashwagandha
- ~1000 phytochemical records with CYP interaction data

### DrugBank (via Tavily Web Search)
- CYP metabolism pathways
- Drug-drug interaction data
- ADMET properties

### PubMed (via Tavily Web Search)
- Clinical case reports
- Research studies
- Evidence hierarchy: Clinical > In Vivo > In Vitro > Computational

## Security & Compliance

- **PII Handling**: No patient data stored; queries are ephemeral
- **Medical Disclaimer**: All responses include disclaimer to consult healthcare professional
- **Source Attribution**: Full transparency with clickable citations
- **IAM Roles**: Least-privilege access for all AWS services
- **Secrets Management**: Tavily API key in AWS Secrets Manager

## Future Enhancements

1. **Expanded Database**: Add 50+ AYUSH plants to IMPPAT
2. **Mobile App**: Native iOS/Android apps with offline mode
3. **Clinical Integration**: FHIR API for EHR integration
4. **Pharmacist Dashboard**: Review and approve AI-generated responses
5. **User Feedback Loop**: Collect practitioner feedback to improve curated DB
6. **Multi-Region Deployment**: DR setup in us-west-2
7. **Advanced Analytics**: ML model for interaction prediction

## Contributing

See individual steering files for component-specific development guidelines:
- Backend: `steering-backend.md`
- Lambda: `steering-lambda.md`
- Agents: `steering-bedrock-agents.md`
- Frontend: `steering-frontend.md`
- Data: `steering-data-preparation.md`
- Ops: `steering-deployment.md`

## License

[License Information]

## Contact

- **Project Lead**: [Name]
- **AWS Account**: 667736132441
- **Region**: us-east-1
- **Support**: [Email]

---

**Last Updated**: 2024-01-15  
**Spec Version**: 1.0  
**Workflow Type**: Requirements-First  
**Spec Type**: Feature
