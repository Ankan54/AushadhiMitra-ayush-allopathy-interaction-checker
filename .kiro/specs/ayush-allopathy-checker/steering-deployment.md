# Deployment & Operations Steering File - AushadhiMitra

## Purpose
Complete deployment guide and operational procedures for AushadhiMitra drug interaction checker on AWS infrastructure.

## AWS Account Configuration
- **Account ID**: 667736132441
- **Primary Region**: us-east-1 (US East - N. Virginia)
- **Backup Region**: us-west-2 (for disaster recovery)

---

## Pre-Deployment Checklist

### AWS Services Setup
- [ ] AWS Bedrock access enabled in account
- [ ] Claude 3 Sonnet model access granted
- [ ] Claude 3 Haiku model access granted
- [ ] Amazon Nova Pro model access granted
- [ ] S3 bucket created: `ausadhi-mitra-667736132441`
- [ ] DynamoDB table created: `ausadhi-imppat`
- [ ] RDS PostgreSQL instance running: `scm-postgres.c2na6oc62pb7.us-east-1.rds.amazonaws.com`
- [ ] EC2 instance provisioned for Docker deployment
- [ ] VPC and security groups configured
- [ ] IAM roles and policies created

### IAM Roles Required

#### 1. BedrockFlowExecutionRole
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeAgent",
        "bedrock:InvokeModel"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "lambda:InvokeFunction"
      ],
      "Resource": "arn:aws:lambda:us-east-1:667736132441:function:*"
    }
  ]
}
```

#### 2. LambdaExecutionRole
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:us-east-1:667736132441:*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:Query",
        "dynamodb:BatchGetItem"
      ],
      "Resource": "arn:aws:dynamodb:us-east-1:667736132441:table/ausadhi-imppat"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::ausadhi-mitra-667736132441/reference/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:us-east-1:667736132441:secret:tavily-api-key-*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "rds-db:connect"
      ],
      "Resource": "arn:aws:rds-db:us-east-1:667736132441:dbuser:*/*"
    }
  ]
}
```

#### 3. EC2InstanceRole (for FastAPI backend)
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeAgent",
        "bedrock:InvokeFlow"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "cloudwatch:PutMetricData"
      ],
      "Resource": "*"
    }
  ]
}
```

---

## Deployment Steps

### Phase 1: Data Preparation (Day 1)

#### 1.1 Upload S3 Reference Files
```bash
# Upload reference data
aws s3 cp reference/name_mappings.json s3://ausadhi-mitra-667736132441/reference/
aws s3 cp reference/cyp_enzymes.json s3://ausadhi-mitra-667736132441/reference/
aws s3 cp reference/nti_drugs.json s3://ausadhi-mitra-667736132441/reference/

# Verify uploads
aws s3 ls s3://ausadhi-mitra-667736132441/reference/
```

#### 1.2 Load DynamoDB IMPPAT Data
```bash
# Load each plant's data
python scripts/imppat_pipeline.py --plant curcuma_longa --csv data/imppat_curcuma.csv
python scripts/imppat_pipeline.py --plant glycyrrhiza_glabra --csv data/imppat_glycyrrhiza.csv
python scripts/imppat_pipeline.py --plant zingiber_officinale --csv data/imppat_zingiber.csv
python scripts/imppat_pipeline.py --plant hypericum_perforatum --csv data/imppat_hypericum.csv
python scripts/imppat_pipeline.py --plant withania_somnifera --csv data/imppat_withania.csv

# Verify record counts
aws dynamodb scan --table-name ausadhi-imppat --select COUNT
```

#### 1.3 Initialize PostgreSQL Database
```bash
# Connect to PostgreSQL
psql -h scm-postgres.c2na6oc62pb7.us-east-1.rds.amazonaws.com -U admin -d aushadhimitra

# Create tables
\i scripts/create_tables.sql

# Load curated interactions
python scripts/load_curated_interactions.py

# Verify data
SELECT COUNT(*) FROM curated_interactions;
SELECT COUNT(*) FROM allopathy_cache;
SELECT COUNT(*) FROM interaction_sources;
```

### Phase 2: Lambda Deployment (Day 2)

#### 2.1 Package Lambda Functions
```bash
# Navigate to lambda directory
cd lambda

# Deploy all Lambda functions
./deploy_lambdas.sh

# Verify deployments
aws lambda list-functions --query 'Functions[?starts_with(FunctionName, `ausadhi`)].FunctionName'
```

#### 2.2 Test Lambda Functions
```bash
# Test planner_tools
aws lambda invoke --function-name planner_tools \
  --payload '{"action": "identify_substances", "parameters": {"user_input": "turmeric and warfarin"}}' \
  response.json

# Test ayush_data
aws lambda invoke --function-name ayush_data \
  --payload '{"action": "imppat_lookup", "parameters": {"scientific_name": "Curcuma longa"}}' \
  response.json

# Test allopathy_data
aws lambda invoke --function-name allopathy_data \
  --payload '{"action": "check_nti_status", "parameters": {"drug_name": "Warfarin"}}' \
  response.json

# Test reasoning_tools
aws lambda invoke --function-name reasoning_tools \
  --payload '{"action": "calculate_severity", "parameters": {"interactions_data": {...}, "is_nti": true}}' \
  response.json
```

### Phase 3: Bedrock Agents Setup (Day 3)

#### 3.1 Create Bedrock Agents
```bash
# Run agent setup script
python scripts/setup_agents.py

# This creates:
# - Planner Agent (Claude 3 Sonnet)
# - AYUSH Collaborator Agent (Claude 3 Haiku)
# - Allopathy Collaborator Agent (Claude 3 Haiku)
# - Reasoning Collaborator Agent (Claude 3 Sonnet)

# Save agent IDs to .env file
```

#### 3.2 Create Bedrock Flow V4
```bash
# Create DoWhile validation flow
python scripts/create_flow_v4.py

# Save flow ID and alias ID to .env file
```

#### 3.3 Test Agents
```bash
# Test Planner Agent
python scripts/test_agent.py --agent planner --query "Check turmeric and warfarin"

# Test full flow
python scripts/test_flow.py --flow-id <flow-id> --query "Check turmeric and warfarin"
```

### Phase 4: Backend Deployment (Day 4)

#### 4.1 Configure Environment
```bash
# Create .env file
cat > backend/.env << EOF
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
POSTGRES_HOST=scm-postgres.c2na6oc62pb7.us-east-1.rds.amazonaws.com
POSTGRES_DB=aushadhimitra
POSTGRES_USER=admin
POSTGRES_PASSWORD=<password>
EOF
```

#### 4.2 Build and Deploy Docker Containers
```bash
# Navigate to backend directory
cd backend

# Build Docker image
docker build -t aushadhimitra-backend:latest .

# Run with docker-compose
docker-compose up -d

# Verify containers running
docker ps

# Check logs
docker logs aushadhimitra-app
docker logs aushadhimitra-nginx
```

#### 4.3 Test Backend Endpoints
```bash
# Health check
curl http://localhost/api/health

# Synchronous interaction check
curl -X POST http://localhost/api/check-interaction \
  -H "Content-Type: application/json" \
  -d '{"ayush_medicine": "turmeric", "allopathy_drug": "warfarin", "user_type": "professional"}'

# List curated interactions
curl http://localhost/api/interactions
```

### Phase 5: Frontend Deployment (Day 5)

#### 5.1 Build Frontend
```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Build production bundle
npm run build

# Copy to backend static directory
cp -r dist/* ../backend/static/
```

#### 5.2 Test Frontend
```bash
# Open browser
open http://localhost

# Test professional UI
# Test patient chat UI
# Test WebSocket streaming
# Test knowledge graph rendering
```

---

## Post-Deployment Verification

### Functional Tests

#### Test 1: Layer 0 Curated Response
```bash
# Query: Turmeric + Warfarin (should hit curated DB)
# Expected: Response in <500ms with pre-built knowledge graph
# Verify: Check logs for "Curated DB hit"
```

#### Test 2: Full Analysis with DoWhile Loop
```bash
# Query: Ashwagandha + Metformin (not in curated DB)
# Expected: Full agent analysis with 1-2 loop iterations
# Verify: Check logs for "DoWhile loop completed" with iteration count
```

#### Test 3: Pipeline Fallback
```bash
# Simulate Flow timeout (if possible)
# Expected: Automatic fallback to Pipeline Mode
# Verify: Check logs for "Switching to Pipeline Mode"
```

#### Test 4: Error Handling
```bash
# Query with invalid medicine name
# Expected: Graceful error message, no crash
# Verify: Check logs for error handling
```

### Performance Tests

#### Test 1: Layer 0 Response Time
```bash
# Run 10 queries to curated interactions
# Measure: Average response time
# Target: <500ms
```

#### Test 2: Full Analysis Response Time
```bash
# Run 10 queries to non-curated interactions
# Measure: Average response time
# Target: <30s
```

#### Test 3: Concurrent Users
```bash
# Simulate 10 concurrent users
# Measure: Response time degradation
# Target: <10% increase
```

### Data Validation

#### Test 1: Curated DB Integrity
```sql
-- Check all curated interactions have required fields
SELECT interaction_key 
FROM curated_interactions 
WHERE response_data IS NULL 
   OR knowledge_graph IS NULL 
   OR severity IS NULL;
-- Expected: 0 rows
```

#### Test 2: DynamoDB Data Completeness
```bash
# Check each plant has METADATA record
aws dynamodb get-item --table-name ausadhi-imppat \
  --key '{"plant_name": {"S": "curcuma_longa"}, "record_key": {"S": "METADATA"}}'
# Expected: Record found with phytochemical_count > 0
```

#### Test 3: S3 Reference Files
```bash
# Verify all reference files are accessible
aws s3 cp s3://ausadhi-mitra-667736132441/reference/name_mappings.json - | jq .
aws s3 cp s3://ausadhi-mitra-667736132441/reference/cyp_enzymes.json - | jq .
aws s3 cp s3://ausadhi-mitra-667736132441/reference/nti_drugs.json - | jq .
# Expected: Valid JSON for all files
```

---

## Monitoring Setup

### CloudWatch Dashboards

#### Dashboard 1: System Health
- Lambda error rates (all functions)
- Bedrock Flow execution time
- PostgreSQL connection pool status
- EC2 CPU and memory utilization

#### Dashboard 2: Performance Metrics
- Layer 0 response time (p50, p95, p99)
- Full analysis response time (p50, p95, p99)
- Curated DB hit rate
- DoWhile loop iterations (average)

#### Dashboard 3: Business Metrics
- Total queries per hour
- Queries by severity (NONE/MINOR/MODERATE/MAJOR)
- Top 10 queried AYUSH medicines
- Top 10 queried allopathic drugs

### CloudWatch Alarms

```bash
# Create alarms
aws cloudwatch put-metric-alarm \
  --alarm-name aushadhi-flow-timeout-high \
  --alarm-description "Alert when Flow timeout rate exceeds 20%" \
  --metric-name FlowTimeout \
  --namespace AushadhiMitra \
  --statistic Average \
  --period 300 \
  --threshold 0.2 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 2

aws cloudwatch put-metric-alarm \
  --alarm-name aushadhi-lambda-errors-high \
  --alarm-description "Alert when Lambda error rate exceeds 5%" \
  --metric-name Errors \
  --namespace AWS/Lambda \
  --statistic Average \
  --period 300 \
  --threshold 0.05 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 2
```

---

## Operational Procedures

### Daily Operations

#### Morning Health Check
```bash
# 1. Check system health
curl http://localhost/api/health

# 2. Check CloudWatch alarms
aws cloudwatch describe-alarms --state-value ALARM

# 3. Review error logs
aws logs tail /aws/lambda/planner_tools --since 24h --filter-pattern "ERROR"

# 4. Check curated DB hit rate
# Target: >30%
```

#### Evening Metrics Review
```bash
# 1. Review daily query volume
# 2. Check average response times
# 3. Review top queried medicines
# 4. Check for any new error patterns
```

### Weekly Maintenance

#### Data Updates
```bash
# 1. Review and add new curated interactions based on user queries
python scripts/add_curated_interaction.py --ayush "..." --allopathy "..." --data "..."

# 2. Clear expired allopathy cache entries (TTL: 7 days)
psql -h scm-postgres... -d aushadhimitra -c "DELETE FROM allopathy_cache WHERE expires_at < NOW();"

# 3. Backup PostgreSQL database
pg_dump -h scm-postgres... -U admin aushadhimitra > backup_$(date +%Y%m%d).sql
```

#### Performance Optimization
```bash
# 1. Analyze slow queries
psql -h scm-postgres... -d aushadhimitra -c "SELECT * FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;"

# 2. Review Lambda cold start times
# 3. Check DynamoDB read capacity utilization
# 4. Review S3 access patterns
```

### Monthly Reviews

#### Cost Optimization
- Review Bedrock model invocation costs
- Analyze Lambda execution time and memory usage
- Check DynamoDB read/write capacity utilization
- Review RDS instance sizing

#### Security Audit
- Review IAM role permissions
- Check for exposed secrets in logs
- Verify S3 bucket policies
- Review VPC security group rules

#### Data Quality
- Validate curated interaction accuracy
- Review IMPPAT data completeness
- Check for outdated reference files
- Verify NTI drug list is current

---

## Troubleshooting Guide

### Issue 1: Bedrock Flow Timeout
**Symptoms**: "Read timed out" error in logs  
**Diagnosis**: Check CloudWatch logs for Flow execution time  
**Resolution**: System auto-falls back to Pipeline Mode; no action needed  
**Prevention**: Monitor Flow timeout rate; if >20%, investigate agent performance

### Issue 2: Curated DB Lookup Fails
**Symptoms**: All queries trigger full analysis, even for known pairs  
**Diagnosis**: Check Lambda logs for "Curated DB miss" on known pairs  
**Resolution**: Verify `check_curated_interaction()` uses `response_data` column  
**Prevention**: Add integration test for curated DB lookups

### Issue 3: Lambda NoneType Error
**Symptoms**: `calculate_severity()` crashes with NoneType error  
**Diagnosis**: Check Lambda logs for stack trace  
**Resolution**: Add null guard in `calculate_severity()` function  
**Prevention**: Add unit tests for null/empty inputs

### Issue 4: PostgreSQL Connection Pool Exhausted
**Symptoms**: "Too many connections" error  
**Diagnosis**: Check RDS connection count  
**Resolution**: Increase connection pool size or RDS max_connections  
**Prevention**: Implement connection pooling with proper timeout

### Issue 5: WebSocket Disconnects
**Symptoms**: Frontend loses connection during long analysis  
**Diagnosis**: Check Nginx timeout settings  
**Resolution**: Increase Nginx proxy_read_timeout to 60s  
**Prevention**: Implement WebSocket reconnection logic in frontend

---

## Rollback Procedures

### Lambda Rollback
```bash
# List function versions
aws lambda list-versions-by-function --function-name planner_tools

# Rollback to previous version
aws lambda update-alias --function-name planner_tools \
  --name PROD --function-version <previous-version>
```

### Backend Rollback
```bash
# Stop current containers
docker-compose down

# Pull previous image
docker pull aushadhimitra-backend:<previous-tag>

# Start with previous version
docker-compose up -d
```

### Database Rollback
```bash
# Restore from backup
psql -h scm-postgres... -U admin aushadhimitra < backup_YYYYMMDD.sql
```

---

## Disaster Recovery

### RTO (Recovery Time Objective): 4 hours
### RPO (Recovery Point Objective): 24 hours

### DR Procedure
1. **Detect Failure**: CloudWatch alarms trigger
2. **Assess Impact**: Determine scope of failure
3. **Activate DR**: Switch to backup region (us-west-2)
4. **Restore Data**: Restore PostgreSQL from latest backup
5. **Verify System**: Run health checks and functional tests
6. **Resume Operations**: Update DNS to point to DR region

### DR Checklist
- [ ] PostgreSQL backup exists and is <24h old
- [ ] S3 reference files replicated to us-west-2
- [ ] DynamoDB global tables configured (if using)
- [ ] Lambda functions deployed to us-west-2
- [ ] Bedrock agents created in us-west-2
- [ ] EC2 AMI snapshot available

---

## Contact Information

### On-Call Rotation
- **Primary**: [Contact Info]
- **Secondary**: [Contact Info]
- **Escalation**: [Contact Info]

### Vendor Support
- **AWS Support**: [Support Plan Level]
- **Tavily API**: [Support Email]

### Documentation
- **Runbook**: [Link]
- **Architecture Diagram**: [Link]
- **API Documentation**: [Link]
