"""AushadhiMitra FastAPI Backend — CO-MAS Multi-Agent Pipeline.

Architecture: POST /api/check starts background thread → /ws/{session_id} streams events.
"""
import json
import uuid
import queue
import logging
import threading
import os
import asyncio
from datetime import datetime, date

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import (
    PLANNER_AGENT_ID, AYUSH_AGENT_ID, ALLOPATHY_AGENT_ID,
    REASONING_AGENT_ID, RESEARCH_AGENT_ID, DB_NAME,
)
from app.models import InteractionRequest
from app.agent_service import run_check
from app.db import lookup_curated, get_sources, save_interaction, list_interactions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# FastAPI app
# ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="AushadhiMitra API",
    description="AYUSH-Allopathy Drug Interaction Checker — CO-MAS Multi-Agent Pipeline",
    version="6.0.0",
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


# ──────────────────────────────────────────────────────────────
# Session queues for POST → WebSocket pattern
# ──────────────────────────────────────────────────────────────

_SESSION_QUEUES: dict[str, queue.Queue] = {}
_SESSION_LOCK = threading.Lock()


def _cleanup_session(session_id: str):
    with _SESSION_LOCK:
        _SESSION_QUEUES.pop(session_id, None)


# ──────────────────────────────────────────────────────────────
# Trace → UI event mapping
# ──────────────────────────────────────────────────────────────

def _map_trace_to_ui_event(event_type: str, data: dict) -> dict | None:
    """Map internal pipeline events to structured UI events."""

    if event_type == "pipeline_status":
        status = data.get("status", "")
        message = data.get("message", "")

        if status == "name_resolution":
            return {
                "type": "pipeline_status",
                "status": "name_resolution",
                "message": message,
                "scientific_name": data.get("scientific_name"),
                "original_name": data.get("original_name"),
                "imppat_url": data.get("imppat_url"),
                "valid": data.get("valid"),
            }

        if status == "input_validation":
            return {
                "type": "pipeline_status",
                "status": "input_validation",
                "message": message,
                "valid": data.get("valid"),
                "supported_drugs": data.get("supported_drugs", []),
            }

        if status == "iteration_start":
            return {
                "type": "pipeline_status",
                "status": "iteration_start",
                "iteration": data.get("iteration", 1),
                "message": message,
            }

        if status == "phase_proposer":
            return {
                "type": "pipeline_status",
                "status": "phase_proposer",
                "iteration": data.get("iteration"),
                "message": message,
            }

        if status == "phase_evaluator":
            return {
                "type": "pipeline_status",
                "status": "phase_evaluator",
                "iteration": data.get("iteration"),
                "message": message,
            }

        if status == "phase_scorer":
            return {
                "type": "pipeline_status",
                "status": "phase_scorer",
                "iteration": data.get("iteration"),
                "message": message,
            }

        if status == "gap_identified":
            return {
                "type": "pipeline_status",
                "status": "gap_identified",
                "iteration": data.get("iteration"),
                "gap": data.get("gap"),
                "message": message,
            }

        if status in ("iteration_retry", "formatting"):
            return {
                "type": "pipeline_status",
                "status": status,
                "iteration": data.get("iteration"),
                "message": message,
            }

        return {"type": "pipeline_status", "status": status, "message": message}

    if event_type == "trace":
        trace_type = data.get("type", "")
        agent = data.get("agent", "")

        if trace_type == "thinking":
            return {
                "type": "agent_thinking",
                "agent": agent,
                "agent_key": data.get("agent_key", ""),
                "iteration": data.get("iteration"),
                "message": data.get("message", ""),
            }

        if trace_type == "model_input":
            return {
                "type": "llm_call",
                "agent": agent,
                "agent_key": data.get("agent_key", ""),
                "iteration": data.get("iteration"),
                "message": data.get("message", ""),
                "prompt_preview": data.get("prompt_preview", ""),
            }

        if trace_type == "model_output":
            return {
                "type": "llm_response",
                "agent": agent,
                "agent_key": data.get("agent_key", ""),
                "iteration": data.get("iteration"),
                "message": data.get("message", ""),
                "tokens": data.get("tokens", {}),
            }

        if trace_type == "tool_call":
            return {
                "type": "tool_call",
                "agent": agent,
                "agent_key": data.get("agent_key", ""),
                "iteration": data.get("iteration"),
                "message": data.get("message", ""),
                "function": data.get("function", ""),
                "parameters": data.get("parameters", {}),
            }

        if trace_type == "tool_result":
            return {
                "type": "tool_result",
                "agent": agent,
                "agent_key": data.get("agent_key", ""),
                "iteration": data.get("iteration"),
                "message": data.get("message", ""),
            }

        if trace_type == "agent_complete":
            return {
                "type": "agent_complete",
                "agent": agent,
                "agent_key": data.get("agent_key", ""),
                "iteration": data.get("iteration"),
                "message": data.get("message", ""),
            }

    return None


# ──────────────────────────────────────────────────────────────
# Background pipeline thread
# ──────────────────────────────────────────────────────────────

def _pipeline_thread(session_id: str, ayush_name: str, allopathy_name: str):
    """Run CO-MAS pipeline in background, push events to session queue."""
    q = _SESSION_QUEUES.get(session_id)
    if not q:
        return

    try:
        for event_type, data in run_check(ayush_name, allopathy_name, session_id):
            q.put((event_type, data))
    except Exception as e:
        logger.exception("Pipeline thread error")
        q.put(("error", {"message": str(e)}))
    finally:
        q.put(("__done__", {}))


# ──────────────────────────────────────────────────────────────
# REST endpoints
# ──────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {
        "status": "healthy",
        "architecture": "co_mas_multi_agent",
        "agents": {
            "planner": PLANNER_AGENT_ID,
            "ayush": AYUSH_AGENT_ID,
            "allopathy": ALLOPATHY_AGENT_ID,
            "research": RESEARCH_AGENT_ID,
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


@app.post("/api/check")
async def start_check(req: InteractionRequest):
    """Start CO-MAS pipeline in background; return session_id for WebSocket streaming."""
    session_id = str(uuid.uuid4())

    # Check curated DB cache first
    try:
        cached = lookup_curated(req.ayush_name, req.allopathy_name)
    except Exception:
        cached = None

    q: queue.Queue = queue.Queue()
    with _SESSION_LOCK:
        _SESSION_QUEUES[session_id] = q

    if cached:
        try:
            sources = get_sources(cached.get("interaction_key", ""))
        except Exception:
            sources = []
        q.put(("__cached__", {"interaction": cached, "sources": sources}))
        q.put(("__done__", {}))
    else:
        t = threading.Thread(
            target=_pipeline_thread,
            args=(session_id, req.ayush_name, req.allopathy_name),
            daemon=True,
        )
        t.start()

    return {"session_id": session_id}


# ──────────────────────────────────────────────────────────────
# WebSocket streaming endpoint
# ──────────────────────────────────────────────────────────────

@app.websocket("/ws/{session_id}")
async def ws_stream(websocket: WebSocket, session_id: str):
    """Stream pipeline events for a given session_id."""
    await websocket.accept()

    # Wait for the session queue to appear (pipeline thread may not have started yet)
    for _ in range(50):
        with _SESSION_LOCK:
            q = _SESSION_QUEUES.get(session_id)
        if q is not None:
            break
        await asyncio.sleep(0.1)

    if q is None:
        await websocket.send_json({"type": "error", "message": "Session not found"})
        await websocket.close()
        return

    final_result = None

    try:
        while True:
            try:
                event_type, data = q.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.05)
                continue

            if event_type == "__cached__":
                interaction = data.get("interaction", {})
                sources = data.get("sources", [])
                await websocket.send_json({
                    "type": "complete",
                    "result": interaction,
                    "cached": True,
                    "sources": json.loads(json.dumps(sources, default=_serialize)),
                    "session_id": session_id,
                })
                continue

            if event_type == "__done__":
                if final_result is not None:
                    await websocket.send_json({
                        "type": "complete",
                        "result": final_result,
                        "cached": False,
                        "session_id": session_id,
                    })
                break

            if event_type == "error":
                msg = data.get("message", "Unknown error") if isinstance(data, dict) else str(data)
                supported = data.get("supported_drugs", []) if isinstance(data, dict) else []
                await websocket.send_json({
                    "type": "error",
                    "message": msg,
                    "supported_drugs": supported,
                })
                break

            if event_type == "done":
                final_result = data.get("result", {})
                # Don't break — wait for __done__ sentinel
                continue

            # Map trace/pipeline events to UI events
            ui_event = _map_trace_to_ui_event(event_type, data if isinstance(data, dict) else {})
            if ui_event:
                try:
                    await websocket.send_json(ui_event)
                except Exception:
                    pass

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        logger.exception("WebSocket error")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        _cleanup_session(session_id)
        try:
            await websocket.close()
        except Exception:
            pass


@app.websocket("/ws/check")
async def ws_check_legacy(websocket: WebSocket):
    """Legacy WebSocket endpoint — guides clients to the new POST /api/check flow."""
    await websocket.accept()
    await websocket.send_json({
        "type": "error",
        "message": (
            "This endpoint is deprecated. "
            "POST to /api/check to get a session_id, "
            "then connect to /ws/{session_id}."
        ),
    })
    await websocket.close()


# ──────────────────────────────────────────────────────────────
# Static files / SPA
# ──────────────────────────────────────────────────────────────

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")

if os.path.isdir(STATIC_DIR):
    assets_dir = os.path.join(STATIC_DIR, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/")
    async def serve_index():
        index = os.path.join(STATIC_DIR, "index.html")
        if os.path.isfile(index):
            return FileResponse(index)
        return {"message": "AushadhiMitra API v6.0 — CO-MAS Pipeline"}

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Catch-all for SPA client-side routing."""
        if full_path.startswith("api/") or full_path.startswith("ws/"):
            raise HTTPException(status_code=404)
        index = os.path.join(STATIC_DIR, "index.html")
        if os.path.isfile(index):
            return FileResponse(index)
        raise HTTPException(status_code=404)
else:
    @app.get("/")
    async def root():
        return {"message": "AushadhiMitra API v6.0 — CO-MAS Multi-Agent Pipeline"}
