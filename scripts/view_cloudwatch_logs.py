#!/usr/bin/env python3
"""
View CloudWatch logs for Bedrock model invocations.

Usage:
    python scripts/view_cloudwatch_logs.py               # Last 15 minutes
    python scripts/view_cloudwatch_logs.py --minutes 60  # Last hour
    python scripts/view_cloudwatch_logs.py --follow      # Tail logs
"""
import boto3
import json
import argparse
import time
from datetime import datetime, timedelta

LOG_GROUP = "bedrock_agents"
REGION = "us-east-1"


def format_log_event(event: dict) -> str:
    """Format a single log event for display."""
    try:
        msg = json.loads(event.get("message", "{}"))
        ts = msg.get("timestamp", "")
        model = msg.get("modelId", "unknown")[:30]
        operation = msg.get("operation", "?")
        
        # Extract input/output preview
        input_data = msg.get("input", {})
        output_data = msg.get("output", {})
        
        input_preview = ""
        if isinstance(input_data, dict):
            messages = input_data.get("messages", [])
            if messages:
                content = messages[-1].get("content", [])
                if content and isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("text"):
                            input_preview = c["text"][:100]
                            break
        
        output_preview = ""
        if isinstance(output_data, dict):
            output_msg = output_data.get("message", {})
            content = output_msg.get("content", [])
            if content and isinstance(content, list):
                for c in content:
                    if isinstance(c, dict) and c.get("text"):
                        output_preview = c["text"][:100]
                        break
        
        tokens_in = msg.get("inputTokenCount", 0)
        tokens_out = msg.get("outputTokenCount", 0)
        
        lines = [
            f"[{ts}] {operation} | {model}",
            f"  Tokens: in={tokens_in}, out={tokens_out}",
        ]
        if input_preview:
            lines.append(f"  Input: {input_preview}...")
        if output_preview:
            lines.append(f"  Output: {output_preview}...")
        
        return "\n".join(lines)
    except Exception as e:
        return f"[Error parsing log] {str(e)}"


def get_logs(minutes: int = 15, limit: int = 50):
    """Fetch recent logs from CloudWatch."""
    client = boto3.client("logs", region_name=REGION)
    
    start_time = int((datetime.utcnow() - timedelta(minutes=minutes)).timestamp() * 1000)
    
    print(f"Fetching logs from last {minutes} minutes (log group: {LOG_GROUP})")
    print("=" * 80)
    
    try:
        response = client.filter_log_events(
            logGroupName=LOG_GROUP,
            startTime=start_time,
            limit=limit,
        )
        
        events = response.get("events", [])
        print(f"Found {len(events)} log events\n")
        
        for event in events:
            print(format_log_event(event))
            print("-" * 60)
            
    except Exception as e:
        print(f"Error fetching logs: {e}")


def tail_logs(interval: int = 5):
    """Continuously tail logs."""
    client = boto3.client("logs", region_name=REGION)
    
    print(f"Tailing logs from {LOG_GROUP} (Ctrl+C to stop)")
    print("=" * 80)
    
    last_timestamp = int((datetime.utcnow() - timedelta(seconds=30)).timestamp() * 1000)
    seen_ids = set()
    
    try:
        while True:
            response = client.filter_log_events(
                logGroupName=LOG_GROUP,
                startTime=last_timestamp,
                limit=20,
            )
            
            events = response.get("events", [])
            for event in events:
                event_id = event.get("eventId")
                if event_id not in seen_ids:
                    seen_ids.add(event_id)
                    print(format_log_event(event))
                    print("-" * 60)
                    last_timestamp = max(last_timestamp, event.get("timestamp", 0) + 1)
            
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print("\nStopped tailing logs.")


def main():
    parser = argparse.ArgumentParser(description="View Bedrock CloudWatch logs")
    parser.add_argument("--minutes", type=int, default=15, help="Minutes of history to fetch")
    parser.add_argument("--limit", type=int, default=50, help="Max events to fetch")
    parser.add_argument("--follow", "-f", action="store_true", help="Tail logs continuously")
    parser.add_argument("--interval", type=int, default=5, help="Poll interval for --follow (seconds)")
    
    args = parser.parse_args()
    
    if args.follow:
        tail_logs(args.interval)
    else:
        get_logs(args.minutes, args.limit)


if __name__ == "__main__":
    main()
