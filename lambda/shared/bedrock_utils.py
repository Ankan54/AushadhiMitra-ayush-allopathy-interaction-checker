"""
Bedrock Agent response formatting utilities.
Uses the function-definition response format (not OpenAPI) matching SCM pattern.
"""
import json
from datetime import datetime, date


def _serialize(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    try:
        import decimal
        if isinstance(obj, decimal.Decimal):
            return float(obj)
    except ImportError:
        pass
    raise TypeError(f"Type {type(obj)} not serializable")


def bedrock_response(action_group: str, function: str, result: dict) -> dict:
    """Format a response for the Bedrock Agent action group protocol."""
    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": action_group,
            "function": function,
            "functionResponse": {
                "responseBody": {
                    "TEXT": {
                        "body": json.dumps(result, default=_serialize)
                    }
                }
            },
        },
    }
