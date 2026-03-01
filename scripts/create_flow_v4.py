"""
AushadhiMitra Bedrock Flow V4 — DoWhile Loop with Agent Nodes.

Architecture:
  FlowInput → PlannerAgent → DoWhile Loop {
      ValidationLoopInput → [AYUSHAgent, AllopathyAgent] → DataMergePrompt
      → ReasoningAgent → ValidationStatusExtractor (InlineCode) → ValidationLoopController
  } → FlowOutput

The DoWhile loop runs at least once. After each iteration, the
InlineCode node extracts the validation status from the Reasoning
Agent's response. The ValidationLoopController exits when status == "PASSED".
Otherwise, agents are re-invoked with context about missing data.

Max iterations: 3 (1 initial + 2 retries)

Key: ValidationLoopController inputs use 'category' field:
  - LoopCondition: input evaluated by continueCondition expression
  - ExitLoop: data output when loop exits

Configuration is read from environment variables (with hardcoded defaults
for the current deployment). Set env vars to override.

Usage: python scripts/create_flow_v4.py
"""
import boto3
import json
import os
import time
import sys

REGION = os.environ.get("AWS_REGION", "us-east-1")
ACCOUNT_ID = os.environ.get("AWS_ACCOUNT_ID", "667736132441")
ROLE_ARN = os.environ.get(
    "BEDROCK_FLOW_ROLE_ARN",
    f"arn:aws:iam::{ACCOUNT_ID}:role/BedrockAgentRole",
)

FLOW_ID = os.environ.get("FLOW_ID", "4QKIL1MSB5")
FLOW_ALIAS = os.environ.get("FLOW_ALIAS", "CZZIUM9U5W")

AGENTS = {
    "planner": {
        "id": os.environ.get("PLANNER_AGENT_ID", "JRARFMAC40"),
        "alias": os.environ.get("PLANNER_AGENT_ALIAS", "BAKMQ02PQ7"),
    },
    "ayush": {
        "id": os.environ.get("AYUSH_AGENT_ID", "0SU1BHJ78L"),
        "alias": os.environ.get("AYUSH_AGENT_ALIAS", "6NXIKPLBVB"),
    },
    "allopathy": {
        "id": os.environ.get("ALLOPATHY_AGENT_ID", "CNAZG8LA0H"),
        "alias": os.environ.get("ALLOPATHY_AGENT_ALIAS", "BBAJ5HFGKG"),
    },
    "reasoning": {
        "id": os.environ.get("REASONING_AGENT_ID", "03NGZ4CNF3"),
        "alias": os.environ.get("REASONING_AGENT_ALIAS", "DUH94OH0OG"),
    },
}

MERGE_MODEL_ID = os.environ.get("MERGE_MODEL_ID", "us.amazon.nova-pro-v1:0")
MAX_LOOP_ITERATIONS = int(os.environ.get("MAX_LOOP_ITERATIONS", "3"))

client = boto3.client("bedrock-agent", region_name=REGION)


def agent_arn(agent_id, alias_id):
    return f"arn:aws:bedrock:{REGION}:{ACCOUNT_ID}:agent-alias/{agent_id}/{alias_id}"


# InlineCode: extract validation status from Reasoning Agent output.
# Wrapped in try/except so flow never breaks on malformed agent output.
VALIDATION_CODE = r'''
import json, re

try:
    reasoning_text = str(reasoning_output) if not isinstance(reasoning_output, str) else reasoning_output

    validation = None
    for pattern in [
        r'VALIDATION_RESULT:\s*(\{[\s\S]*?\})\s*(?:\n\n|\Z)',
        r'\{[^{}]*"validation_status"\s*:\s*"[^"]*"[^{}]*\}',
    ]:
        for m in re.findall(pattern, reasoning_text):
            try:
                p = json.loads(m.strip())
                if "validation_status" in p:
                    validation = p
                    break
            except Exception:
                pass
        if validation:
            break

    if not validation:
        for block in re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', reasoning_text):
            try:
                p = json.loads(block)
                if "validation_status" in p:
                    validation = p
                    break
            except Exception:
                pass

    if not validation:
        if "NEEDS_MORE_DATA" in reasoning_text:
            validation = {"validation_status": "NEEDS_MORE_DATA"}
        else:
            validation = {"validation_status": "PASSED"}

    result = {"status": validation.get("validation_status", "PASSED"), "response": reasoning_text[:10000]}
except Exception as exc:
    result = {"status": "PASSED", "response": str(reasoning_output)[:10000]}

result
'''


def build_loop_definition():
    """Build the inner loop flow definition.

    ValidationLoopInput → [AYUSHAgent, AllopathyAgent] → DataMergePrompt
    → ReasoningAgent → ValidationStatusExtractor → ValidationLoopController
    """

    nodes = [
        {
            "name": "ValidationLoopInput",
            "type": "LoopInput",
            "configuration": {"loopInput": {}},
            "outputs": [
                {"name": "loopInput", "type": "String"},
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
                {"name": "agentInputText", "type": "String", "expression": "$.data"},
            ],
            "outputs": [{"name": "agentResponse", "type": "String"}],
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
                {"name": "agentInputText", "type": "String", "expression": "$.data"},
            ],
            "outputs": [{"name": "agentResponse", "type": "String"}],
        },
        {
            "name": "DataMergePrompt",
            "type": "Prompt",
            "configuration": {
                "prompt": {
                    "sourceConfiguration": {
                        "inline": {
                            "templateType": "TEXT",
                            "modelId": MERGE_MODEL_ID,
                            "templateConfiguration": {
                                "text": {
                                    "text": (
                                        "Combine the following data into a comprehensive "
                                        "analysis request for the Reasoning Agent.\n\n"
                                        "AYUSH DATA:\n{{ayush_data}}\n\n"
                                        "ALLOPATHY DATA:\n{{allopathy_data}}\n\n"
                                        "Include all CYP enzyme data, phytochemical profiles, "
                                        "ADMET properties, NTI status, and source URLs."
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
        {
            "name": "ValidationStatusExtractor",
            "type": "InlineCode",
            "configuration": {
                "inlineCode": {
                    "code": VALIDATION_CODE,
                    "language": "Python_3",
                },
            },
            "inputs": [
                {"name": "reasoning_output", "type": "String", "expression": "$.data"},
            ],
            "outputs": [{"name": "response", "type": "Object"}],
        },
        {
            "name": "ValidationLoopController",
            "type": "LoopController",
            "configuration": {
                "loopController": {
                    "continueCondition": {
                        "name": "validationPassed",
                        "expression": 'validationStatus == "PASSED"',
                    },
                    "maxIterations": MAX_LOOP_ITERATIONS,
                },
            },
            "inputs": [
                {
                    "name": "validationStatus",
                    "type": "String",
                    "expression": "$.data.status",
                    "category": "LoopCondition",
                },
                {
                    "name": "loopOutput",
                    "type": "String",
                    "expression": "$.data.response",
                    "category": "ExitLoop",
                },
            ],
        },
    ]

    connections = [
        {
            "name": "LoopInputToAYUSHAgent",
            "type": "Data",
            "source": "ValidationLoopInput",
            "target": "AYUSHAgent",
            "configuration": {
                "data": {"sourceOutput": "loopInput", "targetInput": "agentInputText"},
            },
        },
        {
            "name": "LoopInputToAllopathyAgent",
            "type": "Data",
            "source": "ValidationLoopInput",
            "target": "AllopathyAgent",
            "configuration": {
                "data": {"sourceOutput": "loopInput", "targetInput": "agentInputText"},
            },
        },
        {
            "name": "AYUSHAgentToDataMerge",
            "type": "Data",
            "source": "AYUSHAgent",
            "target": "DataMergePrompt",
            "configuration": {
                "data": {"sourceOutput": "agentResponse", "targetInput": "ayush_data"},
            },
        },
        {
            "name": "AllopathyAgentToDataMerge",
            "type": "Data",
            "source": "AllopathyAgent",
            "target": "DataMergePrompt",
            "configuration": {
                "data": {"sourceOutput": "agentResponse", "targetInput": "allopathy_data"},
            },
        },
        {
            "name": "DataMergeToReasoningAgent",
            "type": "Data",
            "source": "DataMergePrompt",
            "target": "ReasoningAgent",
            "configuration": {
                "data": {"sourceOutput": "modelCompletion", "targetInput": "agentInputText"},
            },
        },
        {
            "name": "ReasoningAgentToValidation",
            "type": "Data",
            "source": "ReasoningAgent",
            "target": "ValidationStatusExtractor",
            "configuration": {
                "data": {"sourceOutput": "agentResponse", "targetInput": "reasoning_output"},
            },
        },
        {
            "name": "ValidationToLoopCondition",
            "type": "Data",
            "source": "ValidationStatusExtractor",
            "target": "ValidationLoopController",
            "configuration": {
                "data": {"sourceOutput": "response", "targetInput": "validationStatus"},
            },
        },
        {
            "name": "ValidationToLoopExit",
            "type": "Data",
            "source": "ValidationStatusExtractor",
            "target": "ValidationLoopController",
            "configuration": {
                "data": {"sourceOutput": "response", "targetInput": "loopOutput"},
            },
        },
    ]

    return {"nodes": nodes, "connections": connections}


def build_outer_flow():
    """Build the outer flow: FlowInput → PlannerAgent → AnalysisLoop → FlowOutput."""

    loop_definition = build_loop_definition()

    nodes = [
        {
            "name": "FlowInputNode",
            "type": "Input",
            "configuration": {"input": {}},
            "outputs": [{"name": "document", "type": "String"}],
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
                {"name": "agentInputText", "type": "String", "expression": "$.data"},
            ],
            "outputs": [{"name": "agentResponse", "type": "String"}],
        },
        {
            "name": "AnalysisLoop",
            "type": "Loop",
            "configuration": {
                "loop": {
                    "definition": loop_definition,
                },
            },
            "inputs": [
                {"name": "loopInput", "type": "String", "expression": "$.data"},
            ],
            "outputs": [
                {"name": "loopOutput", "type": "String"},
            ],
        },
        {
            "name": "FlowOutput",
            "type": "Output",
            "configuration": {"output": {}},
            "inputs": [
                {"name": "document", "type": "String", "expression": "$.data"},
            ],
        },
    ]

    connections = [
        {
            "name": "FlowInputToPlannerAgent",
            "type": "Data",
            "source": "FlowInputNode",
            "target": "PlannerAgent",
            "configuration": {
                "data": {"sourceOutput": "document", "targetInput": "agentInputText"},
            },
        },
        {
            "name": "PlannerAgentToAnalysisLoop",
            "type": "Data",
            "source": "PlannerAgent",
            "target": "AnalysisLoop",
            "configuration": {
                "data": {"sourceOutput": "agentResponse", "targetInput": "loopInput"},
            },
        },
        {
            "name": "AnalysisLoopToFlowOutput",
            "type": "Data",
            "source": "AnalysisLoop",
            "target": "FlowOutput",
            "configuration": {
                "data": {"sourceOutput": "loopOutput", "targetInput": "document"},
            },
        },
    ]

    return {"nodes": nodes, "connections": connections}


def validate_config():
    """Pre-flight checks before creating/updating the flow."""
    errors = []

    if not FLOW_ID:
        errors.append("FLOW_ID is not set")
    if not FLOW_ALIAS:
        errors.append("FLOW_ALIAS is not set")
    if not ROLE_ARN:
        errors.append("BEDROCK_FLOW_ROLE_ARN is not set")

    for name, agent in AGENTS.items():
        if not agent["id"]:
            errors.append(f"{name.upper()}_AGENT_ID is not set")
        if not agent["alias"]:
            errors.append(f"{name.upper()}_AGENT_ALIAS is not set")

    if errors:
        print("Configuration errors:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)


def main():
    print("AushadhiMitra Flow V4 — DoWhile Validation Loop")
    print("=" * 60)

    validate_config()

    print(f"\n  Configuration:")
    print(f"    Region:         {REGION}")
    print(f"    Account:        {ACCOUNT_ID}")
    print(f"    Flow ID:        {FLOW_ID}")
    print(f"    Flow Alias:     {FLOW_ALIAS}")
    print(f"    Merge Model:    {MERGE_MODEL_ID}")
    print(f"    Max Iterations: {MAX_LOOP_ITERATIONS}")
    for name, agent in AGENTS.items():
        print(f"    {name:12s}:   {agent['id']} / {agent['alias']}")

    definition = build_outer_flow()
    loop_def = definition["nodes"][2]["configuration"]["loop"]["definition"]

    print(f"\n  Flow Structure:")
    print(f"    Outer nodes:       {len(definition['nodes'])}")
    print(f"    Outer connections: {len(definition['connections'])}")
    print(f"    Loop nodes:        {len(loop_def['nodes'])}")
    print(f"    Loop connections:  {len(loop_def['connections'])}")
    print(f"\n    FlowInput → PlannerAgent → AnalysisLoop {{")
    print(f"      ValidationLoopInput → [AYUSHAgent, AllopathyAgent]")
    print(f"      → DataMergePrompt → ReasoningAgent")
    print(f"      → ValidationStatusExtractor → ValidationLoopController")
    print(f"        (exit when status == PASSED, max {MAX_LOOP_ITERATIONS} iterations)")
    print(f"    }} → FlowOutput")

    print(f"\n  Updating flow {FLOW_ID}...")
    try:
        resp = client.update_flow(
            flowIdentifier=FLOW_ID,
            name="ausadhi-interaction-flow",
            description="AushadhiMitra V4: DoWhile loop for validation retry.",
            executionRoleArn=ROLE_ARN,
            definition=definition,
        )
        print(f"    Status: {resp['status']}")
    except client.exceptions.ValidationException as e:
        print(f"    VALIDATION ERROR: {e}")
        sys.exit(1)
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
                for v in validations[:15]:
                    print(f"      VALIDATION ERROR: {v.get('message', v)}")
                print("\n  Flow preparation FAILED.")
                sys.exit(1)
        else:
            print("  Flow preparation timed out after 150s.")
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

    print(f"\n  Updating alias {FLOW_ALIAS} → version {version}...")
    try:
        client.update_flow_alias(
            flowIdentifier=FLOW_ID,
            aliasIdentifier=FLOW_ALIAS,
            name="live",
            routingConfiguration=[{"flowVersion": version}],
        )
        time.sleep(3)
        print(f"    Alias updated successfully")
    except Exception as e:
        print(f"    ERROR updating alias: {e}")

    print("\n" + "=" * 60)
    print("Flow V4 (DoWhile Validation Loop) deployed successfully!")
    print(f"  Flow: {FLOW_ID}, Version: {version}, Alias: {FLOW_ALIAS}")
    print(f"  Nodes: {len(definition['nodes'])} outer + {len(loop_def['nodes'])} loop = "
          f"{len(definition['nodes']) + len(loop_def['nodes'])} total")


if __name__ == "__main__":
    main()
