"""
run_trace.py — Run the real pipeline locally (host AWS credentials) and
print every event exactly as the WebSocket would send them to the UI.

Usage: python scripts/run_trace.py [ayush] [allopathy]
"""
import sys, os, json, time, textwrap, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Add backend to path so app.* imports work
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "backend"))

AYUSH     = sys.argv[1] if len(sys.argv) > 1 else "turmeric"
ALLOPATHY = sys.argv[2] if len(sys.argv) > 2 else "warfarin"

# ── ANSI ──────────────────────────────────────────────────────────────────────
R="\033[0m"; BOLD="\033[1m"; GREY="\033[90m"; CYAN="\033[96m"
YELLOW="\033[93m"; GREEN="\033[92m"; BLUE="\033[94m"
MAGENTA="\033[95m"; RED="\033[91m"; WHITE="\033[97m"

def c(text, *codes): return "".join(codes)+str(text)+R
def ts(): return c(f"[{time.strftime('%H:%M:%S')}]", GREY)
def div(label="", ch="-", w=74):
    if label:
        p = max(0, (w-len(label)-2)//2)
        print(c(ch*p+f" {label} "+ch*(w-p-len(label)-2), GREY))
    else:
        print(c(ch*w, GREY))

ICONS = {
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
    "validation_max_retries": (" !", RED+BOLD),
    "warning":                (" W", YELLOW),
    "code_interpreter":       (" #", CYAN),
    "code_result":            (" #", GREEN),
    "preprocessing":          (" p", GREY),
    "condition":              (" C", YELLOW),
}

def render_trace(d):
    t   = d.get("type","processing")
    agt = d.get("agent","")
    msg = d.get("message","")
    node= d.get("node","")
    icon, col = ICONS.get(t, (" .", GREY))
    short = (msg[:230]+"...") if len(msg)>230 else msg
    atag  = c(f"[{agt}]", CYAN)  if agt  else ""
    ntag  = c(f"[{node}]", GREY) if (node and node!=agt) else ""
    print(f"{ts()} {c(f'[{icon}]',col)} {atag}{ntag} {short}")
    if t == "tool_call" and d.get("parameters"):
        for k,v in list(d["parameters"].items())[:6]:
            val = str(v); val = (val[:130]+"...") if len(val)>130 else val
            print(c(f"             {k}: {val}", GREY))
    if t == "tool_result":
        snip = msg.replace("Tool returned: ","")[:200]
        print(c(f"             => {snip}", GREEN))

def render_final(data):
    if "response_data" in data:
        data = data["response_data"]
    sev   = data.get("severity","?")
    score = data.get("severity_score","?")
    ayush = data.get("ayush_name","?")
    allo  = data.get("allopathy_name","?")
    sc = {
        "MAJOR":RED, "MODERATE":YELLOW, "MINOR":CYAN, "NONE":GREEN
    }.get(sev, WHITE)

    print(c(f"\n  {ayush.upper()}  +  {allo.upper()}", BOLD))
    print(c(f"  Severity : {sev}   (score: {score}/100)\n", sc, BOLD))

    ix = data.get("interactions") or data.get("interactions_data") or {}
    if isinstance(ix, dict):
        cyps = ix.get("cyp_enzymes",[])
        if cyps:
            print(c("  CYP Enzymes involved:", YELLOW))
            for e in cyps[:8]:
                nm  = e if isinstance(e,str) else e.get("name","?")
                eff = "" if isinstance(e,str) else f"  -> {e.get('effect','')}"
                print(f"    - {nm}{eff}")

        phytos = ix.get("phytochemicals",[])
        if phytos:
            print(c("\n  Active Phytochemicals:", MAGENTA))
            for p in phytos[:6]:
                print(f"    - {p if isinstance(p,str) else p.get('name',p)}")

        mechs = ix.get("mechanisms",[])
        if mechs:
            print(c("\n  Interaction Mechanisms:", CYAN))
            for m in mechs[:4]:
                print(f"    - {m if isinstance(m,str) else m.get('mechanism',m)}")

        clinical = ix.get("clinical_effects",[])
        if clinical:
            print(c("\n  Clinical Effects:", RED))
            for e in clinical[:4]:
                print(f"    - {e if isinstance(e,str) else e.get('effect',e)}")

    kg = data.get("knowledge_graph",{})
    if isinstance(kg,dict) and kg.get("nodes"):
        nodes = kg["nodes"]; edges = kg.get("edges",[])
        print(c(f"\n  Knowledge Graph :  {len(nodes)} nodes   {len(edges)} edges", BLUE))
        types={}
        for n in nodes:
            t2 = n.get("data",{}).get("type","?"); types[t2]=types.get(t2,0)+1
        for t2,cnt in types.items():
            print(c(f"    {t2}: {cnt}", GREY))

    sources = data.get("sources",[])
    if sources:
        print(c(f"\n  Sources ({len(sources)}):", GREY))
        for s in sources[:6]:
            title = (s.get("title","") if isinstance(s,dict) else str(s))[:62]
            cat   = s.get("category","") if isinstance(s,dict) else ""
            url   = s.get("url","")      if isinstance(s,dict) else ""
            print(c(f"    [{cat:<16}]  {title}", GREY))
            if url: print(c(f"                       {url[:78]}", GREY))

    disc = data.get("disclaimer","")
    if disc:
        print()
        for line in textwrap.wrap(disc, 68):
            print(c(f"  {line}", GREY))
    print()

# ── Run ───────────────────────────────────────────────────────────────────────
def main():
    from app.agent_service import run_interaction_pipeline

    print()
    div(f"AushadhiMitra  --  Live Pipeline Trace", "=", 74)
    print(c(f"  Query : {AYUSH}  +  {ALLOPATHY}", BOLD))
    print(c(f"  Mode  : pipeline_fallback (direct agent invocation)", GREY))
    div("", "=", 74)

    counts = {}
    full_response = ""
    t0 = time.time()

    for etype, edata in run_interaction_pipeline(AYUSH, ALLOPATHY):
        counts[etype] = counts.get(etype,0)+1

        if etype == "trace":
            render_trace(edata)

        elif etype == "agent_complete":
            agt  = edata.get("label","?")
            prev = edata.get("response","")
            div(f"Agent Complete: {agt}", "-")
            # print first 400 chars of agent raw response
            preview = (prev[:400]+"...") if len(prev)>400 else prev
            print(c(f"  {preview}", GREEN))

        elif etype == "validation":
            st    = edata.get("status","?")
            score = edata.get("completeness_score",0)
            itr   = edata.get("iteration",0)
            issues  = edata.get("issues",[])
            missing = edata.get("missing_data",[])
            div(f"Validation #{itr}   status={st}   score={score}/100", "-")
            vcol = GREEN if st=="PASSED" else YELLOW
            print(c(f"  Status : {st}   Score : {score}/100", vcol, BOLD))
            for iss in issues[:5]:   print(c(f"  Issue  : {iss}", YELLOW))
            for m   in missing[:3]:  print(c(f"  Missing: {m}", YELLOW))

        elif etype == "response":
            full_response += edata

        elif etype == "done":
            elapsed = time.time()-t0
            div("DONE", "=")
            print(c(f"  execution_mode    : {edata.get('execution_mode','?')}", CYAN))
            print(c(f"  validation_iters  : {edata.get('validation_iterations',0)}", CYAN))
            print(c(f"  final_validation  : {edata.get('final_validation','?')}", CYAN))
            print(c(f"  pipeline_stages   : {edata.get('pipeline_stages',[])}", CYAN))
            print(c(f"  elapsed           : {elapsed:.1f}s", GREY))

        elif etype == "error":
            print(c(f"\n  [!] ERROR: {edata.get('message','?')[:300]}", RED, BOLD))

    # ── Final response ─────────────────────────────────────────────────────────
    div("FINAL RESPONSE  (what the UI renders)", "=", 74)
    if full_response:
        try:
            render_final(json.loads(full_response))
        except json.JSONDecodeError:
            for line in full_response.splitlines():
                print(f"  {line}")
    else:
        print(c("  (no structured response received)", GREY))

    div("EVENT SUMMARY", "=", 74)
    for k,v in sorted(counts.items()):
        print(f"  {c(k,CYAN):<50}  x{v}")
    print()

main()
