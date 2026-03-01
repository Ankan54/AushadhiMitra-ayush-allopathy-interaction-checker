"""AushadhiMitra FastAPI Backend V4 — serves React UI + WebSocket trace streaming.

Architecture: Bedrock Flow with DoWhile validation loop (pipeline fallback).
  FlowInput → Planner → DoWhile { AYUSH, Allopathy, Merge, Reasoning, Validation } → Output
  Streams both flow-level and agent-level traces via WebSocket.
"""
import json
import uuid
import logging
import os
from datetime import datetime, date

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from app.config import (
    PLANNER_AGENT_ID, AYUSH_AGENT_ID, ALLOPATHY_AGENT_ID,
    REASONING_AGENT_ID, FLOW_ID, DB_NAME,
)
from app.agent_service import run_check, run_interaction_pipeline, invoke_agent_streaming
from app.db import lookup_curated, get_sources, save_interaction, list_interactions
from app.models import InteractionRequest, HealthResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AushadhiMitra API",
    description="AYUSH-Allopathy Drug Interaction Checker — Flow V4 DoWhile Loop",
    version="4.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _serialize(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


@app.get("/api/health")
async def health():
    return {
        "status": "healthy",
        "architecture": "flow_v4_dowhile_loop",
        "execution_mode": "flow_with_pipeline_fallback",
        "flow": {"id": FLOW_ID, "version": "4", "type": "DoWhile"},
        "agents": {
            "planner": PLANNER_AGENT_ID,
            "ayush": AYUSH_AGENT_ID,
            "allopathy": ALLOPATHY_AGENT_ID,
            "reasoning": REASONING_AGENT_ID,
        },
        "database": DB_NAME,
    }


@app.get("/api/interactions")
async def get_interactions():
    try:
        interactions = list_interactions(20)
        return JSONResponse(content=json.loads(json.dumps(interactions, default=_serialize)))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/check-interaction")
async def check_interaction_rest(req: InteractionRequest):
    """REST endpoint for interaction check (non-streaming)."""
    cached = lookup_curated(req.ayush_name, req.allopathy_name)
    if cached:
        sources = get_sources(cached["interaction_key"])
        return JSONResponse(content=json.loads(json.dumps({
            "cached": True,
            "interaction": cached,
            "sources": sources,
        }, default=_serialize)))

    full_text = ""
    for event_type, data in run_check(req.ayush_name, req.allopathy_name):
        if event_type == "response":
            full_text += data
        elif event_type == "error":
            raise HTTPException(status_code=500, detail=data.get("message", "Pipeline error"))

    return {"cached": False, "response": full_text}


@app.websocket("/ws/check-interaction")
async def ws_check_interaction(websocket: WebSocket):
    """WebSocket endpoint for real-time pipeline trace streaming.

    Expected input: {"ayush_name": "...", "allopathy_name": "...", "mode": "auto|flow|pipeline"}

    Sends structured events:
      {type: "status",         message: "..."}
      {type: "trace",          data: {...}}
      {type: "agent_complete", agent: "...", preview: "..."}
      {type: "validation",     status: "...", ...}
      {type: "cached_result",  interaction: {...}, sources: [...]}
      {type: "response_chunk", text: "..."}
      {type: "complete",       full_response: "...", ...}
      {type: "error",          message: "..."}
    """
    await websocket.accept()

    try:
        data = await websocket.receive_json()
        ayush_name = (data.get("ayush_name") or "").strip()
        allopathy_name = (data.get("allopathy_name") or "").strip()

        # Validate via Pydantic model (reuses field_validator rules)
        try:
            validated = InteractionRequest(
                ayush_name=ayush_name, allopathy_name=allopathy_name
            )
            ayush_name = validated.ayush_name
            allopathy_name = validated.allopathy_name
        except ValidationError as e:
            error_messages = "; ".join(
                err.get("msg", "") for err in e.errors()
            )
            await websocket.send_json({
                "type": "error",
                "message": f"Invalid input: {error_messages}",
            })
            await websocket.close()
            return

        mode = data.get("mode", "auto")
        if mode not in ("auto", "flow", "pipeline"):
            mode = "auto"

        await websocket.send_json({
            "type": "status",
            "message": f"Checking curated database for {ayush_name} + {allopathy_name}...",
        })

        try:
            cached = lookup_curated(ayush_name, allopathy_name)
        except Exception as e:
            logger.warning("Curated DB lookup failed: %s", e)
            cached = None

        if cached:
            try:
                sources = get_sources(cached["interaction_key"])
            except Exception:
                sources = []
            await websocket.send_json({
                "type": "cached_result",
                "interaction": json.loads(json.dumps(cached, default=_serialize)),
                "sources": json.loads(json.dumps(sources, default=_serialize)),
            })
            await websocket.close()
            return

        await websocket.send_json({
            "type": "status",
            "message": f"No cached result. Starting analysis (mode={mode})...",
        })

        session_id = str(uuid.uuid4())
        full_response = ""

        for event_type, event_data in run_check(
            ayush_name, allopathy_name, session_id, mode=mode
        ):
            if event_type == "trace":
                await websocket.send_json({"type": "trace", "data": event_data})

            elif event_type == "agent_complete":
                await websocket.send_json({
                    "type": "agent_complete",
                    "agent": event_data.get("label", ""),
                    "preview": event_data.get("response", "")[:300],
                })

            elif event_type == "validation":
                await websocket.send_json({
                    "type": "validation",
                    "status": event_data.get("status", "UNKNOWN"),
                    "completeness_score": event_data.get("completeness_score", 0),
                    "iteration": event_data.get("iteration", 0),
                    "issues": event_data.get("issues", []),
                    "missing_data": event_data.get("missing_data", []),
                })

            elif event_type == "response":
                full_response += event_data
                await websocket.send_json({
                    "type": "response_chunk",
                    "text": event_data,
                })

            elif event_type == "done":
                await websocket.send_json({
                    "type": "complete",
                    "full_response": full_response,
                    "session_id": session_id,
                    "cached": event_data.get("cached", False),
                    "execution_mode": event_data.get("execution_mode", "unknown"),
                    "loop_iterations": event_data.get("loop_iterations", 0),
                    "pipeline_stages": event_data.get("pipeline_stages", []),
                    "validation_iterations": event_data.get("validation_iterations", 0),
                    "final_validation": event_data.get("final_validation", "UNKNOWN"),
                })

            elif event_type == "error":
                await websocket.send_json({
                    "type": "error",
                    "message": event_data.get("message", "Unknown error"),
                })

        await websocket.close()

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.exception("WebSocket error")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
            await websocket.close()
        except Exception:
            pass


STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    async def serve_index():
        index = os.path.join(STATIC_DIR, "index.html")
        if os.path.isfile(index):
            return FileResponse(index)
        return {"message": "AushadhiMitra API v4.0 — Flow V4 DoWhile Loop"}
else:
    @app.get("/")
    async def root():
        return {"message": "AushadhiMitra API v4.0 — Flow V4 DoWhile Loop"}
