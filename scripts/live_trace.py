"""
live_trace.py — Connect to the live WebSocket and print every trace event
exactly as the UI would receive them, then render the final response.

Usage:  python scripts/live_trace.py [ayush] [allopathy] [mode]
        python scripts/live_trace.py turmeric warfarin pipeline
"""
import asyncio, json, sys, time, textwrap, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import websockets

AYUSH     = sys.argv[1] if len(sys.argv) > 1 else "turmeric"
ALLOPATHY = sys.argv[2] if len(sys.argv) > 2 else "warfarin"
MODE      = sys.argv[3] if len(sys.argv) > 3 else "pipeline"
WS_URL    = "ws://localhost:8000/ws/check-interaction"

# ── ANSI colours ──────────────────────────────────────────────────────────────
R = "\033[0m"
BOLD = "\033[1m"
GREY = "\033[90m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
RED = "\033[91m"
WHITE = "\033[97m"

def c(text, *codes): return "".join(codes) + str(text) + R
def ts(): return c(f"[{time.strftime('%H:%M:%S')}]", GREY)
def divider(label="", ch="-", w=72):
    if label:
        pad = (w - len(label) - 2) // 2
        print(c(ch*pad + f" {label} " + ch*(w - pad - len(label) - 2), GREY))
    else:
        print(c(ch*w, GREY))

TRACE_ICONS = {
    "pipeline_step":          (">>", CYAN+BOLD),
    "step_start":             ("->", BLUE),
    "loop_iteration":         (" @", YELLOW+BOLD),
    "thinking":               (" ~", MAGENTA),
    "tool_call":              (" T", YELLOW),
    "tool_result":            (" R", GREEN),
    "model_input":            (" .", GREY),
    "model_output":           (" .", GREY),
    "final_response":         (" *", GREEN+BOLD),
    "agent_error":            (" !", RED+BOLD),
    "retry":                  (" ~", YELLOW),
    "fallback":               (" F", YELLOW+BOLD),
    "flow_start":             (" F", CYAN+BOLD),
    "node_input":             (" <", GREY),
    "node_output":            (" >", GREY),
    "preprocessing":          (" p", GREY),
    "condition":              (" C", YELLOW),
    "validation_max_retries": (" !", RED+BOLD),
    "warning":                (" W", YELLOW),
    "code_interpreter":       (" #", CYAN),
    "code_result":            (" #", GREEN),
}

def render_trace(d):
    t    = d.get("type", "processing")
    agt  = d.get("agent", "")
    msg  = d.get("message", "")
    node = d.get("node", "")
    icon, col = TRACE_ICONS.get(t, (" .", GREY))
    short = (msg[:220] + "...") if len(msg) > 220 else msg
    agent_tag = c(f"[{agt}]", CYAN) if agt else ""
    node_tag  = c(f"[{node}]", GREY) if (node and node != agt) else ""
    print(f"{ts()} {c(f'[{icon}]', col)} {agent_tag}{node_tag} {short}")
    if t == "tool_call" and d.get("parameters"):
        for k, v in list(d["parameters"].items())[:6]:
            val = str(v)
            val = (val[:120] + "...") if len(val) > 120 else val
            print(c(f"             {k}: {val}", GREY))
    if t == "tool_result":
        snippet = msg.replace("Tool returned: ", "")[:180]
        print(c(f"             => {snippet}", GREEN))

async def run():
    print()
    divider(f"AushadhiMitra -- Live Pipeline Trace", "=", 72)
    print(c(f"  Query:  {AYUSH}  +  {ALLOPATHY}", BOLD))
    print(c(f"  Mode:   {MODE}", GREY))
    print(c(f"  URL:    {WS_URL}", GREY))
    divider("", "=", 72)

    counts = {}
    full_response = ""
    t0 = time.time()

    async with websockets.connect(
        WS_URL,
        max_size=10*1024*1024,
        open_timeout=30,
        ping_interval=None,   # disable keepalive pings — pipeline blocks event loop
        ping_timeout=None,
        close_timeout=120,
    ) as ws:
        await ws.send(json.dumps({
            "ayush_name": AYUSH,
            "allopathy_name": ALLOPATHY,
            "mode": MODE,
        }))

        async for raw in ws:
            evt = json.loads(raw)
            etype = evt.get("type", "")
            counts[etype] = counts.get(etype, 0) + 1

            if etype == "status":
                divider(evt["message"][:64], "-")

            elif etype == "trace":
                render_trace(evt.get("data", evt))

            elif etype == "agent_complete":
                agt  = evt.get("agent", "?")
                prev = evt.get("preview", "")
                divider(f"Agent Complete: {agt}", "-")
                print(c(f"  Preview: {prev[:350]}", GREEN))

            elif etype == "validation":
                st    = evt.get("status", "?")
                score = evt.get("completeness_score", 0)
                itr   = evt.get("iteration", 0)
                issues = evt.get("issues", [])
                missing = evt.get("missing_data", [])
                divider(f"Validation #{itr}   status={st}   score={score}/100", "-")
                vcol = GREEN if st == "PASSED" else YELLOW
                print(c(f"  Status: {st}   Score: {score}/100", vcol, BOLD))
                for iss in issues[:5]:
                    print(c(f"  Issue:   {iss}", YELLOW))
                for m in missing[:3]:
                    print(c(f"  Missing: {m}", YELLOW))

            elif etype == "cached_result":
                divider("CACHED RESULT", "=")
                ix = evt.get("interaction", {})
                print(c(f"  Severity: {ix.get('severity','')}   Score: {ix.get('severity_score','')}", GREEN, BOLD))
                print(c(f"  Key:      {ix.get('interaction_key','')}", GREY))

            elif etype == "response_chunk":
                full_response += evt.get("text", "")

            elif etype == "complete":
                elapsed = time.time() - t0
                full_response = evt.get("full_response", full_response)
                divider("COMPLETE", "=")
                print(c(f"  execution_mode:      {evt.get('execution_mode','?')}", CYAN))
                print(c(f"  validation_iters:    {evt.get('validation_iterations',0)}", CYAN))
                print(c(f"  final_validation:    {evt.get('final_validation','?')}", CYAN))
                print(c(f"  pipeline_stages:     {evt.get('pipeline_stages',[])}", CYAN))
                print(c(f"  loop_iterations:     {evt.get('loop_iterations',0)}", CYAN))
                print(c(f"  elapsed:             {elapsed:.1f}s", GREY))

            elif etype == "error":
                print(c(f"\n  [!] ERROR: {evt.get('message','?')[:300]}", RED, BOLD))

    # ── Final response ─────────────────────────────────────────────────────────
    divider("FINAL RESPONSE  (rendered by UI)", "=", 72)
    if full_response:
        try:
            parsed = json.loads(full_response)
            render_final(parsed)
        except json.JSONDecodeError:
            for line in full_response.splitlines():
                print(f"  {line}")
    else:
        print(c("  (no structured response body)", GREY))

    # ── Event summary ──────────────────────────────────────────────────────────
    divider("EVENT COUNTS", "=", 72)
    for k, v in sorted(counts.items()):
        print(f"  {c(k, CYAN):<50}  x{v}")
    print()


def render_final(data: dict):
    if "response_data" in data:
        data = data["response_data"]
    sev   = data.get("severity", "?")
    score = data.get("severity_score", "?")
    ayush = data.get("ayush_name", "?")
    allo  = data.get("allopathy_name", "?")
    sev_col = {"MAJOR": RED, "MODERATE": YELLOW, "MINOR": CYAN, "NONE": GREEN}.get(sev, WHITE)

    print(c(f"\n  {ayush.upper()}  +  {allo.upper()}", BOLD))
    print(c(f"  Severity : {sev}   (score: {score}/100)", sev_col, BOLD))
    print()

    interactions = data.get("interactions") or data.get("interactions_data") or {}
    if isinstance(interactions, dict):
        cyps = interactions.get("cyp_enzymes", [])
        if cyps:
            print(c("  CYP Enzymes:", YELLOW))
            for e in cyps[:8]:
                name = e if isinstance(e, str) else e.get("name", "?")
                eff  = "" if isinstance(e, str) else f"  ({e.get('effect','')})"
                print(f"    - {name}{eff}")

        phytos = interactions.get("phytochemicals", [])
        if phytos:
            print(c("\n  Phytochemicals:", MAGENTA))
            for p in phytos[:6]:
                print(f"    - {p if isinstance(p,str) else p.get('name', p)}")

        mechs = interactions.get("mechanisms", [])
        if mechs:
            print(c("\n  Mechanisms:", CYAN))
            for m in mechs[:4]:
                print(f"    - {m if isinstance(m,str) else m.get('mechanism', m)}")

        clinical = interactions.get("clinical_effects", [])
        if clinical:
            print(c("\n  Clinical Effects:", RED))
            for e in clinical[:4]:
                print(f"    - {e if isinstance(e,str) else e.get('effect', e)}")

    kg = data.get("knowledge_graph", {})
    if isinstance(kg, dict) and kg.get("nodes"):
        nodes = kg["nodes"]
        edges = kg.get("edges", [])
        print(c(f"\n  Knowledge Graph :  {len(nodes)} nodes   {len(edges)} edges", BLUE))
        types = {}
        for n in nodes:
            t = n.get("data", {}).get("type", "unknown")
            types[t] = types.get(t, 0) + 1
        for t, cnt in types.items():
            print(c(f"    {t}: {cnt}", GREY))

    sources = data.get("sources", [])
    if sources:
        print(c(f"\n  Sources ({len(sources)}):", GREY))
        for s in sources[:6]:
            title = s.get("title", "")[:62] if isinstance(s, dict) else str(s)[:62]
            cat   = s.get("category", "") if isinstance(s, dict) else ""
            url   = s.get("url", "") if isinstance(s, dict) else ""
            print(c(f"    [{cat:<16}]  {title}", GREY))
            if url:
                print(c(f"                       {url[:80]}", GREY))

    disc = data.get("disclaimer", "")
    if disc:
        print()
        for line in textwrap.wrap(disc, 68):
            print(c(f"  {line}", GREY))
    print()


asyncio.run(run())
