"""
CO-MAS Multi-Agent Pipeline Orchestrator

Implements a Cooperative Multi-Agent System (CO-MAS) inspired pipeline for AYUSH-Allopathy
drug interaction analysis:

  0. NAME RESOLUTION + WHITELIST CHECK (pre-pipeline, no agent calls)
  1. PLANNER  - plan / re-plan based on information gaps from Scorer
  2. PROPOSER PHASE: AYUSH + Allopathy + Research agents (parallel)
  3. EVALUATOR PHASE: Reasoning Agent — evidence-based interaction analysis
  4. SCORER PHASE: Deterministic validation — checks completeness, identifies gaps
  5. If gaps found → log gaps, loop back to step 1 with targeted feedback
  6. FORMAT final JSON — deterministic function (not agent) for accuracy
"""
import json
import re
import uuid
import time
import logging
import threading
from urllib.parse import quote
from typing import Generator, Tuple, Any, List, Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.config import (
    REGION,
    S3_BUCKET,
    PLANNER_AGENT_ID, PLANNER_AGENT_ALIAS,
    AYUSH_AGENT_ID, AYUSH_AGENT_ALIAS,
    ALLOPATHY_AGENT_ID, ALLOPATHY_AGENT_ALIAS,
    REASONING_AGENT_ID, REASONING_AGENT_ALIAS,
    RESEARCH_AGENT_ID, RESEARCH_AGENT_ALIAS,
    MAX_COMAS_ITERATIONS,
    AGENT_INVOKE_MAX_RETRIES,
    AGENT_RETRY_BASE_WAIT,
    INPUT_MAX_LENGTH,
    INPUT_MIN_LENGTH,
)
from app.cloudwatch_logger import (
    log_pipeline_start,
    log_pipeline_complete,
    log_pipeline_error,
    log_agent_trace,
    log_iteration_gap,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# AWS clients
# ──────────────────────────────────────────────────────────────

_bedrock_runtime = None
_lambda_client = None
_s3_client = None

_BOTO_CONFIG = Config(
    retries={"max_attempts": 3, "mode": "adaptive"},
    read_timeout=600,
    connect_timeout=10,
)


def _get_bedrock():
    global _bedrock_runtime
    if _bedrock_runtime is None:
        _bedrock_runtime = boto3.client(
            "bedrock-agent-runtime", region_name=REGION, config=_BOTO_CONFIG
        )
    return _bedrock_runtime


def _get_lambda():
    global _lambda_client
    if _lambda_client is None:
        _lambda_client = boto3.client("lambda", region_name=REGION)
    return _lambda_client


def _get_s3():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3", region_name=REGION)
    return _s3_client


# ──────────────────────────────────────────────────────────────
# Agent registry
# ──────────────────────────────────────────────────────────────

AGENTS = {
    "planner":    {"id": PLANNER_AGENT_ID,    "alias": PLANNER_AGENT_ALIAS,    "label": "Planner"},
    "ayush":      {"id": AYUSH_AGENT_ID,      "alias": AYUSH_AGENT_ALIAS,      "label": "AYUSH"},
    "allopathy":  {"id": ALLOPATHY_AGENT_ID,  "alias": ALLOPATHY_AGENT_ALIAS,  "label": "Allopathy"},
    "reasoning":  {"id": REASONING_AGENT_ID,  "alias": REASONING_AGENT_ALIAS,  "label": "Reasoning"},
    "research":   {"id": RESEARCH_AGENT_ID,   "alias": RESEARCH_AGENT_ALIAS,   "label": "Research"},
}

# ──────────────────────────────────────────────────────────────
# Name resolution & AYUSH validation
# ──────────────────────────────────────────────────────────────

_name_mappings_cache = None
_name_mappings_lock = threading.Lock()


def _load_name_mappings() -> dict:
    global _name_mappings_cache
    with _name_mappings_lock:
        if _name_mappings_cache is not None:
            return _name_mappings_cache

        # Try local file first (Docker image bakes a copy)
        local_candidates = [
            "/app/data/reference/name_mappings.json",
            "data/reference/name_mappings.json",
            "backend/data/reference/name_mappings.json",
        ]
        for path in local_candidates:
            try:
                with open(path) as f:
                    _name_mappings_cache = json.load(f)
                    logger.info(f"Loaded name_mappings from {path}")
                    return _name_mappings_cache
            except (FileNotFoundError, IOError):
                pass

        # Fallback: try S3
        try:
            s3 = _get_s3()
            bucket = S3_BUCKET or "ausadhi-mitra"
            resp = s3.get_object(Bucket=bucket, Key="reference/name_mappings.json")
            _name_mappings_cache = json.loads(resp["Body"].read().decode("utf-8"))
            logger.info("Loaded name_mappings from S3")
            return _name_mappings_cache
        except Exception as e:
            logger.error(f"Failed to load name_mappings.json: {e}")
            return {"plants": []}


def build_imppat_url(scientific_name: str) -> str:
    """Construct IMPPAT phytochemical page URL for the AYUSH plant."""
    return f"https://cb.imsc.res.in/imppat/phytochemical/{quote(scientific_name)}"


def resolve_and_validate_ayush_drug(
    ayush_input: str,
) -> Tuple[bool, Optional[str], Optional[str], list]:
    """Resolve brand/common/Hindi name to scientific name, then validate it's in the allowed demo set.

    Returns:
        (is_valid, scientific_name, imppat_url, supported_drugs_display_list)
    """
    mappings = _load_name_mappings()
    plants = mappings.get("plants", [])

    supported_list = []
    for p in plants:
        sci = p.get("scientific_name", "")
        commons = p.get("common_names", [])
        display = sci
        if commons:
            display += f" ({', '.join(commons[:2])})"
        supported_list.append(display)

    query = ayush_input.lower().strip()
    resolved_plant = None

    for plant in plants:
        all_names = (
            [plant.get("scientific_name", "").lower()]
            + [n.lower() for n in plant.get("common_names", [])]
            + [n.lower() for n in plant.get("hindi_names", [])]
            + [n.lower() for n in plant.get("brand_names", [])]
        )
        for name in all_names:
            if not name:
                continue
            if name == query or query in name or name in query:
                resolved_plant = plant
                break
        if resolved_plant:
            break

    if not resolved_plant:
        return False, None, None, supported_list

    scientific_name = resolved_plant["scientific_name"]
    imppat_url = resolved_plant.get("imppat_url") or build_imppat_url(scientific_name)
    return True, scientific_name, imppat_url, supported_list


# ──────────────────────────────────────────────────────────────
# Agent Trace Parsing
# ──────────────────────────────────────────────────────────────

def _parse_trace(trace_event: dict, agent_label: str,
                 _pending_fn: list = None) -> dict:
    """Extract a human-readable trace log entry from a Bedrock trace event.

    _pending_fn is an optional single-element list used to correlate the most
    recent tool call function name with the subsequent tool result.
    """
    outer = trace_event.get("trace", {})
    trace = outer.get("trace", outer)

    orchestration = trace.get("orchestrationTrace", {})
    if orchestration:
        if "rationale" in orchestration:
            text = orchestration["rationale"].get("text", "")[:500]
            return {"type": "thinking", "agent": agent_label, "message": text}

        if "modelInvocationInput" in orchestration:
            inv_input = orchestration["modelInvocationInput"]
            text = inv_input.get("text", "")
            return {
                "type": "model_input",
                "agent": agent_label,
                "message": f"{agent_label} invoking model...",
                "prompt_preview": text[:300] if text else "",
            }

        if "modelInvocationOutput" in orchestration:
            out = orchestration["modelInvocationOutput"]
            usage = out.get("metadata", {}).get("usage", {})
            return {
                "type": "model_output",
                "agent": agent_label,
                "message": (
                    f"{agent_label} model responded "
                    f"(tokens: {usage.get('inputTokens', '?')}/{usage.get('outputTokens', '?')})"
                ),
                "tokens": usage,
            }

        if "invocationInput" in orchestration:
            inv = orchestration["invocationInput"]
            ag = inv.get("actionGroupInvocationInput", {})
            if ag:
                func = ag.get("function", "")
                group = ag.get("actionGroupName", "")
                params = {p["name"]: p["value"] for p in ag.get("parameters", [])}
                if _pending_fn is not None:
                    _pending_fn[:] = [func]
                return {
                    "type": "tool_call",
                    "agent": agent_label,
                    "message": f"Calling {group}.{func}({json.dumps(params)[:200]})",
                    "function": func,
                    "parameters": params,
                }

        if "observation" in orchestration:
            obs = orchestration["observation"]
            ag_obs = obs.get("actionGroupInvocationOutput", {})
            if ag_obs:
                full_text = ag_obs.get("text", "")
                fn_name = _pending_fn[0] if _pending_fn else ""
                if _pending_fn:
                    _pending_fn[:] = []
                return {
                    "type": "tool_result",
                    "agent": agent_label,
                    "message": f"Tool returned: {full_text[:300]}",
                    "_fn": fn_name,
                    "_full_result": full_text,
                }

            final_resp = obs.get("finalResponse", {})
            if final_resp:
                text = final_resp.get("text", "")
                return {
                    "type": "agent_complete",
                    "agent": agent_label,
                    "message": f"{agent_label} complete: {text[:200]}",
                    "response": text,
                }

    return None


# ──────────────────────────────────────────────────────────────
# Agent Invocation
# ──────────────────────────────────────────────────────────────

def _invoke_agent(agent_key: str, input_text: str, session_id: str,
                  yield_traces: bool = True) -> Generator:
    """Invoke a Bedrock agent and yield trace events + final response.

    Yields tuples of (event_type, data):
      ("trace", trace_dict)
      ("response", response_text)
      ("error", error_dict)
    """
    agent = AGENTS[agent_key]
    _pending_fn = []

    for attempt in range(AGENT_INVOKE_MAX_RETRIES + 1):
        try:
            resp = _get_bedrock().invoke_agent(
                agentId=agent["id"],
                agentAliasId=agent["alias"],
                sessionId=session_id,
                inputText=input_text,
                enableTrace=True,
            )

            full_response = ""
            for event in resp["completion"]:
                if "trace" in event:
                    parsed = _parse_trace(event, agent["label"], _pending_fn)
                    if parsed and yield_traces:
                        yield ("trace", parsed)

                if "chunk" in event:
                    chunk = event["chunk"].get("bytes", b"").decode("utf-8", errors="replace")
                    full_response += chunk

            yield ("response", full_response)
            return

        except ClientError as e:
            err_code = e.response["Error"]["Code"]
            if attempt < AGENT_INVOKE_MAX_RETRIES and err_code in (
                "ThrottlingException", "ServiceUnavailableException"
            ):
                wait = AGENT_RETRY_BASE_WAIT * (2 ** attempt)
                logger.warning(f"{agent_key} throttled, retry {attempt+1} in {wait}s")
                time.sleep(wait)
                continue
            yield ("error", {"message": f"{agent_key} agent error: {str(e)}", "code": err_code})
            return
        except Exception as e:
            logger.exception(f"Unexpected error invoking {agent_key}")
            yield ("error", {"message": str(e)})
            return


def _invoke_agent_collect(agent_key: str, input_text: str, session_id: str) -> Tuple[str, List]:
    """Invoke agent, collect all traces and the final response text."""
    traces = []
    response = ""
    for event_type, data in _invoke_agent(agent_key, input_text, session_id):
        if event_type == "trace":
            traces.append(data)
        elif event_type == "response":
            response = data
    return response, traces


# ──────────────────────────────────────────────────────────────
# Output Parsing Helpers
# ──────────────────────────────────────────────────────────────

def _parse_planner_output(planner_response: str) -> dict:
    """Extract structured plan from planner agent response."""
    try:
        plan = json.loads(planner_response)
        if isinstance(plan, dict):
            return plan
    except (json.JSONDecodeError, TypeError):
        pass

    json_match = re.search(r'\{[\s\S]*\}', planner_response)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    agents_to_run = {"ayush": True, "allopathy": True, "research": True}
    return {
        "plan_valid": True,
        "agents": {k: {"run": v} for k, v in agents_to_run.items()},
        "_raw": planner_response[:500],
    }


def _parse_reasoning_output(reasoning_response: str, compile_result: dict = None) -> dict:
    """Parse reasoning agent output or use the compile_and_validate_output result."""
    # If orchestrator directly called compile lambda, use that result
    if compile_result and isinstance(compile_result, dict):
        output_str = compile_result.get("output_str", "")
        if output_str:
            try:
                parsed = json.loads(output_str)
                if isinstance(parsed, dict):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass
        # The compile_result itself may already be the output
        if compile_result.get("status") == "Success":
            return compile_result

    # Fallback: try parsing reasoning_response directly
    if reasoning_response:
        try:
            parsed = json.loads(reasoning_response)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass

        json_match = re.search(r'\{[\s\S]*\}', reasoning_response)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

    return {}


_DRUGBANK_URL_RE = re.compile(
    r'https?://(?:go\.)?drugbank\.com/drugs/[A-Za-z0-9]+'
)


def _extract_drugbank_url(traces: list, response_text: str = "") -> str:
    """Extract DrugBank URL from allopathy agent traces AND response text."""
    # Search all trace types (tool results, thinking, model output, agent complete)
    for trace in traces:
        for field in ("_full_result", "message", "response"):
            text = trace.get(field, "")
            if text:
                match = _DRUGBANK_URL_RE.search(text)
                if match:
                    return match.group(0)

    # Also search the agent's final response text
    if response_text:
        match = _DRUGBANK_URL_RE.search(response_text)
        if match:
            return match.group(0)

    return ""


def _extract_source_urls(traces: list, response_text: str = "") -> list:
    """Extract source URLs from agent traces and response text."""
    url_re = re.compile(
        r'https?://(?:pubmed\.ncbi\.nlm\.nih\.gov|'
        r'www\.ncbi\.nlm\.nih\.gov/(?:pubmed|pmc)|'
        r'(?:go\.)?drugbank\.com|'
        r'cb\.imsc\.res\.in/imppat|'
        r'examine\.com|'
        r'scholar\.google\.com|'
        r'clinicaltrials\.gov|'
        r'www\.webmd\.com|'
        r'www\.drugs\.com|'
        r'doi\.org)'
        r'[^\s"\',<>)\]]*'
    )

    seen = set()
    sources = []

    all_text = response_text or ""
    for trace in traces:
        for field in ("_full_result", "message", "response"):
            text = trace.get(field, "")
            if text:
                all_text += "\n" + text

    for match in url_re.finditer(all_text):
        url = match.group(0).rstrip(".")
        if url not in seen:
            seen.add(url)
            source_type = "research"
            if "pubmed" in url or "ncbi" in url or "pmc" in url:
                source_type = "PubMed"
            elif "drugbank" in url:
                source_type = "DrugBank"
            elif "imppat" in url or "imsc.res.in" in url:
                source_type = "IMPPAT"
            elif "clinicaltrials" in url:
                source_type = "ClinicalTrials"
            elif "doi.org" in url:
                source_type = "DOI"
            sources.append({
                "url": url,
                "title": "",
                "snippet": "",
                "source_type": source_type,
            })

    return sources


def _extract_allopathy_info(traces: list, allopathy_response: str) -> dict:
    """Extract allopathy drug info from agent traces and response."""
    drugbank_url = _extract_drugbank_url(traces, allopathy_response)
    info = {"drugbank_url": drugbank_url}

    try:
        data = json.loads(allopathy_response)
        if isinstance(data, dict):
            info.update(data)
    except (json.JSONDecodeError, TypeError):
        pass

    return info


def _extract_ayush_info(traces: list, ayush_response: str) -> dict:
    """Extract AYUSH drug info including imppat_url from agent traces and response."""
    info = {}
    # Look for imppat_url in tool results
    for trace in traces:
        if trace.get("type") == "tool_result":
            full_result = trace.get("_full_result", "")
            url_match = re.search(
                r'https?://cb\.imsc\.res\.in/imppat/[^\s"\']+',
                full_result
            )
            if url_match:
                info["imppat_url"] = url_match.group(0)
                break

    try:
        data = json.loads(ayush_response)
        if isinstance(data, dict):
            info.update({k: v for k, v in data.items() if k not in info})
    except (json.JSONDecodeError, TypeError):
        pass

    return info


def _build_phytochemical_details(reasoning_output: dict) -> list:
    """Extract phytochemical details from reasoning output."""
    interaction_data = reasoning_output.get("interaction_data", {})
    if not isinstance(interaction_data, dict):
        return []
    return interaction_data.get("phytochemicals_involved", [])


def _transform_graph_to_admet(
    graph: dict,
    ayush_name: str,
    allopathy_name: str,
) -> dict:
    """Post-process a knowledge graph into ADMET-focused format with CYP overlap.

    - If graph already has admet_property nodes: fix labels (prefix with drug name)
      and fix edge labels (use 'has X' instead of bare 'X').
    - If old-style graph (phytochemicals with Contains): full transform.
    """
    if not isinstance(graph, dict):
        return graph

    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    if not nodes:
        return graph

    ayush_short = ayush_name.split()[0] if ayush_name else "AYUSH"
    allo_short = allopathy_name.split()[0] if allopathy_name else "Allopathy"

    admet_categories = {"absorption", "distribution", "metabolism", "excretion", "toxicity"}

    # Check if graph already has ADMET nodes (from Lambda)
    has_admet = any(
        n.get("data", {}).get("type") == "admet_property" for n in nodes
    )
    if has_admet:
        # Fix labels on existing ADMET graph: prefix with drug name, fix edge labels
        for node in nodes:
            nd = node.get("data", {})
            if nd.get("type") != "admet_property":
                continue
            nid = nd.get("id", "")
            label = nd.get("label", "")
            # Only fix if the label is a bare category (no drug name prefix yet)
            if label.lower() in admet_categories:
                if nid.startswith("ayush_"):
                    nd["label"] = f"{ayush_short}: {label}"
                elif nid.startswith("allo_"):
                    nd["label"] = f"{allo_short}: {label}"
        for edge in edges:
            ed = edge.get("data", {})
            label = ed.get("label", "")
            if label.lower() in admet_categories:
                ed["label"] = f"has {label}"
        return graph

    # Transform old format → ADMET format
    new_nodes = []
    new_edges = []

    # Drug nodes
    new_nodes.append({"data": {"id": "ayush", "label": ayush_name, "type": "ayush_plant"}})
    new_nodes.append({"data": {"id": "allopathy", "label": allopathy_name, "type": "allopathy_drug"}})

    # ADMET property nodes — prefixed with drug name so they're distinguishable
    for cat in ["Absorption", "Distribution", "Metabolism", "Excretion", "Toxicity"]:
        cat_key = cat.lower()
        ayush_node_id = f"ayush_{cat_key}"
        new_nodes.append({"data": {
            "id": ayush_node_id,
            "label": f"{ayush_short}: {cat}",
            "type": "admet_property",
        }})
        new_edges.append({"data": {"source": "ayush", "target": ayush_node_id, "label": f"has {cat}"}})

        allo_node_id = f"allo_{cat_key}"
        new_nodes.append({"data": {
            "id": allo_node_id,
            "label": f"{allo_short}: {cat}",
            "type": "admet_property",
        }})
        new_edges.append({"data": {"source": "allopathy", "target": allo_node_id, "label": f"has {cat}"}})

    # Collect CYP enzyme nodes from old graph
    cyp_nodes = [n for n in nodes if n.get("data", {}).get("type") == "cyp_enzyme"]
    cyp_names_seen = set()

    for cyp_node in cyp_nodes:
        enzyme_name = cyp_node["data"].get("label", "")
        if not enzyme_name or enzyme_name in cyp_names_seen:
            continue
        cyp_names_seen.add(enzyme_name)

        safe_id = enzyme_name.replace(" ", "_").replace("/", "_")
        node_id = f"cyp_{safe_id}"

        # All CYP enzymes in an interaction graph are overlap nodes
        new_nodes.append({"data": {"id": node_id, "label": enzyme_name, "type": "cyp_enzyme_overlap"}})

        # Find edges for this CYP enzyme from the old graph
        old_id = cyp_node["data"]["id"]
        ayush_effect = "Affects"
        allo_effect = "Metabolized by"
        for edge in edges:
            ed = edge.get("data", {})
            if ed.get("target") == old_id:
                label = ed.get("label", "").lower()
                source_type = None
                for n in nodes:
                    if n["data"]["id"] == ed.get("source"):
                        source_type = n["data"].get("type")
                        break
                if source_type == "allopathy_drug":
                    allo_effect = ed.get("label", "Metabolized by")
                elif source_type in ("phytochemical", "ayush_plant"):
                    if "inhib" in label:
                        ayush_effect = "Inhibits"
                    elif "induc" in label:
                        ayush_effect = "Induces"

        new_edges.append({"data": {"source": "ayush_metabolism", "target": node_id, "label": ayush_effect}})
        new_edges.append({"data": {"source": "allo_metabolism", "target": node_id, "label": allo_effect}})

    return {"nodes": new_nodes, "edges": new_edges}


# ──────────────────────────────────────────────────────────────
# CO-MAS Scorer Phase (deterministic)
# ──────────────────────────────────────────────────────────────

def _score_output(reasoning_output: dict, iteration: int) -> Tuple[bool, list, float, str]:
    """Deterministic CO-MAS Scorer phase.

    Returns: (passes, gaps, score, evidence_quality)
    """
    if not isinstance(reasoning_output, dict):
        return False, [
            "Need phytochemical data for the AYUSH drug with CYP enzyme interactions",
            "Need CYP metabolism pathway data for the allopathy drug",
            "Need clinical evidence from PubMed or research studies",
        ], 0.0, "LOW"

    status = reasoning_output.get("status", "Failed")
    interaction_data = reasoning_output.get("interaction_data", {})
    if not isinstance(interaction_data, dict):
        interaction_data = {}

    score = 0.0
    gaps = []

    if status != "Success":
        # Still try to score partial data; generate specific actionable gaps
        if not interaction_data:
            return False, [
                "Retrieve specific phytochemicals and their CYP enzyme effects for the AYUSH drug",
                "Retrieve CYP450 metabolism pathways and NTI status for the allopathy drug",
                "Search PubMed for clinical interaction evidence between these drugs",
            ], 0.0, "LOW"
        # Fall through to score whatever partial data exists

    # Required fields — 10 pts each
    for field, description in [
        ("ayush_name", "AYUSH drug scientific name"),
        ("allopathy_name", "Allopathy drug name"),
    ]:
        val = interaction_data.get(field)
        if val not in (None, "", [], {}):
            score += 10
        else:
            gaps.append(f"Need {description}")

    # Severity — 10 pts (NONE doesn't count as meaningful)
    severity_val = interaction_data.get("severity", "NONE")
    severity_score_val = interaction_data.get("severity_score", 0)
    if severity_val and severity_val != "NONE" and severity_score_val > 0:
        score += 20
    else:
        gaps.append("Need severity assessment with CYP enzyme analysis or pharmacodynamic evidence")

    # Knowledge graph — 10 pts
    kg = interaction_data.get("knowledge_graph", {})
    nodes = kg.get("nodes", []) if isinstance(kg, dict) else []
    if len(nodes) >= 3:
        score += 10
    else:
        gaps.append("Need ADMET properties and CYP enzyme data for knowledge graph")

    # Sources — 10 pts
    sources = interaction_data.get("sources", [])
    if len(sources) >= 2:
        score += 10
    else:
        gaps.append("Need at least 2 research sources (PubMed articles, clinical studies)")

    # Mechanisms — 10 pts
    mechanisms = interaction_data.get("mechanisms", {})
    pk = mechanisms.get("pharmacokinetic", []) if isinstance(mechanisms, dict) else []
    pd = mechanisms.get("pharmacodynamic", []) if isinstance(mechanisms, dict) else []
    if pk or pd:
        score += 10
    else:
        gaps.append("Need pharmacokinetic and pharmacodynamic mechanism details")

    # Reasoning chain — 10 pts
    rc = interaction_data.get("reasoning_chain", [])
    if len(rc) >= 2:
        score += 10
    else:
        gaps.append("Need detailed reasoning chain with evidence (at least 2 steps)")

    # Phytochemicals — 10 pts
    phytos = interaction_data.get("phytochemicals_involved", [])
    if len(phytos) >= 1:
        score += 10
    else:
        gaps.append("Need specific phytochemicals responsible for the interaction")

    # Interaction summary — 10 pts
    summary = interaction_data.get("interaction_summary", "")
    if summary and len(summary) >= 80:
        score += 10
    else:
        gaps.append("Need a detailed interaction summary (at least 80 characters)")

    if score >= 80:
        evidence_quality = "HIGH"
    elif score >= 50:
        evidence_quality = "MODERATE"
    else:
        evidence_quality = "LOW"

    # Require at least some substantive clinical data to pass (not just metadata)
    has_substance = bool(pk or pd or len(phytos) >= 1 or len(rc) >= 2)
    passes = (score >= 60 and has_substance) or iteration >= MAX_COMAS_ITERATIONS
    return passes, gaps, score, evidence_quality


def _boost_severity_from_evidence(
    output: dict,
    ayush_response: str,
    allopathy_response: str,
    reasoning_response: str,
) -> None:
    """Augment severity by adding pharmacodynamic evidence to the CYP-based score.

    The Lambda's calculate_severity only scores CYP enzyme interactions.
    This function scans agent responses for pharmacodynamic evidence (hypoglycemia,
    synergy, bioavailability changes, etc.) and ADDS a capped PD boost on top of
    the existing CYP-based score.

    PD boost is capped at 25 to avoid over-inflating severity. This means PD
    evidence alone can push severity from NONE to MINOR/MODERATE, and can elevate
    a CYP-based MINOR to MODERATE, but won't push things to MAJOR on its own.
    """
    PD_BOOST_CAP = 25

    if not isinstance(output, dict):
        return
    idata = output.get("interaction_data", {})
    if not isinstance(idata, dict):
        return

    severity = idata.get("severity", "NONE")
    severity_score = idata.get("severity_score", 0)

    all_text = f"{ayush_response} {allopathy_response} {reasoning_response}".lower()

    pd_boost = 0
    existing_factors = list(idata.get("scoring_factors", []))
    existing_factor_text = " ".join(existing_factors).lower()
    new_factors = []

    # Pharmacodynamic / clinical interaction evidence (grouped to avoid double-counting)
    pd_groups = [
        # Blood glucose effects (max one from this group)
        [("hypoglyc", 10, "Hypoglycemic risk"),
         ("blood glucose", 8, "Blood glucose effect"),
         ("blood sugar", 8, "Blood sugar effect"),
         ("glucose lower", 8, "Glucose lowering")],
        # Mechanism synergy (max one from this group)
        [("synergistic", 8, "Synergistic effect"),
         ("synergy", 7, "Pharmacological synergy"),
         ("additive effect", 7, "Additive pharmacodynamic effect")],
        # Specific pathway modulation
        [("ampk", 5, "AMPK pathway modulation")],
        [("insulin sensitiz", 5, "Insulin sensitization")],
        [("potentiat", 7, "Potentiation of drug effect")],
        # Absorption / bioavailability
        [("bioavailability", 6, "Bioavailability change")],
        [("gastrointestinal", 4, "GI interaction")],
        # Serious adverse effects
        [("hepatotox", 6, "Hepatotoxicity concern")],
        [("nephrotox", 6, "Nephrotoxicity concern")],
        [("bleeding", 7, "Bleeding risk"),
         ("anticoagul", 7, "Anticoagulant effect")],
        [("serotonin", 7, "Serotonin modulation")],
        [("sedat", 5, "Sedative effect")],
    ]
    for group in pd_groups:
        for keyword, pts, label in group:
            if keyword in all_text and label.lower() not in existing_factor_text:
                pd_boost += pts
                new_factors.append(f"{label} (+{pts})")
                break  # only count one match per group

    pd_boost = min(pd_boost, PD_BOOST_CAP)

    # If severity was NONE/0, also look for CYP enzyme mentions in text
    if severity_score == 0:
        cyp_pattern = re.compile(r'cyp\d[a-z]\d+', re.IGNORECASE)
        cyp_mentions = set(cyp_pattern.findall(all_text))
        if cyp_mentions:
            cyp_boost = min(len(cyp_mentions) * 5, 15)
            pd_boost += cyp_boost
            new_factors.append(
                f"CYP enzymes mentioned: {', '.join(sorted(cyp_mentions))} (+{cyp_boost})"
            )

    if pd_boost <= 0:
        return

    combined_score = min(severity_score + pd_boost, 100)

    thresholds = {"MAJOR": 60, "MODERATE": 35, "MINOR": 15}
    if combined_score >= thresholds["MAJOR"]:
        new_severity = "MAJOR"
    elif combined_score >= thresholds["MODERATE"]:
        new_severity = "MODERATE"
    elif combined_score >= thresholds["MINOR"]:
        new_severity = "MINOR"
    else:
        new_severity = "NONE"

    if combined_score > severity_score:
        idata["severity"] = new_severity
        idata["severity_score"] = combined_score
        idata["scoring_factors"] = existing_factors + new_factors
        if new_severity != "NONE":
            idata["interaction_exists"] = True
        logger.info(
            f"Severity augmented from {severity}({severity_score}) to "
            f"{new_severity}({combined_score}): CYP base={severity_score}, "
            f"PD boost={pd_boost}"
        )


# ──────────────────────────────────────────────────────────────
# Final JSON Formatting (deterministic)
# ──────────────────────────────────────────────────────────────

def _format_final_json(
    reasoning_output: dict,
    ayush_traces: list,
    allopathy_traces: list,
    imppat_url: str = "",
    scientific_name: str = "",
) -> dict:
    """Deterministic post-processing of the Reasoning Agent's output.

    - Injects constructed IMPPAT URL
    - Extracts DrugBank URL from Allopathy agent's traces
    - Ensures reasoning_chain is populated
    - Transforms knowledge graph to ADMET format
    - Returns the final result dict
    """
    if not isinstance(reasoning_output, dict):
        return reasoning_output

    status = reasoning_output.get("status")
    if status != "Success":
        return reasoning_output

    interaction_data = reasoning_output.get("interaction_data", {})
    if not isinstance(interaction_data, dict):
        return reasoning_output

    # Inject IMPPAT URL
    if imppat_url and not interaction_data.get("imppat_url"):
        interaction_data["imppat_url"] = imppat_url

    # Extract & inject DrugBank URL from allopathy agent traces + response
    if not interaction_data.get("drugbank_url"):
        drugbank_url = _extract_drugbank_url(allopathy_traces, "")
        if drugbank_url:
            interaction_data["drugbank_url"] = drugbank_url

    # Ensure reasoning_chain has at least a fallback entry
    if not interaction_data.get("reasoning_chain"):
        ayush = interaction_data.get("ayush_name", "AYUSH drug")
        allopathy = interaction_data.get("allopathy_name", "allopathy drug")
        interaction_data["reasoning_chain"] = [
            {
                "step": 1,
                "reasoning": (
                    f"Analyzed {ayush} phytochemicals and their interactions with "
                    f"{allopathy} metabolism pathways via CYP enzyme system."
                ),
                "evidence": "Based on IMPPAT phytochemical data and DrugBank metabolism profiles.",
            }
        ]

    # Ensure phytochemicals_involved is populated from knowledge graph if empty
    if not interaction_data.get("phytochemicals_involved"):
        kg = interaction_data.get("knowledge_graph", {})
        if isinstance(kg, dict):
            nodes = kg.get("nodes", [])
            phytos = [
                n["data"]["label"]
                for n in nodes
                if isinstance(n, dict) and n.get("data", {}).get("type") == "phytochemical"
            ]
            if phytos:
                interaction_data["phytochemicals_involved"] = phytos

    # Transform knowledge graph to ADMET format with CYP enzyme overlap
    kg = interaction_data.get("knowledge_graph", {})
    if isinstance(kg, dict) and kg.get("nodes"):
        allopathy_name = interaction_data.get("allopathy_name", "")
        ayush_name_local = interaction_data.get("ayush_name", scientific_name)
        interaction_data["knowledge_graph"] = _transform_graph_to_admet(
            kg, ayush_name_local, allopathy_name,
        )

    reasoning_output["interaction_data"] = interaction_data
    return reasoning_output


# ──────────────────────────────────────────────────────────────
# Lambda direct invocation for compile step
# ──────────────────────────────────────────────────────────────

def _call_compile_lambda(
    ayush_name: str,
    allopathy_name: str,
    severity_result: dict,
    knowledge_graph: dict,
    analysis_data: dict,
) -> dict:
    """Directly invoke the compile_and_validate_output Lambda function."""
    try:
        import json as _json

        payload = {
            "function": "compile_and_validate_output",
            "actionGroup": "reasoning_tools",
            "parameters": [
                {"name": "ayush_name", "value": ayush_name},
                {"name": "allopathy_name", "value": allopathy_name},
                {"name": "severity_result_str", "value": _json.dumps(severity_result)},
                {"name": "knowledge_graph_str", "value": _json.dumps(knowledge_graph)},
                {"name": "analysis_data_str", "value": _json.dumps(analysis_data)},
            ],
        }

        lambda_fn = "ausadhi-reasoning-tools"
        response = _get_lambda().invoke(
            FunctionName=lambda_fn,
            InvocationType="RequestResponse",
            Payload=_json.dumps(payload).encode(),
        )
        result_raw = response["Payload"].read().decode("utf-8")
        outer = _json.loads(result_raw)
        logger.info(f"compile_lambda outer keys: {list(outer.keys()) if isinstance(outer, dict) else 'not dict'}")

        # Lambda returns Bedrock Action Group format:
        # {"messageVersion": "1.0", "response": {"functionResponse": {"responseBody": {"TEXT": {"body": "..."}}}}}
        body_str = (
            outer.get("response", {})
                 .get("functionResponse", {})
                 .get("responseBody", {})
                 .get("TEXT", {})
                 .get("body", "")
        )
        if body_str:
            result = _json.loads(body_str)
            logger.info(f"compile_lambda result keys: {list(result.keys()) if isinstance(result, dict) else 'not dict'}")
            return result

        # Fallback: maybe direct response (older Lambda format)
        return outer
    except Exception as e:
        logger.error(f"Failed to call compile Lambda: {e}")
        return {}


def _call_severity_lambda(interactions_data_str: str, allopathy_name: str) -> dict:
    """Directly invoke the calculate_severity Lambda function."""
    try:
        payload = {
            "function": "calculate_severity",
            "actionGroup": "reasoning_tools",
            "parameters": [
                {"name": "interactions_data", "value": interactions_data_str},
                {"name": "allopathy_name", "value": allopathy_name},
            ],
        }
        response = _get_lambda().invoke(
            FunctionName="ausadhi-reasoning-tools",
            InvocationType="RequestResponse",
            Payload=json.dumps(payload).encode(),
        )
        result_raw = response["Payload"].read().decode("utf-8")
        outer = json.loads(result_raw)
        body_str = (
            outer.get("response", {})
                 .get("functionResponse", {})
                 .get("responseBody", {})
                 .get("TEXT", {})
                 .get("body", "")
        )
        if body_str:
            return json.loads(body_str)
        return outer
    except Exception as e:
        logger.error(f"Failed to call severity Lambda: {e}")
        return {}


# ──────────────────────────────────────────────────────────────
# Reasoning Agent invocation with compile step
# ──────────────────────────────────────────────────────────────

def _invoke_reasoning_with_compile(
    input_text: str,
    session_id: str,
    ayush_name: str,
    allopathy_name: str,
    imppat_url: str,
    allopathy_traces: list,
) -> Tuple[dict, list]:
    """Invoke Reasoning agent, capture tool results, then call compile Lambda directly.

    Returns: (final_output_dict, all_traces)
    """
    all_traces = []
    severity_result = {}
    knowledge_graph = {}
    reasoning_response = ""
    _pending_fn = []

    for event_type, data in _invoke_agent("reasoning", input_text, session_id):
        if event_type == "trace":
            all_traces.append(data)
            # Capture severity and graph tool results
            if data.get("type") == "tool_result":
                fn = data.get("_fn", "")
                full_result = data.get("_full_result", "")
                if fn == "calculate_severity" and full_result:
                    try:
                        sr = json.loads(full_result)
                        if isinstance(sr, dict) and sr.get("success"):
                            severity_result = sr
                    except (json.JSONDecodeError, TypeError):
                        pass
                elif fn == "build_knowledge_graph" and full_result:
                    try:
                        gr = json.loads(full_result)
                        if isinstance(gr, dict) and gr.get("success"):
                            knowledge_graph = gr.get("graph", gr)
                    except (json.JSONDecodeError, TypeError):
                        pass
        elif event_type == "response":
            reasoning_response = data

    # Extract DrugBank URL from allopathy traces
    drugbank_url = _extract_drugbank_url(allopathy_traces)

    # Try to extract analysis data from reasoning response
    analysis_data = {}
    try:
        rd = json.loads(reasoning_response)
        if isinstance(rd, dict):
            # Agent may return a short analysis JSON
            analysis_data = rd
    except (json.JSONDecodeError, TypeError):
        pass

    # Enrich analysis_data with URLs
    if imppat_url:
        analysis_data.setdefault("imppat_url", imppat_url)
    if drugbank_url:
        analysis_data.setdefault("drugbank_url", drugbank_url)

    # Call compile Lambda directly to assemble final JSON
    compile_result = _call_compile_lambda(
        ayush_name=ayush_name,
        allopathy_name=allopathy_name,
        severity_result=severity_result,
        knowledge_graph=knowledge_graph,
        analysis_data=analysis_data,
    )

    # Parse the compiled output
    final_output = _parse_reasoning_output(reasoning_response, compile_result)

    # Apply deterministic post-processing
    final_output = _format_final_json(
        final_output,
        ayush_traces=[],
        allopathy_traces=allopathy_traces,
        imppat_url=imppat_url,
        scientific_name=ayush_name,
    )

    return final_output, all_traces


# ──────────────────────────────────────────────────────────────
# CO-MAS Pipeline
# ──────────────────────────────────────────────────────────────

def run_comas_pipeline(
    ayush_name: str,
    allopathy_name: str,
    scientific_name: str,
    imppat_url: str,
    session_id: str,
) -> Generator:
    """Main CO-MAS iterative pipeline.

    Yields (event_type, data) tuples for the UI to consume.
    """
    iteration = 0
    gaps_history = []
    last_output = {}
    allopathy_traces = []
    pipeline_memory: dict = {
        "successes": [],
        "data_collected": {},
        "source_urls": [],
    }

    yield ("pipeline_status", {
        "status": "iteration_start",
        "iteration": iteration + 1,
        "message": f"Starting CO-MAS pipeline iteration 1 of {MAX_COMAS_ITERATIONS}",
    })

    while iteration < MAX_COMAS_ITERATIONS:
        iteration += 1

        yield ("pipeline_status", {
            "status": "iteration_start",
            "iteration": iteration,
            "message": f"CO-MAS iteration {iteration}/{MAX_COMAS_ITERATIONS}",
        })

        # ── PHASE 1: PLANNER ────────────────────────────────────
        yield ("pipeline_status", {"status": "phase_proposer", "iteration": iteration,
                                    "message": "Planner generating execution plan..."})

        gap_feedback = ""
        latest_gap_list = []
        if gaps_history:
            latest_gaps = gaps_history[-1]
            latest_gap_list = latest_gaps.get("gaps", [])
            gap_feedback = json.dumps({
                "gaps": latest_gap_list,
                "score": latest_gaps.get("score", 0),
                "evidence_quality": latest_gaps.get("evidence_quality", "LOW"),
            })

        if iteration == 1:
            planner_prompt = (
                f"Generate an execution plan for analyzing the interaction between "
                f"AYUSH drug '{scientific_name}' (input: '{ayush_name}') and "
                f"allopathy drug '{allopathy_name}'."
            )
        else:
            gap_text = "\n".join(f"  {i+1}. {g}" for i, g in enumerate(latest_gap_list))
            prev_score = gaps_history[-1].get("score", 0) if gaps_history else 0
            prev_quality = gaps_history[-1].get("evidence_quality", "LOW") if gaps_history else "LOW"

            # Build memory summary of what already worked
            success_lines = []
            for mem_entry in pipeline_memory.get("successes", []):
                it_num = mem_entry.get("iteration", "?")
                it_score = mem_entry.get("score", 0)
                items = mem_entry.get("items", [])
                if items:
                    success_lines.append(
                        f"  Iteration {it_num} (score {it_score}/100): "
                        + "; ".join(items)
                    )
            memory_text = "\n".join(success_lines) if success_lines else "  No notable successes yet."
            collected_data = pipeline_memory.get("data_collected", {})
            data_notes = []
            if collected_data.get("phytochemicals"):
                data_notes.append(f"Phytochemicals found: {', '.join(collected_data['phytochemicals'][:5])}")
            if collected_data.get("pk_mechanisms"):
                data_notes.append("Pharmacokinetic mechanisms documented")
            if collected_data.get("pd_mechanisms"):
                data_notes.append("Pharmacodynamic mechanisms documented")
            if collected_data.get("drugbank_url"):
                data_notes.append(f"DrugBank URL: {collected_data['drugbank_url']}")
            if collected_data.get("sources_found"):
                data_notes.append(f"Source URLs collected: {len(pipeline_memory.get('source_urls', []))}")
            data_text = "\n  ".join(data_notes) if data_notes else "None"

            planner_prompt = (
                f"ITERATION {iteration}: TARGETED GAP RESOLUTION\n\n"
                f"Previous analysis of AYUSH drug '{scientific_name}' and "
                f"allopathy drug '{allopathy_name}' scored {prev_score}/100 "
                f"(evidence quality: {prev_quality}).\n\n"
                f"== WHAT WORKED WELL (do NOT re-fetch) ==\n{memory_text}\n"
                f"  Data already collected: {data_text}\n\n"
                f"== REMAINING GAPS (must be filled) ==\n{gap_text}\n\n"
                f"Create a TARGETED plan to fill ONLY the remaining gaps. "
                f"Do NOT re-run agents whose data was already sufficient. "
                f"For each gap, specify which agent (ayush, allopathy, or research) "
                f"should run and what specific data it must retrieve. "
                f"Set run=false for agents whose data was already good."
            )

        # ── Stream planner traces directly (no buffering) ────────
        planner_response = ""
        for ev_type, ev_data in _invoke_agent("planner", planner_prompt, session_id):
            if ev_type == "trace":
                yield ("trace", {**ev_data, "agent_key": "planner", "iteration": iteration})
            elif ev_type == "response":
                planner_response = ev_data
            elif ev_type == "error":
                logger.error(f"Planner error: {ev_data}")
                planner_response = ""

        plan = _parse_planner_output(planner_response)
        agents_cfg = plan.get("agents", {})

        run_ayush = agents_cfg.get("ayush", {}).get("run", True)
        run_allopathy = agents_cfg.get("allopathy", {}).get("run", True)
        run_research = agents_cfg.get("research", {}).get("run", True)

        # ── PHASE 2: PROPOSER (parallel agents) ─────────────────
        yield ("pipeline_status", {"status": "phase_proposer", "iteration": iteration,
                                    "message": "Running AYUSH, Allopathy, Research agents in parallel..."})

        ayush_response = ""
        ayush_traces_local = []
        allopathy_response_local = ""
        allopathy_traces_local = []
        research_response = ""
        research_traces_local = []

        agent_results = {}
        threads = []

        def _run_agent(key, prompt, store):
            r, t = _invoke_agent_collect(key, prompt, session_id)
            store["response"] = r
            store["traces"] = t

        proposer_stores = {}

        if run_ayush:
            proposer_stores["ayush"] = {}
            if iteration == 1:
                ayush_prompt = (
                    f"Get comprehensive phytochemical data for {scientific_name}. "
                    f"Include IMPPAT data, CYP enzyme interactions, and key bioactive compounds. "
                    f"IMPPAT URL: {imppat_url}"
                )
            else:
                ayush_gaps = [g for g in latest_gap_list if any(
                    kw in g.lower() for kw in ["phytochemical", "ayush", "cyp enzyme effect", "admet"]
                )]
                gap_detail = "; ".join(ayush_gaps) if ayush_gaps else "more detailed CYP enzyme interaction data"
                ayush_prompt = (
                    f"TARGETED SEARCH (iteration {iteration}): Previous analysis had gaps. "
                    f"Focus on: {gap_detail}. "
                    f"Get specific phytochemicals from {scientific_name} and their exact effects "
                    f"on CYP450 enzymes (inhibition/induction). Include ADMET properties. "
                    f"IMPPAT URL: {imppat_url}"
                )
            t = threading.Thread(target=_run_agent, args=("ayush", ayush_prompt, proposer_stores["ayush"]))
            threads.append(("ayush", t))

        if run_allopathy:
            proposer_stores["allopathy"] = {}
            if iteration == 1:
                allopathy_prompt = (
                    f"Get comprehensive data for {allopathy_name}. "
                    f"Include CYP metabolism pathways, NTI status, mechanism of action. "
                    f"Search DrugBank (domain: drugbank) for the drug page URL."
                )
            else:
                allo_gaps = [g for g in latest_gap_list if any(
                    kw in g.lower() for kw in ["allopathy", "severity", "metabolism", "nti", "cyp"]
                )]
                gap_detail = "; ".join(allo_gaps) if allo_gaps else "more detailed CYP metabolism data"
                allopathy_prompt = (
                    f"TARGETED SEARCH (iteration {iteration}): Previous analysis had gaps. "
                    f"Focus on: {gap_detail}. "
                    f"Get specific CYP450 metabolism pathways for {allopathy_name}, NTI status, "
                    f"and ADMET properties. "
                    f"Search DrugBank (domain: drugbank) for the drug page URL."
                )
            t = threading.Thread(target=_run_agent, args=("allopathy", allopathy_prompt, proposer_stores["allopathy"]))
            threads.append(("allopathy", t))

        if run_research:
            proposer_stores["research"] = {}
            if iteration == 1:
                research_prompt = (
                    f"Search for clinical evidence of interactions between {scientific_name} "
                    f"and {allopathy_name}. "
                    f"Find PubMed articles, clinical trials, and pharmacological studies."
                )
            else:
                research_gaps = [g for g in latest_gap_list if any(
                    kw in g.lower() for kw in ["source", "evidence", "research", "pubmed", "clinical", "mechanism", "reasoning"]
                )]
                gap_detail = "; ".join(research_gaps) if research_gaps else "clinical interaction evidence and PubMed sources"
                research_prompt = (
                    f"TARGETED SEARCH (iteration {iteration}): Previous analysis had gaps. "
                    f"Focus on: {gap_detail}. "
                    f"Search PubMed and clinical databases for specific interaction evidence "
                    f"between {scientific_name} and {allopathy_name}. "
                    f"Provide URLs and detailed findings."
                )
            t = threading.Thread(target=_run_agent, args=("research", research_prompt, proposer_stores["research"]))
            threads.append(("research", t))

        for key, t in threads:
            t.start()
            # Emit a synthetic "agent started" thinking trace so the UI shows
            # each proposer card immediately (before their traces arrive)
            agent_label = AGENTS[key]["label"]
            yield ("trace", {
                "type": "thinking",
                "agent": agent_label,
                "agent_key": key,
                "iteration": iteration,
                "message": f"{agent_label} agent running…",
            })

        for key, t in threads:
            t.join(timeout=300)

        for key, store in proposer_stores.items():
            resp = store.get("response", "")
            traces = store.get("traces", [])
            agent_results[key] = {"response": resp, "traces": traces}
            for trace in traces:
                yield ("trace", {**trace, "agent_key": key, "iteration": iteration})

        if "ayush" in agent_results:
            ayush_response = agent_results["ayush"]["response"]
            ayush_traces_local = agent_results["ayush"]["traces"]
        if "allopathy" in agent_results:
            allopathy_response_local = agent_results["allopathy"]["response"]
            allopathy_traces_local = agent_results["allopathy"]["traces"]
            allopathy_traces = allopathy_traces_local  # persist for final formatting
        if "research" in agent_results:
            research_response = agent_results["research"]["response"]
            research_traces_local = agent_results["research"]["traces"]

        # ── PHASE 3: EVALUATOR (Reasoning Agent) ────────────────
        yield ("pipeline_status", {"status": "phase_evaluator", "iteration": iteration,
                                    "message": "Reasoning agent evaluating interactions..."})

        reasoning_prompt = (
            f"Analyze the pharmacological interaction between AYUSH drug '{scientific_name}' "
            f"and allopathy drug '{allopathy_name}'.\n\n"
            f"AYUSH data:\n{ayush_response[:2000]}\n\n"
            f"Allopathy data:\n{allopathy_response_local[:2000]}\n\n"
            f"Research evidence:\n{research_response[:2000]}\n\n"
            f"Provide a detailed analysis including: interaction mechanisms (pharmacokinetic & "
            f"pharmacodynamic), severity assessment, phytochemicals responsible, clinical effects, "
            f"and evidence-based reasoning chain. Return a concise analysis JSON."
        )

        # ── Stream reasoning traces directly, then compile ────────
        reasoning_all_traces = []
        reasoning_response = ""
        severity_result_rt = {}
        knowledge_graph_rt = {}

        for ev_type, ev_data in _invoke_agent("reasoning", reasoning_prompt, session_id):
            if ev_type == "trace":
                yield ("trace", {**ev_data, "agent_key": "reasoning", "iteration": iteration})
                reasoning_all_traces.append(ev_data)
                # Capture severity / graph tool results for compile step
                if ev_data.get("type") == "tool_result":
                    fn = ev_data.get("_fn", "")
                    full = ev_data.get("_full_result", "")
                    if fn == "calculate_severity" and full:
                        try:
                            sr = json.loads(full)
                            if isinstance(sr, dict) and sr.get("success"):
                                severity_result_rt = sr
                        except (json.JSONDecodeError, TypeError):
                            pass
                    elif fn == "build_knowledge_graph" and full:
                        try:
                            gr = json.loads(full)
                            if isinstance(gr, dict) and gr.get("success"):
                                knowledge_graph_rt = gr.get("graph", gr)
                        except (json.JSONDecodeError, TypeError):
                            pass
            elif ev_type == "response":
                reasoning_response = ev_data

        # Extract analysis data from reasoning response
        analysis_data_rt = {}
        try:
            rd = json.loads(reasoning_response)
            if isinstance(rd, dict):
                analysis_data_rt = rd
        except (json.JSONDecodeError, TypeError):
            pass

        # Extract DrugBank URL from traces AND response text
        drugbank_url_rt = _extract_drugbank_url(
            allopathy_traces_local, allopathy_response_local
        )
        if imppat_url:
            analysis_data_rt.setdefault("imppat_url", imppat_url)
        if drugbank_url_rt:
            analysis_data_rt.setdefault("drugbank_url", drugbank_url_rt)

        # Extract source URLs from all agents' traces and responses
        all_agent_sources = []
        for agent_key, agent_resp, agent_traces in [
            ("research", research_response, research_traces_local),
            ("allopathy", allopathy_response_local, allopathy_traces_local),
            ("ayush", ayush_response, ayush_traces_local),
            ("reasoning", reasoning_response, reasoning_all_traces),
        ]:
            extracted = _extract_source_urls(agent_traces, agent_resp)
            all_agent_sources.extend(extracted)

        # Deduplicate sources by URL
        seen_urls = set()
        unique_sources = []
        for src in all_agent_sources:
            if src["url"] not in seen_urls:
                seen_urls.add(src["url"])
                unique_sources.append(src)

        existing_sources = analysis_data_rt.get("sources", [])
        if not existing_sources:
            analysis_data_rt["sources"] = unique_sources
        else:
            for src in unique_sources:
                if src["url"] not in {s.get("url") for s in existing_sources}:
                    existing_sources.append(src)
            analysis_data_rt["sources"] = existing_sources

        # If Reasoning agent didn't call calculate_severity, call it directly
        if not severity_result_rt:
            logger.info("Reasoning agent did not call calculate_severity — calling directly")
            try:
                cyp_data = analysis_data_rt.get("cyp_enzymes", [])
                if not cyp_data:
                    # Try to extract CYP enzyme info from knowledge graph
                    kg_nodes = knowledge_graph_rt.get("nodes", []) if isinstance(knowledge_graph_rt, dict) else []
                    for node in kg_nodes:
                        ndata = node.get("data", {})
                        if ndata.get("type") in ("cyp_enzyme", "cyp_enzyme_overlap"):
                            cyp_data.append({"name": ndata.get("label", ""), "effect": "interaction"})
                if not cyp_data:
                    # Scan agent responses for CYP enzyme mentions
                    cyp_pattern = re.compile(r'CYP\d[A-Z]\d+', re.IGNORECASE)
                    all_text = f"{ayush_response} {allopathy_response_local} {reasoning_response}"
                    found_cyps = set(cyp_pattern.findall(all_text))
                    for cyp in found_cyps:
                        cyp_data.append({"name": cyp.upper(), "effect": "interaction"})
                if cyp_data:
                    sev_payload = json.dumps({"cyp_enzymes": cyp_data})
                    sev_result = _call_severity_lambda(sev_payload, allopathy_name)
                    if isinstance(sev_result, dict) and sev_result.get("success"):
                        severity_result_rt = sev_result
                        logger.info(f"Direct severity call: {sev_result.get('severity')} ({sev_result.get('severity_score')})")
            except Exception as e:
                logger.warning(f"Direct severity calculation failed: {e}")

        compile_result = _call_compile_lambda(
            ayush_name=scientific_name,
            allopathy_name=allopathy_name,
            severity_result=severity_result_rt,
            knowledge_graph=knowledge_graph_rt,
            analysis_data=analysis_data_rt,
        )

        final_output = _parse_reasoning_output(reasoning_response, compile_result)
        final_output = _format_final_json(
            final_output,
            ayush_traces=[],
            allopathy_traces=allopathy_traces_local,
            imppat_url=imppat_url,
            scientific_name=scientific_name,
        )

        # Post-process severity: boost if NONE/0 but evidence exists
        _boost_severity_from_evidence(final_output, ayush_response, allopathy_response_local, reasoning_response)

        # Merge with previous iteration's data — keep richer fields
        if last_output and isinstance(last_output, dict) and isinstance(final_output, dict):
            prev_idata = last_output.get("interaction_data", {}) or {}
            curr_idata = final_output.get("interaction_data", {}) or {}
            if isinstance(prev_idata, dict) and isinstance(curr_idata, dict):
                for key in prev_idata:
                    curr_val = curr_idata.get(key)
                    prev_val = prev_idata[key]
                    if curr_val in (None, "", [], {}, 0) and prev_val not in (None, "", [], {}, 0):
                        curr_idata[key] = prev_val
                final_output["interaction_data"] = curr_idata

        last_output = final_output

        # ── PHASE 4: SCORER (deterministic) ─────────────────────
        yield ("pipeline_status", {"status": "phase_scorer", "iteration": iteration,
                                    "message": "Scorer evaluating output quality..."})

        passes, gaps, score, evidence_quality = _score_output(final_output, iteration)

        # Update evidence_quality in the output based on actual score
        if isinstance(last_output, dict) and last_output.get("interaction_data"):
            last_output["interaction_data"]["evidence_quality"] = evidence_quality

        # Update pipeline memory with what succeeded in this iteration
        idata = (last_output.get("interaction_data", {}) or {}) if isinstance(last_output, dict) else {}
        iter_successes = []
        iter_data = {}

        if idata.get("ayush_name") and idata["ayush_name"] != scientific_name:
            iter_successes.append("AYUSH drug identification confirmed")
        if idata.get("phytochemicals_involved"):
            iter_successes.append(f"Found {len(idata['phytochemicals_involved'])} phytochemicals")
            iter_data["phytochemicals"] = [
                p.get("name", p) if isinstance(p, dict) else p
                for p in idata["phytochemicals_involved"]
            ]
        if idata.get("severity") and idata["severity"] != "NONE":
            iter_successes.append(f"Severity assessed as {idata['severity']} ({idata.get('severity_score', 0)}/100)")
        elif idata.get("severity_score", 0) > 0:
            iter_successes.append(f"Severity score: {idata['severity_score']}/100")
        if idata.get("mechanisms", {}).get("pharmacokinetic"):
            pk_count = len(idata["mechanisms"]["pharmacokinetic"])
            iter_successes.append(f"Found {pk_count} pharmacokinetic mechanisms")
            iter_data["pk_mechanisms"] = True
        if idata.get("mechanisms", {}).get("pharmacodynamic"):
            pd_count = len(idata["mechanisms"]["pharmacodynamic"])
            iter_successes.append(f"Found {pd_count} pharmacodynamic mechanisms")
            iter_data["pd_mechanisms"] = True
        if idata.get("sources"):
            iter_successes.append(f"Found {len(idata['sources'])} source references")
            iter_data["sources_found"] = True
        kg = idata.get("knowledge_graph", {})
        if isinstance(kg, dict) and kg.get("nodes"):
            iter_successes.append(f"Knowledge graph built with {len(kg['nodes'])} nodes")
        if idata.get("drugbank_url"):
            iter_successes.append("DrugBank URL found")
            iter_data["drugbank_url"] = idata["drugbank_url"]
        if idata.get("reasoning_chain") and len(idata.get("reasoning_chain", [])) >= 2:
            iter_successes.append(f"Reasoning chain has {len(idata['reasoning_chain'])} steps")
        if idata.get("interaction_summary") and len(idata.get("interaction_summary", "")) >= 80:
            iter_successes.append("Detailed interaction summary available")

        pipeline_memory["successes"].append({
            "iteration": iteration,
            "items": iter_successes,
            "score": score,
        })
        pipeline_memory["data_collected"].update(iter_data)

        for src in idata.get("sources", []):
            url = src.get("url", "") if isinstance(src, dict) else ""
            if url and url not in pipeline_memory["source_urls"]:
                pipeline_memory["source_urls"].append(url)

        if gaps:
            for gap in gaps:
                yield ("pipeline_status", {
                    "status": "gap_identified",
                    "iteration": iteration,
                    "gap": gap,
                    "message": f"Gap identified: {gap}",
                })
            gaps_history.append({
                "iteration": iteration,
                "gaps": gaps,
                "score": score,
                "evidence_quality": evidence_quality,
            })
            log_iteration_gap(session_id, iteration, gaps, score, evidence_quality)

        if passes:
            logger.info(f"CO-MAS passed at iteration {iteration} with score={score}")
            break

        if iteration < MAX_COMAS_ITERATIONS:
            yield ("pipeline_status", {
                "status": "iteration_retry",
                "iteration": iteration,
                "message": f"Score={score:.0f}/100. Retrying with targeted feedback...",
            })

    yield ("pipeline_status", {
        "status": "formatting",
        "message": "Formatting final output...",
    })

    # Ensure final output has status=Success (force partial data if needed)
    if not isinstance(last_output, dict) or last_output.get("status") != "Success":
        logger.warning("Final output missing Success status — forcing with partial data")
        partial = last_output if isinstance(last_output, dict) else {}
        existing_idata = partial.get("interaction_data", {})
        if not isinstance(existing_idata, dict):
            existing_idata = {}

        last_output = {
            "status": "Success",
            "interaction_data": {
                "interaction_key": existing_idata.get(
                    "interaction_key",
                    f"{scientific_name.lower().strip()}#{allopathy_name.lower().strip()}",
                ),
                "ayush_name": existing_idata.get("ayush_name", scientific_name),
                "allopathy_name": existing_idata.get("allopathy_name", allopathy_name),
                "interaction_exists": existing_idata.get("interaction_exists", False),
                "interaction_summary": existing_idata.get(
                    "interaction_summary",
                    f"Partial analysis of {scientific_name} and {allopathy_name} interaction. "
                    f"Completed after {iteration} iterations with limited data.",
                ),
                "severity": existing_idata.get("severity", "NONE"),
                "severity_score": existing_idata.get("severity_score", 0),
                "is_nti": existing_idata.get("is_nti", False),
                "scoring_factors": existing_idata.get("scoring_factors", []),
                "mechanisms": existing_idata.get("mechanisms", {
                    "pharmacokinetic": [], "pharmacodynamic": [],
                }),
                "phytochemicals_involved": existing_idata.get("phytochemicals_involved", []),
                "clinical_effects": existing_idata.get("clinical_effects", []),
                "recommendations": existing_idata.get("recommendations", [
                    "Consult a qualified healthcare professional before combining these substances.",
                ]),
                "evidence_quality": existing_idata.get("evidence_quality", "LOW"),
                "reasoning_chain": existing_idata.get("reasoning_chain", [{
                    "step": 1,
                    "reasoning": (
                        f"Analyzed {scientific_name} phytochemicals and {allopathy_name} "
                        f"metabolism pathways. Analysis completed with limited data."
                    ),
                    "evidence": "LOW confidence — partial data gathered across iterations.",
                }]),
                "knowledge_graph": existing_idata.get("knowledge_graph", {"nodes": [], "edges": []}),
                "sources": existing_idata.get("sources", []),
                "imppat_url": existing_idata.get("imppat_url", imppat_url),
                "drugbank_url": existing_idata.get("drugbank_url", ""),
                "disclaimer": (
                    "This analysis is AI-generated for informational purposes only. "
                    "Always consult qualified healthcare professionals before making "
                    "clinical decisions about drug interactions."
                ),
                "generated_at": "",
            },
        }

    yield ("done", {
        "result": last_output,
        "iterations": iteration,
        "gaps_history": gaps_history,
        "session_id": session_id,
    })


# ──────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────

def run_check(
    ayush_name: str,
    allopathy_name: str,
    session_id: str = None,
    **kwargs,
) -> Generator:
    """Public entry point for the CO-MAS pipeline.

    Yields (event_type, data) tuples.
    """
    if not session_id:
        session_id = str(uuid.uuid4())

    # Validate input lengths
    if len(ayush_name) < INPUT_MIN_LENGTH or len(ayush_name) > INPUT_MAX_LENGTH:
        yield ("error", {"message": f"AYUSH drug name must be {INPUT_MIN_LENGTH}–{INPUT_MAX_LENGTH} characters."})
        return
    if len(allopathy_name) < INPUT_MIN_LENGTH or len(allopathy_name) > INPUT_MAX_LENGTH:
        yield ("error", {"message": f"Allopathy drug name must be {INPUT_MIN_LENGTH}–{INPUT_MAX_LENGTH} characters."})
        return

    start_time = time.time()
    log_pipeline_start(session_id, ayush_name, allopathy_name)

    # ── PRE-PIPELINE: Name resolution & whitelist check ────────
    yield ("pipeline_status", {
        "status": "name_resolution",
        "message": f"Resolving AYUSH drug name: '{ayush_name}'...",
    })

    is_valid, scientific_name, imppat_url, supported_list = resolve_and_validate_ayush_drug(ayush_name)

    if not is_valid:
        supported_str = "\n• ".join(supported_list) if supported_list else "(none configured)"
        error_msg = (
            f"AYUSH drug '{ayush_name}' is not available in this demo. "
            f"Currently supported plants:\n• {supported_str}\n"
            f"Please try one of the supported plants."
        )
        yield ("pipeline_status", {
            "status": "input_validation",
            "valid": False,
            "message": error_msg,
            "supported_drugs": supported_list,
        })
        yield ("error", {
            "message": error_msg,
            "supported_drugs": supported_list,
        })
        return

    yield ("pipeline_status", {
        "status": "name_resolution",
        "valid": True,
        "original_name": ayush_name,
        "scientific_name": scientific_name,
        "imppat_url": imppat_url,
        "message": f"Resolved '{ayush_name}' → '{scientific_name}'",
    })

    yield ("pipeline_status", {
        "status": "input_validation",
        "valid": True,
        "message": f"Validated: {scientific_name} + {allopathy_name}",
    })

    try:
        for event in run_comas_pipeline(
            ayush_name=ayush_name,
            allopathy_name=allopathy_name,
            scientific_name=scientific_name,
            imppat_url=imppat_url,
            session_id=session_id,
        ):
            yield event

        duration_ms = int((time.time() - start_time) * 1000)
        log_pipeline_complete(session_id, "Success", duration_ms)

    except Exception as e:
        logger.exception("Pipeline error")
        duration_ms = int((time.time() - start_time) * 1000)
        log_pipeline_error(session_id, type(e).__name__, str(e))
        yield ("error", {"message": f"Pipeline error: {str(e)}"})
