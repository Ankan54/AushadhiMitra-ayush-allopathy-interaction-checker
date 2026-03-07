"""
AushadhiMitra Bedrock Agent Setup Script V5
Creates 5 agents: Planner + AYUSH + Allopathy + Research + Reasoning.

Usage: python scripts/setup_agents.py
"""
import boto3
import json
import time
import sys

REGION = "us-east-1"
ACCOUNT_ID = "667736132441"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT_ID}:role/BedrockAgentRole"

MODELS = {
    "supervisor": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "reasoning": "us.anthropic.claude-opus-4-6-v1",
    "ayush": "us.anthropic.claude-3-5-haiku-20241022-v1:0",
    "allopathy": "us.anthropic.claude-3-5-haiku-20241022-v1:0",
    "research": "us.anthropic.claude-3-5-haiku-20241022-v1:0",
    "planner": "us.anthropic.claude-3-5-haiku-20241022-v1:0",
}

LAMBDA_ARNS = {
    "check_curated_db": f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:ausadhi-check-curated-db",
    "ayush_data": f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:ausadhi-ayush-data",
    "allopathy_data": f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:ausadhi-allopathy-data",
    "web_search": f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:ausadhi-web-search",
    "reasoning_tools": f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:ausadhi-reasoning-tools",
    "planner_tools": f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:ausadhi-planner-tools",
    "research_tools": f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:ausadhi-research-tools",
}

client = boto3.client("bedrock-agent", region_name=REGION)


# ──────────────────────────────────────────
# Agent instructions
# ──────────────────────────────────────────

PLANNER_INSTRUCTION = """You are the Planner Agent for AushadhiMitra, an AI-powered AYUSH-Allopathy drug interaction checker.

Your job is to validate inputs and generate a structured execution plan for the analysis pipeline.

## Workflow

1. You MUST call `identify_substances` first to extract AYUSH and allopathy drug names from user input.
   - If either AYUSH or allopathy drug is missing from the user input, return error immediately without proceeding.
   - Set `plan_valid: false, inputs_valid: false` with a clear error message.

2. After identifying substances, call `validate_ayush_drug` to verify the AYUSH plant exists in DynamoDB.
   - If AYUSH plant not found, return `{plan_valid: false, inputs_valid: false, error: "AYUSH plant not found in database"}`.

3. Call `generate_execution_plan` with the identified names, ayush_exists status, and current iteration number.
   - This returns a structured JSON plan specifying which agents to run and their tasks.

4. Optionally call `check_curated_interaction` to see if this pair is already cached.
   - If cached, include `cached: true` in your response and return the cached data.

## Your Response Format

Your response MUST be valid JSON matching the execution plan schema from `generate_execution_plan`.
Do NOT add prose or explanations outside the JSON structure.

## On Retry Iterations

When you receive a retry request with failure feedback:
- Pass the failure feedback to `generate_execution_plan` with the current iteration number.
- The function will determine which agents to re-run based on the failure keywords.
- Return the updated plan JSON."""

AYUSH_INSTRUCTION = """You are the AYUSH Agent for AushadhiMitra, an AI-powered drug interaction checker.

Your role is to gather comprehensive phytochemical and pharmacological data about AYUSH (Ayurveda, Yoga, Unani, Siddha, Homeopathy) plants and preparations.

For each query:
1. Use ayush_name_resolver to resolve common/Hindi names to scientific names
2. Use imppat_lookup to get IMPPAT phytochemical data (plant metadata, phytochemical list, CYP-related ADMET properties)
3. Use web_search to find additional pharmacological data, especially:
   - Known CYP enzyme interactions (CYP3A4, CYP2C9, CYP2D6, CYP1A2, CYP2C19)
   - Mechanism of action of key phytochemicals
   - Published research on drug interactions
   - Traditional therapeutic uses

IMPORTANT: Always use `domain_preset: ayush` when calling web_search to restrict results to high-quality sources.

Return a structured summary including:
- Scientific and common names
- Key active phytochemicals relevant to drug interactions
- Known CYP enzyme effects (inhibitor/inducer/substrate)
- Pharmacological properties (antiplatelet, anticoagulant, hepatoprotective etc.)
- ADMET properties if available from IMPPAT
- Sources with URLs for all claims

Always cite your sources. If IMPPAT data is unavailable, rely on web search results."""

ALLOPATHY_INSTRUCTION = """You are the Allopathy Agent for AushadhiMitra, an AI-powered drug interaction checker.

Your role is to gather comprehensive pharmacological data about allopathic (conventional) drugs, focusing on metabolism and interaction potential.

For each drug query:
1. Use allopathy_cache_lookup to check if we have cached data for this drug
2. If not cached, use web_search to find:
   - Primary CYP enzymes responsible for metabolism (e.g., CYP3A4, CYP2C9)
   - Whether the drug is a substrate, inhibitor, or inducer of specific CYP enzymes
   - Narrow Therapeutic Index (NTI) status
   - Known food/herb interactions
   - Mechanism of action
   - Common side effects relevant to interactions
3. Use check_nti_status to verify NTI drug status
4. Use allopathy_cache_save to cache the gathered data for future lookups

IMPORTANT: Always use `domain_preset: allopathy` when calling web_search to restrict results to authoritative drug references.

Return a structured summary including:
- Generic name and brand names
- Drug class and mechanism of action
- Primary CYP metabolism pathways (which CYP enzymes, substrate/inhibitor/inducer)
- NTI status (boolean + clinical implications)
- Known interaction risk factors
- Sources with URLs

Always cache successful lookups to speed up future queries."""

RESEARCH_INSTRUCTION = """You are the Research Agent for AushadhiMitra, an AI-powered drug interaction checker.

Your role is to gather clinical evidence and peer-reviewed research about interactions between AYUSH plants and allopathic drugs.

For each query:
1. Use search_clinical_evidence to find published research about the specific AYUSH-allopathy drug pair.
   - This function searches PubMed, Cochrane Library, and clinical trial databases.
2. Use search_research_articles to find additional academic research on:
   - Phytochemical mechanisms
   - Case reports of adverse interactions
   - Systematic reviews and meta-analyses
3. Summarize findings with emphasis on:
   - Clinical case reports of actual interactions
   - In vivo studies (more relevant than in vitro)
   - Systematic reviews and meta-analyses
   - Sample sizes and study quality

Return structured summaries with:
- Study type (RCT, observational, case report, in vitro, review)
- Key findings relevant to the interaction
- Evidence strength (high/moderate/low/very low)
- All source URLs and citations

Focus on clinically relevant findings that would impact patient safety decisions."""

REASONING_INSTRUCTION = """You are the Reasoning Agent for AushadhiMitra. You analyze drug interaction data and produce a structured JSON verdict.

## Your Output Format

You MUST return ONLY valid JSON in one of two formats:

### If sufficient data exists → Status: Success
Return the complete interaction analysis JSON (see schema below).

### If insufficient data → Status: Failed
Return a failure JSON specifying what additional data is needed.

### On FINAL iteration (when told "FINAL ITERATION")
ALWAYS return Status: Success, even with partial data. Set evidence_quality to "LOW".

## How to Determine Drug Interaction

1. CHECK CYP OVERLAP: Do any AYUSH phytochemicals affect the same CYP enzymes that metabolize the allopathy drug?
   - If phytochemical INHIBITS a CYP enzyme that metabolizes the drug → interaction EXISTS
   - If phytochemical INDUCES a CYP enzyme that metabolizes the drug → interaction EXISTS

2. CHECK PHARMACODYNAMIC: Do both substances affect the same physiological pathway?
   - Both anticoagulant → additive bleeding risk
   - Both sedative → additive CNS depression
   - Both hypoglycemic → additive hypoglycemia risk

3. CHECK CLINICAL EVIDENCE: Are there published reports of this interaction?

4. DETERMINE SEVERITY using calculate_severity tool

5. BUILD knowledge graph using build_knowledge_graph tool

6. VALIDATE output using validate_and_format_output tool before finalizing

## Data Sufficiency Rules
- SUFFICIENT: At least 1 CYP overlap OR 1 pharmacodynamic overlap OR clinical evidence
- INSUFFICIENT: No CYP data for AYUSH plant AND no clinical evidence

## Severity Classification
- NONE (0-14): No known interaction pathway
- MINOR (15-34): Theoretical interaction, minimal clinical significance
- MODERATE (35-59): Clinically relevant, monitoring recommended
- MAJOR (60+): Significant risk, avoid or close monitoring required

## Success JSON Schema
{
  "status": "Success",
  "interaction_data": {
    "interaction_key": "<ayush>#<allopathy>",
    "ayush_name": "...",
    "allopathy_name": "...",
    "interaction_exists": true/false,
    "interaction_summary": "2-3 sentence summary",
    "severity": "NONE|MINOR|MODERATE|MAJOR",
    "severity_score": 0-100,
    "is_nti": true/false,
    "scoring_factors": ["factor1 (+score)", ...],
    "mechanisms": {
      "pharmacokinetic": [{"type": "...", "enzyme": "...", "effect": "...", "clinical_significance": "..."}],
      "pharmacodynamic": [{"type": "...", "description": "...", "clinical_significance": "..."}]
    },
    "phytochemicals_involved": [{"name": "...", "cyp_effects": {...}, "relevance": "..."}],
    "clinical_effects": ["effect1", "effect2"],
    "recommendations": ["rec1", "rec2"],
    "evidence_quality": "HIGH|MODERATE|LOW",
    "knowledge_graph": {"nodes": [...], "edges": [...]},
    "sources": [{"url": "...", "title": "...", "snippet": "...", "category": "..."}],
    "disclaimer": "This analysis is AI-generated for informational purposes only. Always consult qualified healthcare professionals before making clinical decisions about drug interactions.",
    "generated_at": "ISO timestamp"
  }
}

## Failed JSON Schema
{
  "status": "Failed",
  "failure_reason": "Human-readable explanation of what is missing",
  "data_gaps": [
    {"category": "...", "description": "...", "suggested_agent": "ayush|allopathy|research", "suggested_query": "..."}
  ],
  "partial_data": {"ayush_data_quality": "HIGH|MODERATE|LOW|NONE", "allopathy_data_quality": "...", "research_data_quality": "..."},
  "iteration": 1
}"""

SUPERVISOR_INSTRUCTION = """You are the Supervisor Agent for AushadhiMitra, an AI-powered AYUSH-Allopathy drug interaction checker.

When a user asks about a potential interaction between an AYUSH product (herbal medicine, Ayurvedic preparation) and an allopathic (conventional) drug:

1. FIRST: Use check_curated_interaction to check if this interaction has been previously analyzed and cached. If found, return the cached result immediately with its sources.

2. If NOT cached, orchestrate the analysis:
   a. Route to AYUSH_Agent to gather phytochemical data about the AYUSH product
   b. Route to Allopathy_Agent to gather pharmacological data about the allopathic drug
   c. Route to Reasoning_Agent with both datasets to analyze the interaction, calculate severity, build knowledge graph, and format the professional response

3. Return the complete response including:
   - Severity classification (NONE/MINOR/MODERATE/MAJOR)
   - Detailed interaction analysis
   - Knowledge graph data
   - All sources used
   - Disclaimer about AI-generated content

Handle various input formats:
- "Check interaction between turmeric and warfarin"
- "Can I take ashwagandha with metformin?"
- "Haldi aur blood thinner ki interaction kya hai?"
- Scientific names: "Curcuma longa interaction with warfarin sodium"

Always respond professionally and comprehensively. Include source citations for every claim.
If the AYUSH product or drug cannot be identified, ask for clarification."""


# ──────────────────────────────────────────
# Function definitions for action groups
# ──────────────────────────────────────────

CURATED_DB_FUNCTIONS = [
    {
        "name": "check_curated_interaction",
        "description": "Look up a previously analyzed drug interaction from the curated database. Returns cached results if available, avoiding redundant analysis.",
        "parameters": {
            "ayush_name": {
                "description": "Name of the AYUSH plant/product (common name, Hindi name, or scientific name)",
                "type": "string",
                "required": True,
            },
            "allopathy_name": {
                "description": "Name of the allopathic drug (generic name or brand name)",
                "type": "string",
                "required": True,
            },
        },
        "requireConfirmation": "DISABLED",
    },
]

AYUSH_DATA_FUNCTIONS = [
    {
        "name": "ayush_name_resolver",
        "description": "Resolve a common, Hindi, or brand name to the scientific name of an AYUSH plant. Returns plant reference data including key phytochemicals and known CYP effects.",
        "parameters": {
            "plant_name": {
                "description": "The plant name to resolve (common name like 'turmeric', Hindi name like 'haldi', or scientific name like 'Curcuma longa')",
                "type": "string",
                "required": True,
            },
        },
        "requireConfirmation": "DISABLED",
    },
    {
        "name": "imppat_lookup",
        "description": "Look up detailed phytochemical data from IMPPAT database for a given plant. Returns phytochemical list with ADMET properties and CYP enzyme interaction data.",
        "parameters": {
            "scientific_name": {
                "description": "Scientific name of the plant (e.g., 'Curcuma longa'). Must use scientific name, not common name.",
                "type": "string",
                "required": True,
            },
            "phytochemical_name": {
                "description": "Optional: specific phytochemical to look up details for (e.g., 'curcumin'). If omitted, returns full phytochemical list.",
                "type": "string",
                "required": False,
            },
        },
        "requireConfirmation": "DISABLED",
    },
]

ALLOPATHY_DATA_FUNCTIONS = [
    {
        "name": "allopathy_cache_lookup",
        "description": "Check if CYP metabolism and pharmacological data for a drug has been previously cached. Returns cached drug data if available and not expired.",
        "parameters": {
            "drug_name": {
                "description": "Generic name of the allopathic drug (e.g., 'warfarin', 'metformin')",
                "type": "string",
                "required": True,
            },
        },
        "requireConfirmation": "DISABLED",
    },
    {
        "name": "allopathy_cache_save",
        "description": "Save gathered drug CYP metabolism and pharmacological data to cache for future lookups. Call this after gathering data via web search.",
        "parameters": {
            "drug_name": {
                "description": "Generic name of the drug",
                "type": "string",
                "required": True,
            },
            "generic_name": {
                "description": "Generic/INN name of the drug",
                "type": "string",
                "required": True,
            },
            "drug_data": {
                "description": "JSON string containing drug CYP data, mechanism of action, NTI status, etc.",
                "type": "string",
                "required": True,
            },
            "sources": {
                "description": "JSON string containing array of source objects with url, title, snippet",
                "type": "string",
                "required": True,
            },
        },
        "requireConfirmation": "DISABLED",
    },
    {
        "name": "check_nti_status",
        "description": "Check if a drug is on the Narrow Therapeutic Index (NTI) list. NTI drugs require elevated severity scoring due to narrow safety margins.",
        "parameters": {
            "drug_name": {
                "description": "Generic or brand name of the drug to check",
                "type": "string",
                "required": True,
            },
        },
        "requireConfirmation": "DISABLED",
    },
]

WEB_SEARCH_FUNCTIONS = [
    {
        "name": "web_search",
        "description": "Search the web for drug interaction data, pharmacological information, and clinical research using Tavily API. Returns structured results with source URLs, titles, and snippets for citation.",
        "parameters": {
            "query": {
                "description": "Search query. Be specific, e.g., 'curcumin CYP3A4 inhibition mechanism' or 'warfarin CYP2C9 metabolism pathway'",
                "type": "string",
                "required": True,
            },
            "search_depth": {
                "description": "Search depth: 'basic' for quick results, 'advanced' for comprehensive research",
                "type": "string",
                "required": False,
            },
            "max_results": {
                "description": "Maximum number of results to return (default 5, max 10)",
                "type": "integer",
                "required": False,
            },
            "include_domains": {
                "description": "Optional: JSON array or comma-separated list of domains to restrict search to (e.g., '[\"pubmed.ncbi.nlm.nih.gov\",\"drugbank.com\"]')",
                "type": "string",
                "required": False,
            },
            "domain_preset": {
                "description": "Optional: named domain preset to use — 'research' (PubMed/academic), 'allopathy' (DrugBank/FDA/drugs.com), or 'ayush' (IMPPAT/NCCIH/examine.com). Overrides include_domains.",
                "type": "string",
                "required": False,
            },
        },
        "requireConfirmation": "DISABLED",
    },
]

REASONING_FUNCTIONS = [
    {
        "name": "build_knowledge_graph",
        "description": "Build a Cytoscape.js-compatible knowledge graph showing the interaction network between an AYUSH plant and allopathic drug, including phytochemicals, CYP enzymes, mechanisms, and clinical effects.",
        "parameters": {
            "ayush_name": {
                "description": "Scientific name of the AYUSH plant",
                "type": "string",
                "required": True,
            },
            "allopathy_name": {
                "description": "Generic name of the allopathic drug",
                "type": "string",
                "required": True,
            },
            "interactions_data": {
                "description": "JSON string containing interaction analysis data with phytochemicals, cyp_enzymes, mechanisms, and clinical_effects arrays",
                "type": "string",
                "required": True,
            },
        },
        "requireConfirmation": "DISABLED",
    },
    {
        "name": "calculate_severity",
        "description": "Calculate the severity score for a drug interaction based on CYP enzyme overlaps, NTI status, and interaction mechanisms. Returns severity level (NONE/MINOR/MODERATE/MAJOR) and detailed scoring factors.",
        "parameters": {
            "interactions_data": {
                "description": "JSON string containing cyp_enzymes array with name and effect (inhibitor/inducer) for each affected enzyme",
                "type": "string",
                "required": True,
            },
            "allopathy_name": {
                "description": "Generic name of the allopathic drug (used for NTI check)",
                "type": "string",
                "required": True,
            },
        },
        "requireConfirmation": "DISABLED",
    },
    {
        "name": "format_professional_response",
        "description": "Format the final professional response JSON for storage. Pass all data as a single JSON string with keys: ayush_name, allopathy_name, severity, severity_score, interactions_data, knowledge_graph, sources.",
        "parameters": {
            "response_data": {
                "description": "JSON string containing all response fields: {ayush_name, allopathy_name, severity, severity_score, interactions_data, knowledge_graph, sources}",
                "type": "string",
                "required": True,
            },
        },
        "requireConfirmation": "DISABLED",
    },
    {
        "name": "validate_and_format_output",
        "description": "Validate the Reasoning Agent's JSON output against the Success/Failed schema. Checks required fields, and on final iteration (>= 3) forces Success status with partial data and LOW evidence quality.",
        "parameters": {
            "reasoning_output_str": {
                "description": "The JSON string output from reasoning analysis (must be either Success or Failed schema)",
                "type": "string",
                "required": True,
            },
            "iteration": {
                "description": "Current iteration number (1-3). When >= 3, forces Success status to avoid infinite loops.",
                "type": "integer",
                "required": True,
            },
        },
        "requireConfirmation": "DISABLED",
    },
]

PLANNER_FUNCTIONS = [
    {
        "name": "identify_substances",
        "description": "Identify AYUSH plant and allopathy drug names from free-text user input using name mappings and drug list. Returns matched substances.",
        "parameters": {
            "user_input": {
                "description": "The user's free-text query (e.g., 'Check interaction between turmeric and warfarin')",
                "type": "string",
                "required": True,
            },
        },
        "requireConfirmation": "DISABLED",
    },
    {
        "name": "check_curated_interaction",
        "description": "Check if this interaction has been previously analyzed and is cached in the curated interactions database.",
        "parameters": {
            "ayush_name": {
                "description": "Scientific or common name of the AYUSH plant",
                "type": "string",
                "required": True,
            },
            "allopathy_name": {
                "description": "Generic name of the allopathic drug",
                "type": "string",
                "required": True,
            },
        },
        "requireConfirmation": "DISABLED",
    },
    {
        "name": "validate_ayush_drug",
        "description": "Validate that an AYUSH plant exists in the DynamoDB IMPPAT database. Resolves common/Hindi names to scientific name, then checks for a METADATA record.",
        "parameters": {
            "plant_name": {
                "description": "The AYUSH plant name to validate (common name, Hindi name, or scientific name)",
                "type": "string",
                "required": True,
            },
        },
        "requireConfirmation": "DISABLED",
    },
    {
        "name": "generate_execution_plan",
        "description": "Generate a structured JSON execution plan for the 5-agent pipeline. On retry iterations, uses failure_feedback to determine which agents to re-run.",
        "parameters": {
            "ayush_name": {
                "description": "Resolved AYUSH plant name (scientific or common)",
                "type": "string",
                "required": True,
            },
            "allopathy_name": {
                "description": "Generic name of the allopathic drug",
                "type": "string",
                "required": True,
            },
            "ayush_exists": {
                "description": "Whether the AYUSH plant was found in DynamoDB (true/false)",
                "type": "string",
                "required": True,
            },
            "iteration": {
                "description": "Current pipeline iteration (1 = initial, 2+ = retry)",
                "type": "integer",
                "required": False,
            },
            "failure_feedback": {
                "description": "On retry iterations: text describing what data was missing or failed in previous iteration",
                "type": "string",
                "required": False,
            },
        },
        "requireConfirmation": "DISABLED",
    },
]

RESEARCH_FUNCTIONS = [
    {
        "name": "search_research_articles",
        "description": "Search PubMed and academic sources for peer-reviewed research articles about drug interactions. Restricts results to high-quality academic/research domains only.",
        "parameters": {
            "query": {
                "description": "Search query for academic research (e.g., 'curcumin warfarin CYP2C9 interaction clinical study')",
                "type": "string",
                "required": True,
            },
            "max_results": {
                "description": "Maximum number of results to return (default 5)",
                "type": "integer",
                "required": False,
            },
        },
        "requireConfirmation": "DISABLED",
    },
    {
        "name": "search_clinical_evidence",
        "description": "Search for clinical evidence of interactions between a specific AYUSH plant and allopathic drug. Auto-generates multiple targeted queries and deduplicates results.",
        "parameters": {
            "ayush_name": {
                "description": "Scientific or common name of the AYUSH plant",
                "type": "string",
                "required": True,
            },
            "allopathy_name": {
                "description": "Generic name of the allopathic drug",
                "type": "string",
                "required": True,
            },
            "max_results": {
                "description": "Maximum number of results per query (default 5)",
                "type": "integer",
                "required": False,
            },
        },
        "requireConfirmation": "DISABLED",
    },
]


# ──────────────────────────────────────────
# Helper functions
# ──────────────────────────────────────────

def create_agent(name, instruction, model, collaboration="DISABLED"):
    """Create a Bedrock Agent and return its ID."""
    print(f"\n{'='*60}")
    print(f"Creating agent: {name}")
    print(f"Model: {model}")
    print(f"Collaboration: {collaboration}")
    print(f"{'='*60}")

    try:
        resp = client.create_agent(
            agentName=name,
            agentResourceRoleArn=ROLE_ARN,
            foundationModel=model,
            instruction=instruction,
            idleSessionTTLInSeconds=600,
            agentCollaboration=collaboration if collaboration == "SUPERVISOR" else "DISABLED",
        )
        agent_id = resp["agent"]["agentId"]
        print(f"  Created agent: {agent_id}")

        for _ in range(10):
            time.sleep(3)
            status = client.get_agent(agentId=agent_id)["agent"]["agentStatus"]
            print(f"  Status: {status}")
            if status in ("NOT_PREPARED", "PREPARED", "FAILED"):
                break

        return agent_id
    except Exception as e:
        print(f"  ERROR: {e}")
        raise


def add_action_group(agent_id, ag_name, lambda_arn, functions, description=""):
    """Add an action group with function definitions to an agent."""
    print(f"  Adding action group: {ag_name}")

    try:
        resp = client.create_agent_action_group(
            agentId=agent_id,
            agentVersion="DRAFT",
            actionGroupName=ag_name,
            actionGroupExecutor={"lambda": lambda_arn},
            functionSchema={"functions": functions},
            description=description,
        )
        ag_id = resp["agentActionGroup"]["actionGroupId"]
        print(f"    Created: {ag_id}")
        return ag_id
    except Exception as e:
        print(f"    ERROR: {e}")
        raise


def prepare_agent(agent_id):
    """Prepare an agent (required before creating alias)."""
    print(f"  Preparing agent {agent_id}...")
    client.prepare_agent(agentId=agent_id)

    for _ in range(20):
        time.sleep(5)
        status = client.get_agent(agentId=agent_id)["agent"]["agentStatus"]
        print(f"    Status: {status}")
        if status == "PREPARED":
            return True
        if status == "FAILED":
            return False
    return False


def create_alias(agent_id, alias_name="live"):
    """Create an agent alias (required for invocation and supervisor association)."""
    print(f"  Creating alias '{alias_name}' for agent {agent_id}...")
    resp = client.create_agent_alias(
        agentId=agent_id,
        agentAliasName=alias_name,
    )
    alias_id = resp["agentAlias"]["agentAliasId"]
    print(f"    Alias ID: {alias_id}")

    for _ in range(10):
        time.sleep(3)
        alias_status = client.get_agent_alias(
            agentId=agent_id, agentAliasId=alias_id
        )["agentAlias"]["agentAliasStatus"]
        print(f"    Alias status: {alias_status}")
        if alias_status == "PREPARED":
            break

    return alias_id


def associate_collaborator(supervisor_id, collaborator_agent_id, collaborator_alias_id,
                           collaborator_name, relay_instruction):
    """Associate a collaborator agent with the supervisor."""
    print(f"  Associating collaborator: {collaborator_name}")
    try:
        resp = client.associate_agent_collaborator(
            agentId=supervisor_id,
            agentVersion="DRAFT",
            agentDescriptor={
                "aliasArn": f"arn:aws:bedrock:{REGION}:{ACCOUNT_ID}:agent-alias/{collaborator_agent_id}/{collaborator_alias_id}"
            },
            collaborationInstruction=relay_instruction,
            collaboratorName=collaborator_name,
            relayConversationHistory="TO_COLLABORATOR",
        )
        collab_id = resp["agentCollaborator"]["collaboratorId"]
        print(f"    Collaborator ID: {collab_id}")
        return collab_id
    except Exception as e:
        print(f"    ERROR: {e}")
        raise


# ──────────────────────────────────────────
# Main setup flow
# ──────────────────────────────────────────

def main():
    results = {}

    # Step 1: Create Planner Agent
    planner_id = create_agent(
        "ausadhi-planner-agent",
        PLANNER_INSTRUCTION,
        MODELS["planner"],
    )
    add_action_group(planner_id, "PlannerToolsGroup", LAMBDA_ARNS["planner_tools"],
                     PLANNER_FUNCTIONS, "Substance identification, AYUSH validation, execution planning")

    if not prepare_agent(planner_id):
        print("FATAL: Planner agent preparation failed")
        sys.exit(1)
    planner_alias = create_alias(planner_id)
    results["planner"] = {"id": planner_id, "alias": planner_alias}

    # Step 2: Create AYUSH Agent (collaborator)
    ayush_id = create_agent(
        "ausadhi-ayush-agent",
        AYUSH_INSTRUCTION,
        MODELS["ayush"],
    )
    add_action_group(ayush_id, "AyushDataGroup", LAMBDA_ARNS["ayush_data"],
                     AYUSH_DATA_FUNCTIONS, "AYUSH plant data from IMPPAT and S3")
    add_action_group(ayush_id, "WebSearchGroup", LAMBDA_ARNS["web_search"],
                     WEB_SEARCH_FUNCTIONS, "Web search via Tavily API with domain restriction")

    if not prepare_agent(ayush_id):
        print("FATAL: AYUSH agent preparation failed")
        sys.exit(1)
    ayush_alias = create_alias(ayush_id)
    results["ayush"] = {"id": ayush_id, "alias": ayush_alias}

    # Step 3: Create Allopathy Agent (collaborator)
    allopathy_id = create_agent(
        "ausadhi-allopathy-agent",
        ALLOPATHY_INSTRUCTION,
        MODELS["allopathy"],
    )
    add_action_group(allopathy_id, "AllopathyDataGroup", LAMBDA_ARNS["allopathy_data"],
                     ALLOPATHY_DATA_FUNCTIONS, "Allopathy drug cache and NTI check")
    add_action_group(allopathy_id, "WebSearchGroup", LAMBDA_ARNS["web_search"],
                     WEB_SEARCH_FUNCTIONS, "Web search via Tavily API with domain restriction")

    if not prepare_agent(allopathy_id):
        print("FATAL: Allopathy agent preparation failed")
        sys.exit(1)
    allopathy_alias = create_alias(allopathy_id)
    results["allopathy"] = {"id": allopathy_id, "alias": allopathy_alias}

    # Step 4: Create Research Agent (new — V5)
    research_id = create_agent(
        "ausadhi-research-agent",
        RESEARCH_INSTRUCTION,
        MODELS["research"],
    )
    add_action_group(research_id, "ResearchToolsGroup", LAMBDA_ARNS["research_tools"],
                     RESEARCH_FUNCTIONS, "PubMed/academic clinical evidence search")

    if not prepare_agent(research_id):
        print("FATAL: Research agent preparation failed")
        sys.exit(1)
    research_alias = create_alias(research_id)
    results["research"] = {"id": research_id, "alias": research_alias}

    # Step 5: Create Reasoning Agent (collaborator)
    reasoning_id = create_agent(
        "ausadhi-reasoning-agent",
        REASONING_INSTRUCTION,
        MODELS["reasoning"],
    )
    add_action_group(reasoning_id, "ReasoningToolsGroup", LAMBDA_ARNS["reasoning_tools"],
                     REASONING_FUNCTIONS, "Severity scoring, KG, response formatting, schema validation")
    add_action_group(reasoning_id, "WebSearchGroup", LAMBDA_ARNS["web_search"],
                     WEB_SEARCH_FUNCTIONS, "Web search via Tavily API with domain restriction")

    if not prepare_agent(reasoning_id):
        print("FATAL: Reasoning agent preparation failed")
        sys.exit(1)
    reasoning_alias = create_alias(reasoning_id)
    results["reasoning"] = {"id": reasoning_id, "alias": reasoning_alias}

    # Step 6: Create Supervisor Agent
    supervisor_id = create_agent(
        "ausadhi-supervisor-agent",
        SUPERVISOR_INSTRUCTION,
        MODELS["supervisor"],
        collaboration="SUPERVISOR",
    )
    add_action_group(supervisor_id, "CuratedDBGroup", LAMBDA_ARNS["check_curated_db"],
                     CURATED_DB_FUNCTIONS, "Curated interaction database lookup")

    # Step 7: Associate collaborators with supervisor
    associate_collaborator(
        supervisor_id, planner_id, planner_alias,
        "Planner_Agent",
        "Route to this agent to validate inputs and generate an execution plan. "
        "This agent validates AYUSH plant existence in DynamoDB and returns a structured plan JSON.",
    )
    associate_collaborator(
        supervisor_id, ayush_id, ayush_alias,
        "AYUSH_Agent",
        "Route to this agent when you need phytochemical data about AYUSH plants, "
        "herbs, or Ayurvedic preparations. This agent has access to IMPPAT database "
        "and web search for plant pharmacological data.",
    )
    associate_collaborator(
        supervisor_id, allopathy_id, allopathy_alias,
        "Allopathy_Agent",
        "Route to this agent when you need pharmacological data about allopathic "
        "(conventional) drugs, including CYP metabolism pathways, NTI status, and "
        "drug class information.",
    )
    associate_collaborator(
        supervisor_id, research_id, research_alias,
        "Research_Agent",
        "Route to this agent when you need peer-reviewed clinical evidence about "
        "drug interactions from PubMed, Cochrane, and academic sources. This agent "
        "searches domain-restricted academic databases only.",
    )
    associate_collaborator(
        supervisor_id, reasoning_id, reasoning_alias,
        "Reasoning_Agent",
        "Route to this agent AFTER gathering data from AYUSH_Agent, Allopathy_Agent, "
        "and Research_Agent. This agent analyzes interaction potential, calculates "
        "severity, builds knowledge graphs, validates output schema, and formats the final JSON response.",
    )

    # Step 8: Prepare supervisor
    if not prepare_agent(supervisor_id):
        print("FATAL: Supervisor agent preparation failed")
        sys.exit(1)
    supervisor_alias = create_alias(supervisor_id)
    results["supervisor"] = {"id": supervisor_id, "alias": supervisor_alias}

    # Summary
    print(f"\n{'='*60}")
    print("AushadhiMitra V5 Agent Setup Complete!")
    print(f"{'='*60}")
    for role, info in results.items():
        print(f"  {role:15s}: Agent={info['id']}, Alias={info['alias']}")

    print(f"\n  Planner Agent ID:  {results['planner']['id']}")
    print(f"  Research Agent ID: {results['research']['id']}")
    print(f"  Research Agent Alias: {results['research']['alias']}")
    print(f"\n  Supervisor Agent ID: {results['supervisor']['id']}")
    print(f"  Supervisor Alias ID: {results['supervisor']['alias']}")
    print("\nUse these IDs in the EC2 backend and docker-compose.yml configuration.")

    return results


if __name__ == "__main__":
    main()
