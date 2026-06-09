#!/usr/bin/env python3
"""
CLI trace viewer — pretty-prints all events for a given trace ID.

Usage:
    python observability/trace_viewer.py --trace-id <id>
    python observability/trace_viewer.py --recent 20
    python observability/trace_viewer.py --list-traces
"""
import argparse
import json
import os
import sqlite3
import sys

DB_PATH = os.getenv("AUDIT_DB_PATH", "data/audit.db")

COLORS = {
    "tool_call": "\033[94m",
    "approval_request": "\033[93m",
    "approval_decision": "\033[92m",
    "policy_eval": "\033[95m",
    "agent_turn": "\033[96m",
    "error": "\033[91m",
    "reset": "\033[0m",
}


def fmt_event(event: dict) -> str:
    ts = event.get("timestamp", "")[:19]
    etype = event.get("event_type", "unknown")
    actor = event.get("actor", "")
    outcome = event.get("outcome", "")
    color = COLORS.get(etype, "")
    reset = COLORS["reset"]
    details = event.get("details", {})
    detail_str = ""
    if etype == "tool_call":
        tool = details.get("tool", actor)
        result = str(details.get("result", ""))[:80]
        error = details.get("error", "")
        detail_str = f"tool={tool} result={result!r}" if result else f"tool={tool} error={error}"
    elif etype == "policy_eval":
        detail_str = (
            f"action={details.get('action')} matched={details.get('matched_rules')} "
            f"reason={details.get('reason','')[:60]}"
        )
    elif etype == "approval_request":
        detail_str = f"tool={details.get('tool_name')} side_effect={details.get('side_effect_class')}"
    elif etype == "approval_decision":
        detail_str = f"approved={details.get('approved')} by={details.get('decided_by')}"
    elif etype == "agent_turn":
        detail_str = f"input={details.get('user_input','')[:50]!r} tools={details.get('tool_call_count',0)}"
    return f"{color}[{ts}] {etype.upper():20s} actor={actor:20s} outcome={outcome:12s} {detail_str}{reset}"


def get_events_by_trace(trace_id: str) -> list:
    if not os.path.exists(DB_PATH):
        print(f"Audit DB not found at {DB_PATH}")
        sys.exit(1)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM audit_log WHERE trace_id = ? ORDER BY timestamp ASC",
        (trace_id,)
    ).fetchall()
    conn.close()
    result = []
    for row in rows:
        d = dict(row)
        d["details"] = json.loads(d["details"])
        result.append(d)
    return result


def get_recent(limit: int) -> list:
    if not os.path.exists(DB_PATH):
        print(f"Audit DB not found at {DB_PATH}")
        sys.exit(1)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    result = []
    for row in rows:
        d = dict(row)
        d["details"] = json.loads(d["details"])
        result.append(d)
    return list(reversed(result))


def list_traces() -> list:
    if not os.path.exists(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT trace_id, COUNT(*) as event_count, MIN(timestamp) as started, MAX(timestamp) as ended "
        "FROM audit_log GROUP BY trace_id ORDER BY started DESC LIMIT 20"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def main():
    parser = argparse.ArgumentParser(description="Agentic AI Harness — Trace Viewer")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--trace-id", help="Show all events for a specific trace ID")
    group.add_argument("--recent", type=int, metavar="N", help="Show N most recent events")
    group.add_argument("--list-traces", action="store_true", help="List recent trace IDs")
    args = parser.parse_args()

    if args.trace_id:
        events = get_events_by_trace(args.trace_id)
        if not events:
            print(f"No events found for trace: {args.trace_id}")
            sys.exit(1)
        print(f"\n{'='*80}")
        print(f"TRACE: {args.trace_id}  ({len(events)} events)")
        print(f"{'='*80}")
        for event in events:
            print(fmt_event(event))
        print(f"{'='*80}\n")
    elif args.recent:
        events = get_recent(args.recent)
        print(f"\n{'='*80}")
        print(f"RECENT {len(events)} EVENTS")
        print(f"{'='*80}")
        for event in events:
            print(fmt_event(event))
        print(f"{'='*80}\n")
    elif args.list_traces:
        traces = list_traces()
        if not traces:
            print("No traces found.")
            sys.exit(0)
        print(f"\n{'='*80}")
        print(f"{'TRACE ID':40s} {'EVENTS':8s} {'STARTED':20s}")
        print(f"{'='*80}")
        for t in traces:
            print(f"{t['trace_id']:40s} {t['event_count']:8d} {t['started'][:19]:20s}")
        print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
