"""
CloudWatch Logging for AushadhiMitra CO-MAS Pipeline Traces.
"""
import boto3
import json
import time
import logging
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

LOG_GROUP = "/aws/bedrock/ausadhi-mitra-pipeline-logs"
REGION = "us-east-1"

_logs_client = None
_sequence_tokens: Dict[str, Optional[str]] = {}


def _get_client():
    global _logs_client
    if _logs_client is None:
        _logs_client = boto3.client("logs", region_name=REGION)
    return _logs_client


def _put_log_event(stream_name: str, message: dict):
    """Write a log event to CloudWatch with sequence token handling."""
    global _sequence_tokens

    try:
        client = _get_client()
        event = {
            "timestamp": int(time.time() * 1000),
            "message": json.dumps(message, default=str),
        }

        kwargs = {
            "logGroupName": LOG_GROUP,
            "logStreamName": stream_name,
            "logEvents": [event],
        }

        if stream_name in _sequence_tokens and _sequence_tokens[stream_name]:
            kwargs["sequenceToken"] = _sequence_tokens[stream_name]

        try:
            response = client.put_log_events(**kwargs)
            _sequence_tokens[stream_name] = response.get("nextSequenceToken")
        except client.exceptions.InvalidSequenceTokenException as e:
            msg = str(e)
            if "sequenceToken is:" in msg:
                expected = msg.split("sequenceToken is:")[-1].strip()
                _sequence_tokens[stream_name] = expected if expected != "null" else None
                kwargs["sequenceToken"] = _sequence_tokens[stream_name]
                response = client.put_log_events(**kwargs)
                _sequence_tokens[stream_name] = response.get("nextSequenceToken")

    except Exception as e:
        logger.warning(f"Failed to write to CloudWatch: {e}")


def log_pipeline_start(session_id: str, ayush_name: str, allopathy_name: str):
    """Log CO-MAS pipeline execution start."""
    _put_log_event("pipeline-executions", {
        "event": "PIPELINE_START",
        "session_id": session_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "ayush_drug": ayush_name,
        "allopathy_drug": allopathy_name,
    })


def log_pipeline_complete(session_id: str, status: str, duration_ms: int,
                          iterations: int = 1, result_summary: Optional[Dict] = None):
    """Log CO-MAS pipeline completion."""
    _put_log_event("pipeline-executions", {
        "event": "PIPELINE_COMPLETE",
        "session_id": session_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "status": status,
        "duration_ms": duration_ms,
        "comas_iterations": iterations,
        "result": result_summary or {},
    })


def log_pipeline_error(session_id: str, error_type: str, error_message: str,
                       phase: Optional[str] = None):
    """Log CO-MAS pipeline error."""
    _put_log_event("errors", {
        "event": "PIPELINE_ERROR",
        "session_id": session_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "error_type": error_type,
        "error_message": error_message,
        "phase": phase,
    })


def log_iteration_gap(session_id: str, iteration: int, gaps: list,
                      score: float, evidence_quality: str):
    """Log CO-MAS Scorer-identified information gaps at the end of an iteration."""
    _put_log_event("pipeline-executions", {
        "event": "ITERATION_GAP",
        "session_id": session_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "iteration": iteration,
        "score": score,
        "evidence_quality": evidence_quality,
        "gaps": gaps,
    })


def log_agent_trace(session_id: str, agent_name: str, event_type: str,
                    data: Optional[Dict] = None):
    """Log agent-level trace events."""
    stream = "agent-traces"
    if agent_name == "reasoning":
        stream = "reasoning-agent"
    elif agent_name == "planner":
        stream = "planner-agent"

    _put_log_event(stream, {
        "event": event_type.upper(),
        "session_id": session_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "agent": agent_name,
        "data": data or {},
    })
