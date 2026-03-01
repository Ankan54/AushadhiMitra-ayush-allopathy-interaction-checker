"""
Validation Parser Lambda
Used as a Flow node after the Reasoning Agent to extract validation status.

Input: Reasoning Agent's text response (contains VALIDATION_RESULT JSON)
Output: Structured JSON for Condition node routing:
  {
    "validation_status": "PASSED" | "NEEDS_MORE_DATA",
    "needs_ayush": true/false,
    "needs_allopathy": true/false,
    "needs_web_search": true/false,
    "missing_queries": ["query1", "query2"],
    "full_response": "original reasoning response"
  }
"""
import json
import re
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    logger.info(f"Event keys: {list(event.keys())}")

    reasoning_text = ""
    if isinstance(event, str):
        reasoning_text = event
    elif isinstance(event, dict):
        reasoning_text = (
            event.get("reasoning_response", "")
            or event.get("inputText", "")
            or event.get("document", "")
            or json.dumps(event)
        )

    validation = _extract_validation(reasoning_text)

    needs_ayush = False
    needs_allopathy = False
    needs_web = False
    missing_queries = []

    for item in validation.get("missing_data", []):
        agent = item.get("source_agent", "").lower()
        query = item.get("query_suggestion", "")
        if "ayush" in agent:
            needs_ayush = True
        elif "allopathy" in agent:
            needs_allopathy = True
        elif "web" in agent:
            needs_web = True
        if query:
            missing_queries.append(query)

    result = {
        "validation_status": validation.get("validation_status", "PASSED"),
        "completeness_score": validation.get("completeness_score", 100),
        "needs_ayush": needs_ayush,
        "needs_allopathy": needs_allopathy,
        "needs_web_search": needs_web,
        "missing_queries": missing_queries,
        "issues": validation.get("issues", []),
        "full_response": reasoning_text,
    }

    logger.info(f"Validation result: status={result['validation_status']}, "
                f"ayush={needs_ayush}, allopathy={needs_allopathy}, web={needs_web}")

    return result


def _extract_validation(text: str) -> dict:
    """Extract VALIDATION_RESULT JSON from the reasoning agent's text output."""

    patterns = [
        r'VALIDATION_RESULT:\s*(\{[\s\S]*?\})\s*(?:\n\n|\Z)',
        r'"validation_status"\s*:\s*"[^"]+"\s*,[\s\S]*?"missing_data"\s*:\s*\[[\s\S]*?\][\s\S]*?\}',
        r'\{[^{}]*"validation_status"[^{}]*\}',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            try:
                candidate = match.strip()
                if not candidate.startswith("{"):
                    candidate = "{" + candidate + "}"
                parsed = json.loads(candidate)
                if "validation_status" in parsed:
                    return parsed
            except json.JSONDecodeError:
                continue

    json_blocks = re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text)
    for block in json_blocks:
        try:
            parsed = json.loads(block)
            if "validation_status" in parsed:
                return parsed
        except json.JSONDecodeError:
            continue

    if "NEEDS_MORE_DATA" in text:
        return {"validation_status": "NEEDS_MORE_DATA", "completeness_score": 50,
                "issues": ["Validation JSON not parseable but NEEDS_MORE_DATA detected"],
                "missing_data": []}

    return {"validation_status": "PASSED", "completeness_score": 80,
            "issues": ["Validation JSON not found in response, assuming PASSED"],
            "missing_data": []}
