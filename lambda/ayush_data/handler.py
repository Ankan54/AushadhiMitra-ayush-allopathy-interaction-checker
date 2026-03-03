"""
AYUSH Data Action Group Lambda
Triggered by: Bedrock AYUSH Agent
Functions: ayush_name_resolver, imppat_lookup, search_cyp_interactions

Reads reference data from S3 and phytochemical data from DynamoDB.
DynamoDB table: ausadhi-imppat
  PK: plant_name (lowercase folder name, e.g. "curcuma_longa")
  SK: record_key  ("METADATA" or "PHYTO#<imppat_id>")
"""
import json
import sys
import os
import logging
from decimal import Decimal

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sys.path.insert(0, "/opt/python")
sys.path.insert(0, "/var/task")

import boto3
from boto3.dynamodb.conditions import Key, Attr
from shared.bedrock_utils import bedrock_response

S3_BUCKET = os.environ.get("S3_BUCKET", "ausadhi-mitra-667736132441")
TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "ausadhi-imppat")

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)

_name_mappings_cache = None


class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o) if o % 1 else int(o)
        return super().default(o)


def lambda_handler(event, context):
    logger.info(f"Event: {json.dumps(event, default=str)}")

    action_group = event.get("actionGroup", "ayush_data")
    function = event.get("function", "")
    params = {p["name"]: p["value"] for p in event.get("parameters", [])}

    try:
        if function == "ayush_name_resolver":
            result = ayush_name_resolver(params.get("plant_name", ""))
        elif function == "imppat_lookup":
            result = imppat_lookup(
                params.get("scientific_name", ""),
                params.get("phytochemical_name"),
            )
        elif function == "search_cyp_interactions":
            result = search_cyp_interactions(
                params.get("scientific_name", ""),
                params.get("cyp_enzyme"),
            )
        else:
            result = {"error": f"Unknown function: {function}"}
    except Exception as e:
        logger.exception(f"Error in {function}")
        result = {"error": str(e)}

    return bedrock_response(action_group, function, _decimal_safe(result))


def _decimal_safe(obj):
    return json.loads(json.dumps(obj, cls=DecimalEncoder))


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


def _scientific_to_pk(scientific_name: str) -> str:
    """Convert scientific name to DynamoDB partition key format."""
    return scientific_name.strip().replace(" ", "_").lower()


def ayush_name_resolver(plant_name: str) -> dict:
    """Resolve a common/Hindi/brand name to the scientific name and return plant reference data."""
    if not plant_name:
        return {"resolved": False, "message": "plant_name is required"}

    mappings = _load_name_mappings()
    query = plant_name.lower().strip()

    for plant in mappings.get("plants", []):
        all_names = (
            [plant.get("scientific_name", "").lower()]
            + [n.lower() for n in plant.get("common_names", [])]
            + [n.lower() for n in plant.get("hindi_names", [])]
            + [n.lower() for n in plant.get("brand_names", [])]
        )
        if query in all_names or any(query in n for n in all_names):
            pk = _scientific_to_pk(plant["scientific_name"])
            meta = _get_metadata(pk)
            sci = plant["scientific_name"]
            from urllib.parse import quote as _quote
            imppat_url = (
                plant.get("imppat_url")
                or f"https://cb.imsc.res.in/imppat/phytochemical/{_quote(sci)}"
            )
            return {
                "resolved": True,
                "scientific_name": sci,
                "common_names": plant.get("common_names", []),
                "hindi_names": plant.get("hindi_names", []),
                "dynamodb_key": pk,
                "imppat_url": imppat_url,
                "total_phytochemicals": meta.get("total_phytochemicals", 0) if meta else 0,
                "key_phytochemicals": plant.get("key_phytochemicals", []),
                "known_cyp_effects": plant.get("known_cyp_effects", {}),
                "effect_categories": plant.get("effect_categories", []),
            }

    return {
        "resolved": False,
        "query": plant_name,
        "message": f"Could not resolve '{plant_name}' to a known AYUSH plant. "
                   "Try using the scientific name or a common English name.",
        "available_plants": [p["scientific_name"] for p in mappings.get("plants", [])],
    }


def _get_metadata(pk: str) -> dict:
    try:
        resp = table.get_item(Key={"plant_name": pk, "record_key": "METADATA"})
        return resp.get("Item")
    except Exception as e:
        logger.error(f"DynamoDB metadata lookup failed: {e}")
        return None


def imppat_lookup(scientific_name: str, phytochemical_name: str = None) -> dict:
    """Look up IMPPAT phytochemical data from DynamoDB.

    If phytochemical_name is provided, searches for that compound and returns its details.
    Otherwise returns plant metadata + phytochemical summary list (first 50).
    """
    if not scientific_name:
        return {"success": False, "message": "scientific_name is required"}

    pk = _scientific_to_pk(scientific_name)

    if phytochemical_name:
        return _lookup_single_phyto(pk, scientific_name, phytochemical_name)

    meta = _get_metadata(pk)
    if not meta:
        return {
            "success": False,
            "message": f"No IMPPAT data found for '{scientific_name}' in DynamoDB",
        }

    resp = table.query(
        KeyConditionExpression=Key("plant_name").eq(pk) & Key("record_key").begins_with("PHYTO#"),
        Limit=50,
        ProjectionExpression="record_key, phytochemical_name, plant_part, imppat_id, cyp_interactions, is_cyp_relevant",
    )
    items = resp.get("Items", [])

    phyto_summary = []
    for item in items:
        entry = {
            "name": item.get("phytochemical_name", ""),
            "plant_part": item.get("plant_part", ""),
            "imppat_id": item.get("imppat_id", ""),
            "is_cyp_relevant": item.get("is_cyp_relevant", False),
        }
        cyp = item.get("cyp_interactions", {})
        if cyp:
            entry["cyp_interactions"] = cyp
        phyto_summary.append(entry)

    return {
        "success": True,
        "plant_name": meta.get("scientific_name", scientific_name),
        "common_name": meta.get("common_name", ""),
        "system_of_medicine": meta.get("system_of_medicine", ""),
        "total_phytochemicals": meta.get("total_phytochemicals", 0),
        "returned_count": len(phyto_summary),
        "phytochemicals": phyto_summary,
    }


def _lookup_single_phyto(pk: str, scientific_name: str, phytochemical_name: str) -> dict:
    """Find a specific phytochemical by name (scan with filter)."""
    query_lower = phytochemical_name.lower().strip()

    resp = table.query(
        KeyConditionExpression=Key("plant_name").eq(pk) & Key("record_key").begins_with("PHYTO#"),
        FilterExpression=Attr("phytochemical_name").contains(phytochemical_name),
    )
    items = resp.get("Items", [])

    if not items:
        resp = table.query(
            KeyConditionExpression=Key("plant_name").eq(pk) & Key("record_key").begins_with("PHYTO#"),
        )
        all_items = resp.get("Items", [])
        for item in all_items:
            if query_lower in item.get("phytochemical_name", "").lower():
                items = [item]
                break

    if not items:
        return {
            "success": False,
            "message": f"Phytochemical '{phytochemical_name}' not found in {scientific_name}",
        }

    item = items[0]
    return {
        "success": True,
        "phytochemical_name": item.get("phytochemical_name", ""),
        "plant_part": item.get("plant_part", ""),
        "imppat_id": item.get("imppat_id", ""),
        "smiles": item.get("smiles", ""),
        "classification": item.get("classification", {}),
        "admet_properties": item.get("admet", {}),
        "drug_likeness_properties": item.get("drug_likeness", {}),
        "physicochemical_properties": item.get("physicochemical", {}),
        "cyp_interactions": item.get("cyp_interactions", {}),
        "is_cyp_relevant": item.get("is_cyp_relevant", False),
    }


def search_cyp_interactions(scientific_name: str, cyp_enzyme: str = None) -> dict:
    """Search for all CYP-relevant phytochemicals in a plant.

    Optionally filter by a specific CYP enzyme (e.g., "CYP3A4").
    Returns phytochemicals that are CYP inhibitors/substrates.
    """
    if not scientific_name:
        return {"success": False, "message": "scientific_name is required"}

    pk = _scientific_to_pk(scientific_name)

    resp = table.query(
        KeyConditionExpression=Key("plant_name").eq(pk) & Key("record_key").begins_with("PHYTO#"),
        FilterExpression=Attr("is_cyp_relevant").eq(True),
    )
    items = resp.get("Items", [])

    while "LastEvaluatedKey" in resp:
        resp = table.query(
            KeyConditionExpression=Key("plant_name").eq(pk) & Key("record_key").begins_with("PHYTO#"),
            FilterExpression=Attr("is_cyp_relevant").eq(True),
            ExclusiveStartKey=resp["LastEvaluatedKey"],
        )
        items.extend(resp.get("Items", []))

    results = []
    for item in items:
        cyp = item.get("cyp_interactions", {})

        if cyp_enzyme:
            enzyme_key = cyp_enzyme.strip()
            matching = {k: v for k, v in cyp.items() if enzyme_key.lower() in k.lower()}
            if not matching:
                continue
            cyp = matching

        results.append({
            "phytochemical_name": item.get("phytochemical_name", ""),
            "plant_part": item.get("plant_part", ""),
            "imppat_id": item.get("imppat_id", ""),
            "cyp_interactions": cyp,
        })

    return {
        "success": True,
        "plant_name": scientific_name,
        "cyp_enzyme_filter": cyp_enzyme or "all",
        "total_cyp_relevant": len(results),
        "phytochemicals": results[:100],
    }
