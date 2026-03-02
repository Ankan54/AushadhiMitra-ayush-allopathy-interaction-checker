"""
Reasoning Tools Action Group Lambda
Triggered by: Bedrock Reasoning Agent
Functions: build_knowledge_graph, calculate_severity, format_professional_response

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
        elif function == "format_professional_response":
            raw = params.get("response_data", "{}")
            try:
                rd = json.loads(raw) if isinstance(raw, str) else raw
            except json.JSONDecodeError:
                rd = {}
            result = format_professional_response(
                rd.get("ayush_name", ""),
                rd.get("allopathy_name", ""),
                rd.get("severity", ""),
                str(rd.get("severity_score", "0")),
                json.dumps(rd.get("interactions_data", {})),
                json.dumps(rd.get("knowledge_graph", {})),
                json.dumps(rd.get("sources", [])),
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
    if not isinstance(interactions, dict):
        interactions = {}

    nodes = []
    edges = []

    nodes.append({
        "data": {"id": "ayush", "label": ayush_name, "type": "ayush_plant"},
    })
    nodes.append({
        "data": {"id": "allopathy", "label": allopathy_name, "type": "allopathy_drug"},
    })

    phytochemicals = interactions.get("phytochemicals", [])
    if isinstance(phytochemicals, list):
        for i, phyto in enumerate(phytochemicals[:10]):
            name = phyto if isinstance(phyto, str) else phyto.get("name", f"phyto_{i}")
            node_id = f"phyto_{i}"
            nodes.append({
                "data": {"id": node_id, "label": name, "type": "phytochemical"},
            })
            edges.append({
                "data": {"source": "ayush", "target": node_id, "label": "contains"},
            })

    cyp_enzymes = interactions.get("cyp_enzymes", [])
    if isinstance(cyp_enzymes, list):
        for i, enzyme in enumerate(cyp_enzymes[:8]):
            name = enzyme if isinstance(enzyme, str) else enzyme.get("name", f"cyp_{i}")
            effect = "" if isinstance(enzyme, str) else enzyme.get("effect", "")
            node_id = f"cyp_{i}"
            nodes.append({
                "data": {"id": node_id, "label": name, "type": "cyp_enzyme"},
            })
            edges.append({
                "data": {"source": "allopathy", "target": node_id,
                         "label": "metabolized by"},
            })
            for j, phyto_node in enumerate(nodes):
                if phyto_node["data"].get("type") == "phytochemical":
                    if effect:
                        edges.append({
                            "data": {
                                "source": phyto_node["data"]["id"],
                                "target": node_id,
                                "label": effect,
                            },
                        })

    mechanisms = interactions.get("mechanisms", [])
    if isinstance(mechanisms, list):
        for i, mech in enumerate(mechanisms[:5]):
            name = mech if isinstance(mech, str) else mech.get("mechanism", f"mech_{i}")
            node_id = f"mech_{i}"
            nodes.append({
                "data": {"id": node_id, "label": name, "type": "mechanism"},
            })

    clinical = interactions.get("clinical_effects", [])
    if isinstance(clinical, list):
        for i, effect in enumerate(clinical[:5]):
            name = effect if isinstance(effect, str) else effect.get("effect", f"effect_{i}")
            node_id = f"effect_{i}"
            nodes.append({
                "data": {"id": node_id, "label": name, "type": "clinical_effect"},
            })

    return {
        "success": True,
        "graph": {
            "nodes": nodes,
            "edges": edges,
        },
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


def calculate_severity(interactions_data_str: str, allopathy_name: str) -> dict:
    """Calculate interaction severity score based on CYP enzyme reference data and NTI status."""
    try:
        interactions = json.loads(interactions_data_str) if isinstance(interactions_data_str, str) else interactions_data_str
    except (json.JSONDecodeError, TypeError):
        interactions = {}
    if not isinstance(interactions, dict):
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


def format_professional_response(ayush_name: str, allopathy_name: str,
                                  severity: str, severity_score_str: str,
                                  interactions_data_str: str,
                                  knowledge_graph_str: str,
                                  sources_str: str) -> dict:
    """Format the final professional response JSON for storage and UI display."""
    try:
        interactions = json.loads(interactions_data_str) if isinstance(interactions_data_str, str) else interactions_data_str
    except (json.JSONDecodeError, TypeError):
        interactions = {}
    if not isinstance(interactions, dict):
        interactions = {}

    try:
        knowledge_graph = json.loads(knowledge_graph_str) if isinstance(knowledge_graph_str, str) else knowledge_graph_str
    except (json.JSONDecodeError, TypeError):
        knowledge_graph = {}
    if not isinstance(knowledge_graph, dict):
        knowledge_graph = {}

    try:
        sources = json.loads(sources_str) if isinstance(sources_str, str) else sources_str
    except (json.JSONDecodeError, TypeError):
        sources = []
    if not isinstance(sources, list):
        sources = []

    try:
        severity_score = int(severity_score_str) if severity_score_str else 0
    except (ValueError, TypeError):
        severity_score = 0

    interaction_key = f"{ayush_name.lower().strip()}#{allopathy_name.lower().strip()}"

    response = {
        "interaction_key": interaction_key,
        "ayush_name": ayush_name,
        "allopathy_name": allopathy_name,
        "severity": severity,
        "severity_score": severity_score,
        "interactions": interactions,
        "knowledge_graph": knowledge_graph,
        "sources": sources,
        "generated_at": datetime.utcnow().isoformat(),
        "disclaimer": (
            "This analysis is AI-generated for informational purposes only. "
            "Always consult qualified healthcare professionals before making "
            "clinical decisions about drug interactions."
        ),
    }

    return {
        "success": True,
        "response_data": response,
    }
