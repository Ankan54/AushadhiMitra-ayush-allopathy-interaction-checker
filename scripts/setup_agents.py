"""
AushadhiMitra Bedrock Agent Setup Script
Creates 4 agents: 3 collaborators + 1 supervisor with multi-agent collaboration.

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
}

LAMBDA_ARNS = {
    "check_curated_db": f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:ausadhi-check-curated-db",
    "ayush_data": f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:ausadhi-ayush-data",
    "allopathy_data": f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:ausadhi-allopathy-data",
    "web_search": f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:ausadhi-web-search",
    "reasoning_tools": f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:ausadhi-reasoning-tools",
}

client = boto3.client("bedrock-agent", region_name=REGION)


# ──────────────────────────────────────────
# Agent instructions
# ──────────────────────────────────────────

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

Return a structured summary including:
- Generic name and brand names
- Drug class and mechanism of action
- Primary CYP metabolism pathways (which CYP enzymes, substrate/inhibitor/inducer)
- NTI status (boolean + clinical implications)
- Known interaction risk factors
- Sources with URLs

Always cache successful lookups to speed up future queries."""

REASONING_INSTRUCTION = """You are the Reasoning Agent for AushadhiMitra, an AI-powered drug interaction checker.

You receive data from the AYUSH Agent (phytochemical/plant data) and Allopathy Agent (drug metabolism data), and your role is to:

1. ANALYZE the interaction potential between the AYUSH plant and allopathic drug:
   - Identify overlapping CYP enzyme pathways
   - Determine if phytochemicals inhibit/induce enzymes that metabolize the drug
   - Assess pharmacodynamic interactions (e.g., both are anticoagulants)
   - Consider clinical significance

2. Use calculate_severity to compute a severity score based on:
   - CYP enzyme interactions found
   - NTI drug status
   - Number of overlapping pathways

3. Use build_knowledge_graph to create a visual representation of the interaction network

4. Use web_search for any additional evidence needed about specific interaction mechanisms

5. Use format_professional_response to create the final structured response

Your analysis must be:
- Evidence-based: cite specific CYP enzymes, phytochemicals, and mechanisms
- Clinically relevant: focus on what matters for patient safety
- Severity-appropriate: MAJOR interactions require clear warnings
- Source-transparent: include all web sources used

Severity classification:
- NONE: No known interaction pathway
- MINOR: Theoretical interaction, minimal clinical significance
- MODERATE: Clinically relevant, monitoring recommended
- MAJOR: Significant risk, avoid combination or close monitoring required"""

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

        # Wait for agent to be ready
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

    # Step 1: Create AYUSH Agent (collaborator)
    ayush_id = create_agent(
        "ausadhi-ayush-agent",
        AYUSH_INSTRUCTION,
        MODELS["ayush"],
    )
    add_action_group(ayush_id, "AyushDataGroup", LAMBDA_ARNS["ayush_data"],
                     AYUSH_DATA_FUNCTIONS, "AYUSH plant data from IMPPAT and S3")
    add_action_group(ayush_id, "WebSearchGroup", LAMBDA_ARNS["web_search"],
                     WEB_SEARCH_FUNCTIONS, "Web search via Tavily API")

    if not prepare_agent(ayush_id):
        print("FATAL: AYUSH agent preparation failed")
        sys.exit(1)
    ayush_alias = create_alias(ayush_id)
    results["ayush"] = {"id": ayush_id, "alias": ayush_alias}

    # Step 2: Create Allopathy Agent (collaborator)
    allopathy_id = create_agent(
        "ausadhi-allopathy-agent",
        ALLOPATHY_INSTRUCTION,
        MODELS["allopathy"],
    )
    add_action_group(allopathy_id, "AllopathyDataGroup", LAMBDA_ARNS["allopathy_data"],
                     ALLOPATHY_DATA_FUNCTIONS, "Allopathy drug cache and NTI check")
    add_action_group(allopathy_id, "WebSearchGroup", LAMBDA_ARNS["web_search"],
                     WEB_SEARCH_FUNCTIONS, "Web search via Tavily API")

    if not prepare_agent(allopathy_id):
        print("FATAL: Allopathy agent preparation failed")
        sys.exit(1)
    allopathy_alias = create_alias(allopathy_id)
    results["allopathy"] = {"id": allopathy_id, "alias": allopathy_alias}

    # Step 3: Create Reasoning Agent (collaborator)
    reasoning_id = create_agent(
        "ausadhi-reasoning-agent",
        REASONING_INSTRUCTION,
        MODELS["reasoning"],
    )
    add_action_group(reasoning_id, "ReasoningToolsGroup", LAMBDA_ARNS["reasoning_tools"],
                     REASONING_FUNCTIONS, "Severity scoring, KG, response formatting")
    add_action_group(reasoning_id, "WebSearchGroup", LAMBDA_ARNS["web_search"],
                     WEB_SEARCH_FUNCTIONS, "Web search via Tavily API")

    if not prepare_agent(reasoning_id):
        print("FATAL: Reasoning agent preparation failed")
        sys.exit(1)
    reasoning_alias = create_alias(reasoning_id)
    results["reasoning"] = {"id": reasoning_id, "alias": reasoning_alias}

    # Step 4: Create Supervisor Agent
    supervisor_id = create_agent(
        "ausadhi-supervisor-agent",
        SUPERVISOR_INSTRUCTION,
        MODELS["supervisor"],
        collaboration="SUPERVISOR",
    )
    add_action_group(supervisor_id, "CuratedDBGroup", LAMBDA_ARNS["check_curated_db"],
                     CURATED_DB_FUNCTIONS, "Curated interaction database lookup")

    # Step 5: Associate collaborators with supervisor
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
        supervisor_id, reasoning_id, reasoning_alias,
        "Reasoning_Agent",
        "Route to this agent AFTER gathering data from both AYUSH_Agent and "
        "Allopathy_Agent. This agent analyzes interaction potential, calculates "
        "severity, builds knowledge graphs, and formats the final professional response.",
    )

    # Step 6: Prepare supervisor
    if not prepare_agent(supervisor_id):
        print("FATAL: Supervisor agent preparation failed")
        sys.exit(1)
    supervisor_alias = create_alias(supervisor_id)
    results["supervisor"] = {"id": supervisor_id, "alias": supervisor_alias}

    # Summary
    print(f"\n{'='*60}")
    print("AushadhiMitra Agent Setup Complete!")
    print(f"{'='*60}")
    for role, info in results.items():
        print(f"  {role:15s}: Agent={info['id']}, Alias={info['alias']}")

    print(f"\n  Supervisor Agent ID: {results['supervisor']['id']}")
    print(f"  Supervisor Alias ID: {results['supervisor']['alias']}")
    print("\nUse these IDs in the EC2 backend and Telegram Lambda configuration.")

    return results


if __name__ == "__main__":
    main()
