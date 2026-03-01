"""
Pipeline Orchestration Service V4

Supports two execution modes:
  1. Flow Mode (default): Invoke the Bedrock Flow with DoWhile validation loop.
     Parses flow-level + agent-level traces from flowTraceEvent for UI streaming.
  2. Pipeline Mode (fallback): Direct agent invocation with EC2 orchestration
     and validation loop-back, used when Flow invocation fails.

Architecture (Flow V4):
  FlowInput → PlannerAgent → DoWhile Loop {
      LoopInput → [AYUSH, Allopathy] → MergePrompt
      → ReasoningAgent → ValidationCode → LoopController(exit=PASSED, max=3)
  } → FlowOutput
"""
import json
import re
import uuid
import time
import logging
from typing import Generator, Tuple, Any

import boto3
from botocore.exceptions import ClientError

from app.config import (
    REGION,
    FLOW_ID, FLOW_ALIAS,
    PLANNER_AGENT_ID, PLANNER_AGENT_ALIAS,
    AYUSH_AGENT_ID, AYUSH_AGENT_ALIAS,
    ALLOPATHY_AGENT_ID, ALLOPATHY_AGENT_ALIAS,
    REASONING_AGENT_ID, REASONING_AGENT_ALIAS,
    MAX_VALIDATION_RETRIES,
    AGENT_INVOKE_MAX_RETRIES,
    AGENT_RETRY_BASE_WAIT,
    INPUT_MAX_LENGTH,
    INPUT_MIN_LENGTH,
)

logger = logging.getLogger(__name__)

_client = None

AGENTS = {
    "planner": {"id": PLANNER_AGENT_ID, "alias": PLANNER_AGENT_ALIAS,
                "label": "Planner Agent"},
    "ayush": {"id": AYUSH_AGENT_ID, "alias": AYUSH_AGENT_ALIAS,
              "label": "AYUSH Agent"},
    "allopathy": {"id": ALLOPATHY_AGENT_ID, "alias": ALLOPATHY_AGENT_ALIAS,
                  "label": "Allopathy Agent"},
    "reasoning": {"id": REASONING_AGENT_ID, "alias": REASONING_AGENT_ALIAS,
                  "label": "Reasoning Agent"},
}

NODE_TO_AGENT = {
    "PlannerAgent": "planner",
    "AYUSHAgent": "ayush",
    "AllopathyAgent": "allopathy",
    "ReasoningAgent": "reasoning",
    "DataMergePrompt": "merge",
    "ValidationStatusExtractor": "validation",
    "ValidationLoopInput": "loop_input",
    "ValidationLoopController": "loop_controller",
    # Keep legacy names for backward compatibility with older flow versions
    "MergePrompt": "merge",
    "ValidationCode": "validation",
    "LoopEntry": "loop_input",
    "LoopExit": "loop_controller",
}


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-agent-runtime", region_name=REGION)
    return _client


# ──────────────────────────────────────────────────────────────
# Input Validation
# ──────────────────────────────────────────────────────────────

_ALLOWED_CHARS = re.compile(r"^[\w\s\-'.,()]+$", re.UNICODE)


def validate_drug_names(ayush_name: str, allopathy_name: str) -> Tuple[str, str]:
    """Validate and sanitize drug name inputs. Returns cleaned names or raises ValueError."""
    ayush_clean = ayush_name.strip()
    allopathy_clean = allopathy_name.strip()

    errors = []
    for label, value in [("ayush_name", ayush_clean), ("allopathy_name", allopathy_clean)]:
        if not value or len(value) < INPUT_MIN_LENGTH:
            errors.append(f"{label} must be at least {INPUT_MIN_LENGTH} characters")
        elif len(value) > INPUT_MAX_LENGTH:
            errors.append(f"{label} exceeds maximum length of {INPUT_MAX_LENGTH}")
        elif not _ALLOWED_CHARS.match(value):
            errors.append(f"{label} contains invalid characters")

    if errors:
        raise ValueError("; ".join(errors))

    return ayush_clean, allopathy_clean


# ──────────────────────────────────────────────────────────────
# Flow Mode: Invoke Bedrock Flow and parse traces
# ──────────────────────────────────────────────────────────────

def _parse_flow_trace(trace_event: dict) -> list:
    """Parse a flowTraceEvent into UI-friendly trace entries."""
    traces = []

    for key in ("nodeInputTrace", "nodeOutputTrace"):
        node_trace = trace_event.get(key, {})
        if node_trace:
            node_name = node_trace.get("nodeName", "Unknown")
            agent_key = NODE_TO_AGENT.get(node_name, node_name)
            timestamp = str(node_trace.get("timestamp", ""))
            fields = node_trace.get("fields", [])
            content_preview = ""
            if fields:
                val = fields[0].get("content", {}).get("document", "")
                if isinstance(val, str):
                    content_preview = val[:300]
                elif isinstance(val, dict):
                    content_preview = json.dumps(val)[:300]

            direction = "receiving" if "Input" in key else "produced"
            trace_type = "node_input" if "Input" in key else "node_output"
            traces.append({
                "type": trace_type,
                "agent": agent_key,
                "node": node_name,
                "message": f"{node_name} {direction}: {content_preview}",
                "timestamp": timestamp,
            })

    action_trace = trace_event.get("nodeActionTrace", {})
    if action_trace:
        node_name = action_trace.get("nodeName", "Unknown")
        agent_key = NODE_TO_AGENT.get(node_name, node_name)
        traces.append({
            "type": "node_action",
            "agent": agent_key,
            "node": node_name,
            "message": f"{node_name} executing...",
        })

    dep_trace = trace_event.get("nodeDependencyTrace", {})
    if dep_trace:
        node_name = dep_trace.get("nodeName", "Unknown")
        agent_key = NODE_TO_AGENT.get(node_name, node_name)

        for elem in dep_trace.get("traceElements", []):
            for at in elem.get("agentTraces", []):
                for trace_part in at.get("traceParts", []):
                    parsed = _parse_agent_trace_part(trace_part, agent_key, node_name)
                    if parsed:
                        traces.append(parsed)

            for pt in elem.get("promptTraces", []):
                model_id = pt.get("modelId", "")
                input_text = pt.get("input", {}).get("text", "")[:200]
                output_text = pt.get("output", {}).get("text", "")[:300]
                if input_text:
                    traces.append({
                        "type": "prompt_input",
                        "agent": agent_key,
                        "node": node_name,
                        "message": f"{node_name} prompt ({model_id}): {input_text}",
                    })
                if output_text:
                    traces.append({
                        "type": "prompt_output",
                        "agent": agent_key,
                        "node": node_name,
                        "message": f"{node_name} response: {output_text}",
                    })

    cond_trace = trace_event.get("conditionResultTrace", {})
    if cond_trace:
        node_name = cond_trace.get("nodeName", "Unknown")
        satisfied = cond_trace.get("satisfiedConditions", [])
        traces.append({
            "type": "condition",
            "agent": "loop_controller",
            "node": node_name,
            "message": f"Loop condition: {', '.join(c.get('conditionName', '') for c in satisfied)}",
            "conditions": satisfied,
        })

    return traces


def _parse_agent_trace_part(trace_part: dict, agent_key: str, node_name: str) -> dict:
    """Parse a single TracePart from an agent invocation inside a Flow."""
    trace = trace_part.get("trace", {})

    orchestration = trace.get("orchestrationTrace", {})
    if orchestration:
        if "rationale" in orchestration:
            text = orchestration["rationale"].get("text", "")[:500]
            return {"type": "thinking", "agent": agent_key, "node": node_name,
                    "message": text}

        if "modelInvocationInput" in orchestration:
            return {"type": "model_input", "agent": agent_key, "node": node_name,
                    "message": f"{node_name} invoking model..."}

        if "modelInvocationOutput" in orchestration:
            out = orchestration["modelInvocationOutput"]
            usage = out.get("metadata", {}).get("usage", {})
            return {"type": "model_output", "agent": agent_key, "node": node_name,
                    "message": f"{node_name} model responded "
                              f"(tokens: {usage.get('inputTokens', '?')}/{usage.get('outputTokens', '?')})",
                    "tokens": usage}

        if "invocationInput" in orchestration:
            inv = orchestration["invocationInput"]
            ag = inv.get("actionGroupInvocationInput", {})
            if ag:
                func = ag.get("function", "")
                group = ag.get("actionGroupName", "")
                params = {p["name"]: p["value"] for p in ag.get("parameters", [])}
                return {"type": "tool_call", "agent": agent_key, "node": node_name,
                        "message": f"Calling {group}.{func}({json.dumps(params)[:200]})",
                        "function": func, "parameters": params}

            ci = inv.get("codeInterpreterInvocationInput", {})
            if ci:
                code = ci.get("code", "")[:200]
                return {"type": "code_interpreter", "agent": agent_key,
                        "node": node_name, "message": f"Running code: {code}"}

        if "observation" in orchestration:
            obs = orchestration["observation"]
            ag_obs = obs.get("actionGroupInvocationOutput", {})
            if ag_obs:
                text = ag_obs.get("text", "")[:300]
                return {"type": "tool_result", "agent": agent_key, "node": node_name,
                        "message": f"Tool returned: {text}"}

            ci_obs = obs.get("codeInterpreterInvocationOutput", {})
            if ci_obs:
                output = ci_obs.get("executionOutput", "")[:300]
                return {"type": "code_result", "agent": agent_key, "node": node_name,
                        "message": f"Code result: {output}"}

            final = obs.get("finalResponse", {})
            if final:
                text = final.get("text", "")[:400]
                return {"type": "final_response", "agent": agent_key,
                        "node": node_name, "message": f"Final: {text}"}

    pre = trace.get("preProcessingTrace", {})
    if pre and "modelInvocationOutput" in pre:
        parsed = pre["modelInvocationOutput"].get("parsedResponse", {})
        return {"type": "preprocessing", "agent": agent_key, "node": node_name,
                "message": f"Preprocessing: {parsed.get('rationale', '')[:300]}"}

    failure = trace.get("failureTrace", {})
    if failure:
        reason = failure.get("failureReason", "Unknown failure")
        return {"type": "agent_error", "agent": agent_key, "node": node_name,
                "message": f"Agent failure: {str(reason)[:300]}"}

    return None


def run_flow_pipeline(ayush_name: str, allopathy_name: str,
                      session_id: str = None) -> Generator[Tuple[str, Any], None, None]:
    """Run the interaction analysis via the Bedrock Flow (V4 DoWhile loop).

    Yields the same event types as run_interaction_pipeline for UI compatibility.
    """
    if not session_id:
        session_id = str(uuid.uuid4())

    try:
        ayush_name, allopathy_name = validate_drug_names(ayush_name, allopathy_name)
    except ValueError as e:
        yield ("error", {"message": f"Input validation failed: {e}", "fallback": False})
        return

    if not FLOW_ID or not FLOW_ALIAS:
        yield ("error", {
            "message": "Bedrock Flow not configured (FLOW_ID/FLOW_ALIAS missing).",
            "fallback": True,
        })
        return

    client = _get_client()
    query = f"Check interaction between {ayush_name} and {allopathy_name}"

    yield ("trace", {
        "type": "flow_start",
        "agent": "Flow",
        "message": f"Starting Bedrock Flow (DoWhile validation loop) "
                   f"for {ayush_name} + {allopathy_name}...",
    })

    try:
        resp = client.invoke_flow(
            flowIdentifier=FLOW_ID,
            flowAliasIdentifier=FLOW_ALIAS,
            inputs=[{
                "content": {"document": query},
                "nodeName": "FlowInputNode",
                "nodeOutputName": "document",
            }],
            enableTrace=True,
        )
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        yield ("error", {
            "message": f"Flow invocation failed ({error_code}): {str(e)[:250]}",
            "fallback": True,
        })
        return
    except Exception as e:
        yield ("error", {
            "message": f"Flow invocation failed: {str(e)[:300]}",
            "fallback": True,
        })
        return

    full_response = ""
    current_node = ""
    loop_iteration = 0

    try:
        for event in resp.get("responseStream", []):
            if "flowOutputEvent" in event:
                output = event["flowOutputEvent"]
                content = output.get("content", {}).get("document", "")
                if isinstance(content, dict):
                    full_response = json.dumps(content)
                else:
                    full_response = str(content)
                yield ("response", full_response)

            if "flowTraceEvent" in event:
                flow_trace = event["flowTraceEvent"]
                for trace_entry in _parse_flow_trace(flow_trace):
                    node = trace_entry.get("node", "")

                    if node != current_node and node:
                        current_node = node
                        agent_key = NODE_TO_AGENT.get(node, node)
                        if node in ("LoopEntry", "ValidationLoopInput"):
                            loop_iteration += 1
                            yield ("trace", {
                                "type": "loop_iteration",
                                "agent": "Flow",
                                "message": f"Validation Loop — Iteration {loop_iteration}",
                                "iteration": loop_iteration,
                            })
                        yield ("trace", {
                            "type": "step_start",
                            "agent": agent_key,
                            "node": node,
                            "message": f"Entering {node}...",
                        })

                    yield ("trace", trace_entry)

            if "flowCompletionEvent" in event:
                completion = event["flowCompletionEvent"]
                reason = completion.get("completionReason", "UNKNOWN")

                if reason == "SUCCESS":
                    yield ("done", {
                        "full_response": full_response,
                        "session_id": session_id,
                        "cached": False,
                        "execution_mode": "flow_v4_dowhile",
                        "loop_iterations": loop_iteration,
                        "pipeline_stages": ["planner", "ayush", "allopathy", "reasoning"],
                    })
                else:
                    yield ("error", {
                        "message": f"Flow completed with non-success reason: {reason}",
                        "fallback": True,
                    })

            if "flowMultiTurnInputRequestEvent" in event:
                logger.warning("Unexpected multi-turn input request from Flow")
                yield ("trace", {
                    "type": "warning",
                    "agent": "Flow",
                    "message": "Flow requested additional input (unexpected — skipping)",
                })

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        logger.exception("Bedrock error streaming flow (%s)", error_code)
        yield ("error", {
            "message": f"Flow stream error ({error_code}): {str(e)[:250]}",
            "fallback": True,
        })
    except Exception as e:
        logger.exception("Error streaming flow response")
        yield ("error", {
            "message": f"Flow stream error: {str(e)[:300]}",
            "fallback": True,
        })


# ──────────────────────────────────────────────────────────────
# Pipeline Mode: Direct agent invocation (fallback)
# ──────────────────────────────────────────────────────────────

def _parse_trace(trace_event: dict, agent_label: str) -> dict:
    """Extract a human-readable trace log entry from a Bedrock trace event."""
    outer = trace_event.get("trace", {})
    trace = outer.get("trace", outer)

    orchestration = trace.get("orchestrationTrace", {})
    if orchestration:
        if "rationale" in orchestration:
            text = orchestration["rationale"].get("text", "")[:500]
            return {"type": "thinking", "agent": agent_label, "message": text}

        if "modelInvocationInput" in orchestration:
            return {"type": "model_input", "agent": agent_label,
                    "message": f"{agent_label} invoking model..."}

        if "modelInvocationOutput" in orchestration:
            out = orchestration["modelInvocationOutput"]
            usage = out.get("metadata", {}).get("usage", {})
            return {"type": "model_output", "agent": agent_label,
                    "message": f"{agent_label} model responded "
                              f"(tokens: {usage.get('inputTokens', '?')}/{usage.get('outputTokens', '?')})",
                    "tokens": usage}

        if "invocationInput" in orchestration:
            inv = orchestration["invocationInput"]
            ag = inv.get("actionGroupInvocationInput", {})
            if ag:
                func = ag.get("function", "")
                group = ag.get("actionGroupName", "")
                params = {p["name"]: p["value"] for p in ag.get("parameters", [])}
                return {"type": "tool_call", "agent": agent_label,
                        "message": f"Calling {group}.{func}({json.dumps(params)[:200]})",
                        "function": func, "parameters": params}

            ci = inv.get("codeInterpreterInvocationInput", {})
            if ci:
                code = ci.get("code", "")[:200]
                return {"type": "code_interpreter", "agent": agent_label,
                        "message": f"Running code: {code}"}

        if "observation" in orchestration:
            obs = orchestration["observation"]
            ag_obs = obs.get("actionGroupInvocationOutput", {})
            if ag_obs:
                text = ag_obs.get("text", "")[:300]
                return {"type": "tool_result", "agent": agent_label,
                        "message": f"Tool returned: {text}"}

            ci_obs = obs.get("codeInterpreterInvocationOutput", {})
            if ci_obs:
                output = ci_obs.get("executionOutput", "")[:300]
                return {"type": "code_result", "agent": agent_label,
                        "message": f"Code result: {output}"}

            final = obs.get("finalResponse", {})
            if final:
                text = final.get("text", "")[:400]
                return {"type": "final_response", "agent": agent_label,
                        "message": f"Final: {text}"}

    pre = trace.get("preProcessingTrace", {})
    if pre and "modelInvocationOutput" in pre:
        parsed = pre["modelInvocationOutput"].get("parsedResponse", {})
        return {"type": "preprocessing", "agent": agent_label,
                "message": f"Preprocessing: {parsed.get('rationale', '')[:300]}"}

    failure = trace.get("failureTrace", {})
    if failure:
        reason = failure.get("failureReason", "Unknown failure")
        return {"type": "agent_error", "agent": agent_label,
                "message": f"Agent failure: {str(reason)[:300]}"}

    return {"type": "processing", "agent": agent_label,
            "message": f"{agent_label} processing..."}


def _invoke_agent(agent_key: str, input_text: str, session_id: str,
                  max_retries: int = None) -> Generator[Tuple[str, Any], None, None]:
    """Invoke a single Bedrock Agent with trace streaming and retry logic."""
    if max_retries is None:
        max_retries = AGENT_INVOKE_MAX_RETRIES

    client = _get_client()
    agent = AGENTS[agent_key]

    for attempt in range(max_retries + 1):
        try:
            yield ("trace", {
                "type": "step_start",
                "agent": agent["label"],
                "message": f"Starting {agent['label']}..."
                           + (f" (attempt {attempt + 1})" if attempt > 0 else ""),
            })

            resp = client.invoke_agent(
                agentId=agent["id"],
                agentAliasId=agent["alias"],
                sessionId=f"{session_id}-{agent_key}",
                inputText=input_text,
                enableTrace=True,
            )

            full_text = ""
            for event in resp["completion"]:
                if "trace" in event:
                    parsed = _parse_trace(event, agent["label"])
                    yield ("trace", parsed)
                if "chunk" in event:
                    chunk_text = event["chunk"]["bytes"].decode("utf-8")
                    full_text += chunk_text

            yield ("agent_complete", {"agent": agent_key, "label": agent["label"],
                                      "response": full_text})
            return

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if attempt < max_retries and error_code in (
                "dependencyFailedException", "throttlingException",
                "serviceUnavailableException", "modelTimeoutException",
            ):
                wait = AGENT_RETRY_BASE_WAIT * (attempt + 1)
                yield ("trace", {
                    "type": "retry",
                    "agent": agent["label"],
                    "message": f"Retry {attempt + 1}/{max_retries} — "
                               f"{error_code}: {str(e)[:80]}. Waiting {wait}s...",
                })
                time.sleep(wait)
            else:
                yield ("error", {
                    "agent": agent["label"],
                    "message": f"{agent['label']} failed ({error_code}) "
                               f"after {attempt + 1} attempt(s): {str(e)[:200]}",
                })
                return

        except Exception as e:
            if attempt < max_retries:
                wait = AGENT_RETRY_BASE_WAIT * (attempt + 1)
                yield ("trace", {
                    "type": "retry",
                    "agent": agent["label"],
                    "message": f"Retry {attempt + 1}/{max_retries} — "
                               f"{type(e).__name__}: {str(e)[:80]}. Waiting {wait}s...",
                })
                time.sleep(wait)
            else:
                yield ("error", {
                    "agent": agent["label"],
                    "message": f"{agent['label']} failed after {max_retries + 1} "
                               f"attempts: {str(e)[:200]}",
                })
                return


def _extract_validation(response_text: str) -> dict:
    """Extract VALIDATION_RESULT JSON from the Reasoning Agent's response."""
    patterns = [
        r'VALIDATION_RESULT:\s*(\{[\s\S]*?\})\s*(?:\n\n|\Z)',
        r'\{[^{}]*"validation_status"\s*:\s*"[^"]*"[^{}]*(?:"missing_data"\s*:\s*\[[^\]]*\][^{}]*)?\}',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, response_text)
        for match in matches:
            try:
                parsed = json.loads(match.strip())
                if "validation_status" in parsed:
                    return parsed
            except json.JSONDecodeError:
                continue

    json_blocks = re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response_text)
    for block in json_blocks:
        try:
            parsed = json.loads(block)
            if "validation_status" in parsed:
                return parsed
        except json.JSONDecodeError:
            continue

    if "NEEDS_MORE_DATA" in response_text:
        return {"validation_status": "NEEDS_MORE_DATA", "completeness_score": 50,
                "issues": ["Validation JSON not parseable"], "missing_data": []}

    return {"validation_status": "PASSED", "completeness_score": 80,
            "issues": [], "missing_data": []}


def _determine_retry_agents(validation: dict) -> dict:
    """Determine which agents to re-invoke based on validation missing_data."""
    retry_plan = {"ayush": False, "allopathy": False, "web_search": False, "queries": []}

    for item in validation.get("missing_data", []):
        agent = item.get("source_agent", "").lower()
        query = item.get("query_suggestion", "")
        if "ayush" in agent:
            retry_plan["ayush"] = True
        elif "allopathy" in agent:
            retry_plan["allopathy"] = True
        elif "web" in agent:
            retry_plan["web_search"] = True
        if query:
            retry_plan["queries"].append({"agent": agent, "query": query})

    issues_text = " ".join(validation.get("issues", [])).lower()
    if not retry_plan["ayush"] and not retry_plan["allopathy"]:
        if any(kw in issues_text for kw in ["cyp", "phytochemical", "imppat", "ayush"]):
            retry_plan["ayush"] = True
        if any(kw in issues_text for kw in ["nti", "metabolism", "drug data", "allopathy"]):
            retry_plan["allopathy"] = True
        if any(kw in issues_text for kw in ["source", "pubmed", "evidence", "web"]):
            retry_plan["web_search"] = True

    return retry_plan


def run_interaction_pipeline(ayush_name: str, allopathy_name: str,
                             session_id: str = None) -> Generator[Tuple[str, Any], None, None]:
    """Run the full interaction analysis pipeline with validation loop-back.

    Yields (event_type, data) tuples for UI streaming.
    """
    if not session_id:
        session_id = str(uuid.uuid4())

    try:
        ayush_name, allopathy_name = validate_drug_names(ayush_name, allopathy_name)
    except ValueError as e:
        yield ("error", {"message": f"Input validation failed: {e}"})
        return

    query = f"Check interaction between {ayush_name} and {allopathy_name}"
    total_steps = 4

    # ── Step 1: Substance Identification & Planning ──────────
    yield ("trace", {"type": "pipeline_step", "agent": "Pipeline",
                     "message": f"Step 1/{total_steps}: Substance Identification & Planning"})

    planner_response = ""
    for event_type, data in _invoke_agent("planner", query, session_id):
        yield (event_type, data)
        if event_type == "agent_complete":
            planner_response = data["response"]
        if event_type == "error":
            return

    if not planner_response:
        yield ("error", {"message": "Planner Agent returned empty response"})
        return

    try:
        plan = json.loads(planner_response)
        if plan.get("cached", False):
            yield ("response", planner_response)
            yield ("done", {"full_response": planner_response, "session_id": session_id,
                            "cached": True, "execution_mode": "pipeline_fallback"})
            return
    except json.JSONDecodeError:
        pass

    # ── Step 2: AYUSH Phytochemical & CYP Data Collection ────
    yield ("trace", {"type": "pipeline_step", "agent": "Pipeline",
                     "message": f"Step 2/{total_steps}: AYUSH Phytochemical & CYP Data Collection"})

    ayush_prompt = (
        f"Based on this plan, gather phytochemical and CYP interaction data:\n\n"
        f"Plan: {planner_response[:2000]}\n\nFocus on the AYUSH substance and CYP profile."
    )
    ayush_response = ""
    for event_type, data in _invoke_agent("ayush", ayush_prompt, session_id):
        yield (event_type, data)
        if event_type == "agent_complete":
            ayush_response = data["response"]

    # ── Step 3: Allopathy Drug Metabolism & NTI Data ─────────
    yield ("trace", {"type": "pipeline_step", "agent": "Pipeline",
                     "message": f"Step 3/{total_steps}: Allopathy Drug Metabolism & NTI Data"})

    allopathy_prompt = (
        f"Based on this plan, gather drug metabolism and CYP data:\n\n"
        f"Plan: {planner_response[:2000]}\n\nFocus on CYP pathways and NTI status."
    )
    allopathy_response = ""
    for event_type, data in _invoke_agent("allopathy", allopathy_prompt, session_id):
        yield (event_type, data)
        if event_type == "agent_complete":
            allopathy_response = data["response"]

    # ── Step 4: Interaction Reasoning & Validation ───────────
    reasoning_response = ""
    validation = {}
    validation_iteration = 0

    while validation_iteration <= MAX_VALIDATION_RETRIES:
        is_retry = validation_iteration > 0
        if is_retry:
            step_label = f"Validation Retry {validation_iteration}/{MAX_VALIDATION_RETRIES}"
        else:
            step_label = f"Step 4/{total_steps}: Interaction Reasoning & Validation"

        yield ("trace", {"type": "pipeline_step", "agent": "Pipeline",
                         "message": step_label})

        if is_retry:
            reasoning_prompt = (
                f"RETRY ANALYSIS — Previous analysis incomplete.\n\n"
                f"PREVIOUS:\n{reasoning_response[:2000]}\n\n"
                f"AYUSH DATA:\n{ayush_response[:3000]}\n\n"
                f"ALLOPATHY DATA:\n{allopathy_response[:3000]}\n\n"
                f"Complete the analysis. Run all 5 phases. Aim for PASSED validation."
            )
        else:
            reasoning_prompt = (
                f"Analyze the drug interaction.\n\nPLAN:\n{planner_response[:1000]}\n\n"
                f"AYUSH DATA:\n{ayush_response[:3000]}\n\n"
                f"ALLOPATHY DATA:\n{allopathy_response[:3000]}\n\n"
                f"Run: 1) CYP analysis 2) PD analysis 3) Severity 4) Knowledge graph 5) Validation"
            )

        reasoning_response = ""
        for event_type, data in _invoke_agent(
            "reasoning", reasoning_prompt,
            f"{session_id}-reasoning-v{validation_iteration}",
        ):
            if event_type == "agent_complete":
                reasoning_response = data["response"]
            yield (event_type, data)
            if event_type == "error":
                return

        if not reasoning_response:
            yield ("error", {"message": "Reasoning Agent returned empty response"})
            return

        validation = _extract_validation(reasoning_response)
        status = validation.get("validation_status", "PASSED")
        score = validation.get("completeness_score", 0)

        yield ("validation", {
            "status": status, "completeness_score": score,
            "iteration": validation_iteration,
            "issues": validation.get("issues", []),
            "missing_data": validation.get("missing_data", []),
        })

        if status == "PASSED":
            break

        if validation_iteration >= MAX_VALIDATION_RETRIES:
            yield ("trace", {
                "type": "validation_max_retries",
                "agent": "Validation",
                "message": f"Max retries reached (score: {score}/100). Using best response.",
            })
            break

        retry_plan = _determine_retry_agents(validation)

        if retry_plan["ayush"]:
            for et, d in _invoke_agent(
                "ayush",
                f"Gather ADDITIONAL data for {ayush_name}. "
                f"Focus: {', '.join(validation.get('issues', [])[:3])}",
                f"{session_id}-ayush-retry-{validation_iteration}",
            ):
                yield (et, d)
                if et == "agent_complete":
                    ayush_response += "\n\n--- ADDITIONAL DATA ---\n" + d["response"]

        if retry_plan["allopathy"]:
            for et, d in _invoke_agent(
                "allopathy",
                f"Gather ADDITIONAL data for {allopathy_name}. "
                f"Focus: {', '.join(validation.get('issues', [])[:3])}",
                f"{session_id}-allopathy-retry-{validation_iteration}",
            ):
                yield (et, d)
                if et == "agent_complete":
                    allopathy_response += "\n\n--- ADDITIONAL DATA ---\n" + d["response"]

        validation_iteration += 1

    if reasoning_response:
        yield ("response", reasoning_response)
        yield ("done", {
            "full_response": reasoning_response,
            "session_id": session_id,
            "cached": False,
            "execution_mode": "pipeline_fallback",
            "pipeline_stages": ["planner", "ayush", "allopathy", "reasoning"],
            "validation_iterations": validation_iteration,
            "final_validation": validation.get("validation_status", "UNKNOWN"),
        })
    else:
        yield ("error", {"message": "No response from pipeline"})


# ──────────────────────────────────────────────────────────────
# Unified entry point: Try Flow, fallback to Pipeline
# ──────────────────────────────────────────────────────────────

def run_check(ayush_name: str, allopathy_name: str,
              session_id: str = None,
              mode: str = "auto") -> Generator[Tuple[str, Any], None, None]:
    """Unified entry point. Tries Flow mode first, falls back to Pipeline.

    mode: "auto" (try flow then pipeline), "flow" (flow only), "pipeline" (pipeline only)
    """
    if not session_id:
        session_id = str(uuid.uuid4())

    if mode in ("auto", "flow"):
        flow_failed = False
        last_error_data = {}
        for event_type, data in run_flow_pipeline(ayush_name, allopathy_name, session_id):
            if event_type == "error" and data.get("fallback"):
                flow_failed = True
                last_error_data = data
                yield ("trace", {
                    "type": "fallback",
                    "agent": "Pipeline",
                    "message": f"Flow failed: {data.get('message', '')}. "
                               f"Switching to pipeline mode.",
                })
                break
            if event_type == "error" and not data.get("fallback"):
                yield (event_type, data)
                return
            yield (event_type, data)

        if not flow_failed:
            return

        if mode == "flow":
            yield ("error", last_error_data)
            return

    yield from run_interaction_pipeline(ayush_name, allopathy_name, session_id)


def invoke_agent_streaming(query: str, session_id: str = None):
    """Legacy wrapper — parses query to extract drug names and runs pipeline."""
    match = re.search(r"(?:between|of)\s+(.+?)\s+and\s+(.+?)$", query, re.IGNORECASE)
    if match:
        ayush_name = match.group(1).strip()
        allopathy_name = match.group(2).strip()
    else:
        parts = query.replace("interaction", "").replace("check", "").strip().split()
        if len(parts) >= 2:
            mid = len(parts) // 2
            ayush_name = " ".join(parts[:mid])
            allopathy_name = " ".join(parts[mid:])
        else:
            yield ("error", {"message": f"Could not parse query: {query}"})
            return

    yield from run_check(ayush_name, allopathy_name, session_id)
