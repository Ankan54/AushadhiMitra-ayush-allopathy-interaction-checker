# Requirements Document

## Introduction

AushadhiMitra is an AI-powered interaction checker that helps users identify potential drug interactions between AYUSH (Ayurveda, Yoga & Naturopathy, Unani, Siddha, and Homeopathy) medicines and allopathic drugs. The system uses a multi-agent architecture built with CrewAI Flows to gather real-time data from multiple sources (IMPPAT, DrugBank, web search), perform grounded reasoning on the gathered evidence, and provide accurate interaction assessments with full source citations.

The system supports two user personas: AYUSH practitioners who need detailed technical information with evidence sources, and individual patients who need simple, multilingual explanations. The architecture emphasizes real-time data gathering to ensure accuracy and relevancy, with local fallback data for demo reliability.

## Glossary

- **AYUSH**: Ayurveda, Yoga & Naturopathy, Unani, Siddha, and Homeopathy traditional medicine systems
- **Allopathic Drug**: Modern pharmaceutical medicine based on Western medical science
- **IMPPAT**: Indian Medicinal Plants, Phytochemistry And Therapeutics database - primary source for AYUSH phytochemical data
- **DrugBank**: Comprehensive pharmaceutical database for allopathic drug ADMET properties
- **ADMET**: Absorption, Distribution, Metabolism, Excretion, Toxicity properties of a drug
- **CYP450 Pathway**: Cytochrome P450 enzyme system responsible for drug metabolism
- **CYP Inhibitor**: A compound that blocks CYP enzyme activity, potentially increasing drug levels
- **CYP Inducer**: A compound that increases CYP enzyme activity, potentially decreasing drug efficacy
- **CYP Substrate**: A drug that is metabolized by a specific CYP enzyme
- **Phytochemical**: Chemical compound produced by plants, the active ingredients in AYUSH medicines
- **Pharmacodynamic Interaction**: Interaction based on the combined effects of medicines on the body
- **Pharmacokinetic Interaction**: Interaction based on how medicines affect each other's absorption, metabolism, or elimination
- **Grounded Response**: AI response that is strictly based on provided evidence sources, not model's internal knowledge
- **Evidence Hierarchy**: Ranking of evidence quality: Clinical Study > In Vivo > In Vitro > Computational Prediction
- **Conflict Detection**: Identifying when different sources provide contradictory information about an interaction
- **CrewAI Flows**: Framework for orchestrating multi-agent workflows with parallel and sequential execution
- **Severity Level**: Classification of interaction risk as NONE, LOW, MODERATE, or HIGH
- **Effect Category**: Classification of a medicine's pharmacodynamic effects (e.g., Blood Sugar Lowering, Blood Thinning)

## Requirements

### Requirement 1: Natural Language Medicine Input

**User Story:** As a patient taking both AYUSH and allopathic medicines, I want to input my medicines in natural language using common names or brand names, so that I can easily check for interactions without medical terminology.

#### Acceptance Criteria

1. WHEN a user sends a message containing medicine names THEN the AYUSH Data Agent or Allopathy Data Agent SHALL extract and identify the medicine references
2. WHEN a user describes medicines using common names (e.g., "haldi" for Turmeric) THEN the agent SHALL normalize the names to standard scientific forms using the local curated database
3. WHEN a user mentions an allopathic brand name (e.g., "Glycomet") THEN the Allopathy Data Agent SHALL perform web search to find its generic name and chemical composition
4. WHEN a user mentions an AYUSH brand name (e.g., "Himalaya Ashwagandha") THEN the AYUSH Data Agent SHALL identify the primary herb or formulation
5. WHEN the system cannot identify a medicine with confidence THEN the Orchestrator SHALL request clarification from the user before proceeding

### Requirement 2: AYUSH Medicine Data Gathering

**User Story:** As a system processing AYUSH medicines, I want to gather comprehensive phytochemical and ADMET data, so that I can accurately assess potential interactions.

#### Acceptance Criteria

1. WHEN an AYUSH medicine is identified THEN the AYUSH Data Agent SHALL first lookup the local curated database for common name to scientific name mapping
2. WHEN the scientific name is found THEN the agent SHALL retrieve phytochemical links from the local pre-extracted IMPPAT data
3. WHEN phytochemical links are available THEN the agent SHALL scrape IMPPAT website to extract ADMET properties including CYP inhibitor/inducer data (displayed from SwissADME)
4. WHEN CYP inducer information is not available from IMPPAT THEN the agent SHALL perform web search to find CYP inducer research data
5. WHEN web scraping fails THEN the agent SHALL automatically fallback to locally cached ADMET data for that medicine
6. WHEN an AYUSH medicine is not in the local database THEN the agent SHALL perform web search to gather basic information and inform the user about limited data availability

### Requirement 3: Allopathic Drug Data Gathering

**User Story:** As a system processing allopathic drugs, I want to gather comprehensive ADMET and CYP metabolism data, so that I can accurately assess potential interactions.

#### Acceptance Criteria

1. WHEN an allopathic drug name is provided (likely a brand name) THEN the Allopathy Data Agent SHALL perform web search to find its chemical composition and generic names
2. WHEN generic names are identified THEN the agent SHALL search DrugBank.com or Drugs.com to extract CYP substrate, inhibitor, and inducer data
3. WHEN CYP inducer information is needed THEN the agent SHALL also search for inducer data via web search
4. WHEN the drug is another AYUSH medicine THEN the system SHALL route it to the AYUSH Data Agent instead
5. WHEN web scraping fails THEN the agent SHALL automatically fallback to locally cached drug data
6. WHEN a drug is not found in any source THEN the agent SHALL inform the Reasoning Agent about data limitations

### Requirement 4: Parallel Data Processing

**User Story:** As a system architect, I want both medicine data gathering processes to run in parallel, so that the system provides faster responses to users.

#### Acceptance Criteria

1. WHEN two medicines are identified THEN the AYUSH Data Agent and Allopathy Data Agent SHALL execute in parallel using CrewAI Flows
2. WHEN both agents complete THEN their results SHALL be passed to the Reasoning Agent for analysis
3. WHEN one agent fails THEN the other agent SHALL continue processing and partial results SHALL be used
4. WHEN processing multiple medicine pairs THEN the system SHALL optimize parallel execution for all pairs
5. WHEN parallel execution exceeds timeout (30 seconds) THEN the system SHALL use available partial results with appropriate caveats

### Requirement 5: Grounded Reasoning and Conflict Detection

**User Story:** As a healthcare information system, I want to generate interaction assessments that are strictly grounded in gathered evidence and transparently handle conflicting sources, so that users receive accurate and trustworthy information.

#### Acceptance Criteria

1. WHEN the Reasoning Agent receives data from both medicine agents THEN it SHALL analyze ONLY the provided evidence without using internal model knowledge for factual claims
2. WHEN analyzing CYP interactions THEN the agent SHALL check if the AYUSH phytochemicals inhibit/induce CYP enzymes that metabolize the allopathic drug
3. WHEN different sources provide conflicting information THEN the agent SHALL explicitly identify and report the conflict
4. WHEN resolving conflicts THEN the agent SHALL prioritize sources based on evidence hierarchy: Clinical Study > In Vivo Study > In Vitro Study > Computational Prediction > Traditional Knowledge
5. WHEN conflicts cannot be resolved THEN the agent SHALL present both viewpoints and recommend consulting a healthcare provider
6. WHEN evidence is insufficient THEN the agent SHALL report "UNKNOWN - Limited data available" rather than inferring safety

### Requirement 6: Severity Classification

**User Story:** As a patient, I want to understand the severity of any interaction found, so that I know how urgently I need to act.

#### Acceptance Criteria

1. WHEN an interaction is detected THEN the Reasoning Agent SHALL classify severity as NONE, LOW, MODERATE, or HIGH using rule-based scoring
2. WHEN calculating severity THEN the agent SHALL consider: CYP interaction type (inhibitor vs inducer), CYP interaction strength (strong/moderate/weak), pharmacodynamic overlap, number of clinical case reports, and evidence quality
3. WHEN CYP inhibition is detected THEN the severity SHALL reflect risk of increased drug levels and potential toxicity
4. WHEN CYP induction is detected THEN the severity SHALL reflect risk of decreased drug efficacy
5. WHEN both CYP and pharmacodynamic interactions exist THEN the scores SHALL be combined for overall severity
6. WHEN severity is HIGH THEN the response SHALL include urgent action recommendations and explicit advice to consult a healthcare provider

### Requirement 7: Source Citation and Traceability

**User Story:** As an AYUSH practitioner, I want interaction results to cite all evidence sources with URLs, so that I can verify the information and assess its reliability.

#### Acceptance Criteria

1. WHEN any claim is made about an interaction THEN the system SHALL cite the specific source URL that supports the claim
2. WHEN data is scraped from IMPPAT THEN the system SHALL include the IMPPAT phytochemical page URL
3. WHEN data is from DrugBank or Drugs.com THEN the system SHALL include the specific drug page URL
4. WHEN research articles support an interaction THEN the system SHALL include PubMed links or article URLs from web search
5. WHEN an interaction is inferred from CYP pathway analysis THEN the system SHALL clearly label it as "Inferred from CYP mechanism" with the sources used for CYP data
6. WHEN evidence quality varies THEN the system SHALL indicate the evidence level (Clinical/In Vivo/In Vitro/Predicted) for each source

### Requirement 8: Professional User Interface (Web)

**User Story:** As an AYUSH practitioner, I want a detailed web interface showing comprehensive drug comparison and evidence, so that I can make informed clinical decisions.

#### Acceptance Criteria

1. WHEN a professional user submits medicines via the web interface THEN the system SHALL display a detailed comparison view
2. WHEN displaying results THEN the interface SHALL show both drugs with their phytochemicals/compounds and ADMET properties
3. WHEN displaying CYP data THEN the interface SHALL show enzyme-specific inhibitor and inducer information for both medicines
4. WHEN displaying the assessment THEN the interface SHALL show the AI-generated technical summary directed toward medical professionals
5. WHEN displaying sources THEN the interface SHALL show ALL clickable links to drugs, compounds, research articles, and data sources used
6. WHEN conflicts exist in sources THEN the interface SHALL explicitly display the conflicting information with source attribution

### Requirement 9: Patient User Interface (Chat)

**User Story:** As a non-medical patient, I want to interact via a simple chat interface in my preferred language, so that I can understand the interaction information easily.

#### Acceptance Criteria

1. WHEN a patient sends a message via the chat interface THEN the Communicator Agent SHALL process it and respond in conversational language
2. WHEN the user writes in Hindi, English, Hinglish, or regional languages (in regional or English alphabets) THEN the Communicator Agent SHALL detect the language and respond in the same language and tone
3. WHEN generating patient responses THEN the Communicator Agent SHALL summarize the interaction assessment in 4-5 simple, direct sentences
4. WHEN severity is MODERATE or HIGH THEN the response SHALL include clear actionable advice (e.g., "Talk to your doctor before taking these together")
5. WHEN technical terms must be used THEN the Communicator Agent SHALL explain them in simple language
6. WHEN the assessment is uncertain THEN the response SHALL advise consulting a healthcare provider without causing unnecessary alarm

### Requirement 10: Two Workflow Architecture

**User Story:** As a system architect, I want two separate CrewAI Flows for professional and patient users that share common data gathering agents, so that the system efficiently serves both user types.

#### Acceptance Criteria

1. WHEN the system initializes THEN it SHALL create two CrewAI Flows: Professional Flow and Patient Flow
2. WHEN either flow executes THEN both SHALL use the same AYUSH Data Agent and Allopathy Data Agent for parallel data gathering
3. WHEN the Professional Flow completes data gathering THEN it SHALL use a Reasoning Agent that generates structured technical output for UI rendering
4. WHEN the Patient Flow completes data gathering THEN it SHALL use a Communicator Agent that generates friendly, multilingual chat responses
5. WHEN routing a request THEN the system SHALL determine the appropriate flow based on the interface (web = Professional, chat = Patient)

### Requirement 11: Local Data Preparation

**User Story:** As a developer preparing for the hackathon, I want pre-extracted local data for reliability, so that the demo works even if web scraping fails.

#### Acceptance Criteria

1. WHEN preparing local data THEN the system SHALL extract medicinal plant names, common names, and phytochemical links from IMPPAT website and store in a local JSON file
2. WHEN preparing local data THEN the system SHALL include ADMET properties for at least 20 priority AYUSH herbs (Ashwagandha, Turmeric, Brahmi, Triphala, etc.)
3. WHEN preparing local data THEN the system SHALL include CYP metabolism data for at least 50 common allopathic drugs
4. WHEN preparing local data THEN the system SHALL include at least 30 pre-curated critical interaction pairs with full evidence
5. WHEN real-time scraping fails THEN the system SHALL automatically and silently fallback to local cached data
6. WHEN using fallback data THEN the system SHALL inform the user that results are from cached data (in professional mode only)

### Requirement 12: Error Handling and Graceful Degradation

**User Story:** As a user, I want the system to handle errors gracefully, so that I receive useful information even when some data sources are unavailable.

#### Acceptance Criteria

1. WHEN web scraping encounters an error THEN the system SHALL log the error and fallback to local cached data without user-visible error messages
2. WHEN a medicine is not found in any source THEN the system SHALL inform the user and suggest checking the spelling or trying alternative names
3. WHEN all data sources fail THEN the system SHALL provide a user-friendly message and recommend consulting a pharmacist
4. WHEN partial data is available THEN the system SHALL proceed with available data and clearly indicate which information is missing
5. WHEN the LLM fails to generate a response THEN the system SHALL provide a template-based fallback response with available data

### Requirement 13: Conversation Context (Chat Interface)

**User Story:** As a patient using the chat interface, I want to have follow-up conversations, so that I can ask additional questions about the same medicines.

#### Acceptance Criteria

1. WHEN a user sends a follow-up message THEN the Orchestrator SHALL maintain conversation context from previous turns
2. WHEN a user references "those medicines" or "the interaction" THEN the system SHALL resolve the reference from conversation history
3. WHEN a user asks for more details THEN the system SHALL provide additional information from the already-gathered data
4. WHEN a user wants to check different medicines THEN the system SHALL start a new data gathering process
5. WHEN the conversation is inactive for 30 minutes THEN the system SHALL expire the session and start fresh

### Requirement 14: Medical Disclaimers

**User Story:** As a user receiving health information, I want to see appropriate disclaimers, so that I understand this tool does not replace professional medical advice.

#### Acceptance Criteria

1. WHEN an interaction result is displayed THEN the system SHALL include a disclaimer that this is for informational purposes only
2. WHEN severity is MODERATE or HIGH THEN the system SHALL explicitly recommend consulting a doctor or pharmacist
3. WHEN providing recommendations THEN the system SHALL NOT advise stopping or changing medication dosage without consulting a healthcare provider
4. WHEN a user asks for medical advice beyond interaction checking THEN the system SHALL redirect them to consult a healthcare professional
5. WHEN the system cannot determine interaction status THEN it SHALL advise the user to consult a pharmacist rather than assuming safety

### Requirement 15: Demo Reliability

**User Story:** As a hackathon presenter, I want reliable demo scenarios, so that the system performs consistently during the presentation.

#### Acceptance Criteria

1. WHEN preparing for demo THEN the system SHALL have pre-identified medicine pairs where web scraping works reliably
2. WHEN demonstrating THEN the presenter SHALL use pre-tested scenarios that showcase real-time data gathering
3. WHEN web scraping fails during demo THEN the automatic fallback SHALL provide seamless experience with cached data
4. WHEN discussing limitations THEN the presentation SHALL mention the need for commercial API access (DrugBank, IMPPAT) for production
5. WHEN caching THEN the system SHALL implement a caching layer to store successful web scrape results for reuse

### Requirement 16: Pharmacodynamic Effect Analysis

**User Story:** As an Interaction Checker, I want to identify pharmacodynamic overlaps even when CYP data is unavailable, so that I can detect additive or antagonistic effects.

#### Acceptance Criteria

1. WHEN analyzing interactions THEN the Reasoning Agent SHALL check for overlapping pharmacodynamic effects (e.g., both cause sedation, both lower blood sugar)
2. WHEN two medicines share the same effect category THEN the agent SHALL flag a potential additive interaction
3. WHEN two medicines have opposing effects THEN the agent SHALL flag a potential antagonistic interaction
4. WHEN pharmacodynamic effects are identified THEN the agent SHALL describe the potential clinical outcome (e.g., "Additive hypoglycemic effect may cause dangerously low blood sugar")
5. WHEN both CYP and pharmacodynamic interactions are found THEN the agent SHALL report both mechanisms

### Requirement 17: Research Article Search

**User Story:** As a Reasoning Agent, I want to search for relevant research articles, so that I can provide evidence-based interaction assessments.

#### Acceptance Criteria

1. WHEN analyzing an interaction THEN the Reasoning Agent SHALL perform web search to find relevant research articles about the specific drug combination
2. WHEN research articles are found THEN the agent SHALL extract key findings about interaction effects
3. WHEN research supports an interaction THEN the agent SHALL cite the source with URL and summarize the finding
4. WHEN research contradicts other sources THEN the agent SHALL include both findings and note the conflict
5. WHEN no relevant research is found THEN the agent SHALL note "No specific research found for this combination" and rely on mechanism-based inference