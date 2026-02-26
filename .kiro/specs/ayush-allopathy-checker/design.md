# Design Document

## Overview

AushadhiMitra is a multi-agent AI system that checks for drug interactions between AYUSH (traditional Indian medicine) and allopathic (modern pharmaceutical) medicines. The system uses **Amazon Bedrock Agents with Multi-Agent Collaboration** to orchestrate a tiered approach: instant responses from a curated interaction database for high-impact pairs (Layer 0), and real-time data gathering via Tavily web search for other queries with S3 fallback for reliability.

The architecture features 1 Supervisor Agent and 3 Collaborator Agents (AYUSH Agent, Allopathy Agent, Reasoning Agent), with AWS Lambda functions serving as Action Groups for deterministic operations. A key differentiator is the dynamic knowledge graph generation that visually maps interaction pathways.

**Key Design Principles:**
- **AWS Managed Services**: Bedrock Agents, Lambda, S3, DynamoDB, API Gateway
- **Multi-Agent Collaboration**: Supervisor routes to specialized collaborators
- **Tiered Response**: Curated instant responses (Layer 0) → Real-time gathering → S3 fallback
- **Serverless Architecture**: Lambda-based action groups for scalability
- **Grounded Reasoning**: LLM uses ONLY provided evidence, not internal knowledge
- **Transparent Conflict Detection**: As a differentiator feature
- **Full Source Citation**: With clickable URLs for verification

**Architecture Summary:**
- **1 Supervisor Agent**: Routes requests and orchestrates workflow
- **3 Collaborator Agents**: AYUSH Agent, Allopathy Agent, Reasoning Agent
- **9 Lambda Action Groups**: Deterministic business logic functions
- **Data Storage**: S3 (static data), DynamoDB (cache)

## AWS Architecture

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER INTERFACES                                 │
│  ┌─────────────────────────────┐    ┌─────────────────────────────────┐     │
│  │   React Web UI              │    │   Streamlit Chat UI             │     │
│  │   (Professional)            │    │   (Patient)                     │     │
│  │   - Cytoscape.js KG         │    │   - Simple chat                 │     │
│  │   - AWS Amplify hosted      │    │   - Hindi/English/Hinglish      │     │
│  └──────────────┬──────────────┘    └──────────────┬──────────────────┘     │
└─────────────────┼──────────────────────────────────┼────────────────────────┘
                  │                                  │
                  └──────────────┬───────────────────┘
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AMAZON API GATEWAY                                   │
│                    (REST API for agent invocation)                          │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    AMAZON BEDROCK AGENTS                                     │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                     SUPERVISOR AGENT                                   │  │
│  │  Model: Claude 3 Sonnet                                               │  │
│  │  Role: Route requests, orchestrate collaborators, synthesize results  │  │
│  │                                                                       │  │
│  │  Instructions:                                                        │  │
│  │  - Parse user input to identify AYUSH and allopathic medicines       │  │
│  │  - Check curated database first for instant response                 │  │
│  │  - Route to AYUSH and Allopathy agents in parallel                   │  │
│  │  - Pass results to Reasoning agent for analysis                      │  │
│  │  - Format final response based on user type                          │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                  │                                           │
│          ┌───────────────────────┼───────────────────────┐                  │
│          ▼                       ▼                       ▼                  │
│  ┌───────────────┐      ┌───────────────┐      ┌───────────────┐           │
│  │ AYUSH AGENT   │      │ ALLOPATHY     │      │ REASONING     │           │
│  │ (Collaborator)│      │ AGENT         │      │ AGENT         │           │
│  │               │      │ (Collaborator)│      │ (Collaborator)│           │
│  │ Model: Haiku  │      │ Model: Haiku  │      │ Model: Sonnet │           │
│  │               │      │               │      │               │           │
│  │ Action Groups:│      │ Action Groups:│      │ Action Groups:│           │
│  │ • name_resolve│      │ • cache_lookup│      │ • build_kg    │           │
│  │ • imppat_load │      │ • web_search  │      │ • calc_severity│          │
│  │ • web_search  │      │ • cache_save  │      │ • web_search  │           │
│  │               │      │               │      │ • format_pro  │           │
│  └───────┬───────┘      └───────┬───────┘      └───────┬───────┘           │
└──────────┼──────────────────────┼──────────────────────┼────────────────────┘
           │                      │                      │
           ▼                      ▼                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AWS LAMBDA FUNCTIONS                                 │
│                         (Action Group Handlers)                             │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐               │
│  │ayush_name_      │ │cache_lookup     │ │build_knowledge_ │               │
│  │resolver         │ │                 │ │graph            │               │
│  │Python 3.12      │ │Python 3.12      │ │Python 3.12      │               │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘               │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐               │
│  │imppat_lookup    │ │web_search_tavily│ │calculate_       │               │
│  │                 │ │                 │ │severity         │               │
│  │Python 3.12      │ │Python 3.12      │ │Python 3.12      │               │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘               │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐               │
│  │cache_save       │ │check_curated_db │ │format_          │               │
│  │                 │ │                 │ │professional_    │               │
│  │Python 3.12      │ │Python 3.12      │ │response         │               │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘               │
└─────────────────────────────────────────────────────────────────────────────┘
           │                      │                      │
           ▼                      ▼                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DATA LAYER                                         │
│  ┌───────────────────────────┐    ┌───────────────────────────────┐        │
│  │      AMAZON S3            │    │      AMAZON DYNAMODB          │        │
│  │  (Static Data)            │    │  (Cache)                      │        │
│  │                           │    │                               │        │
│  │  /curated/                │    │  Table: allopathy_cache       │        │
│  │    curated_interactions   │    │    PK: drug_name              │        │
│  │  /ayush/imppat/           │    │    TTL: 7 days                │        │
│  │    curcuma_longa.json     │    │                               │        │
│  │    glycyrrhiza_glabra.json│    │  Table: kg_cache              │        │
│  │    zingiber_officinale    │    │    PK: ayush#allopathy        │        │
│  │    hypericum_perforatum   │    │    TTL: 30 days               │        │
│  │  /reference/              │    │                               │        │
│  │    nti_drugs.json         │    │                               │        │
│  │    cyp_enzymes.json       │    │                               │        │
│  └───────────────────────────┘    └───────────────────────────────┘        │
└─────────────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        EXTERNAL SERVICES                                     │
│  ┌───────────────────────────┐    ┌───────────────────────────────┐        │
│  │      TAVILY API           │    │   AWS SECRETS MANAGER         │        │
│  │  (Web Search)             │    │   (API Keys)                  │        │
│  │                           │    │                               │        │
│  │  - DrugBank search        │    │   - TAVILY_API_KEY            │        │
│  │  - Research articles      │    │                               │        │
│  │  - CYP inducer data       │    │                               │        │
│  └───────────────────────────┘    └───────────────────────────────┘        │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Technology Stack

**AWS Services:**
| Service | Purpose |
|---------|---------|
| **Amazon Bedrock Agents** | Multi-agent orchestration with Claude models |
| **AWS Lambda** | Action group handlers (Python 3.12) |
| **Amazon S3** | Static data storage (IMPPAT, curated DB) |
| **Amazon DynamoDB** | Caching for allopathy data and knowledge graphs |
| **Amazon API Gateway** | REST API for frontend |
| **AWS Amplify** | React frontend hosting |
| **AWS Secrets Manager** | API keys (Tavily) |
| **AWS CloudFormation/SAM** | Infrastructure as code |

**Foundation Models:**
| Model | Usage |
|-------|-------|
| **Claude 3 Sonnet** | Supervisor Agent, Reasoning Agent |
| **Claude 3 Haiku** | AYUSH Agent, Allopathy Agent (cost-effective) |

**External Services:**
| Service | Purpose |
|---------|---------|
| **Tavily API** | Web search for drug info and research |

### Data Flow Sequence

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           REQUEST FLOW                                       │
└─────────────────────────────────────────────────────────────────────────────┘

User: "Check turmeric with warfarin"
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 1: API Gateway receives request                                         │
│         POST /api/check-interaction                                          │
│         Body: {"ayush": "turmeric", "allopathy": "warfarin", "user": "pro"} │
└─────────────────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 2: Supervisor Agent invoked                                             │
│         - Parses input: AYUSH=Turmeric, Allopathy=Warfarin                  │
│         - Invokes check_curated_db Lambda                                    │
└─────────────────────────────────────────────────────────────────────────────┘
              │
              ├── CURATED HIT ──────────────────────────────────────┐
              │                                                      │
              │   ┌──────────────────────────────────────────────┐   │
              │   │ Return pre-computed response in <500ms       │   │
              │   │ - Pre-built knowledge graph                  │   │
              │   │ - Severity: MAJOR                            │   │
              │   │ - All summaries ready                        │   │
              │   └──────────────────────────────────────────────┘   │
              │                                                      │
              ├── CURATED MISS ─────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 3: Supervisor routes to Collaborator Agents (PARALLEL)                  │
└─────────────────────────────────────────────────────────────────────────────┘
              │
      ┌───────┴───────┐
      ▼               ▼
┌────────────┐  ┌────────────┐
│AYUSH Agent │  │ALLOPATHY   │
│            │  │AGENT       │
│ Lambda:    │  │            │
│ name_resolve│  │ Lambda:    │
│ → Curcuma  │  │ cache_lookup│
│   longa    │  │ → MISS     │
│            │  │            │
│ Lambda:    │  │ Lambda:    │
│ imppat_load│  │ web_search │
│ → S3 JSON  │  │ → Tavily   │
│            │  │            │
│ Result:    │  │ Lambda:    │
│ CYP2C9 inh │  │ cache_save │
│ CYP3A4 inh │  │            │
│            │  │ Result:    │
│completeness│  │ CYP2C9 sub │
│: 0.9       │  │ NTI: true  │
└─────┬──────┘  └─────┬──────┘
      │               │
      └───────┬───────┘
              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 4: Supervisor passes data to Reasoning Agent                            │
└─────────────────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ REASONING AGENT                                                              │
│                                                                              │
│ Lambda: build_knowledge_graph                                                │
│ → Nodes: Turmeric, Curcumin, Warfarin, CYP2C9, CYP3A4                       │
│ → Edges: CONTAINS, INHIBITS, METABOLIZED_BY                                 │
│ → Overlap: CYP2C9 (marked red)                                              │
│                                                                              │
│ Lambda: web_search (research articles)                                       │
│ → "Curcumin warfarin interaction PubMed"                                    │
│ → Found 3 case reports                                                       │
│                                                                              │
│ Lambda: calculate_severity                                                   │
│ → CYP2C9 overlap: +15 points                                                │
│ → NTI drug: +25 points                                                       │
│ → Case reports: +20 points                                                   │
│ → Antiplatelet PD: +15 points                                               │
│ → Total: 75 → MAJOR                                                          │
│                                                                              │
│ LLM: Generate grounded explanation                                           │
└─────────────────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 5: Supervisor receives result and formats based on user_type                       │
│                                                                              │
│ IF professional:                                                             │
│   → Reasoning Agent already called format_professional_response Lambda      │
│   → Return structured JSON with KG, severity, mechanisms, sources           │
│                                                                              │
│ IF patient:                                                                  │
│   → Reasoning Agent generated simple 4-5 sentence response                  │
│   → Return in detected language (English/Hindi/Hinglish)                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Agent Configurations

### Supervisor Agent

```yaml
Name: AushadhiMitra-Supervisor
Model: anthropic.claude-3-sonnet-20240229-v1:0
Description: Main orchestrator for drug interaction checking

Instructions: |
  You are the supervisor agent for AushadhiMitra, an AYUSH-Allopathy drug 
  interaction checker. Your role is to:
  
  1. Parse user input to identify AYUSH medicines and allopathic drugs
  2. First check the curated database for instant response
  3. If not found, route to AYUSH and Allopathy collaborator agents
  4. Pass gathered data to Reasoning agent for analysis
  5. Format the final response based on user type (professional/patient)
  
  Always ensure responses are grounded in evidence. Never make up interactions.
  Cite sources for all claims.

Collaborators:
  - AYUSH-Data-Agent
  - Allopathy-Data-Agent
  - Reasoning-Agent

Action Groups:
  - check_curated_db
```

### AYUSH Collaborator Agent

```yaml
Name: AYUSH-Data-Agent
Model: anthropic.claude-3-haiku-20240307-v1:0
Description: Gathers phytochemical and ADMET data for AYUSH medicines

Instructions: |
  You are a specialized agent for gathering AYUSH medicine data.
  
  1. Use ayush_name_resolver to convert common names to scientific names
  2. Use imppat_lookup to load phytochemical and ADMET data from S3
  3. Check for CYP inhibitor status from the ADMET data
  4. If CYP inducer data is missing, use web_search_tavily to find it
  5. Report data_completeness score and list any gaps
  
  Your scope is 4 plants: Curcuma longa, Glycyrrhiza glabra, 
  Zingiber officinale, Hypericum perforatum.

Action Groups:
  - ayush_name_resolver
  - imppat_lookup
  - web_search_tavily
```

### Allopathy Collaborator Agent

```yaml
Name: Allopathy-Data-Agent
Model: anthropic.claude-3-haiku-20240307-v1:0
Description: Gathers CYP metabolism data for allopathic drugs

Instructions: |
  You are a specialized agent for gathering allopathic drug data.
  
  1. Use cache_lookup to check if drug data is already cached
  2. If cache hit and fresh (<7 days), use cached data
  3. If cache miss, use web_search_tavily with query:
     "{drug_name} DrugBank CYP metabolism substrate inhibitor"
  4. Extract CYP substrate/inhibitor/inducer data from search results
  5. Check if it's a Narrow Therapeutic Index drug
  6. Use cache_save to store results for future queries
  7. Report data_completeness score and list any gaps

Action Groups:
  - cache_lookup
  - web_search_tavily
  - cache_save
```

### Reasoning Collaborator Agent

```yaml
Name: Reasoning-Agent
Model: anthropic.claude-3-sonnet-20240229-v1:0
Description: Analyzes data, builds knowledge graph, calculates severity, formats output

Instructions: |
  You are a specialized reasoning agent that analyzes drug interaction data.
  
  1. Use build_knowledge_graph to construct JSON graph from provided data
  2. Identify overlap nodes (enzymes affected by both medicines)
  3. Use web_search_tavily to find research articles about the combination
  4. Detect any conflicts between sources
  5. Use calculate_severity to compute rule-based severity score
  6. Generate grounded explanation citing ONLY the provided evidence
  
  FOR OUTPUT FORMATTING:
  7. If user_type == "professional":
       - Use format_professional_response Lambda to assemble structured JSON
       - Pass: knowledge_graph, severity, ayush_data, allopathy_data, 
              research_citations, and your generated ai_summary
  8. If user_type == "patient":
       - Generate a simple 4-5 sentence response directly
       - Match the user's language (English/Hindi/Hinglish)
       - Be empathetic, not alarming
       - Include one actionable recommendation
  
  CRITICAL: Never make claims not supported by the evidence.
  If sources conflict, report both viewpoints.
  If data is insufficient, say "UNKNOWN - Limited data available"

Action Groups:
  - build_knowledge_graph
  - calculate_severity
  - web_search_tavily
  - format_professional_response
```

## Lambda Action Groups

### Lambda 1: check_curated_db

```python
# lambda/check_curated_db/handler.py
import json
import boto3

s3 = boto3.client('s3')
BUCKET = 'aushadhimitra-data'

def handler(event, context):
    """Check if drug pair exists in curated database"""
    
    # Parse Bedrock Agent event
    agent = event.get('agent', {})
    action_group = event.get('actionGroup', '')
    api_path = event.get('apiPath', '')
    parameters = event.get('parameters', [])
    
    # Extract parameters
    ayush_name = next((p['value'] for p in parameters if p['name'] == 'ayush_name'), None)
    allopathy_name = next((p['value'] for p in parameters if p['name'] == 'allopathy_name'), None)
    
    # Load curated database from S3
    response = s3.get_object(Bucket=BUCKET, Key='curated/curated_interactions.json')
    curated_db = json.loads(response['Body'].read())
    
    # Normalize names
    ayush_normalized = ayush_name.lower().strip()
    allopathy_normalized = allopathy_name.lower().strip()
    
    # Search for match
    for interaction in curated_db['interactions']:
        ayush_match = ayush_normalized in [n.lower() for n in interaction['ayush']['names']]
        allopathy_match = allopathy_normalized in [n.lower() for n in interaction['allopathy']['names']]
        
        if ayush_match and allopathy_match:
            return {
                'messageVersion': '1.0',
                'response': {
                    'actionGroup': action_group,
                    'apiPath': api_path,
                    'httpMethod': 'GET',
                    'httpStatusCode': 200,
                    'responseBody': {
                        'application/json': {
                            'body': json.dumps({
                                'found': True,
                                'interaction': interaction
                            })
                        }
                    }
                }
            }
    
    # Not found
    return {
        'messageVersion': '1.0',
        'response': {
            'actionGroup': action_group,
            'apiPath': api_path,
            'httpMethod': 'GET',
            'httpStatusCode': 200,
            'responseBody': {
                'application/json': {
                    'body': json.dumps({'found': False})
                }
            }
        }
    }
```

### Lambda 2: ayush_name_resolver

```python
# lambda/ayush_name_resolver/handler.py
import json
import boto3

s3 = boto3.client('s3')
BUCKET = 'aushadhimitra-data'

def handler(event, context):
    """Resolve common AYUSH name to scientific name"""
    
    parameters = event.get('parameters', [])
    common_name = next((p['value'] for p in parameters if p['name'] == 'common_name'), None)
    
    # Load name mappings
    response = s3.get_object(Bucket=BUCKET, Key='ayush/name_mappings.json')
    mappings = json.loads(response['Body'].read())
    
    normalized = common_name.lower().strip()
    
    for plant in mappings['plants']:
        all_names = [n.lower() for n in plant.get('common_names', [])]
        all_names.extend([n.lower() for n in plant.get('hindi_names', [])])
        all_names.extend([n.lower() for n in plant.get('brand_names', [])])
        all_names.append(plant['scientific_name'].lower())
        
        if normalized in all_names:
            return format_response(event, {
                'found': True,
                'scientific_name': plant['scientific_name'],
                'common_name': plant['common_names'][0] if plant['common_names'] else common_name,
                'imppat_file': plant.get('imppat_file')
            })
    
    return format_response(event, {'found': False, 'input': common_name})

def format_response(event, body):
    return {
        'messageVersion': '1.0',
        'response': {
            'actionGroup': event.get('actionGroup', ''),
            'apiPath': event.get('apiPath', ''),
            'httpMethod': 'GET',
            'httpStatusCode': 200,
            'responseBody': {
                'application/json': {'body': json.dumps(body)}
            }
        }
    }
```

### Lambda 3: build_knowledge_graph

```python
# lambda/build_knowledge_graph/handler.py
import json

NODE_COLORS = {
    "plant": "#4CAF50",
    "phytochemical": "#8BC34A",
    "drug": "#2196F3",
    "enzyme": "#FF9800",
    "overlap": "#F44336"
}

def handler(event, context):
    """Build JSON knowledge graph and identify overlaps"""
    
    parameters = event.get('parameters', [])
    ayush_data = json.loads(next((p['value'] for p in parameters if p['name'] == 'ayush_data'), '{}'))
    allopathy_data = json.loads(next((p['value'] for p in parameters if p['name'] == 'allopathy_data'), '{}'))
    
    nodes = []
    edges = []
    overlap_nodes = []
    
    # Add plant node
    plant_id = f"plant_{ayush_data.get('scientific_name', 'unknown').replace(' ', '_').lower()}"
    nodes.append({
        'id': plant_id,
        'type': 'plant',
        'label': ayush_data.get('scientific_name', 'Unknown'),
        'color': NODE_COLORS['plant'],
        'is_overlap': False
    })
    
    # Add drug node
    drug_id = f"drug_{allopathy_data.get('generic_name', 'unknown').lower()}"
    nodes.append({
        'id': drug_id,
        'type': 'drug',
        'label': allopathy_data.get('generic_name', 'Unknown'),
        'color': NODE_COLORS['drug'],
        'is_overlap': False
    })
    
    # Add CYP enzyme nodes
    ayush_cyp_inhibits = set(k for k, v in ayush_data.get('cyp_inhibition', {}).items() if v)
    ayush_cyp_induces = set(k for k, v in ayush_data.get('cyp_induction', {}).items() if v)
    allopathy_substrates = set(k for k, v in allopathy_data.get('cyp_substrate', {}).items() if v)
    
    all_enzymes = ayush_cyp_inhibits | ayush_cyp_induces | allopathy_substrates
    
    for enzyme in all_enzymes:
        enzyme_id = enzyme.lower()
        is_overlap = (enzyme in ayush_cyp_inhibits or enzyme in ayush_cyp_induces) and enzyme in allopathy_substrates
        
        if is_overlap:
            overlap_nodes.append(enzyme_id)
        
        nodes.append({
            'id': enzyme_id,
            'type': 'enzyme',
            'label': enzyme.upper(),
            'color': NODE_COLORS['overlap'] if is_overlap else NODE_COLORS['enzyme'],
            'is_overlap': is_overlap
        })
        
        # Add edges
        if enzyme in ayush_cyp_inhibits:
            edges.append({
                'id': f"e_{plant_id}_{enzyme_id}_inhibits",
                'source': plant_id,
                'target': enzyme_id,
                'relation': 'INHIBITS',
                'is_interaction_path': is_overlap
            })
        
        if enzyme in ayush_cyp_induces:
            edges.append({
                'id': f"e_{plant_id}_{enzyme_id}_induces",
                'source': plant_id,
                'target': enzyme_id,
                'relation': 'INDUCES',
                'is_interaction_path': is_overlap
            })
        
        if enzyme in allopathy_substrates:
            edges.append({
                'id': f"e_{drug_id}_{enzyme_id}_metabolized",
                'source': drug_id,
                'target': enzyme_id,
                'relation': 'METABOLIZED_BY',
                'is_interaction_path': is_overlap
            })
    
    graph = {
        'nodes': nodes,
        'edges': edges,
        'metadata': {
            'ayush_drug': ayush_data.get('scientific_name'),
            'allopathy_drug': allopathy_data.get('generic_name'),
            'overlap_nodes': overlap_nodes,
            'interaction_detected': len(overlap_nodes) > 0
        }
    }
    
    return format_response(event, graph)
```

### Lambda 4: calculate_severity

```python
# lambda/calculate_severity/handler.py
import json

MAJOR_CYPS = ['cyp3a4', 'cyp2d6', 'cyp2c9']

def handler(event, context):
    """Rule-based severity calculation"""
    
    parameters = event.get('parameters', [])
    overlap_nodes = json.loads(next((p['value'] for p in parameters if p['name'] == 'overlap_nodes'), '[]'))
    nti_drug = next((p['value'] for p in parameters if p['name'] == 'nti_drug'), 'false') == 'true'
    research_count = int(next((p['value'] for p in parameters if p['name'] == 'research_count'), '0'))
    pd_overlap = next((p['value'] for p in parameters if p['name'] == 'pd_overlap'), 'false') == 'true'
    
    score = 0
    factors = []
    
    # Factor 1: CYP Pathway Overlap (0-30 points)
    for node in overlap_nodes:
        if node.lower() in MAJOR_CYPS:
            score += 15
            factors.append(f"Overlap on {node.upper()} (major metabolic pathway)")
        else:
            score += 5
            factors.append(f"Overlap on {node.upper()}")
    
    # Factor 2: Narrow Therapeutic Index (0-25 points)
    if nti_drug:
        score += 25
        factors.append("Drug has Narrow Therapeutic Index - high risk")
    
    # Factor 3: Research Evidence (0-30 points)
    if research_count >= 3:
        score += 30
        factors.append(f"Supported by {research_count} research articles")
    elif research_count >= 1:
        score += 20
        factors.append(f"Supported by {research_count} research article(s)")
    
    # Factor 4: Pharmacodynamic Overlap (0-15 points)
    if pd_overlap:
        score += 15
        factors.append("Additive pharmacodynamic effects")
    
    # Severity Classification
    if score >= 60:
        severity = "MAJOR"
        recommendation = "AVOID combination. Consult healthcare provider immediately."
    elif score >= 35:
        severity = "MODERATE"
        recommendation = "Use with caution. Monitor closely for adverse effects."
    elif score >= 15:
        severity = "MINOR"
        recommendation = "Generally safe. Be aware of potential effects."
    else:
        severity = "NONE"
        recommendation = "No significant interaction expected."
    
    result = {
        'severity': severity,
        'score': score,
        'factors': factors,
        'recommendation': recommendation
    }
    
    return format_response(event, result)
```

### Lambda 5: format_professional_response

```python
# lambda/format_professional_response/handler.py
import json
from datetime import datetime

def handler(event, context):
    """Assemble structured JSON response for professional UI"""
    
    parameters = event.get('parameters', [])
    
    # Extract all data passed from Reasoning Agent
    knowledge_graph = json.loads(get_param(parameters, 'knowledge_graph', '{}'))
    severity = json.loads(get_param(parameters, 'severity', '{}'))
    ayush_data = json.loads(get_param(parameters, 'ayush_data', '{}'))
    allopathy_data = json.loads(get_param(parameters, 'allopathy_data', '{}'))
    research_citations = json.loads(get_param(parameters, 'research_citations', '[]'))
    ai_summary = get_param(parameters, 'ai_summary', '')
    conflicts = json.loads(get_param(parameters, 'conflicts', 'null'))
    
    # Build professional response structure
    response = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "query": {
            "ayush_input": ayush_data.get('common_name', ''),
            "allopathy_input": allopathy_data.get('generic_name', ''),
            "resolved_ayush": ayush_data.get('scientific_name', ''),
            "resolved_allopathy": allopathy_data.get('generic_name', '')
        },
        "severity": {
            "level": severity.get('severity', 'UNKNOWN'),
            "score": severity.get('score', 0),
            "factors": severity.get('factors', []),
            "recommendation": severity.get('recommendation', '')
        },
        "knowledge_graph": knowledge_graph,
        "mechanisms": extract_mechanisms(knowledge_graph, ayush_data, allopathy_data),
        "ayush_profile": {
            "name": ayush_data.get('scientific_name', ''),
            "common_names": ayush_data.get('common_names', []),
            "cyp_inhibition": ayush_data.get('cyp_inhibition', {}),
            "cyp_induction": ayush_data.get('cyp_induction', {}),
            "effect_categories": ayush_data.get('effect_categories', []),
            "data_completeness": ayush_data.get('data_completeness', 0),
            "sources": ayush_data.get('sources', [])
        },
        "allopathy_profile": {
            "name": allopathy_data.get('generic_name', ''),
            "drug_class": allopathy_data.get('drug_class', ''),
            "cyp_substrate": allopathy_data.get('cyp_substrate', {}),
            "narrow_therapeutic_index": allopathy_data.get('narrow_therapeutic_index', False),
            "effect_categories": allopathy_data.get('effect_categories', []),
            "data_completeness": allopathy_data.get('data_completeness', 0),
            "sources": allopathy_data.get('sources', [])
        },
        "research_citations": research_citations,
        "conflicts": conflicts,
        "ai_summary": ai_summary,
        "disclaimer": "This information is for educational purposes only. Always consult a healthcare provider before making medication changes."
    }
    
    return format_response(event, response)

def get_param(parameters, name, default=''):
    """Safely extract parameter value"""
    return next((p['value'] for p in parameters if p['name'] == name), default)

def extract_mechanisms(kg, ayush_data, allopathy_data):
    """Extract interaction mechanisms from knowledge graph"""
    mechanisms = []
    
    overlap_nodes = kg.get('metadata', {}).get('overlap_nodes', [])
    
    for node_id in overlap_nodes:
        # Find edges connected to this overlap node
        inhibits_edge = None
        substrate_edge = None
        
        for edge in kg.get('edges', []):
            if edge.get('target') == node_id:
                if edge.get('relation') == 'INHIBITS':
                    inhibits_edge = edge
                elif edge.get('relation') == 'INDUCES':
                    inhibits_edge = edge  # treat induces similarly
                elif edge.get('relation') == 'METABOLIZED_BY':
                    substrate_edge = edge
        
        if inhibits_edge and substrate_edge:
            enzyme_name = node_id.upper()
            mechanism = {
                "type": "pharmacokinetic_cyp",
                "pathway": enzyme_name,
                "direction": "inhibition" if inhibits_edge.get('relation') == 'INHIBITS' else "induction",
                "description": f"{ayush_data.get('scientific_name', 'AYUSH medicine')} affects {enzyme_name}, which metabolizes {allopathy_data.get('generic_name', 'the drug')}.",
                "clinical_significance": "May alter drug blood levels"
            }
            mechanisms.append(mechanism)
    
    # Check for pharmacodynamic overlap
    ayush_effects = set(ayush_data.get('effect_categories', []))
    allo_effects = set(allopathy_data.get('effect_categories', []))
    pd_overlap = ayush_effects & allo_effects
    
    for effect in pd_overlap:
        mechanisms.append({
            "type": "pharmacodynamic",
            "pathway": effect,
            "direction": "additive",
            "description": f"Both medicines have {effect} effects",
            "clinical_significance": "Additive effect may increase risk"
        })
    
    return mechanisms

def format_response(event, body):
    return {
        'messageVersion': '1.0',
        'response': {
            'actionGroup': event.get('actionGroup', ''),
            'apiPath': event.get('apiPath', ''),
            'httpMethod': 'POST',
            'httpStatusCode': 200,
            'responseBody': {
                'application/json': {'body': json.dumps(body)}
            }
        }
    }
```

## Data Schemas

### S3: Curated Interactions (curated_interactions.json)

```json
{
  "version": "1.0",
  "last_updated": "2026-02-25",
  "interactions": [
    {
      "id": "TURMERIC_WARFARIN",
      "ayush": {
        "names": ["turmeric", "haldi", "curcuma longa", "curcumin"],
        "scientific_name": "Curcuma longa"
      },
      "allopathy": {
        "names": ["warfarin", "coumadin", "jantoven"],
        "generic_name": "Warfarin",
        "narrow_therapeutic_index": true
      },
      "severity": "MAJOR",
      "severity_score": 72,
      "severity_factors": [
        "Overlap on CYP2C9 (major metabolic pathway)",
        "Drug has Narrow Therapeutic Index",
        "Supported by 3 case reports",
        "Additive antiplatelet effects"
      ],
      "mechanisms": [
        {
          "type": "pharmacokinetic_cyp",
          "pathway": "CYP2C9",
          "description": "Curcumin inhibits CYP2C9, which metabolizes 85% of Warfarin"
        }
      ],
      "clinical_effects": ["Increased bleeding risk", "Elevated INR"],
      "knowledge_graph": {
        "nodes": [...],
        "edges": [...],
        "metadata": {"overlap_nodes": ["cyp2c9"]}
      },
      "research_citations": [
        {
          "title": "Curcumin-warfarin interaction",
          "pmid": "12345678",
          "url": "https://pubmed.ncbi.nlm.nih.gov/12345678/"
        }
      ],
      "professional_summary": "Technical summary...",
      "patient_summary_en": "Simple English...",
      "patient_summary_hi": "हिंदी में...",
      "patient_summary_hinglish": "Hinglish mein..."
    }
  ]
}
```

### DynamoDB: Allopathy Cache

```
Table: allopathy_cache
Primary Key: drug_name (String)
TTL: ttl (Number - epoch seconds)

{
  "drug_name": "warfarin",
  "generic_name": "Warfarin",
  "brand_names": ["Coumadin", "Jantoven"],
  "drug_class": "Anticoagulant",
  "cyp_substrate": {"CYP2C9": true, "CYP3A4": true},
  "cyp_inhibitor": {},
  "cyp_inducer": {},
  "narrow_therapeutic_index": true,
  "effect_categories": ["blood_thinning"],
  "sources": [...],
  "cached_at": "2026-02-25T10:00:00Z",
  "ttl": 1740700800
}
```

## Deployment

### SAM Template (template.yaml)

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Description: AushadhiMitra - AYUSH-Allopathy Drug Interaction Checker

Parameters:
  TavilyApiKey:
    Type: String
    NoEcho: true

Resources:
  # S3 Bucket for static data
  DataBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: aushadhimitra-data
      
  # DynamoDB Tables
  AllopathyCacheTable:
    Type: AWS::DynamoDB::Table
    Properties:
      TableName: allopathy_cache
      BillingMode: PAY_PER_REQUEST
      AttributeDefinitions:
        - AttributeName: drug_name
          AttributeType: S
      KeySchema:
        - AttributeName: drug_name
          KeyType: HASH
      TimeToLiveSpecification:
        AttributeName: ttl
        Enabled: true
  
  # Lambda Functions
  CheckCuratedDbFunction:
    Type: AWS::Serverless::Function
    Properties:
      FunctionName: aushadhimitra-check-curated-db
      Runtime: python3.12
      Handler: handler.handler
      CodeUri: lambda/check_curated_db/
      Timeout: 30
      MemorySize: 256
      Policies:
        - S3ReadPolicy:
            BucketName: !Ref DataBucket
            
  AyushNameResolverFunction:
    Type: AWS::Serverless::Function
    Properties:
      FunctionName: aushadhimitra-ayush-name-resolver
      Runtime: python3.12
      Handler: handler.handler
      CodeUri: lambda/ayush_name_resolver/
      Timeout: 30
      Policies:
        - S3ReadPolicy:
            BucketName: !Ref DataBucket
            
  WebSearchTavilyFunction:
    Type: AWS::Serverless::Function
    Properties:
      FunctionName: aushadhimitra-web-search-tavily
      Runtime: python3.12
      Handler: handler.handler
      CodeUri: lambda/web_search_tavily/
      Timeout: 60
      Environment:
        Variables:
          TAVILY_API_KEY: !Ref TavilyApiKey

  BuildKnowledgeGraphFunction:
    Type: AWS::Serverless::Function
    Properties:
      FunctionName: aushadhimitra-build-knowledge-graph
      Runtime: python3.12
      Handler: handler.handler
      CodeUri: lambda/build_knowledge_graph/
      Timeout: 30

  CalculateSeverityFunction:
    Type: AWS::Serverless::Function
    Properties:
      FunctionName: aushadhimitra-calculate-severity
      Runtime: python3.12
      Handler: handler.handler
      CodeUri: lambda/calculate_severity/
      Timeout: 30

  FormatProfessionalResponseFunction:
    Type: AWS::Serverless::Function
    Properties:
      FunctionName: aushadhimitra-format-professional-response
      Runtime: python3.12
      Handler: handler.handler
      CodeUri: lambda/format_professional_response/
      Timeout: 30
      MemorySize: 256

  # API Gateway
  ApiGateway:
    Type: AWS::Serverless::Api
    Properties:
      StageName: prod
      Cors:
        AllowOrigin: "'*'"
        AllowMethods: "'POST, GET, OPTIONS'"
        AllowHeaders: "'Content-Type'"
```

## Frontend

### React with Cytoscape.js (Professional UI)

```javascript
// src/components/KnowledgeGraphViewer.jsx
import React from 'react';
import CytoscapeComponent from 'react-cytoscapejs';

const KnowledgeGraphViewer = ({ graph }) => {
  const elements = [
    ...graph.nodes.map(node => ({
      data: { id: node.id, label: node.label },
      style: {
        'background-color': node.is_overlap ? '#F44336' : node.color,
        'width': node.is_overlap ? 60 : 40,
        'height': node.is_overlap ? 60 : 40,
        'label': 'data(label)',
        'font-size': '10px',
        'text-valign': 'bottom',
        'text-margin-y': 5
      }
    })),
    ...graph.edges.map(edge => ({
      data: { 
        id: edge.id, 
        source: edge.source, 
        target: edge.target,
        label: edge.relation 
      },
      style: {
        'line-color': edge.is_interaction_path ? '#F44336' : '#9E9E9E',
        'width': edge.is_interaction_path ? 4 : 2,
        'target-arrow-color': edge.is_interaction_path ? '#F44336' : '#9E9E9E',
        'target-arrow-shape': 'triangle',
        'curve-style': 'bezier',
        'label': 'data(label)',
        'font-size': '8px',
        'text-rotation': 'autorotate'
      }
    }))
  ];

  return (
    <div className="kg-container" style={{ height: '400px', border: '1px solid #ddd' }}>
      <CytoscapeComponent
        elements={elements}
        style={{ width: '100%', height: '100%' }}
        layout={{ name: 'cose', animate: true }}
        cy={(cy) => {
          cy.on('tap', 'node', (evt) => {
            const node = evt.target;
            console.log('Node clicked:', node.data());
          });
        }}
      />
    </div>
  );
};

export default KnowledgeGraphViewer;
```

## Demo Scenarios

| Priority | AYUSH | Allopathic | Expected | Notes |
|----------|-------|------------|----------|-------|
| 1 | Turmeric | Warfarin | MAJOR (curated) | Instant response |
| 2 | St. John's Wort | Cyclosporine | MAJOR (curated) | Dramatic impact |
| 3 | Ginger | Metformin | MODERATE (curated) | Shows moderate |
| 4 | Ashwagandha | Sertraline | Real-time | Shows agent flow |

## Cost Estimate (Hackathon)

| Service | Usage | Estimated Cost |
|---------|-------|----------------|
| Bedrock Agents | ~100 invocations | ~$5 |
| Claude 3 Sonnet | ~50K tokens | ~$2 |
| Claude 3 Haiku | ~100K tokens | ~$1 |
| Lambda | ~500 invocations | ~$0.10 |
| S3 | <1GB | ~$0.02 |
| DynamoDB | On-demand | ~$0.50 |
| **Total** | | **~$10** |