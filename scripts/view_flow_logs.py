#!/usr/bin/env python3
"""
View AushadhiMitra Flow execution logs from CloudWatch.

Shows step-by-step execution with which nodes called which models.

Usage:
    python scripts/view_flow_logs.py                  # Last 30 minutes
    python scripts/view_flow_logs.py --minutes 60    # Last hour
    python scripts/view_flow_logs.py --session <id>  # Specific session
"""
import boto3
import json
import argparse
from datetime import datetime, timedelta

LOG_GROUP = "/aws/bedrock/ausadhi-mitra-flow-logs"
REGION = "us-east-1"


def get_logs(minutes: int = 30, session_filter: str = None):
    client = boto3.client("logs", region_name=REGION)
    
    start_time = int((datetime.utcnow() - timedelta(minutes=minutes)).timestamp() * 1000)
    
    print(f"Flow Execution Logs (last {minutes} minutes)")
    print("=" * 80)
    
    try:
        response = client.get_log_events(
            logGroupName=LOG_GROUP,
            logStreamName="flow-executions",
            startTime=start_time,
            limit=500,
        )
        
        events = response.get("events", [])
        
        # Group by session
        sessions = {}
        for e in events:
            try:
                msg = json.loads(e.get("message", "{}"))
                sid = msg.get("session_id", "unknown")[:8]
                if session_filter and session_filter not in msg.get("session_id", ""):
                    continue
                if sid not in sessions:
                    sessions[sid] = []
                sessions[sid].append(msg)
            except:
                pass
        
        if not sessions:
            print("No flow executions found.")
            return
        
        for sid, events in sessions.items():
            print(f"\n{'='*80}")
            print(f"SESSION: {sid}...")
            print(f"{'='*80}")
            
            for msg in events:
                event = msg.get("event", "?")
                ts = msg.get("timestamp", "")[:19]
                
                if event == "FLOW_START":
                    print(f"\n{ts} | START")
                    print(f"  Drugs: {msg.get('ayush_drug')} + {msg.get('allopathy_drug')}")
                    
                elif event == "FLOW_COMPLETE":
                    print(f"\n{ts} | COMPLETE")
                    print(f"  Status: {msg.get('status')}")
                    print(f"  Duration: {msg.get('duration_ms', 0)/1000:.1f}s")
                    print(f"  Iterations: {msg.get('loop_iterations', 0)}")
                    result = msg.get("result", {})
                    if result:
                        print(f"  Severity: {result.get('severity')} (score: {result.get('severity_score')})")
                        
                elif event == "NODE_EXECUTION":
                    node = msg.get("node", "?")
                    agent = msg.get("agent", "?")
                    step_type = msg.get("step_type", "?")
                    model = msg.get("model")
                    in_tok = msg.get("input_tokens")
                    out_tok = msg.get("output_tokens")
                    
                    tokens_str = ""
                    if in_tok or out_tok:
                        tokens_str = f" [tokens: {in_tok or '?'}/{out_tok or '?'}]"
                    
                    model_str = f" -> {model}" if model else ""
                    
                    print(f"{ts} | {agent:12s} | {step_type:15s}{model_str}{tokens_str}")
                    
                elif event == "NODE_TRACE":
                    node = msg.get("node", "?")
                    trace_type = msg.get("trace_type", "?")
                    preview = msg.get("input_preview", "")[:60]
                    if preview:
                        print(f"{ts} | {node:12s} | {trace_type}: {preview}...")
                        
                elif event == "FLOW_ERROR":
                    print(f"\n{ts} | ERROR")
                    print(f"  Type: {msg.get('error_type')}")
                    print(f"  Message: {msg.get('error_message')[:100]}")
                    
        print(f"\n{'='*80}")
        print(f"Total sessions: {len(sessions)}")
        
    except Exception as e:
        print(f"Error fetching logs: {e}")


def main():
    parser = argparse.ArgumentParser(description="View AushadhiMitra flow logs")
    parser.add_argument("--minutes", type=int, default=30, help="Minutes of history")
    parser.add_argument("--session", type=str, help="Filter by session ID prefix")
    args = parser.parse_args()
    
    get_logs(args.minutes, args.session)


if __name__ == "__main__":
    main()
