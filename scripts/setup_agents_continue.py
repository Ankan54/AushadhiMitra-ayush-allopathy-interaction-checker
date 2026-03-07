"""Continue agent setup from Reasoning Agent onwards.
AYUSH (0SU1BHJ78L/6NXIKPLBVB) and Allopathy (CNAZG8LA0H/BBAJ5HFGKG) already created.
"""
import boto3
import json
import os
import time
import sys

REGION = os.environ.get("AWS_REGION", "us-east-1")
ACCOUNT_ID = os.environ.get("AWS_ACCOUNT_ID", "")
ROLE_ARN = os.environ.get("BEDROCK_AGENT_ROLE_ARN", f"arn:aws:iam::{ACCOUNT_ID}:role/BedrockAgentRole")

client = boto3.client("bedrock-agent", region_name=REGION)

EXISTING = {
    "ayush": {
        "id": os.environ.get("AYUSH_AGENT_ID", "0SU1BHJ78L"),
        "alias": os.environ.get("AYUSH_AGENT_LIVE_ALIAS", "6NXIKPLBVB"),
    },
    "allopathy": {
        "id": os.environ.get("ALLOPATHY_AGENT_ID", "CNAZG8LA0H"),
        "alias": os.environ.get("ALLOPATHY_AGENT_LIVE_ALIAS", "BBAJ5HFGKG"),
    },
}

LAMBDA_ARNS = {
    "check_curated_db": f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:ausadhi-check-curated-db",
    "web_search": f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:ausadhi-web-search",
    "reasoning_tools": f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:ausadhi-reasoning-tools",
}

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

REASONING_FUNCTIONS = [
    {
        "name": "build_knowledge_graph",
        "description": "Build a Cytoscape.js-compatible knowledge graph showing the interaction network between an AYUSH plant and allopathic drug.",
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
                "description": "JSON string with phytochemicals, cyp_enzymes, mechanisms, clinical_effects arrays",
                "type": "string",
                "required": True,
            },
        },
        "requireConfirmation": "DISABLED",
    },
    {
        "name": "calculate_severity",
        "description": "Calculate severity score for a drug interaction based on CYP enzyme overlaps and NTI status. Returns NONE/MINOR/MODERATE/MAJOR.",
        "parameters": {
            "interactions_data": {
                "description": "JSON string with cyp_enzymes array [{name, effect}]",
                "type": "string",
                "required": True,
            },
            "allopathy_name": {
                "description": "Generic name of the allopathic drug for NTI check",
                "type": "string",
                "required": True,
            },
        },
        "requireConfirmation": "DISABLED",
    },
    {
        "name": "format_professional_response",
        "description": "Format the final response JSON. Pass all data as a single JSON: {ayush_name, allopathy_name, severity, severity_score, interactions_data, knowledge_graph, sources}",
        "parameters": {
            "response_data": {
                "description": "JSON string with all response fields",
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
        "description": "Search the web for drug interaction data using Tavily API. Returns source URLs, titles, snippets for citation.",
        "parameters": {
            "query": {
                "description": "Specific search query about drug interactions or pharmacology",
                "type": "string",
                "required": True,
            },
            "search_depth": {
                "description": "Search depth: 'basic' or 'advanced'",
                "type": "string",
                "required": False,
            },
            "max_results": {
                "description": "Max results (default 5, max 10)",
                "type": "integer",
                "required": False,
            },
        },
        "requireConfirmation": "DISABLED",
    },
]

CURATED_DB_FUNCTIONS = [
    {
        "name": "check_curated_interaction",
        "description": "Look up a previously analyzed drug interaction from the curated database. Returns cached results if available.",
        "parameters": {
            "ayush_name": {
                "description": "Name of the AYUSH plant/product",
                "type": "string",
                "required": True,
            },
            "allopathy_name": {
                "description": "Name of the allopathic drug",
                "type": "string",
                "required": True,
            },
        },
        "requireConfirmation": "DISABLED",
    },
]


def prepare_agent(agent_id):
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
    print(f"  Creating alias '{alias_name}' for agent {agent_id}...")
    resp = client.create_agent_alias(agentId=agent_id, agentAliasName=alias_name)
    alias_id = resp["agentAlias"]["agentAliasId"]
    print(f"    Alias ID: {alias_id}")
    for _ in range(10):
        time.sleep(3)
        s = client.get_agent_alias(agentId=agent_id, agentAliasId=alias_id)["agentAlias"]["agentAliasStatus"]
        print(f"    Alias status: {s}")
        if s == "PREPARED":
            break
    return alias_id


# Step 1: Create Reasoning Agent
print("\n" + "=" * 60)
print("Creating Reasoning Agent")
print("=" * 60)

resp = client.create_agent(
    agentName="ausadhi-reasoning-agent",
    agentResourceRoleArn=ROLE_ARN,
    foundationModel="us.anthropic.claude-opus-4-6-v1",
    instruction=REASONING_INSTRUCTION,
    idleSessionTTLInSeconds=600,
)
reasoning_id = resp["agent"]["agentId"]
print(f"  Created: {reasoning_id}")
time.sleep(3)

print("  Adding ReasoningToolsGroup...")
client.create_agent_action_group(
    agentId=reasoning_id, agentVersion="DRAFT",
    actionGroupName="ReasoningToolsGroup",
    actionGroupExecutor={"lambda": LAMBDA_ARNS["reasoning_tools"]},
    functionSchema={"functions": REASONING_FUNCTIONS},
    description="Severity scoring, knowledge graph, response formatting",
)
print("    Done")

print("  Adding WebSearchGroup...")
client.create_agent_action_group(
    agentId=reasoning_id, agentVersion="DRAFT",
    actionGroupName="WebSearchGroup",
    actionGroupExecutor={"lambda": LAMBDA_ARNS["web_search"]},
    functionSchema={"functions": WEB_SEARCH_FUNCTIONS},
    description="Web search via Tavily",
)
print("    Done")

if not prepare_agent(reasoning_id):
    print("FATAL: Reasoning agent failed")
    sys.exit(1)
reasoning_alias = create_alias(reasoning_id)

# Step 2: Create Supervisor Agent
print("\n" + "=" * 60)
print("Creating Supervisor Agent")
print("=" * 60)

resp = client.create_agent(
    agentName="ausadhi-supervisor-agent",
    agentResourceRoleArn=ROLE_ARN,
    foundationModel="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    instruction=SUPERVISOR_INSTRUCTION,
    idleSessionTTLInSeconds=600,
    agentCollaboration="SUPERVISOR",
)
supervisor_id = resp["agent"]["agentId"]
print(f"  Created: {supervisor_id}")
time.sleep(3)

print("  Adding CuratedDBGroup...")
client.create_agent_action_group(
    agentId=supervisor_id, agentVersion="DRAFT",
    actionGroupName="CuratedDBGroup",
    actionGroupExecutor={"lambda": LAMBDA_ARNS["check_curated_db"]},
    functionSchema={"functions": CURATED_DB_FUNCTIONS},
    description="Curated interaction database lookup",
)
print("    Done")

# Step 3: Associate collaborators
print("\n  Associating AYUSH_Agent...")
client.associate_agent_collaborator(
    agentId=supervisor_id, agentVersion="DRAFT",
    agentDescriptor={
        "aliasArn": f"arn:aws:bedrock:{REGION}:{ACCOUNT_ID}:agent-alias/{EXISTING['ayush']['id']}/{EXISTING['ayush']['alias']}"
    },
    collaborationInstruction="Route here for AYUSH plant phytochemical data from IMPPAT and web search.",
    collaboratorName="AYUSH_Agent",
    relayConversationHistory="TO_COLLABORATOR",
)
print("    Done")

print("  Associating Allopathy_Agent...")
client.associate_agent_collaborator(
    agentId=supervisor_id, agentVersion="DRAFT",
    agentDescriptor={
        "aliasArn": f"arn:aws:bedrock:{REGION}:{ACCOUNT_ID}:agent-alias/{EXISTING['allopathy']['id']}/{EXISTING['allopathy']['alias']}"
    },
    collaborationInstruction="Route here for allopathic drug CYP metabolism, NTI status, and pharmacological data.",
    collaboratorName="Allopathy_Agent",
    relayConversationHistory="TO_COLLABORATOR",
)
print("    Done")

print("  Associating Reasoning_Agent...")
client.associate_agent_collaborator(
    agentId=supervisor_id, agentVersion="DRAFT",
    agentDescriptor={
        "aliasArn": f"arn:aws:bedrock:{REGION}:{ACCOUNT_ID}:agent-alias/{reasoning_id}/{reasoning_alias}"
    },
    collaborationInstruction="Route here AFTER both AYUSH and Allopathy agents have returned data. Analyzes interactions, calculates severity, builds knowledge graph, formats final response.",
    collaboratorName="Reasoning_Agent",
    relayConversationHistory="TO_COLLABORATOR",
)
print("    Done")

# Step 4: Prepare supervisor and create alias
if not prepare_agent(supervisor_id):
    print("FATAL: Supervisor agent failed")
    sys.exit(1)
supervisor_alias = create_alias(supervisor_id)

# Summary
print(f"\n{'='*60}")
print("AushadhiMitra Agent Setup Complete!")
print(f"{'='*60}")
print(f"  AYUSH Agent:     {EXISTING['ayush']['id']} / {EXISTING['ayush']['alias']}")
print(f"  Allopathy Agent: {EXISTING['allopathy']['id']} / {EXISTING['allopathy']['alias']}")
print(f"  Reasoning Agent: {reasoning_id} / {reasoning_alias}")
print(f"  Supervisor Agent: {supervisor_id} / {supervisor_alias}")
print(f"\n  ** Supervisor Agent ID: {supervisor_id}")
print(f"  ** Supervisor Alias ID: {supervisor_alias}")
print(f"\n  Use these in EC2 backend and Telegram Lambda config.")
