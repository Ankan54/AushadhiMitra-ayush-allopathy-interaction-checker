"""
IMPPAT Data Loader Lambda
Reads a single plant's IMPPAT JSON from S3 and batch-writes to DynamoDB.

Invoke once per plant:
  {"plant_folder": "Curcuma_longa"}  (matches S3 prefix impat_jsons/Curcuma_longa/plant_data.json)

DynamoDB table: ausadhi-imppat
  PK: plant_name (lowercase, e.g. "curcuma_longa")
  SK: record_key  ("METADATA" or "PHYTO#<phytochemical_name_lower>")

Skips bulky chemical_descriptors; keeps ADMET, physicochemical, drug_likeness.
Extracts CYP-related properties into a top-level field for fast agent queries.
"""
import json
import os
import logging
import boto3
from decimal import Decimal

logger = logging.getLogger()
logger.setLevel(logging.INFO)

S3_BUCKET = os.environ.get("S3_BUCKET", "")
TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "ausadhi-imppat")

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)

CYP_KEYWORDS = ["cyp1a2", "cyp2c9", "cyp2c19", "cyp2d6", "cyp3a4", "p-glycoprotein"]


def lambda_handler(event, context):
    plant_folder = event.get("plant_folder", "")
    if not plant_folder:
        return {"error": "plant_folder is required"}

    s3_key = f"impat_jsons/{plant_folder}/plant_data.json"
    tmp_path = f"/tmp/{plant_folder.replace('/', '_')}_plant_data.json"

    logger.info(f"Loading {s3_key} from S3...")
    s3.download_file(S3_BUCKET, s3_key, tmp_path)

    logger.info("Parsing JSON...")
    with open(tmp_path, "r") as f:
        plant_data = json.load(f)

    plant_name_raw = plant_data.get("plant_name", plant_folder.replace("_", " "))
    pk = plant_folder.lower()

    phytochemicals = plant_data.get("phytochemicals", [])
    total = len(phytochemicals)
    logger.info(f"Plant: {plant_name_raw}, phytochemicals: {total}")

    metadata_item = {
        "plant_name": pk,
        "record_key": "METADATA",
        "scientific_name": plant_name_raw,
        "common_name": plant_data.get("common_name", ""),
        "synonymous_names": plant_data.get("synonymous_names", ""),
        "system_of_medicine": plant_data.get("system_of_medicine", ""),
        "total_phytochemicals": total,
    }
    table.put_item(Item=_sanitize(metadata_item))
    logger.info("Metadata record written")

    written = 0
    cyp_relevant_count = 0
    batch_items = {}

    for phyto in phytochemicals:
        phyto_name = phyto.get("phytochemical_name", "").strip()
        if not phyto_name:
            continue

        details = phyto.get("details", {})

        admet_dict = _props_to_dict(details.get("admet_properties", []))
        physico_dict = _props_to_dict(details.get("physicochemical_properties", []))
        druglike_dict = _props_to_dict(details.get("drug_likeness_properties", []))

        cyp_props = {}
        for key, val in admet_dict.items():
            if any(kw in key.lower() for kw in CYP_KEYWORDS):
                cyp_props[key] = val

        is_cyp_relevant = any(
            v.lower() == "yes" for v in cyp_props.values()
        )
        if is_cyp_relevant:
            cyp_relevant_count += 1

        imppat_id = (phyto.get("imppat_phytochemical_identifier", "")
                     or details.get("imppat_phytochemical_identifier", "")
                     or phyto_name.lower())
        record_key = f"PHYTO#{imppat_id}"

        item = {
            "plant_name": pk,
            "record_key": record_key,
            "phytochemical_name": phyto_name,
            "plant_part": phyto.get("plant_part", ""),
            "imppat_id": imppat_id,
            "smiles": details.get("smiles", ""),
            "classification": {
                "kingdom": details.get("classyfire_kingdom", ""),
                "superclass": details.get("classyfire_superclass", ""),
                "class": details.get("classyfire_class", ""),
                "subclass": details.get("classyfire_subclass", ""),
                "np_pathway": details.get("np_classifier_biosynthetic_pathway", ""),
                "np_superclass": details.get("np_classifier_superclass", ""),
                "np_class": details.get("np_classifier_class", ""),
            },
            "admet": admet_dict,
            "physicochemical": physico_dict,
            "drug_likeness": druglike_dict,
            "cyp_interactions": cyp_props,
            "is_cyp_relevant": is_cyp_relevant,
        }

        batch_items[record_key] = _sanitize(item)

        if len(batch_items) >= 25:
            _batch_write(list(batch_items.values()))
            written += len(batch_items)
            batch_items = {}
            if written % 500 == 0:
                logger.info(f"  Written {written}/{total}...")

    if batch_items:
        _batch_write(list(batch_items.values()))
        written += len(batch_items)

    result = {
        "plant": plant_name_raw,
        "total_phytochemicals": total,
        "written_to_dynamodb": written,
        "cyp_relevant": cyp_relevant_count,
    }
    logger.info(f"Load complete: {json.dumps(result)}")
    return result


def _props_to_dict(props_list):
    if isinstance(props_list, dict):
        return props_list
    result = {}
    for p in props_list:
        name = p.get("property_name", "")
        value = p.get("property_value", "")
        if name:
            result[name] = value
    return result


def _batch_write(items):
    with table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=item)


def _sanitize(obj):
    """Convert floats to Decimal for DynamoDB, remove empty strings."""
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items() if v != "" and v is not None}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, float):
        return Decimal(str(obj))
    return obj
