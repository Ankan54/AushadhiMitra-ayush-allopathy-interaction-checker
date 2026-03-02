"""
validate_fixes.py - Post-deploy validation for all 9 bug fixes.

Run:  python scripts/validate_fixes.py
Each test invokes the real deployed Lambda and asserts the correct behaviour.
"""
import json, boto3, sys, textwrap, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REGION = "us-east-1"
client = boto3.client("lambda", region_name=REGION)

PASS = "\033[92m  PASS\033[0m"
FAIL = "\033[91m  FAIL\033[0m"
INFO = "\033[94m  INFO\033[0m"

results = []


def invoke(func_name: str, event: dict) -> dict:
    resp = client.invoke(
        FunctionName=func_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(event).encode(),
    )
    raw = resp["Payload"].read().decode()
    return json.loads(raw)


def bedrock_event(action_group: str, function: str, params: dict) -> dict:
    return {
        "actionGroup": action_group,
        "function": function,
        "parameters": [{"name": k, "value": v} for k, v in params.items()],
    }


def check(label: str, condition: bool, detail: str = "", warn_only: bool = False):
    tag = PASS if condition else (f"\033[93m  WARN\033[0m" if warn_only else FAIL)
    status = "PASS" if condition else ("WARN" if warn_only else "FAIL")
    print(f"{tag}  {label}")
    if detail:
        for line in textwrap.wrap(detail, 110):
            print(f"       {line}")
    results.append((status, label))


def extract_body(raw: dict) -> dict:
    """Pull the inner result dict from a Bedrock action group response."""
    try:
        return json.loads(
            raw["response"]["actionGroup"]["function"]["responseBody"]["TEXT"]["body"]
        )
    except Exception:
        pass
    try:
        return json.loads(
            raw["response"]["functionResponse"]["responseBody"]["TEXT"]["body"]
        )
    except Exception:
        pass
    return raw


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("  AushadhiMitra — Bug Fix Validation Suite")
print("=" * 70)

# ── BUG 1: planner_tools — curated DB SQL column ─────────────────────────────
print("\n[BUG 1] planner_tools — curated DB SQL column (response_data)")
event = bedrock_event(
    "planner_tools",
    "check_curated_interaction",
    {"ayush_name": "turmeric", "allopathy_name": "warfarin"},
)
raw = invoke("ausadhi-planner-tools", event)
body = extract_body(raw)
print(f"  {INFO}  Raw response keys: {list(body.keys())}")
# Old bug: crashed with column 'interaction_data' does not exist.
# New behaviour: returns found=True/False without a SQL error.
no_sql_error = "error" not in body or "interaction_data" not in str(body.get("error", ""))
check("No SQL 'interaction_data' column error", no_sql_error, str(body))
if body.get("found"):
    has_data = isinstance(body.get("interaction_data"), (dict, str))
    check("interaction_data key present in response (reads from response_data col)", has_data, str(body.get("interaction_data"))[:120])

# ── BUG 2: reasoning_tools — severity thresholds ─────────────────────────────
print("\n[BUG 2] reasoning_tools - correct severity thresholds (MAJOR>=60)")
event = bedrock_event(
    "reasoning_tools",
    "calculate_severity",
    {
        "interactions_data": json.dumps({
            "cyp_enzymes": [
                {"name": "CYP2C9", "effect": "inhibit"},
                {"name": "CYP3A4", "effect": "inhibit"},
            ]
        }),
        "allopathy_name": "warfarin",   # NTI drug → +25
    },
)
raw = invoke("ausadhi-reasoning-tools", event)
body = extract_body(raw)
print(f"  {INFO}  severity={body.get('severity')}  score={body.get('severity_score')}  "
      f"thresholds={body.get('thresholds')}  factors={body.get('scoring_factors')}")
check("Returned MAJOR severity for warfarin + 2 CYP inhibitions",
      body.get("severity") == "MAJOR",
      f"Got: {body.get('severity')} (score={body.get('severity_score')})")
check("MAJOR threshold is 60 (was wrong default of 30)",
      body.get("thresholds", {}).get("MAJOR") == 60,
      f"Got thresholds: {body.get('thresholds')}")
check("NTI drug detected (warfarin)",
      body.get("is_nti") is True,
      f"is_nti={body.get('is_nti')}")

# ── BUG 3: reasoning_tools — null guard on interactions_data="null" ───────────
print("\n[BUG 3] reasoning_tools — null guard: interactions_data='null' must not crash")
event = bedrock_event(
    "reasoning_tools",
    "calculate_severity",
    {"interactions_data": "null", "allopathy_name": "aspirin"},
)
raw = invoke("ausadhi-reasoning-tools", event)
body = extract_body(raw)
print(f"  {INFO}  Result: {body}")
check("No crash on interactions_data='null'",
      "error" not in body,
      str(body))
check("severity=NONE when no data",
      body.get("severity") == "NONE",
      f"Got: {body.get('severity')}")

# ── BUG 3b: null guard in build_knowledge_graph ───────────────────────────────
print("\n[BUG 3b] reasoning_tools — null guard: build_knowledge_graph with 'null'")
event = bedrock_event(
    "reasoning_tools",
    "build_knowledge_graph",
    {"ayush_name": "turmeric", "allopathy_name": "warfarin", "interactions_data": "null"},
)
raw = invoke("ausadhi-reasoning-tools", event)
body = extract_body(raw)
print(f"  {INFO}  success={body.get('success')}  nodes={body.get('node_count')}  edges={body.get('edge_count')}")
check("No crash on build_knowledge_graph with 'null'",
      "error" not in body and body.get("success") is True,
      str(body))

# ── BUG 4: reasoning_tools — int() crash on bad severity_score ───────────────
print("\n[BUG 4] reasoning_tools — non-numeric severity_score must not crash")
event = bedrock_event(
    "reasoning_tools",
    "format_professional_response",
    {
        "response_data": json.dumps({
            "ayush_name": "ginger",
            "allopathy_name": "aspirin",
            "severity": "MINOR",
            "severity_score": "not-a-number",
            "interactions_data": {},
            "knowledge_graph": {},
            "sources": [],
        })
    },
)
raw = invoke("ausadhi-reasoning-tools", event)
body = extract_body(raw)
print(f"  {INFO}  Result: success={body.get('success')}  "
      f"severity_score={body.get('response_data', {}).get('severity_score')}")
check("No crash on non-numeric severity_score",
      "error" not in body and body.get("success") is True,
      str(body))
check("severity_score defaults to 0",
      body.get("response_data", {}).get("severity_score") == 0,
      f"Got: {body.get('response_data', {}).get('severity_score')}")

# ── BUG 6: allopathy_data — null guard in cache_save ─────────────────────────
print("\n[BUG 6] allopathy_data — cache_save with drug_data='null' must not crash")
event = bedrock_event(
    "allopathy_data",
    "allopathy_cache_save",
    {
        "drug_name": "test-null-drug-bugfix",
        "generic_name": "test",
        "drug_data": "null",
        "sources": "null",
    },
)
raw = invoke("ausadhi-allopathy-data", event)
body = extract_body(raw)
print(f"  {INFO}  Result: {body}")
check("No crash on drug_data='null' in cache_save",
      "error" not in body and body.get("saved") is True,
      str(body))

# ── BUG 7: web_search — safe int() for max_results ───────────────────────────
print("\n[BUG 7] web_search — non-numeric max_results must not crash at parse stage")
event = bedrock_event(
    "web_search",
    "web_search",
    {"query": "turmeric warfarin interaction CYP", "search_depth": "basic", "max_results": "abc"},
)
raw = invoke("ausadhi-web-search", event)
body = extract_body(raw)
print(f"  {INFO}  Result: success={body.get('success')}  "
      f"total_results={body.get('total_results')}  error={body.get('message','')[:80]}")
# Should not raise ValueError from int("abc") — will proceed with default max_results=5
# It may fail for API reasons (quota/key) but NOT from the int() parse crash
not_int_crash = not (body.get("success") is False and "invalid literal" in str(body.get("message", "")))
check("No ValueError crash from int('abc') in max_results",
      not_int_crash,
      str(body))

# ── BUG 8: allopathy_data — NTI field name primary_cyp_substrates ────────────
print("\n[BUG 8] allopathy_data — check_nti_status warfarin → primary_cyp_substrates")
event = bedrock_event(
    "allopathy_data",
    "check_nti_status",
    {"drug_name": "warfarin"},
)
raw = invoke("ausadhi-allopathy-data", event)
body = extract_body(raw)
print(f"  {INFO}  is_nti={body.get('is_nti')}  "
      f"primary_cyp_substrates={body.get('primary_cyp_substrates')}")
check("warfarin detected as NTI",
      body.get("is_nti") is True,
      str(body))
check("primary_cyp_substrates key present (not old singular form)",
      "primary_cyp_substrates" in body,
      f"Keys: {list(body.keys())}")
check("primary_cyp_substrates is a non-empty list",
      isinstance(body.get("primary_cyp_substrates"), list) and len(body.get("primary_cyp_substrates", [])) > 0,
      f"Got: {body.get('primary_cyp_substrates')}")
check("Old key 'primary_cyp_substrate' is gone",
      "primary_cyp_substrate" not in body,
      f"Keys: {list(body.keys())}")

# ── BUG 9: reasoning_tools — score capped at 100 ─────────────────────────────
print("\n[BUG 9] reasoning_tools — severity_score must be capped at 100")
# Build a very high-score scenario: many CYP inhibitions + NTI
cyp_list = [{"name": f"CYP{e}", "effect": "inhibit"} for e in
            ["1A2", "2C9", "2C19", "2D6", "3A4", "2B6", "2C8", "2E1"]]
event = bedrock_event(
    "reasoning_tools",
    "calculate_severity",
    {
        "interactions_data": json.dumps({"cyp_enzymes": cyp_list}),
        "allopathy_name": "warfarin",
    },
)
raw = invoke("ausadhi-reasoning-tools", event)
body = extract_body(raw)
score = body.get("severity_score", -1)
print(f"  {INFO}  score={score}  severity={body.get('severity')}")
check("severity_score ≤ 100",
      isinstance(score, (int, float)) and score <= 100,
      f"Got: {score}")

# ── BUG 5 note (backend only) ─────────────────────────────────────────────────
print("\n[BUG 5] agent_service.py — validation fallback (backend code, no Lambda)")
print(f"  {INFO}  This fix is in backend/app/agent_service.py (Docker on EC2).")
print(f"  {INFO}  Fix: parse failure default PASSED → NEEDS_MORE_DATA")
print(f"  {INFO}  Verified statically — test covered below via unit check.")

# Static verification of the fix
import os, re
svc_path = os.path.join(
    r"C:\Users\ANKAN\WORK\AushadhiMitra-ayush-allopathy-interaction-checker",
    "backend", "app", "agent_service.py"
)
with open(svc_path) as f:
    src = f.read()
check("NEEDS_MORE_DATA in parse-failure fallback (static check)",
      "NEEDS_MORE_DATA" in src and "Validation response could not be parsed" in src,
      "Verified in backend/app/agent_service.py source")
check("Old PASSED fallback removed",
      not re.search(r'"validation_status":\s*"PASSED".*"completeness_score":\s*80', src),
      "No silent PASSED default remaining")

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
total = len(results)
passed = sum(1 for s, _ in results if s == "PASS")
failed = sum(1 for s, _ in results if s == "FAIL")
warned = sum(1 for s, _ in results if s == "WARN")
print(f"  Results: {passed}/{total} passed  |  {warned} warnings  |  {failed} failures")
print("=" * 70 + "\n")

sys.exit(0 if failed == 0 else 1)
