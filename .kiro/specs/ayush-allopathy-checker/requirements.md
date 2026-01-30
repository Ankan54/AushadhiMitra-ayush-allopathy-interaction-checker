# Requirements Document

## Introduction

AushadhiMitra is an AI-powered interaction checker that helps users identify potential drug interactions between AYUSH (Ayurveda, Yoga & Naturopathy, Unani, Siddha, and Homeopathy) medicines and allopathic drugs. The system uses a multi-agent architecture to parse natural language queries, identify medicines across both systems, check for interactions using multiple data sources, and provide patient-friendly explanations in English and Hindi.

## Glossary

- **AYUSH**: Ayurveda, Yoga & Naturopathy, Unani, Siddha, and Homeopathy traditional medicine systems
- **Allopathic Drug**: Modern pharmaceutical medicine based on Western medical science
- **Orchestrator Agent**: The primary agent that manages conversation flow and routes requests to specialist agents
- **Medicine Identifier Agent**: Specialist agent responsible for normalizing medicine names and identifying medicine types
- **Interaction Checker Agent**: Specialist agent that evaluates potential interactions using multiple data layers
- **Explanation Agent**: Specialist agent that generates patient-friendly explanations and translations
- **CYP450 Pathway**: Cytochrome P450 enzyme system responsible for drug metabolism
- **Pharmacodynamic Interaction**: Interaction based on the combined effects of medicines on the body
- **RAG**: Retrieval-Augmented Generation for searching research literature
- **Interaction Severity**: Classification of interaction risk as Safe, Caution, Warning, or Danger
- **Effect Category**: Classification of a medicine's pharmacodynamic effects (e.g., Blood Sugar Lowering, Blood Thinning) used for inferring potential interactions
- **Additive Interaction**: When two medicines with similar effects combine to produce an enhanced effect
- **Antagonistic Interaction**: When two medicines have opposing effects that may reduce efficacy

## Requirements

### Requirement 1

**User Story:** As a patient taking both AYUSH and allopathic medicines, I want to input my medicines in natural language, so that I can easily check for interactions without medical terminology.

#### Acceptance Criteria

1. WHEN a user sends a message containing medicine names THEN the Orchestrator Agent SHALL parse the message and extract medicine references
2. WHEN a user describes medicines using common terms or brand names THEN the Medicine Identifier Agent SHALL normalize the names to standard forms
3. WHEN a user misspells a medicine name THEN the Medicine Identifier Agent SHALL correct the spelling and identify the intended medicine
4. WHEN a user mentions a brand name THEN the Medicine Identifier Agent SHALL map the brand name to its generic equivalent
5. WHEN the system cannot identify a medicine with confidence THEN the Orchestrator Agent SHALL request clarification from the user

### Requirement 2

**User Story:** As a user, I want the system to recognize both AYUSH and allopathic medicines, so that I can check interactions across both medical systems.

#### Acceptance Criteria

1. WHEN a medicine name is provided THEN the Medicine Identifier Agent SHALL classify it as either AYUSH or Allopathic
2. WHEN an AYUSH medicine is identified THEN the Medicine Identifier Agent SHALL determine its system classification (Ayurveda, Siddha, Unani, or Homeopathy)
3. WHEN an AYUSH formulation contains multiple ingredients THEN the Medicine Identifier Agent SHALL extract the active ingredient list
4. WHEN an allopathic drug is identified THEN the Medicine Identifier Agent SHALL retrieve its drug class and mechanism of action
5. WHEN a medicine has multiple aliases THEN the Medicine Identifier Agent SHALL recognize all common variations

### Requirement 3

**User Story:** As a user checking medicine safety, I want to know if my medicines interact, so that I can make informed decisions about my health.

#### Acceptance Criteria

1. WHEN two or more medicines are identified THEN the Interaction Checker Agent SHALL evaluate all pairwise combinations for interactions
2. WHEN checking for interactions THEN the Interaction Checker Agent SHALL query the curated interaction database first
3. WHEN no direct interaction is found in the database THEN the Interaction Checker Agent SHALL check for pharmacodynamic effect overlaps
4. WHEN pharmacodynamic checking is inconclusive THEN the Interaction Checker Agent SHALL evaluate CYP450 pathway interactions
5. WHEN database and inference methods find no interaction THEN the Interaction Checker Agent SHALL search research literature using RAG

### Requirement 4

**User Story:** As a patient, I want to understand the severity of any interaction found, so that I know how urgently I need to act.

#### Acceptance Criteria

1. WHEN an interaction is detected THEN the Interaction Checker Agent SHALL classify the severity as Safe, Caution, Warning, or Danger
2. WHEN calculating severity THEN the Interaction Checker Agent SHALL consider the interaction mechanism type
3. WHEN calculating severity THEN the Interaction Checker Agent SHALL consider the clinical evidence level
4. WHEN multiple interactions are found THEN the Orchestrator Agent SHALL present them ordered by severity from highest to lowest
5. WHEN severity is Warning or Danger THEN the Explanation Agent SHALL include urgent action recommendations

### Requirement 5

**User Story:** As a non-medical professional, I want explanations in simple language, so that I can understand what the interaction means without medical training.

#### Acceptance Criteria

1. WHEN an interaction is found THEN the Explanation Agent SHALL generate a patient-friendly explanation of the mechanism
2. WHEN explaining an interaction THEN the Explanation Agent SHALL describe observable symptoms or effects the user should monitor
3. WHEN providing recommendations THEN the Explanation Agent SHALL include specific actionable steps
4. WHEN citing evidence THEN the Explanation Agent SHALL reference the source type and reliability level
5. WHEN no interaction is found THEN the Explanation Agent SHALL provide reassurance with appropriate caveats

### Requirement 6

**User Story:** As a Hindi-speaking user, I want to receive information in Hindi, so that I can fully understand the health information.

#### Acceptance Criteria

1. WHEN a user requests Hindi language THEN the Explanation Agent SHALL translate all explanations to Hindi
2. WHEN translating THEN the Explanation Agent SHALL preserve medical accuracy while using accessible vocabulary
3. WHEN displaying medicine names in Hindi THEN the system SHALL show both the Hindi name and the standard medical name
4. WHEN a user inputs medicine names in Hindi THEN the Medicine Identifier Agent SHALL recognize common Hindi medicine names
5. WHEN severity levels are displayed THEN the Explanation Agent SHALL translate severity categories to Hindi equivalents

### Requirement 7

**User Story:** As a user managing multiple medicines, I want to check interactions for more than two medicines at once, so that I can evaluate my complete medication regimen.

#### Acceptance Criteria

1. WHEN a user provides three or more medicines THEN the Interaction Checker Agent SHALL evaluate all pairwise combinations
2. WHEN multiple interactions are found THEN the Orchestrator Agent SHALL present a summary of all interactions
3. WHEN presenting multiple interactions THEN the system SHALL group interactions by severity level
4. WHEN no interactions are found among multiple medicines THEN the Explanation Agent SHALL confirm that all checked pairs are safe
5. WHEN the interaction check is complex THEN the Orchestrator Agent SHALL provide progress indicators to the user

### Requirement 8

**User Story:** As a user, I want to have a conversational experience, so that I can ask follow-up questions and get clarifications naturally.

#### Acceptance Criteria

1. WHEN a user sends a message THEN the Orchestrator Agent SHALL maintain conversation context across multiple turns
2. WHEN the system needs more information THEN the Orchestrator Agent SHALL ask clarifying questions in natural language
3. WHEN a user asks a follow-up question THEN the Orchestrator Agent SHALL reference previous interaction results
4. WHEN a user requests more details about an interaction THEN the Orchestrator Agent SHALL route to the appropriate specialist agent
5. WHEN a conversation is complete THEN the Orchestrator Agent SHALL offer to check additional medicines

### Requirement 9

**User Story:** As a system architect, I want clear separation between agent responsibilities, so that the system is maintainable and each agent can be improved independently.

#### Acceptance Criteria

1. WHEN the Orchestrator Agent receives a request THEN it SHALL route to exactly one specialist agent at a time
2. WHEN a specialist agent completes its task THEN it SHALL return structured results to the Orchestrator Agent
3. WHEN the Medicine Identifier Agent processes input THEN it SHALL not perform interaction checking
4. WHEN the Interaction Checker Agent evaluates medicines THEN it SHALL not generate user-facing explanations
5. WHEN the Explanation Agent generates output THEN it SHALL not perform medicine identification or interaction checking

### Requirement 10

**User Story:** As a developer, I want the system to handle edge cases gracefully, so that users receive helpful responses even when data is incomplete.

#### Acceptance Criteria

1. WHEN a medicine is not found in any database THEN the Orchestrator Agent SHALL inform the user and suggest web search as a fallback
2. WHEN research literature search returns no results THEN the Interaction Checker Agent SHALL report insufficient evidence rather than claiming safety
3. WHEN the system encounters an error THEN the Orchestrator Agent SHALL provide a user-friendly error message
4. WHEN data sources are unavailable THEN the system SHALL operate with reduced functionality using cached data
5. WHEN confidence in medicine identification is low THEN the Medicine Identifier Agent SHALL present multiple options to the user

### Requirement 11

**User Story:** As a healthcare provider, I want interaction results to cite evidence sources, so that I can verify the information and assess its reliability.

#### Acceptance Criteria

1. WHEN an interaction is reported THEN the system SHALL include the evidence source type (curated database, clinical study, case report, or mechanism inference)
2. WHEN research papers support an interaction THEN the system SHALL include PubMed IDs or DOIs
3. WHEN an interaction is inferred from pharmacodynamic effects THEN the system SHALL clearly label it as inferred rather than directly documented
4. WHEN CYP450 pathway interactions are identified THEN the system SHALL specify which enzyme pathways are involved
5. WHEN evidence quality varies THEN the system SHALL indicate the evidence level (high, medium, or low)

### Requirement 12

**User Story:** As a system administrator, I want to use a curated interaction database, so that common interactions are checked quickly and reliably.

#### Acceptance Criteria

1. WHEN the system initializes THEN it SHALL load the curated interaction database into memory
2. WHEN a medicine pair is queried THEN the Interaction Checker Agent SHALL search the curated database in under 100 milliseconds
3. WHEN the curated database contains an interaction THEN the system SHALL use that data as the primary source
4. WHEN the curated database is updated THEN the system SHALL reload the data without requiring a restart
5. WHEN the curated database contains at least 100 interaction pairs THEN the system SHALL be considered ready for hackathon demonstration


### Requirement 13

**User Story:** As a user receiving health information, I want to see appropriate disclaimers, so that I understand this tool does not replace professional medical advice.

#### Acceptance Criteria

1. WHEN an interaction result is displayed THEN the Explanation Agent SHALL include a disclaimer that this is for informational purposes only
2. WHEN severity is Warning or Danger THEN the Explanation Agent SHALL explicitly recommend consulting a doctor or pharmacist
3. WHEN the system provides recommendations THEN it SHALL NOT advise stopping or changing medication dosage without consulting a healthcare provider
4. WHEN a user asks for medical advice beyond interaction checking THEN the Orchestrator Agent SHALL redirect them to consult a healthcare professional
5. WHEN the system cannot determine interaction status THEN it SHALL advise the user to consult a pharmacist rather than assuming safety

### Requirement 14

**User Story:** As a user in India, I want to access the system via WhatsApp, so that I can check interactions using a familiar platform without installing a new app.

#### Acceptance Criteria

1. WHEN a user sends a message via WhatsApp THEN the system SHALL process the message through the Orchestrator Agent
2. WHEN responding via WhatsApp THEN the system SHALL format responses appropriately for the WhatsApp message format
3. WHEN displaying severity levels via WhatsApp THEN the system SHALL use emoji indicators (🟢 Safe, 🟡 Caution, 🟠 Warning, 🔴 Danger)
4. WHEN a conversation spans multiple messages THEN the system SHALL maintain session context for at least 30 minutes of inactivity
5. WHEN the web interface is used THEN the system SHALL provide equivalent functionality to the WhatsApp interface

### Requirement 15

**User Story:** As an Interaction Checker Agent, I want to categorize medicines by their pharmacodynamic effects, so that I can identify potential additive or antagonistic interactions even without direct evidence.

#### Acceptance Criteria

1. WHEN a medicine is identified THEN the system SHALL categorize it into one or more effect categories (Blood Sugar Lowering, Blood Pressure Lowering, Blood Thinning, Sedation/CNS Depression, Immune Modulation, Hepatotoxic, Nephrotoxic)
2. WHEN two medicines share the same effect category THEN the Interaction Checker Agent SHALL flag a potential additive effect interaction
3. WHEN two medicines have opposing effect categories THEN the Interaction Checker Agent SHALL flag a potential antagonistic interaction
4. WHEN an AYUSH medicine's effect category is unknown THEN the system SHALL attempt to infer from its traditional use and known active compounds
5. WHEN effect category matching identifies a potential interaction THEN the system SHALL clearly label it as inferred from pharmacodynamic similarity

### Requirement 16

**User Story:** As a user who wants to share results with my doctor, I want to generate a summary report, so that I can have an informed discussion during my consultation.

#### Acceptance Criteria

1. WHEN a user requests a report THEN the system SHALL generate a structured summary of all medicines checked and interactions found
2. WHEN generating a report THEN the system SHALL include medicine names, interaction details, severity levels, and evidence sources
3. WHEN generating a report THEN the system SHALL format it as shareable text suitable for copying or forwarding
4. WHEN the report is generated THEN it SHALL include the date and time of the interaction check
5. WHEN the report is generated THEN it SHALL include a note recommending discussion with a healthcare provider
