# Requirements Document

## Introduction

AushadhiMitra is an AI-powered interaction checker that helps users identify potential drug interactions between AYUSH (Ayurveda, Yoga & Naturopathy, Unani, Siddha, and Homeopathy) medicines and allopathic drugs. The system uses **AWS Bedrock Agents with Multi-Agent Collaboration** to orchestrate specialized agents that gather real-time data from multiple sources (IMPPAT, DrugBank via web search, Tavily API for research), perform grounded reasoning on the gathered evidence, and provide accurate interaction assessments with full source citations.

The system supports two user personas: AYUSH practitioners who need detailed technical information with evidence sources and interactive knowledge graph visualization, and individual patients who need simple, multilingual explanations. The architecture emphasizes a tiered approach: instant responses for curated high-impact interactions, and real-time data gathering for other queries with local fallback for reliability.

## Glossary

- **AYUSH**: Ayurveda, Yoga & Naturopathy, Unani, Siddha, and Homeopathy traditional medicine systems
- **Allopathic Drug**: Modern pharmaceutical medicine based on Western medical science
- **Amazon Bedrock Agents**: AWS managed service for building conversational AI agents with tool use capabilities
- **Multi-Agent Collaboration**: AWS Bedrock feature enabling supervisor agents to orchestrate multiple specialized sub-agents
- **Supervisor Agent**: Central agent that routes requests and coordinates collaborator agents
- **Collaborator Agent**: Specialized sub-agent handling specific domain tasks
- **Action Group**: Collection of Lambda functions that define actions an agent can perform
- **Knowledge Base**: Amazon Bedrock feature for RAG using S3 documents and vector embeddings
- **IMPPAT**: Indian Medicinal Plants, Phytochemistry And Therapeutics database - primary source for AYUSH phytochemical data
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
- **Curated Interaction Database**: Pre-computed high-confidence interaction pairs with complete data for instant demo responses
- **Narrow Therapeutic Index (NTI)**: Drugs where small changes in blood levels can cause serious toxicity
- **Hero Scenario**: Pre-tested, high-impact demo scenario showcasing dramatic clinical consequences

## Requirements

### Requirement 1: Natural Language Medicine Input

**User Story:** As a patient taking both AYUSH and allopathic medicines, I want to input my medicines in natural language using common names or brand names, so that I can easily check for interactions without medical terminology.

#### Acceptance Criteria

1. WHEN a user sends a message containing medicine names THEN the Supervisor Agent SHALL extract and identify medicine references
2. WHEN a user describes medicines using common names (e.g., "haldi" for Turmeric) THEN the system SHALL normalize names using the local curated database
3. WHEN a user mentions an allopathic brand name (e.g., "Glycomet") THEN the Allopathy Collaborator Agent SHALL perform web search to find its generic name
4. WHEN a user mentions an AYUSH brand name (e.g., "Himalaya Ashwagandha") THEN the AYUSH Collaborator Agent SHALL identify the primary herb using local brand mapping
5. WHEN the system cannot identify a medicine with confidence THEN the Supervisor Agent SHALL request clarification from the user

### Requirement 2: Curated Interaction Database (Layer 0)

**User Story:** As a hackathon presenter, I want instant, reliable responses for high-impact interaction pairs, so that the demo is impressive and consistent.

#### Acceptance Criteria

1. WHEN a query matches a curated interaction pair THEN the system SHALL return the pre-computed response in under 500ms (Layer 0)
2. WHEN preparing the curated database THEN it SHALL include at least 10-15 high-impact interaction pairs with dramatic clinical consequences
3. WHEN a curated pair is queried THEN the response SHALL include: pre-built knowledge graph, severity assessment, clinical effects, research citations, and AI summary
4. WHEN building curated entries THEN each SHALL include at least one research paper citation with PubMed link
5. WHEN the curated database contains an interaction THEN it SHALL be marked with evidence quality (clinical_study, case_report, in_vitro)
6. WHEN a curated pair includes NTI drugs (Warfarin, Cyclosporine, Digoxin) THEN it SHALL be flagged as high-priority

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

### Requirement 3: AWS Bedrock Multi-Agent Architecture

**User Story:** As a system architect, I want to use AWS Bedrock's multi-agent collaboration to orchestrate specialized agents, so that the system is scalable, maintainable, and uses managed AWS services.

#### Acceptance Criteria

1. WHEN the system is deployed THEN it SHALL use Amazon Bedrock Agents with Multi-Agent Collaboration feature
2. WHEN configuring agents THEN there SHALL be 1 Supervisor Agent and 3 Collaborator Agents (AYUSH, Allopathy, Reasoning)
3. WHEN the Supervisor Agent receives a request THEN it SHALL route to appropriate collaborator agents based on the query
4. WHEN collaborator agents execute THEN they SHALL use AWS Lambda functions as Action Groups for deterministic operations
5. WHEN agents need LLM capabilities THEN they SHALL use Amazon Bedrock foundation models (Claude 3 Sonnet/Haiku)
6. WHEN agents need document retrieval THEN they SHALL optionally use Amazon Bedrock Knowledge Bases

### Requirement 4: AYUSH Collaborator Agent

**User Story:** As a system processing AYUSH medicines, I want a specialized collaborator agent to gather comprehensive phytochemical and ADMET data.

#### Acceptance Criteria

1. WHEN the AYUSH Collaborator Agent is invoked THEN it SHALL first check the curated interaction database for instant response
2. WHEN not in curated database THEN the agent SHALL use Lambda Action Groups to lookup local database for name normalization
3. WHEN the scientific name is found THEN the agent SHALL retrieve phytochemical data from S3-stored IMPPAT JSON files
4. WHEN CYP inducer information is not available THEN the agent SHALL use Tavily web search via Lambda
5. WHEN any data source fails THEN the agent SHALL automatically fallback to locally cached data
6. WHEN data gathering is complete THEN the agent SHALL report data_completeness score and gaps

### Requirement 5: Allopathy Collaborator Agent

**User Story:** As a system processing allopathic drugs, I want a specialized collaborator agent to gather comprehensive CYP metabolism data via web search.

#### Acceptance Criteria

1. WHEN the Allopathy Collaborator Agent is invoked THEN it SHALL first check DynamoDB cache for previously gathered data
2. WHEN cached data exists and is fresh (< 7 days) THEN the agent SHALL use cached data
3. WHEN cache miss THEN the agent SHALL use Lambda Action Group to perform Tavily web search for DrugBank CYP data
4. WHEN the drug is a Narrow Therapeutic Index drug THEN the agent SHALL flag it for elevated severity scoring
5. WHEN web search fails THEN the agent SHALL try alternative queries and report gaps
6. WHEN data is successfully gathered THEN it SHALL be cached in DynamoDB for future queries

### Requirement 6: Reasoning Collaborator Agent

**User Story:** As a system analyzing drug interactions, I want a specialized reasoning agent to build knowledge graphs, detect conflicts, and calculate severity.

#### Acceptance Criteria

1. WHEN the Reasoning Collaborator Agent receives data from both agents THEN it SHALL analyze ONLY the provided evidence
2. WHEN analyzing interactions THEN the agent SHALL use Lambda Action Group to build JSON knowledge graph
3. WHEN the knowledge graph is built THEN the agent SHALL identify overlap nodes (enzymes affected by both medicines)
4. WHEN overlap nodes are found THEN the agent SHALL use Lambda Action Group to calculate rule-based severity score
5. WHEN different sources provide conflicting information THEN the agent SHALL explicitly report the conflict
6. WHEN evidence is insufficient THEN the agent SHALL report "UNKNOWN - Limited data available"

### Requirement 6.1: Response Formatting

**User Story:** As a system serving two different user types, I want responses formatted appropriately for each persona.

#### Acceptance Criteria

1. WHEN user_type is "professional" THEN the Reasoning Agent SHALL call format_professional_response Lambda
2. WHEN format_professional_response is called THEN it SHALL assemble structured JSON including: query details, severity assessment, knowledge graph, mechanisms, drug profiles, research citations, conflicts (if any), AI summary, and disclaimer
3. WHEN user_type is "patient" THEN the Reasoning Agent SHALL generate a simple 4-5 sentence response directly using LLM
4. WHEN generating patient response THEN it SHALL match the detected language (English/Hindi/Hinglish)
5. WHEN severity is MODERATE or MAJOR THEN patient response SHALL include clear actionable advice
6. WHEN responding to curated database hits THEN pre-computed summaries SHALL be used directly without calling format Lambda

### Requirement 7: Lambda Action Groups

**User Story:** As a developer, I want agent actions to be implemented as Lambda functions, so that business logic is deterministic and testable.

#### Acceptance Criteria

1. WHEN defining action groups THEN each Lambda function SHALL have an OpenAPI schema defining its parameters
2. WHEN Lambda functions are invoked THEN they SHALL handle the Bedrock Agent event format and return proper responses
3. WHEN implementing action groups THEN the following Lambda functions SHALL be created:
   - `check_curated_db` - Check curated interaction database in S3
   - `ayush_name_resolver` - Local lookup for name normalization
   - `imppat_lookup` - Load phytochemical + ADMET data from S3
   - `web_search_tavily` - Search web using Tavily API
   - `cache_lookup` - Check DynamoDB for cached allopathy data
   - `cache_save` - Save to DynamoDB cache
   - `build_knowledge_graph` - Construct JSON graph and identify overlaps
   - `calculate_severity` - Rule-based severity scoring
   - `format_professional_response` - Assemble structured JSON for professional UI
4. WHEN Lambda functions fail THEN they SHALL return appropriate error responses for agent handling

### Requirement 8: Knowledge Graph Generation

**User Story:** As an AYUSH practitioner, I want to see a visual knowledge graph showing the interaction pathway between medicines.

#### Acceptance Criteria

1. WHEN both agents complete data gathering THEN the system SHALL build a JSON-based knowledge graph via Lambda
2. WHEN building the knowledge graph THEN it SHALL include nodes for: Plant, Phytochemicals, Drug, CYP Enzymes, Transporters
3. WHEN building edges THEN it SHALL include relationships: CONTAINS, INHIBITS, INDUCES, SUBSTRATE_OF, METABOLIZED_BY
4. WHEN overlap nodes are found THEN they SHALL be marked as interaction points
5. WHEN displaying to professional users THEN the graph SHALL be rendered using Cytoscape.js

### Requirement 9: Severity Classification

**User Story:** As a patient, I want to understand the severity of any interaction found.

#### Acceptance Criteria

1. WHEN an interaction is detected THEN the system SHALL classify severity as NONE, MINOR, MODERATE, or MAJOR
2. WHEN calculating severity THEN the Lambda function SHALL consider: CYP pathway importance, NTI status, clinical evidence
3. WHEN the allopathic drug has Narrow Therapeutic Index THEN severity score SHALL be boosted by 25 points
4. WHEN severity is MAJOR THEN the response SHALL include urgent action recommendations

### Requirement 10: Source Citation and Traceability

**User Story:** As an AYUSH practitioner, I want interaction results to cite all evidence sources with URLs.

#### Acceptance Criteria

1. WHEN any claim is made about an interaction THEN the system SHALL cite the specific source URL
2. WHEN data is from IMPPAT THEN the system SHALL include the IMPPAT URL
3. WHEN research articles support an interaction THEN the system SHALL include PubMed links
4. WHEN an interaction is inferred from CYP pathway THEN it SHALL be labeled as "Inferred from CYP mechanism"

### Requirement 11: Professional User Interface (Web)

**User Story:** As an AYUSH practitioner, I want a detailed web interface showing comprehensive drug comparison and interactive knowledge graph.

#### Acceptance Criteria

1. WHEN a professional user submits medicines THEN the system SHALL display a detailed comparison view
2. WHEN displaying the knowledge graph THEN the interface SHALL render an interactive Cytoscape.js visualization
3. WHEN displaying sources THEN the interface SHALL show ALL clickable links
4. WHEN conflicts exist THEN the interface SHALL explicitly display conflicting information

### Requirement 12: Patient User Interface (Chat)

**User Story:** As a non-medical patient, I want to interact via a simple chat interface in my preferred language.

#### Acceptance Criteria

1. WHEN a patient sends a message THEN the system SHALL respond in conversational language
2. WHEN the user writes in Hindi, English, or Hinglish THEN the system SHALL respond in the same language
3. WHEN severity is MODERATE or MAJOR THEN the response SHALL include clear actionable advice

### Requirement 13: AWS Infrastructure

**User Story:** As a developer, I want the system deployed on AWS using managed services for reliability and scalability.

#### Acceptance Criteria

1. WHEN deploying the system THEN it SHALL use the following AWS services:
   - Amazon Bedrock Agents for multi-agent orchestration
   - AWS Lambda for action group functions
   - Amazon S3 for static data (IMPPAT JSON, curated database)
   - Amazon DynamoDB for caching
   - Amazon API Gateway for REST API endpoints
   - AWS Amplify for frontend hosting
2. WHEN configuring Lambda functions THEN they SHALL use Python 3.12 runtime
3. WHEN deploying THEN AWS SAM or CloudFormation SHALL be used for infrastructure as code
4. WHEN storing secrets THEN AWS Secrets Manager SHALL be used for API keys (Tavily)

### Requirement 14: Local Data Preparation

**User Story:** As a developer preparing for the hackathon, I want pre-extracted local data for reliability.

#### Acceptance Criteria

1. WHEN preparing local data THEN it SHALL be uploaded to S3 bucket with the following structure:
   - `s3://bucket/curated/curated_interactions.json`
   - `s3://bucket/ayush/imppat/{plant_name}.json`
   - `s3://bucket/reference/nti_drugs.json`
   - `s3://bucket/reference/cyp_enzymes.json`
2. WHEN preparing AYUSH data THEN it SHALL include data for 4 priority plants: Curcuma longa, Glycyrrhiza glabra, Zingiber officinale, Hypericum perforatum
3. WHEN real-time data gathering fails THEN the system SHALL fallback to S3 cached data

### Requirement 15: Error Handling and Graceful Degradation

**User Story:** As a user, I want the system to handle errors gracefully.

#### Acceptance Criteria

1. WHEN Lambda functions encounter errors THEN they SHALL return appropriate error responses
2. WHEN Bedrock Agent orchestration fails THEN fallback responses SHALL be returned
3. WHEN partial data is available THEN the system SHALL proceed and indicate missing information

### Requirement 16: Medical Disclaimers

**User Story:** As a user receiving health information, I want to see appropriate disclaimers.

#### Acceptance Criteria

1. WHEN an interaction result is displayed THEN the system SHALL include a disclaimer
2. WHEN severity is MODERATE or MAJOR THEN the system SHALL recommend consulting a doctor
3. WHEN the system cannot determine interaction status THEN it SHALL advise consulting a pharmacist

### Requirement 17: Demo Reliability

**User Story:** As a hackathon presenter, I want reliable demo scenarios.

#### Acceptance Criteria

1. WHEN demonstrating THEN the presenter SHALL use curated hero scenarios first
2. WHEN Tavily web search fails during demo THEN automatic S3 fallback SHALL provide seamless experience
3. WHEN discussing limitations THEN the presentation SHALL mention need for commercial API access for production

### Requirement 18: Pharmacodynamic Effect Analysis

**User Story:** As an Interaction Checker, I want to identify pharmacodynamic overlaps.

#### Acceptance Criteria

1. WHEN analyzing interactions THEN the Reasoning Agent SHALL check for overlapping pharmacodynamic effects
2. WHEN two medicines share the same effect category THEN the agent SHALL flag additive interaction
3. WHEN both CYP and pharmacodynamic interactions are found THEN the agent SHALL report both

### Requirement 19: Research Article Search

**User Story:** As a Reasoning Agent, I want to search for relevant research articles.

#### Acceptance Criteria

1. WHEN analyzing an interaction THEN the agent SHALL use Tavily Lambda to search for research articles
2. WHEN research articles are found THEN the agent SHALL extract key findings
3. WHEN research contradicts other sources THEN the agent SHALL note the conflict