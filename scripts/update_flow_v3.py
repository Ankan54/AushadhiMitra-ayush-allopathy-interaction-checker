"""
Update AushadhiMitra Bedrock Flow V3 - with Validation Loop-back.

Flow architecture:
  Input → Planner → AYUSH → Allopathy → Merge → Reasoning
  → ValidationParser (Lambda) → Condition
    ├─ PASSED → OutputPassed
    └─ default (NEEDS_MORE_DATA) → RetryPrompt → RetryReasoning → OutputRetry

Since Bedrock Flows are DAGs, we use a two-pass pipeline.
The EC2 backend implements the full multi-iteration loop separately.

Usage: python scripts/update_flow_v3.py
"""
import boto3
import json
import time
import sys

REGION = "us-east-1"
ACCOUNT_ID = "667736132441"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT_ID}:role/BedrockAgentRole"

FLOW_ID = "4QKIL1MSB5"
FLOW_ALIAS = "CZZIUM9U5W"

AGENTS = {
    "planner": {"id": "JRARFMAC40", "alias": "BAKMQ02PQ7"},
    "ayush": {"id": "0SU1BHJ78L", "alias": "6NXIKPLBVB"},
    "allopathy": {"id": "CNAZG8LA0H", "alias": "BBAJ5HFGKG"},
    "reasoning": {"id": "03NGZ4CNF3", "alias": "DUH94OH0OG"},
}

VALIDATION_LAMBDA_ARN = (
    f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:ausadhi-validation-parser"
)

client = boto3.client("bedrock-agent", region_name=REGION)


def agent_arn(agent_id, alias_id):
    return f"arn:aws:bedrock:{REGION}:{ACCOUNT_ID}:agent-alias/{agent_id}/{alias_id}"


def build_flow_definition():
    """Build V3 flow with validation Condition node and two-pass retry."""

    nodes = [
        # --- INPUT ---
        {
            "name": "FlowInputNode",
            "type": "Input",
            "configuration": {"input": {}},
            "outputs": [{"name": "document", "type": "String"}],
        },
        # --- PLANNER ---
        {
            "name": "PlannerAgent",
            "type": "Agent",
            "configuration": {
                "agent": {
                    "agentAliasArn": agent_arn(
                        AGENTS["planner"]["id"], AGENTS["planner"]["alias"]
                    ),
                },
            },
            "inputs": [
                {"name": "agentInputText", "type": "String", "expression": "$.data"},
            ],
            "outputs": [{"name": "agentResponse", "type": "String"}],
        },
        # --- AYUSH ---
        {
            "name": "AYUSHAgent",
            "type": "Agent",
            "configuration": {
                "agent": {
                    "agentAliasArn": agent_arn(
                        AGENTS["ayush"]["id"], AGENTS["ayush"]["alias"]
                    ),
                },
            },
            "inputs": [
                {"name": "agentInputText", "type": "String", "expression": "$.data"},
            ],
            "outputs": [{"name": "agentResponse", "type": "String"}],
        },
        # --- ALLOPATHY ---
        {
            "name": "AllopathyAgent",
            "type": "Agent",
            "configuration": {
                "agent": {
                    "agentAliasArn": agent_arn(
                        AGENTS["allopathy"]["id"], AGENTS["allopathy"]["alias"]
                    ),
                },
            },
            "inputs": [
                {"name": "agentInputText", "type": "String", "expression": "$.data"},
            ],
            "outputs": [{"name": "agentResponse", "type": "String"}],
        },
        # --- MERGE PROMPT ---
        {
            "name": "MergePrompt",
            "type": "Prompt",
            "configuration": {
                "prompt": {
                    "sourceConfiguration": {
                        "inline": {
                            "templateType": "TEXT",
                            "modelId": "us.amazon.nova-pro-v1:0",
                            "templateConfiguration": {
                                "text": {
                                    "text": (
                                        "Combine the following AYUSH phytochemical data and "
                                        "Allopathy drug data into a single comprehensive analysis "
                                        "request.\n\n"
                                        "AYUSH DATA:\n{{ayush_data}}\n\n"
                                        "ALLOPATHY DATA:\n{{allopathy_data}}\n\n"
                                        "Include all CYP enzyme data, phytochemical profiles, "
                                        "ADMET properties, NTI status, drug metabolism pathways, "
                                        "and source URLs."
                                    ),
                                    "inputVariables": [
                                        {"name": "ayush_data"},
                                        {"name": "allopathy_data"},
                                    ],
                                },
                            },
                            "inferenceConfiguration": {
                                "text": {"temperature": 0.1, "maxTokens": 4096},
                            },
                        },
                    },
                },
            },
            "inputs": [
                {"name": "ayush_data", "type": "String", "expression": "$.data"},
                {"name": "allopathy_data", "type": "String", "expression": "$.data"},
            ],
            "outputs": [{"name": "modelCompletion", "type": "String"}],
        },
        # --- REASONING AGENT (first pass) ---
        {
            "name": "ReasoningAgent",
            "type": "Agent",
            "configuration": {
                "agent": {
                    "agentAliasArn": agent_arn(
                        AGENTS["reasoning"]["id"], AGENTS["reasoning"]["alias"]
                    ),
                },
            },
            "inputs": [
                {"name": "agentInputText", "type": "String", "expression": "$.data"},
            ],
            "outputs": [{"name": "agentResponse", "type": "String"}],
        },
        # --- VALIDATION PARSER (Lambda) ---
        {
            "name": "ValidationParser",
            "type": "LambdaFunction",
            "configuration": {
                "lambdaFunction": {
                    "lambdaArn": VALIDATION_LAMBDA_ARN,
                },
            },
            "inputs": [
                {"name": "functionInput", "type": "String", "expression": "$.data"},
            ],
            "outputs": [{"name": "functionResponse", "type": "Object"}],
        },
        # --- VALIDATION CONDITION ---
        # Condition nodes have NO outputs (routing is via Conditional connections)
        {
            "name": "ValidationCheck",
            "type": "Condition",
            "configuration": {
                "condition": {
                    "conditions": [
                        {
                            "name": "passed",
                            "expression": 'status == "PASSED"',
                        },
                        {
                            "name": "default",
                        },
                    ],
                },
            },
            "inputs": [
                {
                    "name": "status",
                    "type": "String",
                    "expression": "$.data.validation_status",
                },
            ],
        },
        # --- OUTPUT: PASSED ---
        {
            "name": "OutputPassed",
            "type": "Output",
            "configuration": {"output": {}},
            "inputs": [
                {
                    "name": "document",
                    "type": "String",
                    "expression": "$.data.full_response",
                },
            ],
        },
        # --- RETRY PROMPT ---
        {
            "name": "RetryPrompt",
            "type": "Prompt",
            "configuration": {
                "prompt": {
                    "sourceConfiguration": {
                        "inline": {
                            "templateType": "TEXT",
                            "modelId": "us.amazon.nova-pro-v1:0",
                            "templateConfiguration": {
                                "text": {
                                    "text": (
                                        "The previous drug interaction analysis was INCOMPLETE. "
                                        "The validation identified missing data.\n\n"
                                        "PREVIOUS ANALYSIS:\n{{analysis}}\n\n"
                                        "ISSUES FOUND:\n{{issues}}\n\n"
                                        "Create a refined request that addresses all gaps. "
                                        "Ensure all 5 major CYP enzymes are covered, "
                                        "NTI status is verified, and P-gp interactions assessed."
                                    ),
                                    "inputVariables": [
                                        {"name": "analysis"},
                                        {"name": "issues"},
                                    ],
                                },
                            },
                            "inferenceConfiguration": {
                                "text": {"temperature": 0.2, "maxTokens": 4096},
                            },
                        },
                    },
                },
            },
            "inputs": [
                {"name": "analysis", "type": "String", "expression": "$.data.full_response"},
                {"name": "issues", "type": "String", "expression": "$.data.issues"},
            ],
            "outputs": [{"name": "modelCompletion", "type": "String"}],
        },
        # --- RETRY REASONING (second pass) ---
        {
            "name": "RetryReasoning",
            "type": "Agent",
            "configuration": {
                "agent": {
                    "agentAliasArn": agent_arn(
                        AGENTS["reasoning"]["id"], AGENTS["reasoning"]["alias"]
                    ),
                },
            },
            "inputs": [
                {"name": "agentInputText", "type": "String", "expression": "$.data"},
            ],
            "outputs": [{"name": "agentResponse", "type": "String"}],
        },
        # --- OUTPUT: RETRY ---
        {
            "name": "OutputRetry",
            "type": "Output",
            "configuration": {"output": {}},
            "inputs": [
                {"name": "document", "type": "String", "expression": "$.data"},
            ],
        },
    ]

    connections = [
        # ===== LINEAR PIPELINE =====
        {
            "name": "InputToPlanner",
            "type": "Data",
            "source": "FlowInputNode",
            "target": "PlannerAgent",
            "configuration": {
                "data": {"sourceOutput": "document", "targetInput": "agentInputText"},
            },
        },
        {
            "name": "PlannerToAyush",
            "type": "Data",
            "source": "PlannerAgent",
            "target": "AYUSHAgent",
            "configuration": {
                "data": {"sourceOutput": "agentResponse", "targetInput": "agentInputText"},
            },
        },
        {
            "name": "PlannerToAllopathy",
            "type": "Data",
            "source": "PlannerAgent",
            "target": "AllopathyAgent",
            "configuration": {
                "data": {"sourceOutput": "agentResponse", "targetInput": "agentInputText"},
            },
        },
        {
            "name": "AyushToMerge",
            "type": "Data",
            "source": "AYUSHAgent",
            "target": "MergePrompt",
            "configuration": {
                "data": {"sourceOutput": "agentResponse", "targetInput": "ayush_data"},
            },
        },
        {
            "name": "AllopathyToMerge",
            "type": "Data",
            "source": "AllopathyAgent",
            "target": "MergePrompt",
            "configuration": {
                "data": {"sourceOutput": "agentResponse", "targetInput": "allopathy_data"},
            },
        },
        {
            "name": "MergeToReasoning",
            "type": "Data",
            "source": "MergePrompt",
            "target": "ReasoningAgent",
            "configuration": {
                "data": {"sourceOutput": "modelCompletion", "targetInput": "agentInputText"},
            },
        },
        # ===== VALIDATION PIPELINE =====
        {
            "name": "ReasoningToParser",
            "type": "Data",
            "source": "ReasoningAgent",
            "target": "ValidationParser",
            "configuration": {
                "data": {"sourceOutput": "agentResponse", "targetInput": "functionInput"},
            },
        },
        # Condition node gets validation_status from parser
        {
            "name": "ParserToCondition",
            "type": "Data",
            "source": "ValidationParser",
            "target": "ValidationCheck",
            "configuration": {
                "data": {"sourceOutput": "functionResponse", "targetInput": "status"},
            },
        },
        # ===== PASSED PATH =====
        # Data: parser full response → OutputPassed
        {
            "name": "ParserToOutputPassed",
            "type": "Data",
            "source": "ValidationParser",
            "target": "OutputPassed",
            "configuration": {
                "data": {"sourceOutput": "functionResponse", "targetInput": "document"},
            },
        },
        # Conditional routing: condition → OutputPassed when "passed"
        {
            "name": "ConditionPassed",
            "type": "Conditional",
            "source": "ValidationCheck",
            "target": "OutputPassed",
            "configuration": {
                "conditional": {"condition": "passed"},
            },
        },
        # ===== NEEDS_MORE_DATA PATH =====
        # Data: parser → RetryPrompt (analysis)
        {
            "name": "ParserToRetryAnalysis",
            "type": "Data",
            "source": "ValidationParser",
            "target": "RetryPrompt",
            "configuration": {
                "data": {"sourceOutput": "functionResponse", "targetInput": "analysis"},
            },
        },
        # Data: parser → RetryPrompt (issues)
        {
            "name": "ParserToRetryIssues",
            "type": "Data",
            "source": "ValidationParser",
            "target": "RetryPrompt",
            "configuration": {
                "data": {"sourceOutput": "functionResponse", "targetInput": "issues"},
            },
        },
        # Conditional routing: condition → RetryPrompt when default
        {
            "name": "ConditionDefault",
            "type": "Conditional",
            "source": "ValidationCheck",
            "target": "RetryPrompt",
            "configuration": {
                "conditional": {"condition": "default"},
            },
        },
        # Retry path: RetryPrompt → RetryReasoning → OutputRetry
        {
            "name": "RetryPromptToReasoning",
            "type": "Data",
            "source": "RetryPrompt",
            "target": "RetryReasoning",
            "configuration": {
                "data": {"sourceOutput": "modelCompletion", "targetInput": "agentInputText"},
            },
        },
        {
            "name": "RetryReasoningToOutput",
            "type": "Data",
            "source": "RetryReasoning",
            "target": "OutputRetry",
            "configuration": {
                "data": {"sourceOutput": "agentResponse", "targetInput": "document"},
            },
        },
    ]

    return {"nodes": nodes, "connections": connections}


def main():
    print("Updating AushadhiMitra Flow V3 - Validation Loop-back")
    print("=" * 60)

    definition = build_flow_definition()
    print(f"  Nodes: {len(definition['nodes'])}")
    print(f"  Connections: {len(definition['connections'])}")
    print(f"\n  Pipeline:")
    print(f"    Input -> Planner -> AYUSH -> Allopathy -> Merge -> Reasoning")
    print(f"    -> ValidationParser -> Condition")
    print(f"      |-- PASSED -> OutputPassed")
    print(f"      +-- NEEDS_MORE_DATA -> RetryPrompt -> RetryReasoning -> OutputRetry")

    print(f"\n  Updating flow {FLOW_ID}...")
    try:
        resp = client.update_flow(
            flowIdentifier=FLOW_ID,
            name="ausadhi-interaction-flow",
            description="AushadhiMitra V3: validation loop-back via Condition node.",
            executionRoleArn=ROLE_ARN,
            definition=definition,
        )
        print(f"    Status: {resp['status']}")
    except Exception as e:
        print(f"    ERROR: {e}")
        sys.exit(1)

    print("\n  Preparing flow...")
    try:
        client.prepare_flow(flowIdentifier=FLOW_ID)
        for i in range(30):
            time.sleep(5)
            flow = client.get_flow(flowIdentifier=FLOW_ID)
            status = flow["status"]
            print(f"    [{i+1}] Status: {status}")
            if status == "Prepared":
                break
            if status == "Failed":
                validations = flow.get("validations", [])
                for v in validations[:10]:
                    print(f"      VALIDATION: {v.get('message', v)}")
                print("  Flow preparation FAILED!")
                sys.exit(1)
    except Exception as e:
        print(f"    ERROR preparing: {e}")
        sys.exit(1)

    print("\n  Creating new flow version...")
    try:
        ver_resp = client.create_flow_version(flowIdentifier=FLOW_ID)
        version = ver_resp["version"]
        print(f"    Version: {version}")
    except Exception as e:
        print(f"    ERROR creating version: {e}")
        sys.exit(1)

    print(f"\n  Updating alias {FLOW_ALIAS} -> version {version}...")
    try:
        client.update_flow_alias(
            flowIdentifier=FLOW_ID,
            aliasIdentifier=FLOW_ALIAS,
            name="live",
            routingConfiguration=[{"flowVersion": version}],
        )
        time.sleep(3)
        print(f"    Alias updated")
    except Exception as e:
        print(f"    ERROR updating alias: {e}")

    print("\n" + "=" * 60)
    print("Flow V3 updated successfully!")
    print(f"  Flow: {FLOW_ID}, Version: {version}, Alias: {FLOW_ALIAS}")
    print(f"  Nodes: {len(definition['nodes'])} (was 7, now 13)")


if __name__ == "__main__":
    main()
