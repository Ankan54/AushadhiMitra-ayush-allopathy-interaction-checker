#!/usr/bin/env python3
"""
Unified Log Viewer for AushadhiMitra.

Combines flow execution logs with model invocation logs to show:
- Which flow step is executing
- Which model was called
- Token usage

Usage:
    python scripts/view_unified_logs.py                  # Last 30 minutes
    python scripts/view_unified_logs.py --minutes 60    # Last hour
"""
import boto3
import json
import argparse
from datetime import datetime, timedelta
from collections import defaultdict

FLOW_LOG_GROUP = "/aws/bedrock/ausadhi-mitra-flow-logs"
MODEL_LOG_GROUP = "bedrock_agents"
REGION = "us-east-1"


def get_flow_logs(client, start_time_ms: int):
    """Get flow execution logs."""
    try:
        response = client.get_log_events(
            logGroupName=FLOW_LOG_GROUP,
            logStreamName="flow-executions",
            startTime=start_time_ms,
            limit=500,
        )
        return response.get("events", [])
    except Exception as e:
        print(f"Error fetching flow logs: {e}")
        return []


def get_model_logs(client, start_time_ms: int):
    """Get model invocation logs."""
    try:
        response = client.filter_log_events(
            logGroupName=MODEL_LOG_GROUP,
            startTime=start_time_ms,
            limit=500,
        )
        return response.get("events", [])
    except Exception as e:
        print(f"Error fetching model logs: {e}")
        return []


def format_model_name(model_id: str) -> str:
    """Shorten model ID for display."""
    if "nova-premier" in model_id:
        return "Nova Premier"
    elif "nova-pro" in model_id:
        return "Nova Pro"
    elif "claude" in model_id.lower():
        return model_id.split("/")[-1].split(":")[0]
    return model_id.split(":")[-1][:20]


def main():
    parser = argparse.ArgumentParser(description="View unified AushadhiMitra logs")
    parser.add_argument("--minutes", type=int, default=30, help="Minutes of history")
    args = parser.parse_args()
    
    client = boto3.client("logs", region_name=REGION)
    start_time = int((datetime.utcnow() - timedelta(minutes=args.minutes)).timestamp() * 1000)
    
    print(f"AushadhiMitra Unified Logs (last {args.minutes} minutes)")
    print("=" * 90)
    
    # Get both log types
    flow_events = get_flow_logs(client, start_time)
    model_events = get_model_logs(client, start_time)
    
    # Parse flow events
    flows = defaultdict(list)
    for e in flow_events:
        try:
            msg = json.loads(e.get("message", "{}"))
            ts = e.get("timestamp", 0)
            sid = msg.get("session_id", "")[:8]
            flows[sid].append((ts, "flow", msg))
        except:
            pass
    
    # Parse model events
    model_calls = []
    for e in model_events:
        try:
            msg = json.loads(e.get("message", "{}"))
            ts = e.get("timestamp", 0)
            model_calls.append((ts, "model", msg))
        except:
            pass
    
    # Merge and sort by timestamp
    all_events = []
    for sid, events in flows.items():
        for ts, typ, msg in events:
            all_events.append((ts, typ, sid, msg))
    for ts, typ, msg in model_calls:
        all_events.append((ts, typ, "", msg))
    
    all_events.sort(key=lambda x: x[0])
    
    if not all_events:
        print("No events found.")
        return
    
    # Display grouped by flow session
    current_session = None
    session_start = None
    
    for ts, typ, sid, msg in all_events:
        dt = datetime.utcfromtimestamp(ts/1000).strftime('%H:%M:%S')
        
        if typ == "flow":
            event = msg.get("event", "?")
            
            if event in ("FLOW_START", "flow_start"):
                if current_session != sid:
                    if current_session:
                        print()
                    print(f"\n{'='*90}")
                    print(f"SESSION: {sid}... | {msg.get('ayush_drug', '')} + {msg.get('allopathy_drug', '')}")
                    print(f"{'='*90}")
                    current_session = sid
                    session_start = ts
                print(f"{dt} | {'START':12s} | Beginning flow execution")
                
            elif event in ("FLOW_COMPLETE", "flow_complete"):
                duration = msg.get("duration_ms", 0)
                status = msg.get("status", "?")
                result = msg.get("result", {})
                severity = result.get("severity", "?")
                print(f"{dt} | {'COMPLETE':12s} | status={status} duration={duration/1000:.1f}s severity={severity}")
                
            elif event == "NODE_EXECUTION":
                node = msg.get("node", "?")
                step = msg.get("step_type", "")
                model = msg.get("model", "")
                in_tok = msg.get("input_tokens", "")
                out_tok = msg.get("output_tokens", "")
                
                line = f"{dt} | {msg.get('agent', '?'):12s} | {node}"
                if model:
                    line += f" -> {format_model_name(model)}"
                if in_tok or out_tok:
                    line += f" [{in_tok}/{out_tok} tokens]"
                print(line)
                
            elif event == "FLOW_ERROR":
                print(f"{dt} | {'ERROR':12s} | {msg.get('error_type', '?')}: {msg.get('error_message', '')[:60]}")
                
        elif typ == "model" and current_session:
            # Model invocation during active flow session
            model_id = msg.get("modelId", "?")
            operation = msg.get("operation", "?")
            in_tokens = msg.get("inputTokenCount", 0)
            out_tokens = msg.get("outputTokenCount", 0)
            
            # Only show if within 30 seconds of last flow event and has meaningful data
            if in_tokens or out_tokens:
                model_short = format_model_name(model_id)
                print(f"{dt} | {'MODEL':12s} | {operation} -> {model_short} [{in_tokens}/{out_tokens} tokens]")
    
    print(f"\n{'='*90}")
    print(f"Total flow sessions: {len(flows)}")
    print(f"Total model invocations: {len(model_calls)}")


if __name__ == "__main__":
    main()
