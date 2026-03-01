"""
Create AushadhiMitra Bedrock Flow
Replaces the Supervisor Agent with a structured workflow.

Flow: Input → Planner → AYUSH → Allopathy → Reasoning → Output

Each Agent node invokes the individual Bedrock Agent via its alias ARN.
The flow passes data between agents sequentially, with the output of
each agent feeding as input context to the next.

Usage: python scripts/create_flow.py
"""
import boto3
import json
import time
import sys

REGION = "us-east-1"
ACCOUNT_ID = "667736132441"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT_ID}:role/BedrockAgentRole"

AGENTS = {
    "planner": {"id": "JRARFMAC40", "alias": "BAKMQ02PQ7"},
    "ayush": {"id": "0SU1BHJ78L", "alias": "6NXIKPLBVB"},
    "allopathy": {"id": "CNAZG8LA0H", "alias": "BBAJ5HFGKG"},
    "reasoning": {"id": "03NGZ4CNF3", "alias": "DUH94OH0OG"},
}

client = boto3.client("bedrock-agent", region_name=REGION)


def agent_arn(agent_id, alias_id):
    return f"arn:aws:bedrock:{REGION}:{ACCOUNT_ID}:agent-alias/{agent_id}/{alias_id}"


def build_flow_definition():
    """Build the flow definition with nodes and connections."""

    nodes = [
        {
            "name": "FlowInput",
            "type": "Input",
            "configuration": {"input": {}},
            "outputs": [
                {"name": "document", "type": "String"},
            ],
        },
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
                {"name": "agentInputText", "type": "String",
                 "expression": "$.data"},
            ],
            "outputs": [
                {"name": "agentResponse", "type": "String"},
            ],
        },
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
                {"name": "agentInputText", "type": "String",
                 "expression": "$.data"},
            ],
            "outputs": [
                {"name": "agentResponse", "type": "String"},
            ],
        },
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
                {"name": "agentInputText", "type": "String",
                 "expression": "$.data"},
            ],
            "outputs": [
                {"name": "agentResponse", "type": "String"},
            ],
        },
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
                                        "Combine the following AYUSH phytochemical data and Allopathy drug data "
                                        "into a single analysis request for the Reasoning Agent.\n\n"
                                        "AYUSH DATA:\n{{ayush_data}}\n\n"
                                        "ALLOPATHY DATA:\n{{allopathy_data}}\n\n"
                                        "Create a comprehensive analysis request that includes all the data "
                                        "from both agents. The Reasoning Agent will use this to analyze "
                                        "drug interactions, calculate severity, build a knowledge graph, "
                                        "and validate the findings. Include all CYP enzyme data, "
                                        "phytochemical profiles, NTI status, and source URLs."
                                    ),
                                    "inputVariables": [
                                        {"name": "ayush_data"},
                                        {"name": "allopathy_data"},
                                    ],
                                },
                            },
                            "inferenceConfiguration": {
                                "text": {
                                    "temperature": 0.1,
                                    "maxTokens": 4096,
                                },
                            },
                        },
                    },
                },
            },
            "inputs": [
                {"name": "ayush_data", "type": "String",
                 "expression": "$.data"},
                {"name": "allopathy_data", "type": "String",
                 "expression": "$.data"},
            ],
            "outputs": [
                {"name": "modelCompletion", "type": "String"},
            ],
        },
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
                {"name": "agentInputText", "type": "String",
                 "expression": "$.data"},
            ],
            "outputs": [
                {"name": "agentResponse", "type": "String"},
            ],
        },
        {
            "name": "FlowOutput",
            "type": "Output",
            "configuration": {"output": {}},
            "inputs": [
                {"name": "document", "type": "String",
                 "expression": "$.data"},
            ],
        },
    ]

    connections = [
        {
            "name": "input_to_planner",
            "type": "Data",
            "source": "FlowInput",
            "target": "PlannerAgent",
            "configuration": {
                "data": {
                    "sourceOutput": "document",
                    "targetInput": "agentInputText",
                },
            },
        },
        {
            "name": "planner_to_ayush",
            "type": "Data",
            "source": "PlannerAgent",
            "target": "AYUSHAgent",
            "configuration": {
                "data": {
                    "sourceOutput": "agentResponse",
                    "targetInput": "agentInputText",
                },
            },
        },
        {
            "name": "planner_to_allopathy",
            "type": "Data",
            "source": "PlannerAgent",
            "target": "AllopathyAgent",
            "configuration": {
                "data": {
                    "sourceOutput": "agentResponse",
                    "targetInput": "agentInputText",
                },
            },
        },
        {
            "name": "ayush_to_merge",
            "type": "Data",
            "source": "AYUSHAgent",
            "target": "MergePrompt",
            "configuration": {
                "data": {
                    "sourceOutput": "agentResponse",
                    "targetInput": "ayush_data",
                },
            },
        },
        {
            "name": "allopathy_to_merge",
            "type": "Data",
            "source": "AllopathyAgent",
            "target": "MergePrompt",
            "configuration": {
                "data": {
                    "sourceOutput": "agentResponse",
                    "targetInput": "allopathy_data",
                },
            },
        },
        {
            "name": "merge_to_reasoning",
            "type": "Data",
            "source": "MergePrompt",
            "target": "ReasoningAgent",
            "configuration": {
                "data": {
                    "sourceOutput": "modelCompletion",
                    "targetInput": "agentInputText",
                },
            },
        },
        {
            "name": "reasoning_to_output",
            "type": "Data",
            "source": "ReasoningAgent",
            "target": "FlowOutput",
            "configuration": {
                "data": {
                    "sourceOutput": "agentResponse",
                    "targetInput": "document",
                },
            },
        },
    ]

    return {"nodes": nodes, "connections": connections}


def main():
    print("Creating AushadhiMitra Bedrock Flow...")
    print("=" * 60)

    definition = build_flow_definition()

    print(f"  Nodes: {len(definition['nodes'])}")
    print(f"  Connections: {len(definition['connections'])}")
    print(f"  Flow: Input → Planner → [AYUSH + Allopathy] → Merge → Reasoning → Output")

    try:
        resp = client.create_flow(
            name="ausadhi-interaction-flow",
            description="AushadhiMitra drug interaction analysis workflow. "
                        "Planner identifies substances, AYUSH and Allopathy agents "
                        "gather data in parallel, Reasoning agent analyzes and validates.",
            executionRoleArn=ROLE_ARN,
            definition=definition,
        )

        flow_id = resp["id"]
        flow_arn = resp["arn"]
        flow_status = resp["status"]
        print(f"\n  Flow created!")
        print(f"    ID: {flow_id}")
        print(f"    ARN: {flow_arn}")
        print(f"    Status: {flow_status}")

    except Exception as e:
        print(f"\n  ERROR creating flow: {e}")
        sys.exit(1)

    print("\n  Waiting for flow to be ready...")
    for _ in range(20):
        time.sleep(5)
        flow = client.get_flow(flowIdentifier=flow_id)
        status = flow["status"]
        print(f"    Status: {status}")
        if status in ("NotPrepared", "Prepared", "Failed"):
            break

    if status == "Failed":
        print("  Flow creation FAILED!")
        sys.exit(1)

    print("\n  Preparing flow...")
    try:
        client.prepare_flow(flowIdentifier=flow_id)
        for _ in range(20):
            time.sleep(5)
            flow = client.get_flow(flowIdentifier=flow_id)
            status = flow["status"]
            print(f"    Status: {status}")
            if status == "Prepared":
                break
            if status == "Failed":
                print("  Flow preparation FAILED!")
                sys.exit(1)
    except Exception as e:
        print(f"  ERROR preparing flow: {e}")
        sys.exit(1)

    print("\n  Creating flow alias...")
    try:
        alias_resp = client.create_flow_alias(
            flowIdentifier=flow_id,
            name="live",
            description="Production alias for AushadhiMitra interaction flow",
        )
        alias_id = alias_resp["id"]
        print(f"    Alias ID: {alias_id}")
    except Exception as e:
        print(f"  ERROR creating alias: {e}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("Bedrock Flow created successfully!")
    print("=" * 60)
    print(f"  Flow ID: {flow_id}")
    print(f"  Flow Alias: {alias_id}")
    print(f"  Flow ARN: {flow_arn}")
    print(f"\nUse these IDs in the EC2 backend configuration.")

    return {"flow_id": flow_id, "alias_id": alias_id, "arn": flow_arn}


if __name__ == "__main__":
    main()
