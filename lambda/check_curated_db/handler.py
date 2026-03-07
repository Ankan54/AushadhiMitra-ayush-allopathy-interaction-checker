"""
Check Curated DB Action Group Lambda
Triggered by: Bedrock Supervisor Agent
Functions: check_curated_interaction
"""
import json
import sys
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sys.path.insert(0, "/opt/python")
sys.path.insert(0, "/var/task")

from shared.db_utils import get_db, row_to_dict, rows_to_list
from shared.bedrock_utils import bedrock_response


def lambda_handler(event, context):
    logger.info(f"Event: {json.dumps(event, default=str)}")

    action_group = event.get("actionGroup", "check_curated_db")
    function = event.get("function", "")
    params = {p["name"]: p["value"] for p in event.get("parameters", [])}

    try:
        if function == "check_curated_interaction":
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


def check_curated_interaction(ayush_name: str, allopathy_name: str) -> dict:
    """Look up a previously curated drug interaction from the database."""
    if not ayush_name or not allopathy_name:
        return {"found": False, "message": "Both ayush_name and allopathy_name are required"}

    conn = get_db()
    try:
        cur = conn.cursor()
        key = f"{ayush_name.lower().strip()}#{allopathy_name.lower().strip()}"

        cur.execute(
            "SELECT * FROM curated_interactions WHERE interaction_key = %s", (key,)
        )
        row = cur.fetchone()

        if not row:
            cur.execute(
                """SELECT * FROM curated_interactions
                   WHERE LOWER(ayush_name) LIKE %s AND LOWER(allopathy_name) LIKE %s""",
                (f"%{ayush_name.lower().strip()}%", f"%{allopathy_name.lower().strip()}%"),
            )
            row = cur.fetchone()

        if row:
            data = row_to_dict(row)
            cur.execute(
                "SELECT source_url, source_title, source_snippet, source_type, relevance_score "
                "FROM interaction_sources WHERE interaction_key = %s",
                (data["interaction_key"],),
            )
            sources = rows_to_list(cur.fetchall())
            return {
                "found": True,
                "interaction": data,
                "sources": sources,
                "message": "Curated interaction found in database",
            }

        return {
            "found": False,
            "ayush_name": ayush_name,
            "allopathy_name": allopathy_name,
            "message": "No curated interaction found. Full analysis required.",
        }
    finally:
        conn.close()
