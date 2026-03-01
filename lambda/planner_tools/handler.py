"""
Planner Tools Action Group Lambda
Triggered by: Bedrock Planner Agent
Functions: identify_substances, check_curated_interaction

Identifies AYUSH and allopathy substances from user input,
and checks the curated DB for previously analyzed interactions.
"""
import json
import sys
import os
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sys.path.insert(0, "/opt/python")
sys.path.insert(0, "/var/task")

import boto3
from shared.bedrock_utils import bedrock_response
from shared.db_utils import get_db, row_to_dict

S3_BUCKET = os.environ.get("S3_BUCKET", "ausadhi-mitra-667736132441")
s3 = boto3.client("s3")

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
                      severity_score, interaction_data, knowledge_graph, created_at
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
                "interaction_data": data.get("interaction_data", {}),
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
