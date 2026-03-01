"""
Pipeline Orchestration Service V3

Implements the AushadhiMitra interaction analysis pipeline with validation loop-back:
  1. Planner Agent  → Identify substances, check curated DB
  2. AYUSH Agent    → Gather phytochemical/CYP data from DynamoDB
  3. Allopathy Agent → Gather drug metabolism data
  4. Reasoning Agent → Analyze, validate, format response
  5. Validation Check → If NEEDS_MORE_DATA, re-invoke relevant agents and retry

The validation loop re-invokes the specific agent(s) that the Reasoning Agent
identifies as having insufficient data, then re-runs Reasoning with the new data.
Maximum retry iterations: 2 (configurable via MAX_VALIDATION_RETRIES).
"""
import json
import re
import uuid
import time
import logging
from typing import Generator, Tuple, Any

import boto3

from app.config import (
    REGION,
    PLANNER_AGENT_ID, PLANNER_AGENT_ALIAS,
    AYUSH_AGENT_ID, AYUSH_AGENT_ALIAS,
    ALLOPATHY_AGENT_ID, ALLOPATHY_AGENT_ALIAS,
    REASONING_AGENT_ID, REASONING_AGENT_ALIAS,
)

logger = logging.getLogger(__name__)

_client = None

MAX_VALIDATION_RETRIES = 2

AGENTS = {
    "planner": {"id": PLANNER_AGENT_ID, "alias": PLANNER_AGENT_ALIAS, "label": "Planner Agent"},
    "ayush": {"id": AYUSH_AGENT_ID, "alias": AYUSH_AGENT_ALIAS, "label": "AYUSH Agent"},
    "allopathy": {"id": ALLOPATHY_AGENT_ID, "alias": ALLOPATHY_AGENT_ALIAS, "label": "Allopathy Agent"},
    "reasoning": {"id": REASONING_AGENT_ID, "alias": REASONING_AGENT_ALIAS, "label": "Reasoning Agent"},
}


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-agent-runtime", region_name=REGION)
    return _client


def _parse_trace(trace_event: dict, agent_label: str) -> dict:
    """Extract a human-readable trace log entry from a Bedrock trace event."""
    trace = trace_event.get("trace", {})

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

    pre = trace.get("preProcessingTrace", {})
    if pre and "modelInvocationOutput" in pre:
        parsed = pre["modelInvocationOutput"].get("parsedResponse", {})
        return {"type": "preprocessing", "agent": agent_label,
                "message": f"Preprocessing: {parsed.get('rationale', '')[:300]}"}

    return {"type": "processing", "agent": agent_label, "message": f"{agent_label} processing..."}


def _invoke_agent(agent_key: str, input_text: str, session_id: str,
                  max_retries: int = 2) -> Generator[Tuple[str, Any], None, None]:
    """Invoke a single Bedrock Agent with trace streaming and retry logic."""
    client = _get_client()
    agent = AGENTS[agent_key]

    for attempt in range(max_retries + 1):
        try:
            yield ("trace", {"type": "step_start", "agent": agent["label"],
                             "message": f"Starting {agent['label']}..."})

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

        except Exception as e:
            if attempt < max_retries:
                wait = 3 * (attempt + 1)
                yield ("trace", {"type": "retry", "agent": agent["label"],
                                 "message": f"Retry {attempt + 1}/{max_retries} after error: {str(e)[:100]}. Waiting {wait}s..."})
                time.sleep(wait)
            else:
                yield ("error", {"agent": agent["label"],
                                 "message": f"{agent['label']} failed after {max_retries + 1} attempts: {str(e)[:200]}"})
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
                candidate = match.strip()
                parsed = json.loads(candidate)
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
        return {
            "validation_status": "NEEDS_MORE_DATA",
            "completeness_score": 50,
            "issues": ["Validation JSON not parseable but NEEDS_MORE_DATA keyword found"],
            "missing_data": [],
        }

    return {
        "validation_status": "PASSED",
        "completeness_score": 80,
        "issues": [],
        "missing_data": [],
    }


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

    issues = validation.get("issues", [])
    issues_text = " ".join(issues).lower()

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

    Yields (event_type, data) tuples:
    - ("trace", {...})           — intermediate trace events for UI
    - ("agent_complete", {...})  — agent finished with response
    - ("validation", {...})      — validation result (PASSED or NEEDS_MORE_DATA)
    - ("response", "text")       — final response text
    - ("done", {...})            — pipeline complete
    - ("error", {...})           — error occurred
    """
    if not session_id:
        session_id = str(uuid.uuid4())

    query = f"Check interaction between {ayush_name} and {allopathy_name}"
    total_steps = 4

    # ──── Step 1: Planner Agent ────
    yield ("trace", {"type": "pipeline_step", "agent": "Pipeline",
                     "message": f"Step 1/{total_steps}: Planning - identifying substances and checking cache..."})

    planner_response = ""
    for event_type, data in _invoke_agent("planner", query, session_id):
        yield (event_type, data)
        if event_type == "agent_complete":
            planner_response = data["response"]
        if event_type == "error":
            yield ("error", data)
            return

    if not planner_response:
        yield ("error", {"message": "Planner Agent returned no response"})
        return

    try:
        plan = json.loads(planner_response)
        if plan.get("cached", False):
            yield ("trace", {"type": "cache_hit", "agent": "Pipeline",
                             "message": "Found cached result! Returning immediately."})
            yield ("response", planner_response)
            yield ("done", {"full_response": planner_response, "session_id": session_id, "cached": True})
            return
    except json.JSONDecodeError:
        pass

    # ──── Step 2: AYUSH Agent ────
    yield ("trace", {"type": "pipeline_step", "agent": "Pipeline",
                     "message": f"Step 2/{total_steps}: Gathering AYUSH phytochemical data from IMPPAT..."})

    ayush_prompt = (
        f"Based on this plan, gather phytochemical and CYP interaction data:\n\n"
        f"Plan: {planner_response[:2000]}\n\n"
        f"Focus on the AYUSH substance and its CYP enzyme interaction profile."
    )

    ayush_response = ""
    for event_type, data in _invoke_agent("ayush", ayush_prompt, session_id):
        yield (event_type, data)
        if event_type == "agent_complete":
            ayush_response = data["response"]
        if event_type == "error":
            yield ("trace", {"type": "warning", "agent": "Pipeline",
                             "message": "AYUSH Agent failed, continuing with available data..."})

    # ──── Step 3: Allopathy Agent ────
    yield ("trace", {"type": "pipeline_step", "agent": "Pipeline",
                     "message": f"Step 3/{total_steps}: Gathering allopathy drug metabolism data..."})

    allopathy_prompt = (
        f"Based on this plan, gather drug metabolism and CYP data:\n\n"
        f"Plan: {planner_response[:2000]}\n\n"
        f"Focus on the allopathic drug's CYP metabolism pathways and NTI status."
    )

    allopathy_response = ""
    for event_type, data in _invoke_agent("allopathy", allopathy_prompt, session_id):
        yield (event_type, data)
        if event_type == "agent_complete":
            allopathy_response = data["response"]
        if event_type == "error":
            yield ("trace", {"type": "warning", "agent": "Pipeline",
                             "message": "Allopathy Agent failed, continuing with available data..."})

    # ──── Step 4: Reasoning Agent + Validation Loop ────
    reasoning_response = ""
    validation_iteration = 0

    while validation_iteration <= MAX_VALIDATION_RETRIES:
        is_retry = validation_iteration > 0
        step_label = "Step 4" if not is_retry else f"Validation Retry {validation_iteration}"

        yield ("trace", {
            "type": "pipeline_step",
            "agent": "Pipeline",
            "message": (
                f"{step_label}/{total_steps}: Analyzing interactions, "
                f"calculating severity, validating..."
                + (f" (retry #{validation_iteration} with additional data)" if is_retry else "")
            ),
        })

        if is_retry:
            reasoning_prompt = (
                f"RETRY ANALYSIS - Previous analysis was incomplete.\n\n"
                f"PREVIOUS ANALYSIS:\n{reasoning_response[:2000]}\n\n"
                f"ADDITIONAL DATA GATHERED:\n"
                f"AYUSH DATA (updated):\n{ayush_response[:3000]}\n\n"
                f"ALLOPATHY DATA (updated):\n{allopathy_response[:3000]}\n\n"
                f"Please complete the analysis addressing the previously identified gaps.\n"
                f"Run all 5 phases: PK analysis, PD analysis, severity determination, "
                f"knowledge graph, and validation. Aim for PASSED validation."
            )
        else:
            reasoning_prompt = (
                f"Analyze the drug interaction between the AYUSH substance and allopathic drug.\n\n"
                f"PLAN:\n{planner_response[:1000]}\n\n"
                f"AYUSH PHYTOCHEMICAL DATA:\n{ayush_response[:3000]}\n\n"
                f"ALLOPATHY DRUG DATA:\n{allopathy_response[:3000]}\n\n"
                f"Please:\n"
                f"1. Analyze CYP enzyme interactions (all 5 major enzymes) and pharmacodynamic overlaps\n"
                f"2. Assess P-glycoprotein interactions\n"
                f"3. Use calculate_severity to score the interaction\n"
                f"4. Use build_knowledge_graph to create the interaction network\n"
                f"5. Validate completeness and consistency of findings\n"
                f"6. Use format_professional_response to create the final output"
            )

        reasoning_response = ""
        reasoning_session = f"{session_id}-reasoning-v{validation_iteration}"

        for event_type, data in _invoke_agent("reasoning", reasoning_prompt, reasoning_session):
            if event_type == "agent_complete":
                reasoning_response = data["response"]
            yield (event_type, data)
            if event_type == "error":
                yield ("error", data)
                return

        if not reasoning_response:
            yield ("error", {"message": "Reasoning Agent returned no response"})
            return

        # ──── Validation Check ────
        validation = _extract_validation(reasoning_response)
        status = validation.get("validation_status", "PASSED")
        score = validation.get("completeness_score", 0)

        yield ("validation", {
            "status": status,
            "completeness_score": score,
            "iteration": validation_iteration,
            "issues": validation.get("issues", []),
            "missing_data": validation.get("missing_data", []),
        })

        if status == "PASSED":
            yield ("trace", {
                "type": "validation_passed",
                "agent": "Validation",
                "message": f"Validation PASSED (score: {score}/100, "
                           f"iteration: {validation_iteration})"
            })
            break

        # ──── NEEDS_MORE_DATA: Determine which agents to re-invoke ────
        if validation_iteration >= MAX_VALIDATION_RETRIES:
            yield ("trace", {
                "type": "validation_max_retries",
                "agent": "Validation",
                "message": f"Validation still NEEDS_MORE_DATA after {MAX_VALIDATION_RETRIES} "
                           f"retries. Proceeding with best available response (score: {score}/100)."
            })
            break

        retry_plan = _determine_retry_agents(validation)

        yield ("trace", {
            "type": "validation_retry",
            "agent": "Validation",
            "message": (
                f"Validation: NEEDS_MORE_DATA (score: {score}/100). "
                f"Re-invoking: "
                f"{'AYUSH ' if retry_plan['ayush'] else ''}"
                f"{'Allopathy ' if retry_plan['allopathy'] else ''}"
                f"{'WebSearch ' if retry_plan['web_search'] else ''}"
                f"| Issues: {', '.join(validation.get('issues', [])[:3])}"
            ),
        })

        # ──── Re-invoke agents that need more data ────
        if retry_plan["ayush"]:
            ayush_retry_queries = [
                q["query"] for q in retry_plan["queries"]
                if "ayush" in q.get("agent", "").lower()
            ]
            retry_query = "; ".join(ayush_retry_queries) if ayush_retry_queries else (
                f"Gather ADDITIONAL phytochemical and CYP data for {ayush_name}. "
                f"Previous data was incomplete. Focus on: {', '.join(validation.get('issues', [])[:3])}"
            )

            yield ("trace", {"type": "pipeline_step", "agent": "Pipeline",
                             "message": f"Re-invoking AYUSH Agent for missing data..."})

            retry_session = f"{session_id}-ayush-retry-{validation_iteration}"
            for event_type, data in _invoke_agent("ayush", retry_query, retry_session):
                yield (event_type, data)
                if event_type == "agent_complete":
                    ayush_response = ayush_response + "\n\n--- ADDITIONAL DATA ---\n" + data["response"]

        if retry_plan["allopathy"]:
            allo_retry_queries = [
                q["query"] for q in retry_plan["queries"]
                if "allopathy" in q.get("agent", "").lower()
            ]
            retry_query = "; ".join(allo_retry_queries) if allo_retry_queries else (
                f"Gather ADDITIONAL drug metabolism data for {allopathy_name}. "
                f"Previous data was incomplete. Focus on: {', '.join(validation.get('issues', [])[:3])}"
            )

            yield ("trace", {"type": "pipeline_step", "agent": "Pipeline",
                             "message": f"Re-invoking Allopathy Agent for missing data..."})

            retry_session = f"{session_id}-allopathy-retry-{validation_iteration}"
            for event_type, data in _invoke_agent("allopathy", retry_query, retry_session):
                yield (event_type, data)
                if event_type == "agent_complete":
                    allopathy_response = allopathy_response + "\n\n--- ADDITIONAL DATA ---\n" + data["response"]

        validation_iteration += 1

    # ──── Pipeline Complete ────
    if reasoning_response:
        yield ("response", reasoning_response)
        yield ("done", {
            "full_response": reasoning_response,
            "session_id": session_id,
            "cached": False,
            "pipeline_stages": ["planner", "ayush", "allopathy", "reasoning"],
            "validation_iterations": validation_iteration,
            "final_validation": validation.get("validation_status", "UNKNOWN"),
        })
    else:
        yield ("error", {"message": "Reasoning Agent returned no response"})


def invoke_agent_streaming(query: str, session_id: str = None):
    """Legacy wrapper - parses query to extract drug names and runs pipeline."""
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

    yield from run_interaction_pipeline(ayush_name, allopathy_name, session_id)
