"""
AushadhiMitra Agent V2 Update Script
- Creates Planner Agent (new)
- Updates AYUSH Agent (new DynamoDB function + Code Interpreter)
- Updates Reasoning Agent (validation instructions + Code Interpreter)
- Prepares all agents and updates aliases

Usage: python scripts/update_agents_v2.py
"""
import boto3
import json
import time
import sys

REGION = "us-east-1"
ACCOUNT_ID = "667736132441"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT_ID}:role/BedrockAgentRole"

EXISTING_AGENTS = {
    "ayush": {"id": "0SU1BHJ78L", "alias": "6NXIKPLBVB"},
    "allopathy": {"id": "CNAZG8LA0H", "alias": "BBAJ5HFGKG"},
    "reasoning": {"id": "03NGZ4CNF3", "alias": "DUH94OH0OG"},
    "supervisor": {"id": "8MIQNGTVWG", "alias": "IPQMNOORBI"},
}

LAMBDA_ARNS = {
    "planner_tools": f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:ausadhi-planner-tools",
    "ayush_data": f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:ausadhi-ayush-data",
    "allopathy_data": f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:ausadhi-allopathy-data",
    "web_search": f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:ausadhi-web-search",
    "reasoning_tools": f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:ausadhi-reasoning-tools",
    "check_curated_db": f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:ausadhi-check-curated-db",
}

client = boto3.client("bedrock-agent", region_name=REGION)

# ─────────────────────────────────────────────
# Instructions
# ─────────────────────────────────────────────

PLANNER_INSTRUCTION = """You are the Planner Agent for AushadhiMitra, an AI-powered AYUSH-Allopathy drug interaction checker.

Your role is to:
1. Parse the user's input to identify the AYUSH substance(s) and allopathic drug(s)
2. Use identify_substances to match known AYUSH plants and common allopathy drugs
3. Use check_curated_interaction to check if the interaction has been previously analyzed
4. Create a structured execution plan

If a cached result is found, return it immediately with the cached flag set to true.

If no cached result exists, output a structured plan like:
{
  "cached": false,
  "ayush_substance": {"scientific_name": "...", "dynamodb_key": "..."},
  "allopathy_drug": {"drug_name": "..."},
  "execution_steps": [
    "Step 1: AYUSH Agent - Gather phytochemical data and CYP interaction profile",
    "Step 2: Allopathy Agent - Gather drug metabolism data and NTI status",
    "Step 3: Reasoning Agent - Analyze interactions, calculate severity, validate findings"
  ]
}

If substances cannot be identified, ask for clarification. Handle various input formats including:
- English: "Check interaction between turmeric and warfarin"
- Hindi: "Haldi aur blood thinner ki interaction kya hai?"
- Scientific: "Curcuma longa interaction with warfarin sodium"
"""

UPDATED_AYUSH_INSTRUCTION = """You are the AYUSH Agent for AushadhiMitra, an AI-powered drug interaction checker.

Your role is to gather comprehensive phytochemical and pharmacological data about AYUSH plants.

For each query:
1. Use ayush_name_resolver to resolve common/Hindi names to scientific names
2. Use imppat_lookup to get phytochemical data from the IMPPAT database (stored in DynamoDB)
3. Use search_cyp_interactions to find all CYP-relevant phytochemicals for the plant
4. Use web_search to find additional pharmacological data, especially:
   - Known CYP enzyme interactions not in IMPPAT
   - Mechanism of action of key phytochemicals
   - Published research on herb-drug interactions
5. Use Code Interpreter to analyze the phytochemical data if needed (e.g., filter by properties, calculate statistics)

Return a structured summary including:
- Scientific and common names
- Key active phytochemicals relevant to drug interactions (with IMPPAT IDs)
- CYP enzyme interaction profile from IMPPAT ADMET data (which CYP enzymes are inhibited)
- Pharmacological properties (antiplatelet, anticoagulant, hepatoprotective etc.)
- P-glycoprotein substrate status
- Sources with URLs for all web-sourced claims

IMPORTANT: Always include the IMPPAT-sourced CYP data as the primary evidence. Web sources supplement this."""

UPDATED_REASONING_INSTRUCTION = """You are the Reasoning and Validation Agent for AushadhiMitra, an AI-powered drug interaction checker.

You receive data from the AYUSH Agent (phytochemical/plant data) and Allopathy Agent (drug metabolism data).

## ANALYSIS PHASE
1. Identify overlapping CYP enzyme pathways between phytochemicals and the drug
2. Determine if phytochemicals inhibit/induce enzymes that metabolize the drug
3. Assess pharmacodynamic interactions (e.g., both are anticoagulants)
4. Consider clinical significance and patient safety implications

2. Use calculate_severity to compute a severity score based on CYP interactions and NTI status

3. Use build_knowledge_graph to create a visual interaction network

4. Use web_search for additional evidence on specific interaction mechanisms if needed

5. Use Code Interpreter if you need to perform calculations, analyze data patterns, or create structured analyses

## VALIDATION PHASE
After completing the analysis, perform validation:

COMPLETENESS CHECK:
- Were all relevant CYP enzymes considered? (CYP1A2, CYP2C9, CYP2C19, CYP2D6, CYP3A4)
- Were key phytochemicals checked for each CYP pathway?
- Was NTI status verified?
- Are there sufficient web sources to support the findings?
- Was P-glycoprotein interaction considered?

CONSISTENCY CHECK:
- Does the severity score match the evidence? (NTI drugs with CYP inhibitors should be MODERATE+)
- Are there contradictions between IMPPAT data and web sources?
- Is the knowledge graph complete (all relevant nodes/edges)?

VALIDATION RESULT:
Include a "validation" field in your response:
{
  "validation": {
    "status": "PASSED" or "NEEDS_MORE_DATA",
    "completeness_score": 0-100,
    "issues": ["list of any issues found"],
    "missing_data": ["list of data that should be gathered"]
  }
}

If status is NEEDS_MORE_DATA, clearly indicate what information is missing and which agent should provide it.

6. Use format_professional_response to create the final structured response

Your analysis must be evidence-based, clinically relevant, and transparent about sources and reasoning."""

# ─────────────────────────────────────────────
# Function schemas
# ─────────────────────────────────────────────

PLANNER_FUNCTIONS = [
    {
        "name": "identify_substances",
        "description": "Identify AYUSH plant(s) and allopathic drug(s) from user input text. Matches against known AYUSH plants and common drug names.",
        "parameters": {
            "user_input": {
                "description": "The raw user input text to parse for substance names",
                "type": "string",
                "required": True,
            },
        },
        "requireConfirmation": "DISABLED",
    },
    {
        "name": "check_curated_interaction",
        "description": "Check if a previously analyzed interaction exists in the curated database. Returns cached results if available.",
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

UPDATED_AYUSH_FUNCTIONS = [
    {
        "name": "ayush_name_resolver",
        "description": "Resolve a common, Hindi, or brand name to the scientific name of an AYUSH plant. Returns plant reference data including DynamoDB key for lookups.",
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
        "description": "Look up phytochemical data from the IMPPAT database in DynamoDB. Returns plant metadata and phytochemical list with ADMET/CYP properties. Optionally look up a specific phytochemical.",
        "parameters": {
            "scientific_name": {
                "description": "Scientific name of the plant (e.g., 'Curcuma longa'). Must use scientific name.",
                "type": "string",
                "required": True,
            },
            "phytochemical_name": {
                "description": "Optional: specific phytochemical to look up (e.g., 'curcumin'). If omitted, returns full phytochemical list.",
                "type": "string",
                "required": False,
            },
        },
        "requireConfirmation": "DISABLED",
    },
    {
        "name": "search_cyp_interactions",
        "description": "Search for all CYP-relevant phytochemicals in a plant from IMPPAT DynamoDB data. Returns phytochemicals that are CYP inhibitors or P-glycoprotein substrates. Optionally filter by a specific CYP enzyme.",
        "parameters": {
            "scientific_name": {
                "description": "Scientific name of the plant (e.g., 'Curcuma longa')",
                "type": "string",
                "required": True,
            },
            "cyp_enzyme": {
                "description": "Optional: specific CYP enzyme to filter by (e.g., 'CYP3A4', 'CYP2C9')",
                "type": "string",
                "required": False,
            },
        },
        "requireConfirmation": "DISABLED",
    },
]

WEB_SEARCH_FUNCTIONS = [
    {
        "name": "web_search",
        "description": "Search the web for drug interaction data using Tavily API. Returns results with source URLs categorized by type (pubmed, admet, clinical_trial, etc.).",
        "parameters": {
            "query": {
                "description": "Search query. Be specific, e.g., 'curcumin CYP3A4 inhibition mechanism'",
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

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def wait_for_agent(agent_id, target="NOT_PREPARED", max_wait=60):
    for _ in range(max_wait // 3):
        time.sleep(3)
        status = client.get_agent(agentId=agent_id)["agent"]["agentStatus"]
        print(f"    Status: {status}")
        if status in (target, "PREPARED", "FAILED"):
            return status
    return "TIMEOUT"


def prepare_and_update_alias(agent_id, alias_id):
    """Prepare agent and update its existing alias."""
    print(f"  Preparing agent {agent_id}...")
    client.prepare_agent(agentId=agent_id)

    for _ in range(20):
        time.sleep(5)
        status = client.get_agent(agentId=agent_id)["agent"]["agentStatus"]
        print(f"    Status: {status}")
        if status == "PREPARED":
            break
        if status == "FAILED":
            print("    FAILED to prepare!")
            return False

    if alias_id:
        print(f"  Updating alias {alias_id}...")
        client.update_agent_alias(
            agentId=agent_id,
            agentAliasId=alias_id,
            agentAliasName="live",
        )
        for _ in range(10):
            time.sleep(3)
            alias_status = client.get_agent_alias(
                agentId=agent_id, agentAliasId=alias_id
            )["agentAlias"]["agentAliasStatus"]
            print(f"    Alias status: {alias_status}")
            if alias_status == "PREPARED":
                break
    return True


def create_alias(agent_id, alias_name="live"):
    print(f"  Creating alias '{alias_name}'...")
    resp = client.create_agent_alias(
        agentId=agent_id, agentAliasName=alias_name,
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


def list_action_groups(agent_id):
    resp = client.list_agent_action_groups(
        agentId=agent_id, agentVersion="DRAFT",
    )
    return resp.get("actionGroupSummaries", [])


def add_code_interpreter(agent_id):
    """Add Code Interpreter action group to an agent."""
    print(f"  Adding Code Interpreter to agent {agent_id}...")
    existing = list_action_groups(agent_id)
    for ag in existing:
        if ag.get("actionGroupName") == "CodeInterpreterAction":
            print("    Code Interpreter already exists, skipping")
            return ag["actionGroupId"]

    try:
        resp = client.create_agent_action_group(
            agentId=agent_id,
            agentVersion="DRAFT",
            actionGroupName="CodeInterpreterAction",
            parentActionGroupSignature="AMAZON.CodeInterpreter",
            actionGroupState="ENABLED",
        )
        ag_id = resp["agentActionGroup"]["actionGroupId"]
        print(f"    Created Code Interpreter: {ag_id}")
        return ag_id
    except Exception as e:
        print(f"    ERROR adding Code Interpreter: {e}")
        return None


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    results = {}

    # ──── Step 1: Create Planner Agent ────
    print("\n" + "=" * 60)
    print("STEP 1: Creating Planner Agent")
    print("=" * 60)

    planner_id = None
    try:
        resp = client.create_agent(
            agentName="ausadhi-planner-agent",
            agentResourceRoleArn=ROLE_ARN,
            foundationModel="us.amazon.nova-pro-v1:0",
            instruction=PLANNER_INSTRUCTION,
            idleSessionTTLInSeconds=600,
        )
        planner_id = resp["agent"]["agentId"]
        print(f"  Created: {planner_id}")
        wait_for_agent(planner_id)
    except Exception as e:
        print(f"  ERROR: {e}")
        sys.exit(1)

    print("  Adding PlannerToolsGroup...")
    client.create_agent_action_group(
        agentId=planner_id,
        agentVersion="DRAFT",
        actionGroupName="PlannerToolsGroup",
        actionGroupExecutor={"lambda": LAMBDA_ARNS["planner_tools"]},
        functionSchema={"functions": PLANNER_FUNCTIONS},
        description="Substance identification and curated DB check",
    )

    print("  Adding WebSearchGroup...")
    client.create_agent_action_group(
        agentId=planner_id,
        agentVersion="DRAFT",
        actionGroupName="WebSearchGroup",
        actionGroupExecutor={"lambda": LAMBDA_ARNS["web_search"]},
        functionSchema={"functions": WEB_SEARCH_FUNCTIONS},
        description="Web search via Tavily",
    )

    print("  Preparing planner agent...")
    client.prepare_agent(agentId=planner_id)
    for _ in range(20):
        time.sleep(5)
        status = client.get_agent(agentId=planner_id)["agent"]["agentStatus"]
        print(f"    Status: {status}")
        if status == "PREPARED":
            break

    planner_alias = create_alias(planner_id)
    results["planner"] = {"id": planner_id, "alias": planner_alias}

    # ──── Step 2: Update AYUSH Agent ────
    print("\n" + "=" * 60)
    print("STEP 2: Updating AYUSH Agent")
    print("=" * 60)

    ayush_id = EXISTING_AGENTS["ayush"]["id"]
    ayush_alias = EXISTING_AGENTS["ayush"]["alias"]

    print("  Updating agent instructions...")
    client.update_agent(
        agentId=ayush_id,
        agentName="ausadhi-ayush-agent",
        agentResourceRoleArn=ROLE_ARN,
        foundationModel="us.amazon.nova-pro-v1:0",
        instruction=UPDATED_AYUSH_INSTRUCTION,
        idleSessionTTLInSeconds=600,
    )
    time.sleep(2)

    existing_ags = list_action_groups(ayush_id)
    for ag in existing_ags:
        ag_name = ag.get("actionGroupName", "")
        if ag_name == "AyushDataGroup":
            print(f"  Updating AyushDataGroup with new DynamoDB functions...")
            client.update_agent_action_group(
                agentId=ayush_id,
                agentVersion="DRAFT",
                actionGroupId=ag["actionGroupId"],
                actionGroupName="AyushDataGroup",
                actionGroupExecutor={"lambda": LAMBDA_ARNS["ayush_data"]},
                functionSchema={"functions": UPDATED_AYUSH_FUNCTIONS},
                description="AYUSH plant data from DynamoDB IMPPAT",
            )

    add_code_interpreter(ayush_id)

    prepare_and_update_alias(ayush_id, ayush_alias)
    results["ayush"] = {"id": ayush_id, "alias": ayush_alias}

    # ──── Step 3: Update Reasoning Agent ────
    print("\n" + "=" * 60)
    print("STEP 3: Updating Reasoning Agent")
    print("=" * 60)

    reasoning_id = EXISTING_AGENTS["reasoning"]["id"]
    reasoning_alias = EXISTING_AGENTS["reasoning"]["alias"]

    print("  Updating agent instructions with validation logic...")
    client.update_agent(
        agentId=reasoning_id,
        agentName="ausadhi-reasoning-agent",
        agentResourceRoleArn=ROLE_ARN,
        foundationModel="deepseek.v3.2",
        instruction=UPDATED_REASONING_INSTRUCTION,
        idleSessionTTLInSeconds=600,
    )
    time.sleep(2)

    add_code_interpreter(reasoning_id)

    prepare_and_update_alias(reasoning_id, reasoning_alias)
    results["reasoning"] = {"id": reasoning_id, "alias": reasoning_alias}

    # ──── Summary ────
    print("\n" + "=" * 60)
    print("Agent V2 Update Complete!")
    print("=" * 60)
    for role, info in results.items():
        print(f"  {role:15s}: Agent={info['id']}, Alias={info['alias']}")

    print("\nExisting agents (unchanged):")
    print(f"  {'allopathy':15s}: Agent={EXISTING_AGENTS['allopathy']['id']}, Alias={EXISTING_AGENTS['allopathy']['alias']}")
    print(f"  {'supervisor':15s}: Agent={EXISTING_AGENTS['supervisor']['id']} (TO BE REPLACED BY FLOW)")

    return results


if __name__ == "__main__":
    main()
