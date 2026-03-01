"""AushadhiMitra FastAPI Backend V3 - serves React UI + WebSocket trace streaming.

Pipeline architecture with validation loop-back:
  Planner → AYUSH → Allopathy → Reasoning+Validation → (loop if NEEDS_MORE_DATA) → Output
  Each agent invoked individually with streaming traces via WebSocket.
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

from app.config import (
    PLANNER_AGENT_ID, AYUSH_AGENT_ID, ALLOPATHY_AGENT_ID,
    REASONING_AGENT_ID, FLOW_ID, DB_NAME,
)
from app.agent_service import run_interaction_pipeline, invoke_agent_streaming
from app.db import lookup_curated, get_sources, save_interaction, list_interactions
from app.models import InteractionRequest, HealthResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AushadhiMitra API",
    description="AYUSH-Allopathy Drug Interaction Checker - Pipeline Architecture",
    version="3.0.0",
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
        "architecture": "pipeline_v3_validation_loopback",
        "max_validation_retries": 2,
        "agents": {
            "planner": PLANNER_AGENT_ID,
            "ayush": AYUSH_AGENT_ID,
            "allopathy": ALLOPATHY_AGENT_ID,
            "reasoning": REASONING_AGENT_ID,
        },
        "flow_id": FLOW_ID,
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
    for event_type, data in run_interaction_pipeline(req.ayush_name, req.allopathy_name):
        if event_type == "response":
            full_text += data
        elif event_type == "error":
            raise HTTPException(status_code=500, detail=data.get("message", "Pipeline error"))

    return {"cached": False, "response": full_text}


@app.websocket("/ws/check-interaction")
async def ws_check_interaction(websocket: WebSocket):
    """WebSocket endpoint for real-time pipeline trace streaming.

    Sends structured events:
    - {type: "status", message: "..."}          — pipeline status
    - {type: "trace", agent: "...", ...}        — agent trace events
    - {type: "cached_result", ...}              — cached result found
    - {type: "response_chunk", text: "..."}     — final response text
    - {type: "complete", ...}                   — pipeline finished
    - {type: "error", message: "..."}           — error occurred
    """
    await websocket.accept()

    try:
        data = await websocket.receive_json()
        ayush_name = data.get("ayush_name", "")
        allopathy_name = data.get("allopathy_name", "")

        if not ayush_name or not allopathy_name:
            await websocket.send_json({
                "type": "error",
                "message": "Both ayush_name and allopathy_name are required",
            })
            await websocket.close()
            return

        await websocket.send_json({
            "type": "status",
            "message": "Checking curated database...",
        })

        cached = lookup_curated(ayush_name, allopathy_name)
        if cached:
            sources = get_sources(cached["interaction_key"])
            await websocket.send_json({
                "type": "cached_result",
                "interaction": json.loads(json.dumps(cached, default=_serialize)),
                "sources": json.loads(json.dumps(sources, default=_serialize)),
            })
            await websocket.close()
            return

        await websocket.send_json({
            "type": "status",
            "message": "No cached result. Starting pipeline with validation loop-back...",
        })

        session_id = str(uuid.uuid4())
        full_response = ""

        for event_type, data in run_interaction_pipeline(
            ayush_name, allopathy_name, session_id
        ):
            if event_type == "trace":
                await websocket.send_json({"type": "trace", **data})

            elif event_type == "agent_complete":
                await websocket.send_json({
                    "type": "agent_complete",
                    "agent": data.get("label", ""),
                    "preview": data.get("response", "")[:300],
                })

            elif event_type == "validation":
                await websocket.send_json({
                    "type": "validation",
                    "status": data.get("status", "UNKNOWN"),
                    "completeness_score": data.get("completeness_score", 0),
                    "iteration": data.get("iteration", 0),
                    "issues": data.get("issues", []),
                    "missing_data": data.get("missing_data", []),
                })

            elif event_type == "response":
                full_response += data
                await websocket.send_json({
                    "type": "response_chunk",
                    "text": data,
                })

            elif event_type == "done":
                await websocket.send_json({
                    "type": "complete",
                    "full_response": full_response,
                    "session_id": session_id,
                    "cached": data.get("cached", False),
                    "pipeline_stages": data.get("pipeline_stages", []),
                    "validation_iterations": data.get("validation_iterations", 0),
                    "final_validation": data.get("final_validation", "UNKNOWN"),
                })

            elif event_type == "error":
                await websocket.send_json({
                    "type": "error",
                    "message": data.get("message", "Unknown error"),
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
        return {"message": "AushadhiMitra API v3.0 - Pipeline with Validation Loop-back"}
else:
    @app.get("/")
    async def root():
        return {"message": "AushadhiMitra API v3.0 - Pipeline with Validation Loop-back"}
