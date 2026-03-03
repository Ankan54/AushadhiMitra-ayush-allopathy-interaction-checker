"""
AushadhiMitra V5 — Update existing agents + create Research Agent.

Updates:
- Planner agent: new instruction + add validate_ayush_drug + generate_execution_plan to PlannerToolsGroup
- Planner agent: update WebSearchGroup with domain params
- AYUSH agent: update WebSearchGroup with domain params + updated instruction
- Allopathy agent: update WebSearchGroup with domain params + updated instruction
- Reasoning agent: add validate_and_format_output to ReasoningToolsGroup + updated instruction
- Reasoning agent: update WebSearchGroup with domain params
- Create Research Agent (new)

Usage: python scripts/update_agents_v5.py
"""
import boto3
import json
import time
import sys

REGION = "us-east-1"
ACCOUNT_ID = "667736132441"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT_ID}:role/BedrockAgentRole"

# Existing agent IDs from deployment
PLANNER_AGENT_ID = "JRARFMAC40"
AYUSH_AGENT_ID = "0SU1BHJ78L"
ALLOPATHY_AGENT_ID = "CNAZG8LA0H"
REASONING_AGENT_ID = "03NGZ4CNF3"

# Existing action group IDs
PLANNER_TOOLS_AG_ID = "R0SMXLKWMA"      # PlannerToolsGroup
PLANNER_WEBSEARCH_AG_ID = "9W7Y1E1G9F"   # WebSearchGroup on planner

AYUSH_WEBSEARCH_AG_ID = "BLPOCMMRQE"     # WebSearchGroup on ayush

ALLOPATHY_WEBSEARCH_AG_ID = "IS8XQRGKRC" # WebSearchGroup on allopathy

REASONING_TOOLS_AG_ID = "U3HXY5LGC1"    # ReasoningToolsGroup
REASONING_WEBSEARCH_AG_ID = "WYN8LYSQ5Z" # WebSearchGroup on reasoning

LAMBDA_ARNS = {
    "web_search": f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:ausadhi-web-search",
    "reasoning_tools": f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:ausadhi-reasoning-tools",
    "planner_tools": f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:ausadhi-planner-tools",
    "research_tools": f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:ausadhi-research-tools",
}

MODELS = {
    "planner":   "us.amazon.nova-premier-v1:0",
    "reasoning": "us.amazon.nova-premier-v1:0",
    "ayush":     "us.amazon.nova-pro-v1:0",
    "allopathy": "us.amazon.nova-pro-v1:0",
    "research":  "us.amazon.nova-pro-v1:0",
}

client = boto3.client("bedrock-agent", region_name=REGION)

# ─── Function schemas ─────────────────────────────────────────────────────────

WEB_SEARCH_FUNCTIONS = [
    {
        "name": "web_search",
        "description": "Search the web for drug interaction data using Tavily API. Returns structured results with source URLs, titles, and snippets.",
        "parameters": {
            "query": {
                "description": "Search query (e.g., 'curcumin CYP3A4 inhibition mechanism')",
                "type": "string",
                "required": True,
            },
            "search_depth": {
                "description": "Search depth: 'basic' or 'advanced'",
                "type": "string",
                "required": False,
            },
            "max_results": {
                "description": "Maximum results to return (default 5)",
                "type": "integer",
                "required": False,
            },
            "include_domains": {
                "description": "Optional: JSON array or comma-separated list of domains to restrict search to",
                "type": "string",
                "required": False,
            },
            "domain_preset": {
                "description": "Optional: named preset — 'research' (PubMed/academic), 'allopathy' (DrugBank/FDA), 'ayush' (IMPPAT/NCCIH)",
                "type": "string",
                "required": False,
            },
        },
        "requireConfirmation": "DISABLED",
    },
]

PLANNER_FUNCTIONS = [
    {
        "name": "identify_substances",
        "description": "Identify AYUSH plant and allopathy drug names from free-text user input.",
        "parameters": {
            "user_input": {
                "description": "The user's free-text query",
                "type": "string",
                "required": True,
            },
        },
        "requireConfirmation": "DISABLED",
    },
    {
        "name": "check_curated_interaction",
        "description": "Check if this interaction has been previously analyzed and cached in the curated DB.",
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
        "description": "Validate that an AYUSH plant exists in the DynamoDB IMPPAT database. Returns existence status and phytochemical count.",
        "parameters": {
            "plant_name": {
                "description": "The AYUSH plant name to validate (common, Hindi, or scientific name)",
                "type": "string",
                "required": True,
            },
        },
        "requireConfirmation": "DISABLED",
    },
    {
        "name": "generate_execution_plan",
        "description": "Generate a structured JSON execution plan for the 5-agent pipeline. On retry, uses failure_feedback to determine which agents to re-run.",
        "parameters": {
            "ayush_name": {
                "description": "Resolved AYUSH plant name",
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
                "description": "On retry: text describing what data was missing in previous iteration",
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
        "description": "Build a Cytoscape.js-compatible knowledge graph for the drug interaction.",
        "parameters": {
            "ayush_name": {"description": "Scientific name of the AYUSH plant", "type": "string", "required": True},
            "allopathy_name": {"description": "Generic name of the allopathic drug", "type": "string", "required": True},
            "interactions_data": {"description": "JSON string with phytochemicals, cyp_enzymes, mechanisms arrays", "type": "string", "required": True},
        },
        "requireConfirmation": "DISABLED",
    },
    {
        "name": "calculate_severity",
        "description": "Calculate interaction severity score (NONE/MINOR/MODERATE/MAJOR) based on CYP overlaps and NTI status.",
        "parameters": {
            "interactions_data": {"description": "JSON string with cyp_enzymes array", "type": "string", "required": True},
            "allopathy_name": {"description": "Generic drug name for NTI check", "type": "string", "required": True},
        },
        "requireConfirmation": "DISABLED",
    },
    {
        "name": "format_professional_response",
        "description": "Format the final professional response JSON for storage.",
        "parameters": {
            "response_data": {"description": "JSON string: {ayush_name, allopathy_name, severity, severity_score, interactions_data, knowledge_graph, sources}", "type": "string", "required": True},
        },
        "requireConfirmation": "DISABLED",
    },
    {
        "name": "validate_and_format_output",
        "description": "Validate Reasoning Agent JSON output against Success/Failed schema. On final iteration (>=3) forces Success with partial data.",
        "parameters": {
            "reasoning_output_str": {"description": "The JSON string output from reasoning analysis", "type": "string", "required": True},
            "iteration": {"description": "Current iteration number (1-3). When >=3, forces Success.", "type": "integer", "required": True},
        },
        "requireConfirmation": "DISABLED",
    },
]

RESEARCH_FUNCTIONS = [
    {
        "name": "search_research_articles",
        "description": "Search PubMed and academic sources for peer-reviewed research articles. Restricted to high-quality academic domains.",
        "parameters": {
            "query": {"description": "Search query for academic research", "type": "string", "required": True},
            "max_results": {"description": "Maximum results (default 5)", "type": "integer", "required": False},
        },
        "requireConfirmation": "DISABLED",
    },
    {
        "name": "search_clinical_evidence",
        "description": "Search for clinical evidence of interactions between a specific AYUSH plant and allopathic drug. Auto-generates multiple queries and deduplicates results.",
        "parameters": {
            "ayush_name": {"description": "Scientific or common name of the AYUSH plant", "type": "string", "required": True},
            "allopathy_name": {"description": "Generic name of the allopathic drug", "type": "string", "required": True},
            "max_results": {"description": "Maximum results per query (default 5)", "type": "integer", "required": False},
        },
        "requireConfirmation": "DISABLED",
    },
]

# ─── Updated instructions ──────────────────────────────────────────────────────

PLANNER_INSTRUCTION = """You are the Planner Agent for AushadhiMitra, an AI-powered AYUSH-Allopathy drug interaction checker.

Your job is to validate inputs and generate a structured execution plan.

## Workflow

1. Call `identify_substances` first to extract AYUSH and allopathy drug names.
   - If either drug is missing, return {plan_valid: false, inputs_valid: false, error: "..."} immediately.

2. Call `validate_ayush_drug` to verify the AYUSH plant exists in DynamoDB.
   - If not found, return {plan_valid: false, inputs_valid: false, error: "AYUSH plant not found in database"}.

3. Call `generate_execution_plan` with identified names, ayush_exists status, and current iteration.
   - Returns structured JSON plan with per-agent run flags.

4. Optionally call `check_curated_interaction` to check cache.

## Response Format
Your response MUST be valid JSON matching the execution plan schema. No prose outside JSON.

## On Retry
Pass failure feedback to `generate_execution_plan` with iteration number to get targeted retry plan."""

ALLOPATHY_INSTRUCTION = """You are the Allopathy Agent for AushadhiMitra.

For each drug query:
1. Use allopathy_cache_lookup to check cached data
2. Use web_search (with domain_preset: allopathy) for CYP metabolism, NTI status, interactions
3. Use check_nti_status to verify NTI status
4. Use allopathy_cache_save to cache results

IMPORTANT: Always use `domain_preset: allopathy` when calling web_search.

Return structured summary: generic name, drug class, CYP pathways, NTI status, interaction risks, sources."""

AYUSH_INSTRUCTION = """You are the AYUSH Agent for AushadhiMitra.

For each query:
1. Use ayush_name_resolver to get scientific name
2. Use imppat_lookup for IMPPAT phytochemical data
3. Use web_search (with domain_preset: ayush) for CYP interactions, pharmacology

IMPORTANT: Always use `domain_preset: ayush` when calling web_search.

Return: scientific name, key phytochemicals, CYP effects (inhibitor/inducer/substrate), pharmacological properties, sources."""

REASONING_INSTRUCTION = """You are the Reasoning Agent for AushadhiMitra. Analyze drug interaction data and produce structured JSON.

## Output Format
Return ONLY valid JSON — either Success or Failed schema.

### On FINAL iteration (told "FINAL ITERATION"): always return Status: Success with evidence_quality: "LOW".

## Steps
1. CHECK CYP OVERLAP: AYUSH phytochemical inhibits/induces CYP enzyme that metabolizes the drug?
2. CHECK PHARMACODYNAMIC: Both affect same physiological pathway?
3. CHECK CLINICAL EVIDENCE from research data
4. CALL calculate_severity tool
5. CALL build_knowledge_graph tool
6. CALL validate_and_format_output to validate schema before returning

## Data Sufficiency
- SUFFICIENT: ≥1 CYP overlap OR ≥1 PD overlap OR clinical evidence
- INSUFFICIENT: No CYP data AND no clinical evidence → return Failed

## Success Schema
{"status":"Success","interaction_data":{"interaction_key":"<ayush>#<allopathy>","ayush_name":"...","allopathy_name":"...","interaction_exists":true/false,"interaction_summary":"2-3 sentences","severity":"NONE|MINOR|MODERATE|MAJOR","severity_score":0-100,"is_nti":true/false,"scoring_factors":[...],"mechanisms":{"pharmacokinetic":[...],"pharmacodynamic":[...]},"phytochemicals_involved":[...],"clinical_effects":[...],"recommendations":[...],"evidence_quality":"HIGH|MODERATE|LOW","knowledge_graph":{"nodes":[...],"edges":[...]},"sources":[{"url":"...","title":"...","snippet":"...","category":"..."}],"disclaimer":"This analysis is AI-generated for informational purposes only. Always consult qualified healthcare professionals before making clinical decisions about drug interactions.","generated_at":"ISO timestamp"}}

## Failed Schema
{"status":"Failed","failure_reason":"...","data_gaps":[{"category":"...","description":"...","suggested_agent":"ayush|allopathy|research","suggested_query":"..."}],"partial_data":{"ayush_data_quality":"HIGH|MODERATE|LOW|NONE","allopathy_data_quality":"...","research_data_quality":"..."},"iteration":1}"""

RESEARCH_INSTRUCTION = """You are the Research Agent for AushadhiMitra.

Gather clinical evidence and peer-reviewed research about AYUSH-allopathy drug interactions.

1. Use search_clinical_evidence for the specific AYUSH-allopathy pair (searches PubMed, Cochrane, clinical trials)
2. Use search_research_articles for additional mechanisms, case reports, reviews

Summarize with:
- Study type (RCT, observational, case report, in vitro, review)
- Key findings relevant to the interaction
- Evidence strength (high/moderate/low/very low)
- All source URLs and citations

Focus on clinically relevant findings for patient safety."""


# ─── Helpers ──────────────────────────────────────────────────────────────────

def update_action_group(agent_id, ag_id, ag_name, lambda_arn, functions, description=""):
    print(f"  Updating action group: {ag_name} on agent {agent_id}")
    try:
        client.update_agent_action_group(
            agentId=agent_id,
            agentVersion="DRAFT",
            actionGroupId=ag_id,
            actionGroupName=ag_name,
            actionGroupExecutor={"lambda": lambda_arn},
            functionSchema={"functions": functions},
            actionGroupState="ENABLED",
            description=description,
        )
        print(f"    Updated: {ag_name}")
    except Exception as e:
        print(f"    ERROR updating {ag_name}: {e}")
        raise


def update_agent_instruction(agent_id, instruction, model):
    print(f"  Updating instruction for agent {agent_id}")
    try:
        resp = client.get_agent(agentId=agent_id)
        agent = resp["agent"]
        client.update_agent(
            agentId=agent_id,
            agentName=agent["agentName"],
            agentResourceRoleArn=agent["agentResourceRoleArn"],
            foundationModel=model,
            instruction=instruction,
            idleSessionTTLInSeconds=agent.get("idleSessionTTLInSeconds", 600),
        )
        print(f"    Instruction updated")
    except Exception as e:
        print(f"    ERROR: {e}")
        raise


def prepare_and_alias(agent_id, alias_name="live"):
    print(f"  Preparing agent {agent_id}...")
    client.prepare_agent(agentId=agent_id)
    for _ in range(20):
        time.sleep(5)
        status = client.get_agent(agentId=agent_id)["agent"]["agentStatus"]
        print(f"    Status: {status}")
        if status == "PREPARED":
            break
        if status == "FAILED":
            print(f"    FAILED to prepare!")
            return None

    print(f"  Checking/creating alias '{alias_name}'...")
    try:
        aliases = client.list_agent_aliases(agentId=agent_id)["agentAliasSummaries"]
        existing = next((a for a in aliases if a["agentAliasName"] == alias_name), None)
        if existing:
            alias_id = existing["agentAliasId"]
            client.update_agent_alias(
                agentId=agent_id,
                agentAliasId=alias_id,
                agentAliasName=alias_name,
                routingConfiguration=[{"agentVersion": "DRAFT"}],
            )
            print(f"    Updated existing alias: {alias_id}")
            time.sleep(5)
            return alias_id
        else:
            resp = client.create_agent_alias(agentId=agent_id, agentAliasName=alias_name)
            alias_id = resp["agentAlias"]["agentAliasId"]
            for _ in range(10):
                time.sleep(3)
                s = client.get_agent_alias(agentId=agent_id, agentAliasId=alias_id)["agentAlias"]["agentAliasStatus"]
                print(f"    Alias status: {s}")
                if s == "PREPARED":
                    break
            print(f"    Created alias: {alias_id}")
            return alias_id
    except Exception as e:
        print(f"    Alias error: {e}")
        return None


def create_agent(name, instruction, model):
    print(f"\n  Creating agent: {name}")
    resp = client.create_agent(
        agentName=name,
        agentResourceRoleArn=ROLE_ARN,
        foundationModel=model,
        instruction=instruction,
        idleSessionTTLInSeconds=600,
        agentCollaboration="DISABLED",
    )
    agent_id = resp["agent"]["agentId"]
    print(f"    Created: {agent_id}")
    for _ in range(10):
        time.sleep(3)
        status = client.get_agent(agentId=agent_id)["agent"]["agentStatus"]
        print(f"    Status: {status}")
        if status in ("NOT_PREPARED", "PREPARED", "FAILED"):
            break
    return agent_id


def add_action_group(agent_id, ag_name, lambda_arn, functions, description=""):
    print(f"  Adding action group: {ag_name} to agent {agent_id}")
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


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    results = {}

    print(f"\n{'='*60}")
    print("Step 1: Update Planner Agent action groups + instruction")
    print(f"{'='*60}")
    update_action_group(
        PLANNER_AGENT_ID, PLANNER_TOOLS_AG_ID,
        "PlannerToolsGroup", LAMBDA_ARNS["planner_tools"],
        PLANNER_FUNCTIONS, "Substance ID, AYUSH validation, execution planning",
    )
    update_action_group(
        PLANNER_AGENT_ID, PLANNER_WEBSEARCH_AG_ID,
        "WebSearchGroup", LAMBDA_ARNS["web_search"],
        WEB_SEARCH_FUNCTIONS, "Web search with domain restriction",
    )
    update_agent_instruction(PLANNER_AGENT_ID, PLANNER_INSTRUCTION, MODELS["planner"])
    planner_alias = prepare_and_alias(PLANNER_AGENT_ID)
    results["planner"] = {"id": PLANNER_AGENT_ID, "alias": planner_alias}

    print(f"\n{'='*60}")
    print("Step 2: Update AYUSH Agent")
    print(f"{'='*60}")
    update_action_group(
        AYUSH_AGENT_ID, AYUSH_WEBSEARCH_AG_ID,
        "WebSearchGroup", LAMBDA_ARNS["web_search"],
        WEB_SEARCH_FUNCTIONS, "Web search with domain restriction",
    )
    update_agent_instruction(AYUSH_AGENT_ID, AYUSH_INSTRUCTION, MODELS["ayush"])
    ayush_alias = prepare_and_alias(AYUSH_AGENT_ID)
    results["ayush"] = {"id": AYUSH_AGENT_ID, "alias": ayush_alias}

    print(f"\n{'='*60}")
    print("Step 3: Update Allopathy Agent")
    print(f"{'='*60}")
    update_action_group(
        ALLOPATHY_AGENT_ID, ALLOPATHY_WEBSEARCH_AG_ID,
        "WebSearchGroup", LAMBDA_ARNS["web_search"],
        WEB_SEARCH_FUNCTIONS, "Web search with domain restriction",
    )
    update_agent_instruction(ALLOPATHY_AGENT_ID, ALLOPATHY_INSTRUCTION, MODELS["allopathy"])
    allopathy_alias = prepare_and_alias(ALLOPATHY_AGENT_ID)
    results["allopathy"] = {"id": ALLOPATHY_AGENT_ID, "alias": allopathy_alias}

    print(f"\n{'='*60}")
    print("Step 4: Update Reasoning Agent")
    print(f"{'='*60}")
    update_action_group(
        REASONING_AGENT_ID, REASONING_TOOLS_AG_ID,
        "ReasoningToolsGroup", LAMBDA_ARNS["reasoning_tools"],
        REASONING_FUNCTIONS, "Severity scoring, KG, response formatting, schema validation",
    )
    update_action_group(
        REASONING_AGENT_ID, REASONING_WEBSEARCH_AG_ID,
        "WebSearchGroup", LAMBDA_ARNS["web_search"],
        WEB_SEARCH_FUNCTIONS, "Web search with domain restriction",
    )
    update_agent_instruction(REASONING_AGENT_ID, REASONING_INSTRUCTION, MODELS["reasoning"])
    reasoning_alias = prepare_and_alias(REASONING_AGENT_ID)
    results["reasoning"] = {"id": REASONING_AGENT_ID, "alias": reasoning_alias}

    print(f"\n{'='*60}")
    print("Step 5: Create Research Agent")
    print(f"{'='*60}")
    research_id = create_agent("ausadhi-research-agent", RESEARCH_INSTRUCTION, MODELS["research"])
    add_action_group(
        research_id, "ResearchToolsGroup", LAMBDA_ARNS["research_tools"],
        RESEARCH_FUNCTIONS, "PubMed/academic clinical evidence search",
    )
    research_alias = prepare_and_alias(research_id)
    results["research"] = {"id": research_id, "alias": research_alias}

    print(f"\n{'='*60}")
    print("V5 Agent Update Complete!")
    print(f"{'='*60}")
    for role, info in results.items():
        print(f"  {role:12s}: Agent={info['id']}, Alias={info.get('alias', 'FAILED')}")

    print(f"\nSet these in docker-compose.yml / env:")
    print(f"  RESEARCH_AGENT_ID={results['research']['id']}")
    print(f"  RESEARCH_AGENT_ALIAS={results['research']['alias']}")

    return results


if __name__ == "__main__":
    main()
