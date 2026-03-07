#!/usr/bin/env python3
"""
Streaming interaction check client for AushadhiMitra.

Connects to the deployed EC2 backend WebSocket, sends a sample payload,
and prints all streaming events (status, traces, validation) plus the final output.

Default: Deployed EC2 at http://3.210.198.169 (production).

Usage:
  pip install websockets
  python scripts/run_check_streaming.py
  python scripts/run_check_streaming.py Tulsi Warfarin
  python scripts/run_check_streaming.py --url http://localhost:8000  # local dev

Override via env: AUShadhiMitra_WS_URL, AYUSH_NAME, ALLOPATHY_NAME, MODE
"""

import argparse
import asyncio
import json
import os
import sys

# Deployed EC2 instance (production backend) — override via EC2_BASE_URL env var
EC2_BASE_URL = os.environ.get("EC2_BASE_URL", "http://localhost:8000")
BASE_URL = os.environ.get("AUShadhiMitra_WS_URL", EC2_BASE_URL)
WS_URL = None  # set in main() from BASE_URL or --url


def get_payload(ayush: str = None, allopathy: str = None, mode: str = None) -> dict:
    return {
        "ayush_name": ayush or os.environ.get("AYUSH_NAME", "Ashwagandha"),
        "allopathy_name": allopathy or os.environ.get("ALLOPATHY_NAME", "Metformin"),
        "mode": mode or os.environ.get("MODE", "auto"),
    }


def print_event(seq: int, event_type: str, data: dict) -> None:
    """Print one event in a readable way."""
    if event_type == "status":
        print(f"  [{seq}] STATUS: {data.get('message', '')}")
    elif event_type == "trace":
        d = data.get("data", data)
        t = d.get("type", "?")
        agent = d.get("agent", "?")
        msg = (d.get("message") or "")[:200]
        print(f"  [{seq}] TRACE ({t}) {agent}: {msg}")
    elif event_type == "agent_complete":
        agent = data.get("agent", "?")
        preview = (data.get("preview") or "")[:150]
        print(f"  [{seq}] AGENT_DONE: {agent} — {preview}...")
    elif event_type == "validation":
        status = data.get("status", "?")
        score = data.get("completeness_score", "?")
        it = data.get("iteration", "?")
        print(f"  [{seq}] VALIDATION: status={status} score={score} iteration={it}")
    elif event_type == "response_chunk":
        n = len(data.get("text", ""))
        print(f"  [{seq}] CHUNK: {n} chars")
    elif event_type == "complete":
        print(f"  [{seq}] COMPLETE: mode={data.get('execution_mode')} "
              f"loops={data.get('loop_iterations')} val_iter={data.get('validation_iterations')} "
              f"final_val={data.get('final_validation')}")
    elif event_type == "error":
        print(f"  [{seq}] ERROR: {data.get('message', '')[:400]}")
    elif event_type == "cached_result":
        print(f"  [{seq}] CACHED_RESULT (see full_response below)")
    else:
        print(f"  [{seq}] {event_type}: {str(data)[:200]}")


async def run(ws_url: str, payload: dict):
    try:
        import websockets
    except ImportError:
        print("Install websockets: pip install websockets", file=sys.stderr)
        sys.exit(1)

    print("AushadhiMitra — Streaming interaction check")
    print("=" * 60)
    print(f"URL: {ws_url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    print("=" * 60)

    try:
        async with websockets.connect(
            ws_url,
            ping_interval=None,
            ping_timeout=None,
            close_timeout=10,
            max_size=10 * 1024 * 1024,
        ) as ws:
            await ws.send(json.dumps(payload))
            seq = 0
            full_response = ""

            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=300)
                except asyncio.TimeoutError:
                    print("\n[TIMEOUT] No message in 300s")
                    break

                seq += 1
                data = json.loads(msg)
                event_type = data.get("type", "unknown")

                print_event(seq, event_type, data)

                if event_type == "response_chunk":
                    full_response += data.get("text", "")
                if event_type == "complete":
                    full_response = data.get("full_response", full_response)
                    break
                if event_type == "error":
                    break
                if event_type == "cached_result":
                    interaction = data.get("interaction", {})
                    full_response = json.dumps(interaction, indent=2)
                    break

            print()
            print("=" * 60)
            print("FINAL OUTPUT")
            print("=" * 60)
            if full_response:
                print(full_response)
            else:
                print("(no response body)")
            print()
            print(f"Total events: {seq}")

    except Exception as e:
        print(f"Connection error: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="AushadhiMitra streaming interaction check")
    parser.add_argument("ayush_name", nargs="?", default=None, help="AYUSH substance (default: Ashwagandha)")
    parser.add_argument("allopathy_name", nargs="?", default=None, help="Allopathy drug (default: Metformin)")
    parser.add_argument("--url", default=BASE_URL, help=f"Base URL (default: {BASE_URL})")
    parser.add_argument("--mode", choices=("auto", "flow", "pipeline"), default=None, help="Execution mode")
    args = parser.parse_args()

    ws_base = args.url.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_base}/ws/check-interaction"
    payload = get_payload(args.ayush_name, args.allopathy_name, args.mode)

    asyncio.run(run(ws_url, payload))


if __name__ == "__main__":
    main()
