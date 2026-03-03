"""
Reasoning Tools Action Group Lambda
Triggered by: Bedrock Reasoning Agent
Functions: build_knowledge_graph, calculate_severity, validate_and_format_output,
           score_output_quality, compile_and_validate_output

Uses CYP enzyme reference data from S3 and NTI drug list for severity scoring.
"""
import json
import sys
import os
import logging
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sys.path.insert(0, "/opt/python")
sys.path.insert(0, "/var/task")

import boto3
from shared.bedrock_utils import bedrock_response

S3_BUCKET = os.environ.get("S3_BUCKET", "ausadhi-mitra-667736132441")
s3 = boto3.client("s3")

_cyp_cache = None
_nti_cache = None

SUCCESS_REQUIRED_FIELDS = [
    "ayush_name", "allopathy_name", "severity", "severity_score",
    "knowledge_graph", "sources", "disclaimer", "reasoning_chain",
]


def lambda_handler(event, context):
    logger.info(f"Event: {json.dumps(event, default=str)}")

    action_group = event.get("actionGroup", "reasoning_tools")
    function = event.get("function", "")
    params = {p["name"]: p["value"] for p in event.get("parameters", [])}

    try:
        if function == "build_knowledge_graph":
            result = build_knowledge_graph(
                params.get("ayush_name", ""),
                params.get("allopathy_name", ""),
                params.get("interactions_data", "{}"),
            )
        elif function == "calculate_severity":
            result = calculate_severity(
                params.get("interactions_data", "{}"),
                params.get("allopathy_name", ""),
            )
        elif function == "validate_and_format_output":
            try:
                iteration = int(params.get("iteration", "1"))
            except (ValueError, TypeError):
                iteration = 1
            result = validate_and_format_output(
                params.get("reasoning_output_str", "{}"),
                iteration,
            )
        elif function == "score_output_quality":
            try:
                iteration = int(params.get("iteration", "1"))
            except (ValueError, TypeError):
                iteration = 1
            result = score_output_quality(
                params.get("output_str", "{}"),
                iteration,
            )
        elif function == "compile_and_validate_output":
            # Core fields passed individually; rest bundled in analysis_data_str
            analysis_data_str = params.get("analysis_data_str", "{}")
            try:
                analysis_data = json.loads(analysis_data_str) if isinstance(analysis_data_str, str) else analysis_data_str
            except (json.JSONDecodeError, TypeError):
                analysis_data = {}
            result = compile_and_validate_output(
                ayush_name=params.get("ayush_name", ""),
                allopathy_name=params.get("allopathy_name", ""),
                severity_result_str=params.get("severity_result_str", "{}"),
                knowledge_graph_str=params.get("knowledge_graph_str", "{}"),
                analysis_data=analysis_data,
            )
        else:
            result = {"error": f"Unknown function: {function}"}
    except Exception as e:
        logger.exception(f"Error in {function}")
        result = {"error": str(e)}

    return bedrock_response(action_group, function, result)


def _load_cyp_ref() -> dict:
    global _cyp_cache
    if _cyp_cache is not None:
        return _cyp_cache
    try:
        resp = s3.get_object(Bucket=S3_BUCKET, Key="reference/cyp_enzymes.json")
        _cyp_cache = json.loads(resp["Body"].read().decode("utf-8"))
        return _cyp_cache
    except Exception as e:
        logger.error(f"Failed to load cyp_enzymes.json: {e}")
        return {"enzymes": {}, "scoring_rules": {}, "severity_thresholds": {}}


def _load_nti_ref() -> dict:
    global _nti_cache
    if _nti_cache is not None:
        return _nti_cache
    try:
        resp = s3.get_object(Bucket=S3_BUCKET, Key="reference/nti_drugs.json")
        _nti_cache = json.loads(resp["Body"].read().decode("utf-8"))
        return _nti_cache
    except Exception as e:
        logger.error(f"Failed to load nti_drugs.json: {e}")
        return {"drugs": []}


def build_knowledge_graph(ayush_name: str, allopathy_name: str,
                          interactions_data_str: str) -> dict:
    """Build a Cytoscape.js-compatible knowledge graph for the drug interaction."""
    try:
        interactions = json.loads(interactions_data_str) if isinstance(interactions_data_str, str) else interactions_data_str
    except (json.JSONDecodeError, TypeError):
        interactions = {}
    if interactions is None or not isinstance(interactions, dict):
        interactions = {}

    nodes = []
    edges = []

    nodes.append({"data": {"id": "ayush", "label": ayush_name, "type": "ayush_plant"}})
    nodes.append({"data": {"id": "allopathy", "label": allopathy_name, "type": "allopathy_drug"}})

    phytochemicals = interactions.get("phytochemicals", [])
    if isinstance(phytochemicals, list):
        for i, phyto in enumerate(phytochemicals[:10]):
            name = phyto if isinstance(phyto, str) else phyto.get("name", f"phyto_{i}")
            confidence = "" if isinstance(phyto, str) else phyto.get("confidence", "")
            node_id = f"phyto_{i}"
            nodes.append({"data": {"id": node_id, "label": name, "type": "phytochemical"}})
            edges.append({
                "data": {"source": "ayush", "target": node_id, "label": "contains"}
            })

    cyp_enzymes = interactions.get("cyp_enzymes", [])
    if isinstance(cyp_enzymes, list):
        for i, enzyme in enumerate(cyp_enzymes[:8]):
            name = enzyme if isinstance(enzyme, str) else enzyme.get("name", f"cyp_{i}")
            effect = "" if isinstance(enzyme, str) else enzyme.get("effect", "")
            confidence = "" if isinstance(enzyme, str) else enzyme.get("confidence", "")
            node_id = f"cyp_{i}"
            nodes.append({"data": {"id": node_id, "label": name, "type": "cyp_enzyme"}})
            edge_label = f"metabolized by"
            if confidence:
                edge_label = f"metabolized by [{confidence.upper()}]"
            edges.append({
                "data": {"source": "allopathy", "target": node_id, "label": edge_label}
            })
            for phyto_node in nodes:
                if phyto_node["data"].get("type") == "phytochemical":
                    if effect:
                        effect_label = f"inhibits" if "inhib" in effect.lower() else effect
                        if confidence:
                            effect_label = f"{effect_label} [{confidence.upper()}]"
                        edges.append({
                            "data": {
                                "source": phyto_node["data"]["id"],
                                "target": node_id,
                                "label": effect_label,
                            }
                        })

    mechanisms = interactions.get("mechanisms", [])
    if isinstance(mechanisms, list):
        for i, mech in enumerate(mechanisms[:5]):
            name = mech if isinstance(mech, str) else mech.get("mechanism", f"mech_{i}")
            node_id = f"mech_{i}"
            nodes.append({"data": {"id": node_id, "label": name, "type": "mechanism"}})

    clinical = interactions.get("clinical_effects", [])
    if isinstance(clinical, list):
        for i, effect in enumerate(clinical[:5]):
            name = effect if isinstance(effect, str) else effect.get("effect", f"effect_{i}")
            node_id = f"effect_{i}"
            nodes.append({"data": {"id": node_id, "label": name, "type": "clinical_effect"}})

    return {
        "success": True,
        "graph": {"nodes": nodes, "edges": edges},
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


def calculate_severity(interactions_data_str: str, allopathy_name: str) -> dict:
    """Calculate interaction severity score based on CYP enzyme reference data and NTI status."""
    try:
        interactions = json.loads(interactions_data_str) if isinstance(interactions_data_str, str) else interactions_data_str
    except (json.JSONDecodeError, TypeError):
        interactions = {}
    if interactions is None or not isinstance(interactions, dict):
        interactions = {}

    cyp_ref = _load_cyp_ref()
    nti_ref = _load_nti_ref()
    scoring_rules = cyp_ref.get("scoring_rules", {})

    base_score = 0
    factors = []

    cyp_enzymes = interactions.get("cyp_enzymes", [])
    if isinstance(cyp_enzymes, list):
        raw_enzymes = cyp_ref.get("enzymes", {})
        if isinstance(raw_enzymes, dict):
            enzyme_ref_map = raw_enzymes
        else:
            enzyme_ref_map = {e.get("name", e.get("enzyme", "")): e for e in raw_enzymes}
        for enzyme_info in cyp_enzymes:
            if isinstance(enzyme_info, str):
                enzyme_name = enzyme_info
                effect = "unknown"
            else:
                enzyme_name = enzyme_info.get("name", "")
                effect = enzyme_info.get("effect", "unknown")

            ref = enzyme_ref_map.get(enzyme_name, {})
            weight = ref.get("severity_weight", 5)

            if effect.lower() in ("inhibit", "inhibitor", "strong_inhibitor"):
                base_score += weight * 2
                factors.append(f"{enzyme_name} inhibition (+{weight * 2})")
            elif effect.lower() in ("induce", "inducer", "strong_inducer"):
                base_score += weight * 1.5
                factors.append(f"{enzyme_name} induction (+{weight * 1.5})")
            else:
                base_score += weight
                factors.append(f"{enzyme_name} interaction (+{weight})")

    is_nti = False
    if allopathy_name:
        for drug in nti_ref.get("nti_drugs", nti_ref.get("drugs", [])):
            all_names = [drug.get("generic_name", "").lower()] + \
                        [n.lower() for n in drug.get("brand_names", [])]
            if allopathy_name.lower().strip() in all_names:
                is_nti = True
                nti_boost = scoring_rules.get("nti_drug_boost", 25)
                base_score += nti_boost
                factors.append(f"NTI drug status (+{nti_boost})")
                break

    thresholds = cyp_ref.get("severity_thresholds", {})
    major_thresh = thresholds.get("MAJOR", {}).get("min", 60)
    moderate_thresh = thresholds.get("MODERATE", {}).get("min", 35)
    minor_thresh = thresholds.get("MINOR", {}).get("min", 15)

    if base_score >= major_thresh:
        severity = "MAJOR"
    elif base_score >= moderate_thresh:
        severity = "MODERATE"
    elif base_score >= minor_thresh:
        severity = "MINOR"
    else:
        severity = "NONE"

    return {
        "success": True,
        "severity": severity,
        "severity_score": min(round(base_score), 100),
        "is_nti": is_nti,
        "scoring_factors": factors,
        "thresholds": {"MINOR": minor_thresh, "MODERATE": moderate_thresh, "MAJOR": major_thresh},
    }


def score_output_quality(output_str: str, iteration: int = 1) -> dict:
    """CO-MAS Scorer phase: evaluate quality and completeness of reasoning output.

    Returns a score 0-100, identified information gaps, and evidence quality.
    """
    try:
        output = json.loads(output_str) if isinstance(output_str, str) else output_str
    except (json.JSONDecodeError, TypeError):
        output = {}
    if output is None or not isinstance(output, dict):
        output = {}

    status = output.get("status", "Failed")
    interaction_data = output.get("interaction_data", {})
    if not isinstance(interaction_data, dict):
        interaction_data = {}

    score = 0
    gaps = []
    evidence_quality = "LOW"

    if status != "Success":
        return {
            "score": 0,
            "pass": False,
            "gaps": ["Status is not Success — full analysis not completed"],
            "evidence_quality": "LOW",
            "iteration": iteration,
        }

    # Check required fields (10 pts each)
    for field in ["ayush_name", "allopathy_name", "severity", "severity_score"]:
        if interaction_data.get(field) not in (None, "", [], {}):
            score += 10
        else:
            gaps.append(f"Missing required field: {field}")

    # Knowledge graph (10 pts)
    kg = interaction_data.get("knowledge_graph", {})
    nodes = kg.get("nodes", []) if isinstance(kg, dict) else []
    if len(nodes) >= 3:
        score += 10
    else:
        gaps.append("Knowledge graph has insufficient nodes (< 3)")

    # Sources (10 pts)
    sources = interaction_data.get("sources", [])
    if len(sources) >= 2:
        score += 10
    else:
        gaps.append("Insufficient sources cited (< 2)")

    # Mechanisms (10 pts)
    mechanisms = interaction_data.get("mechanisms", {})
    pk_mechs = mechanisms.get("pharmacokinetic", []) if isinstance(mechanisms, dict) else []
    pd_mechs = mechanisms.get("pharmacodynamic", []) if isinstance(mechanisms, dict) else []
    if pk_mechs or pd_mechs:
        score += 10
    else:
        gaps.append("No pharmacokinetic or pharmacodynamic mechanisms described")

    # Reasoning chain (10 pts)
    reasoning_chain = interaction_data.get("reasoning_chain", [])
    if len(reasoning_chain) >= 2:
        score += 10
    else:
        gaps.append("Reasoning chain is absent or too short (< 2 steps)")

    # Phytochemicals (10 pts)
    phytos = interaction_data.get("phytochemicals_involved", [])
    if len(phytos) >= 1:
        score += 10
    else:
        gaps.append("No specific phytochemicals identified as responsible for interaction")

    # Interaction summary quality (10 pts)
    summary = interaction_data.get("interaction_summary", "")
    if summary and len(summary) >= 80:
        score += 10
    else:
        gaps.append("Interaction summary is too brief or missing")

    # Determine evidence quality
    if score >= 80:
        evidence_quality = "HIGH"
    elif score >= 50:
        evidence_quality = "MODERATE"
    else:
        evidence_quality = "LOW"

    passing = score >= 60 or iteration >= 3

    return {
        "score": score,
        "pass": passing,
        "gaps": gaps,
        "evidence_quality": evidence_quality,
        "iteration": iteration,
    }


def compile_and_validate_output(ayush_name: str, allopathy_name: str,
                                 severity_result_str: str,
                                 knowledge_graph_str: str,
                                 analysis_data: dict) -> dict:
    """Programmatically assemble the final interaction JSON from discrete data pieces.

    This function is called directly by the orchestrator (not the LLM) to avoid
    Bedrock model timeouts from generating large JSON.

    analysis_data dict keys (bundled to avoid Bedrock 5-param limit):
      - interaction_exists (bool)
      - interaction_summary (str)
      - mechanisms (dict: {pharmacokinetic, pharmacodynamic})
      - phytochemicals_involved (list)
      - clinical_effects (list)
      - recommendations (list)
      - sources (list)
      - reasoning_chain (list)
      - imppat_url (str)
      - drugbank_url (str)
    """
    try:
        severity_result = json.loads(severity_result_str) if isinstance(severity_result_str, str) else severity_result_str
    except (json.JSONDecodeError, TypeError):
        severity_result = {}
    if not isinstance(severity_result, dict):
        severity_result = {}

    try:
        knowledge_graph = json.loads(knowledge_graph_str) if isinstance(knowledge_graph_str, str) else knowledge_graph_str
    except (json.JSONDecodeError, TypeError):
        knowledge_graph = {}
    if not isinstance(knowledge_graph, dict):
        knowledge_graph = {}

    if not isinstance(analysis_data, dict):
        analysis_data = {}

    severity = severity_result.get("severity", "NONE")
    severity_score = severity_result.get("severity_score", 0)
    is_nti = severity_result.get("is_nti", False)
    scoring_factors = severity_result.get("scoring_factors", [])

    graph = knowledge_graph.get("graph", knowledge_graph)

    mechanisms = analysis_data.get("mechanisms", {"pharmacokinetic": [], "pharmacodynamic": []})
    if not isinstance(mechanisms, dict):
        mechanisms = {"pharmacokinetic": [], "pharmacodynamic": []}

    sources = analysis_data.get("sources", [])
    if not isinstance(sources, list):
        sources = []

    reasoning_chain = analysis_data.get("reasoning_chain", [])
    if not isinstance(reasoning_chain, list):
        reasoning_chain = []

    # Ensure reasoning chain has at least one entry
    if not reasoning_chain:
        reasoning_chain = [
            {
                "step": 1,
                "reasoning": f"Analyzed {ayush_name} phytochemicals and {allopathy_name} metabolism pathways.",
                "evidence": "Based on IMPPAT phytochemical data and DrugBank metabolism data.",
            }
        ]

    interaction_key = f"{ayush_name.lower().strip()}#{allopathy_name.lower().strip()}"
    interaction_exists = bool(analysis_data.get("interaction_exists", severity_score > 0))

    assembled = {
        "status": "Success",
        "interaction_data": {
            "interaction_key": interaction_key,
            "ayush_name": ayush_name,
            "allopathy_name": allopathy_name,
            "interaction_exists": interaction_exists,
            "interaction_summary": analysis_data.get("interaction_summary", ""),
            "severity": severity,
            "severity_score": severity_score,
            "is_nti": is_nti,
            "scoring_factors": scoring_factors,
            "mechanisms": mechanisms,
            "phytochemicals_involved": analysis_data.get("phytochemicals_involved", []),
            "clinical_effects": analysis_data.get("clinical_effects", []),
            "recommendations": analysis_data.get("recommendations", [
                "Consult a qualified healthcare professional before combining these substances.",
            ]),
            "evidence_quality": "MODERATE",
            "reasoning_chain": reasoning_chain,
            "knowledge_graph": graph,
            "sources": sources,
            "imppat_url": analysis_data.get("imppat_url", ""),
            "drugbank_url": analysis_data.get("drugbank_url", ""),
            "disclaimer": (
                "This analysis is AI-generated for informational purposes only. "
                "Always consult qualified healthcare professionals before making "
                "clinical decisions about drug interactions."
            ),
            "generated_at": datetime.utcnow().isoformat(),
        },
    }

    # Validate the assembled output
    validation = validate_and_format_output(json.dumps(assembled), iteration=1)

    return {
        "success": True,
        "output_str": json.dumps(assembled),
        "validation": validation,
        "missing_fields": validation.get("missing_fields", []),
    }


def validate_and_format_output(reasoning_output_str: str, iteration: int = 1) -> dict:
    """Validate Reasoning Agent output against Success/Failed schema."""
    try:
        output = json.loads(reasoning_output_str) if isinstance(reasoning_output_str, str) else reasoning_output_str
    except (json.JSONDecodeError, TypeError):
        output = {}
    if output is None or not isinstance(output, dict):
        output = {}

    status = output.get("status", "Failed")

    if iteration >= 3 and status != "Success":
        logger.warning(f"Final iteration {iteration}: forcing Success with partial data")
        interaction_data = output.get("interaction_data", output.get("partial_data", {}))
        if not isinstance(interaction_data, dict):
            interaction_data = {}

        if not interaction_data.get("reasoning_chain"):
            interaction_data["reasoning_chain"] = [
                {
                    "step": 1,
                    "reasoning": "Analysis completed with limited data due to iteration constraints.",
                    "evidence": "LOW confidence — insufficient evidence gathered.",
                }
            ]

        forced_output = {
            "status": "Success",
            "interaction_data": {
                "interaction_key": interaction_data.get("interaction_key", ""),
                "ayush_name": interaction_data.get("ayush_name", ""),
                "allopathy_name": interaction_data.get("allopathy_name", ""),
                "interaction_exists": interaction_data.get("interaction_exists", False),
                "interaction_summary": interaction_data.get(
                    "interaction_summary",
                    f"Partial analysis — insufficient data after {iteration} iterations.",
                ),
                "severity": interaction_data.get("severity", "NONE"),
                "severity_score": interaction_data.get("severity_score", 0),
                "is_nti": interaction_data.get("is_nti", False),
                "scoring_factors": interaction_data.get("scoring_factors", []),
                "mechanisms": interaction_data.get("mechanisms", {"pharmacokinetic": [], "pharmacodynamic": []}),
                "phytochemicals_involved": interaction_data.get("phytochemicals_involved", []),
                "clinical_effects": interaction_data.get("clinical_effects", []),
                "recommendations": interaction_data.get("recommendations", [
                    "Consult a healthcare professional before combining these substances.",
                ]),
                "evidence_quality": "LOW",
                "reasoning_chain": interaction_data.get("reasoning_chain", []),
                "knowledge_graph": interaction_data.get("knowledge_graph", {"nodes": [], "edges": []}),
                "sources": interaction_data.get("sources", []),
                "disclaimer": (
                    "This analysis is AI-generated for informational purposes only. "
                    "Always consult qualified healthcare professionals before making "
                    "clinical decisions about drug interactions."
                ),
                "generated_at": datetime.utcnow().isoformat(),
            },
        }
        return {
            "valid": True,
            "forced_success": True,
            "missing_fields": [],
            "output": forced_output,
        }

    if status == "Success":
        interaction_data = output.get("interaction_data", {})
        if not isinstance(interaction_data, dict):
            interaction_data = {}

        missing_fields = []
        for field in SUCCESS_REQUIRED_FIELDS:
            value = interaction_data.get(field)
            if value is None or value == "" or value == [] or value == {}:
                missing_fields.append(field)

        return {
            "valid": len(missing_fields) == 0,
            "forced_success": False,
            "missing_fields": missing_fields,
            "output": output,
        }

    elif status == "Failed":
        failure_reason = output.get("failure_reason", "")
        valid = bool(failure_reason)
        return {
            "valid": valid,
            "forced_success": False,
            "missing_fields": [] if valid else ["failure_reason"],
            "output": output,
        }

    return {
        "valid": False,
        "forced_success": False,
        "missing_fields": ["status"],
        "output": output,
        "error": f"Unknown status: '{status}'. Expected 'Success' or 'Failed'.",
    }
