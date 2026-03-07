"""
Planner Tools Action Group Lambda
Triggered by: Bedrock Planner Agent
Functions: identify_substances, check_curated_interaction,
           validate_ayush_drug, generate_execution_plan

Identifies AYUSH and allopathy substances from user input,
validates AYUSH plants against DynamoDB, checks curated DB,
and generates structured execution plans for the 5-agent pipeline.
"""
import json
import sys
import os
import logging
import random

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sys.path.insert(0, "/opt/python")
sys.path.insert(0, "/var/task")

import boto3
from shared.bedrock_utils import bedrock_response
from shared.db_utils import get_db, row_to_dict

S3_BUCKET = os.environ.get("S3_BUCKET", "")
DYNAMODB_TABLE = os.environ.get("DYNAMODB_TABLE", "ausadhi-imppat")

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")

_name_mappings_cache = None


def lambda_handler(event, context):
    logger.info(f"Event: {json.dumps(event, default=str)}")

    action_group = event.get("actionGroup", "planner_tools")
    function = event.get("function", "")
    params = {p["name"]: p["value"] for p in event.get("parameters", [])}

    try:
        if function == "identify_substances":
            result = identify_substances(params.get("user_input", ""))
        elif function == "check_curated_interaction":
            result = check_curated_interaction(
                params.get("ayush_name", ""),
                params.get("allopathy_name", ""),
            )
        elif function == "validate_ayush_drug":
            result = validate_ayush_drug(params.get("plant_name", ""))
        elif function == "generate_execution_plan":
            ayush_exists_raw = params.get("ayush_exists", "true")
            if isinstance(ayush_exists_raw, str):
                ayush_exists = ayush_exists_raw.lower() not in ("false", "0", "no")
            else:
                ayush_exists = bool(ayush_exists_raw)

            try:
                iteration = int(params.get("iteration", "1"))
            except (ValueError, TypeError):
                iteration = 1

            result = generate_execution_plan(
                params.get("ayush_name", ""),
                params.get("allopathy_name", ""),
                ayush_exists,
                iteration,
                params.get("failure_feedback", ""),
            )
        else:
            result = {"error": f"Unknown function: {function}"}
    except Exception as e:
        logger.exception(f"Error in {function}")
        result = {"error": str(e)}

    return bedrock_response(action_group, function, result)


def _load_name_mappings() -> dict:
    global _name_mappings_cache
    if _name_mappings_cache is not None:
        return _name_mappings_cache
    try:
        resp = s3.get_object(Bucket=S3_BUCKET, Key="reference/name_mappings.json")
        _name_mappings_cache = json.loads(resp["Body"].read().decode("utf-8"))
        return _name_mappings_cache
    except Exception as e:
        logger.error(f"Failed to load name_mappings.json: {e}")
        return {"plants": []}


COMMON_ALLOPATHY_DRUGS = [
    "warfarin", "aspirin", "metformin", "atorvastatin", "simvastatin",
    "losartan", "amlodipine", "omeprazole", "diclofenac", "ibuprofen",
    "paracetamol", "acetaminophen", "lisinopril", "metoprolol", "clopidogrel",
    "digoxin", "phenytoin", "carbamazepine", "lithium", "cyclosporine",
    "tacrolimus", "theophylline", "levothyroxine", "insulin", "glimepiride",
    "amoxicillin", "ciprofloxacin", "fluconazole", "ketoconazole", "rifampin",
]


def identify_substances(user_input: str) -> dict:
    """Identify AYUSH plant and allopathy drug names from user input.

    Uses the name_mappings reference to match AYUSH plants,
    and a common drug list + heuristics for allopathy drugs.
    Returns identified substances for the execution plan.
    """
    if not user_input:
        return {"success": False, "message": "user_input is required"}

    input_lower = user_input.lower().strip()
    mappings = _load_name_mappings()

    ayush_matches = []
    for plant in mappings.get("plants", []):
        all_names = (
            [plant.get("scientific_name", "").lower()]
            + [n.lower() for n in plant.get("common_names", [])]
            + [n.lower() for n in plant.get("hindi_names", [])]
            + [n.lower() for n in plant.get("brand_names", [])]
        )
        for name in all_names:
            if name and name in input_lower:
                ayush_matches.append({
                    "matched_term": name,
                    "scientific_name": plant["scientific_name"],
                    "common_names": plant.get("common_names", []),
                    "dynamodb_key": plant["scientific_name"].replace(" ", "_").lower(),
                })
                break

    allopathy_matches = []
    for drug in COMMON_ALLOPATHY_DRUGS:
        if drug in input_lower:
            allopathy_matches.append({"matched_term": drug, "drug_name": drug})

    return {
        "success": True,
        "original_input": user_input,
        "ayush_substances": ayush_matches,
        "allopathy_substances": allopathy_matches,
        "ayush_count": len(ayush_matches),
        "allopathy_count": len(allopathy_matches),
        "needs_clarification": len(ayush_matches) == 0 or len(allopathy_matches) == 0,
        "message": _build_plan_message(ayush_matches, allopathy_matches),
    }


def _build_plan_message(ayush: list, allopathy: list) -> str:
    parts = []
    if ayush:
        names = ", ".join(a["scientific_name"] for a in ayush)
        parts.append(f"AYUSH identified: {names}")
    else:
        parts.append("No AYUSH substance identified from input")

    if allopathy:
        names = ", ".join(a["drug_name"] for a in allopathy)
        parts.append(f"Allopathy identified: {names}")
    else:
        parts.append("No allopathy drug identified from input")

    if ayush and allopathy:
        pairs = len(ayush) * len(allopathy)
        parts.append(f"Execution plan: analyze {pairs} interaction pair(s)")
    return ". ".join(parts)


def check_curated_interaction(ayush_name: str, allopathy_name: str) -> dict:
    """Check if this interaction has been previously analyzed and cached."""
    if not ayush_name or not allopathy_name:
        return {"found": False, "message": "Both ayush_name and allopathy_name are required"}

    conn = get_db()
    try:
        cur = conn.cursor()
        interaction_key = f"{ayush_name.lower().strip()}#{allopathy_name.lower().strip()}"
        cur.execute(
            """SELECT interaction_key, ayush_name, allopathy_name, severity,
                      severity_score, response_data, knowledge_graph, created_at
               FROM curated_interactions
               WHERE interaction_key = %s""",
            (interaction_key,),
        )
        row = cur.fetchone()
        if row:
            data = row_to_dict(row)
            return {
                "found": True,
                "interaction_key": data["interaction_key"],
                "severity": data.get("severity", ""),
                "severity_score": data.get("severity_score", 0),
                "interaction_data": data.get("response_data", {}),
                "knowledge_graph": data.get("knowledge_graph", {}),
                "cached": True,
            }
        return {
            "found": False,
            "interaction_key": interaction_key,
            "message": "No cached interaction found. Full analysis required.",
        }
    except Exception as e:
        logger.error(f"DB lookup error: {e}")
        return {"found": False, "error": str(e)}
    finally:
        conn.close()


def validate_ayush_drug(plant_name: str) -> dict:
    """Validate that an AYUSH plant exists in the DynamoDB IMPPAT database.

    Resolves common/Hindi names to scientific name via name_mappings,
    then checks for METADATA record in DynamoDB.
    Returns existence status, scientific name, and phytochemical count.
    """
    if not plant_name or not plant_name.strip():
        return {
            "exists": False,
            "message": "plant_name is required",
        }

    mappings = _load_name_mappings()
    plant_name_lower = plant_name.lower().strip()

    resolved_scientific = None
    dynamodb_key = None

    for plant in mappings.get("plants", []):
        all_names = (
            [plant.get("scientific_name", "").lower()]
            + [n.lower() for n in plant.get("common_names", [])]
            + [n.lower() for n in plant.get("hindi_names", [])]
            + [n.lower() for n in plant.get("brand_names", [])]
        )
        for name in all_names:
            if name and (name == plant_name_lower or plant_name_lower in name or name in plant_name_lower):
                resolved_scientific = plant["scientific_name"]
                dynamodb_key = plant["scientific_name"].replace(" ", "_").lower()
                break
        if resolved_scientific:
            break

    if not resolved_scientific:
        resolved_scientific = plant_name
        dynamodb_key = plant_name.replace(" ", "_").lower()

    try:
        table = dynamodb.Table(DYNAMODB_TABLE)
        response = table.get_item(
            Key={
                "plant_name": dynamodb_key,
                "record_key": "METADATA",
            }
        )
        item = response.get("Item")

        if item:
            total_phytochemicals = item.get("total_phytochemicals", 0)
            return {
                "exists": True,
                "scientific_name": resolved_scientific,
                "dynamodb_key": dynamodb_key,
                "total_phytochemicals": total_phytochemicals,
                "common_names": item.get("common_names", []),
            }
        else:
            supported = _get_supported_plants_display(mappings)
            return {
                "exists": False,
                "scientific_name": resolved_scientific,
                "dynamodb_key": dynamodb_key,
                "message": (
                    f"DEMO LIMITATION: AYUSH plant '{plant_name}' is not available in this demo. "
                    f"Currently supported plants: {', '.join(supported)}. "
                    "Please try one of the supported plants."
                ),
                "supported_plants": supported,
            }
    except Exception as e:
        logger.error(f"DynamoDB lookup error for {dynamodb_key}: {e}")
        supported = _get_supported_plants_display(mappings)
        return {
            "exists": False,
            "scientific_name": resolved_scientific,
            "dynamodb_key": dynamodb_key,
            "message": f"DynamoDB lookup failed: {str(e)}",
            "supported_plants": supported,
        }


def _get_sample_plants(mappings: dict, count: int) -> list:
    """Return a random sample of plant names from mappings."""
    plants = mappings.get("plants", [])
    sample = random.sample(plants, min(count, len(plants))) if plants else []
    return [p.get("scientific_name", "") for p in sample if p.get("scientific_name")]


def _get_supported_plants_display(mappings: dict) -> list:
    """Return a formatted display list of ALL supported demo plants with common names."""
    result = []
    for p in mappings.get("plants", []):
        sci = p.get("scientific_name", "")
        commons = p.get("common_names", [])
        display = sci
        if commons:
            display += f" ({', '.join(commons[:2])})"
        result.append(display)
    return result


def generate_execution_plan(ayush_name: str, allopathy_name: str,
                             ayush_exists: bool, iteration: int = 1,
                             failure_feedback: str = "") -> dict:
    """Generate a structured execution plan for the 5-agent pipeline.

    Validates inputs, returns plan JSON with per-agent run flags and tasks.
    On retry iterations, uses failure_feedback to determine which agents to re-run.
    """
    if not ayush_name or not ayush_name.strip():
        return {
            "plan_valid": False,
            "inputs_valid": False,
            "error": "AYUSH drug name is required",
        }

    if not allopathy_name or not allopathy_name.strip():
        return {
            "plan_valid": False,
            "inputs_valid": False,
            "error": "Allopathy drug name is required",
        }

    if not ayush_exists:
        return {
            "plan_valid": False,
            "inputs_valid": False,
            "error": f"AYUSH plant '{ayush_name}' not found in database. "
                     "Please provide a valid AYUSH plant name.",
        }

    if iteration <= 1 or not failure_feedback:
        return {
            "plan_valid": True,
            "inputs_valid": True,
            "iteration": iteration,
            "ayush_name": ayush_name,
            "allopathy_name": allopathy_name,
            "agents": {
                "ayush": {
                    "run": True,
                    "tasks": [
                        "Resolve name to scientific name",
                        "Get phytochemicals from IMPPAT",
                        "Search CYP enzyme interactions",
                    ],
                },
                "allopathy": {
                    "run": True,
                    "tasks": [
                        "Check cache for drug data",
                        "Get CYP metabolism pathways",
                        "Check NTI status",
                    ],
                },
                "research": {
                    "run": True,
                    "tasks": [
                        "Search clinical evidence on interaction",
                        "Find PubMed articles",
                    ],
                },
            },
        }

    # Try to parse structured JSON feedback from Scorer phase
    gaps = []
    score = 0.0
    evidence_quality = "unknown"
    feedback_text = failure_feedback
    try:
        fb_data = json.loads(failure_feedback)
        gaps = fb_data.get("gaps", [])
        score = float(fb_data.get("score", 0))
        evidence_quality = fb_data.get("evidence_quality", "unknown")
        feedback_text = "; ".join(gaps) if gaps else failure_feedback
    except (json.JSONDecodeError, TypeError):
        pass  # Use raw text fallback

    feedback_lower = feedback_text.lower()

    # Determine which agents to re-run based on specific gap types
    run_ayush = any(kw in feedback_lower for kw in [
        "ayush", "phytochemical", "cyp", "imppat", "plant", "curcumin", "phyto"
    ])
    run_allopathy = any(kw in feedback_lower for kw in [
        "allopathy", "drug", "nti", "metabolism", "cyp substrate", "enzyme", "drugbank"
    ])
    run_research = any(kw in feedback_lower for kw in [
        "research", "evidence", "pubmed", "clinical", "study", "mechanism", "source"
    ])

    if not run_ayush and not run_allopathy and not run_research:
        run_research = True

    return {
        "plan_valid": True,
        "inputs_valid": True,
        "iteration": iteration,
        "ayush_name": ayush_name,
        "allopathy_name": allopathy_name,
        "failure_feedback": failure_feedback,
        "score": score,
        "evidence_quality": evidence_quality,
        "agents": {
            "ayush": {
                "run": run_ayush,
                "tasks": [
                    "Gather additional phytochemical CYP data",
                    f"Focus on gaps: {feedback_text[:150]}",
                ] if run_ayush else [],
            },
            "allopathy": {
                "run": run_allopathy,
                "tasks": [
                    "Gather additional drug metabolism data",
                    f"Focus on gaps: {feedback_text[:150]}",
                ] if run_allopathy else [],
            },
            "research": {
                "run": run_research,
                "tasks": [
                    "Search additional clinical evidence",
                    f"Focus on gaps: {feedback_text[:150]}",
                ] if run_research else [],
            },
        },
    }
