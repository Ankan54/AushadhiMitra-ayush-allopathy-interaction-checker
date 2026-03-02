"""
Allopathy Data Action Group Lambda
Triggered by: Bedrock Allopathy Agent
Functions: allopathy_cache_lookup, allopathy_cache_save, check_nti_status

Manages cached allopathy drug data (CYP metabolism, NTI status) in PostgreSQL.
Also checks NTI drug reference data from S3.
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
from shared.db_utils import get_db, row_to_dict
from shared.bedrock_utils import bedrock_response

S3_BUCKET = os.environ.get("S3_BUCKET", "ausadhi-mitra-667736132441")
s3 = boto3.client("s3")

_nti_cache = None


def lambda_handler(event, context):
    logger.info(f"Event: {json.dumps(event, default=str)}")

    action_group = event.get("actionGroup", "allopathy_data")
    function = event.get("function", "")
    params = {p["name"]: p["value"] for p in event.get("parameters", [])}

    try:
        if function == "allopathy_cache_lookup":
            result = allopathy_cache_lookup(params.get("drug_name", ""))
        elif function == "allopathy_cache_save":
            result = allopathy_cache_save(
                params.get("drug_name", ""),
                params.get("generic_name", ""),
                params.get("drug_data", "{}"),
                params.get("sources", "[]"),
            )
        elif function == "check_nti_status":
            result = check_nti_status(params.get("drug_name", ""))
        else:
            result = {"error": f"Unknown function: {function}"}
    except Exception as e:
        logger.exception(f"Error in {function}")
        result = {"error": str(e)}

    return bedrock_response(action_group, function, result)


def _load_nti_drugs() -> dict:
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


def allopathy_cache_lookup(drug_name: str) -> dict:
    """Check if we have cached CYP/metabolism data for this drug."""
    if not drug_name:
        return {"found": False, "message": "drug_name is required"}

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT drug_name, generic_name, drug_data, sources, cached_at, expires_at
               FROM allopathy_cache
               WHERE drug_name = %s AND expires_at > NOW()""",
            (drug_name.lower().strip(),),
        )
        row = cur.fetchone()
        if row:
            data = row_to_dict(row)
            return {
                "found": True,
                "drug_name": data["drug_name"],
                "generic_name": data["generic_name"],
                "drug_data": data["drug_data"],
                "sources": data["sources"],
                "cached_at": str(data["cached_at"]),
            }
        return {
            "found": False,
            "drug_name": drug_name,
            "message": "No cached data found. Web search recommended.",
        }
    finally:
        conn.close()


def allopathy_cache_save(drug_name: str, generic_name: str,
                         drug_data_str: str, sources_str: str) -> dict:
    """Save drug CYP/metabolism data to cache for future lookups."""
    if not drug_name:
        return {"saved": False, "message": "drug_name is required"}

    try:
        drug_data = json.loads(drug_data_str) if isinstance(drug_data_str, str) else drug_data_str
    except (json.JSONDecodeError, TypeError):
        drug_data = {"raw": str(drug_data_str) if drug_data_str else ""}
    if not isinstance(drug_data, dict):
        drug_data = {"raw": str(drug_data_str) if drug_data_str else ""}

    try:
        sources = json.loads(sources_str) if isinstance(sources_str, str) else sources_str
    except (json.JSONDecodeError, TypeError):
        sources = []
    if not isinstance(sources, list):
        sources = []

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO allopathy_cache (drug_name, generic_name, drug_data, sources, cached_at, expires_at)
               VALUES (%s, %s, %s, %s, NOW(), NOW() + INTERVAL '7 days')
               ON CONFLICT (drug_name) DO UPDATE SET
                   generic_name = EXCLUDED.generic_name,
                   drug_data = EXCLUDED.drug_data,
                   sources = EXCLUDED.sources,
                   cached_at = NOW(),
                   expires_at = NOW() + INTERVAL '7 days'""",
            (drug_name.lower().strip(), generic_name,
             json.dumps(drug_data), json.dumps(sources)),
        )
        conn.commit()
        return {"saved": True, "drug_name": drug_name}
    finally:
        conn.close()


def check_nti_status(drug_name: str) -> dict:
    """Check if a drug is on the Narrow Therapeutic Index list."""
    if not drug_name:
        return {"is_nti": False, "message": "drug_name is required"}

    nti_data = _load_nti_drugs()
    query = drug_name.lower().strip()

    for drug in nti_data.get("nti_drugs", nti_data.get("drugs", [])):
        all_names = (
            [drug.get("generic_name", "").lower()]
            + [n.lower() for n in drug.get("brand_names", [])]
        )
        if query in all_names or any(query in n for n in all_names):
            return {
                "is_nti": True,
                "generic_name": drug["generic_name"],
                "drug_class": drug.get("drug_class", ""),
                "primary_cyp_substrates": drug.get("primary_cyp_substrates", []),
                "clinical_concern": drug.get("clinical_concern", ""),
                "severity_boost": "Severity should be elevated due to Narrow Therapeutic Index status",
            }

    return {
        "is_nti": False,
        "drug_name": drug_name,
        "message": "Drug is not on the Narrow Therapeutic Index list",
    }
