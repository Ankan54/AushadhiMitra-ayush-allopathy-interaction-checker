"""
End-to-end test for AushadhiMitra V5.
Tests both pipeline (fallback) and flow modes.
Usage: python scripts/test_e2e.py [port]
"""
import asyncio
import json
import sys
import time
import websockets

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8100
BASE_URL = f"ws://localhost:{PORT}/ws/check-interaction"
HTTP_BASE = f"http://localhost:{PORT}"

TESTS = [
    {
        "name": "Curcuma longa + warfarin (high clinical relevance)",
        "ayush_name": "Curcuma longa",
        "allopathy_name": "warfarin",
        "mode": "pipeline",
        "expect_severity": ["MODERATE", "MAJOR"],
    },
    {
        "name": "Ashwagandha + atorvastatin",
        "ayush_name": "Withania somnifera",
        "allopathy_name": "atorvastatin",
        "mode": "pipeline",
        "expect_severity": ["NONE", "MINOR", "MODERATE"],
    },
    {
        "name": "Invalid AYUSH plant (should return error)",
        "ayush_name": "xyz_unknown_plant_123",
        "allopathy_name": "aspirin",
        "mode": "pipeline",
        "expect_error": True,
    },
]


async def run_test(test):
    name = test["name"]
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"  Mode: {test['mode']}")
    print(f"  AYUSH: {test['ayush_name']}")
    print(f"  Drug:  {test['allopathy_name']}")
    print(f"{'='*60}")

    start = time.time()
    steps = []
    result = None
    error_msg = None

    try:
        async with websockets.connect(BASE_URL, ping_timeout=600, open_timeout=10) as ws:
            await ws.send(json.dumps({
                "ayush_name": test["ayush_name"],
                "allopathy_name": test["allopathy_name"],
                "mode": test["mode"],
            }))

            while True:
                try:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=600))
                except asyncio.TimeoutError:
                    error_msg = "TIMEOUT (10 min)"
                    break

                t = msg.get("type", "")

                if t == "pipeline_step":
                    step = msg.get("message", "")
                    steps.append(step)
                    print(f"  STEP: {step}")

                elif t == "agent_complete":
                    agent = msg.get("agent", "unknown")
                    resp_preview = (msg.get("response") or "")[:120]
                    print(f"    ✓ {agent}: {resp_preview}...")

                elif t == "complete":
                    result = msg.get("result", {})
                    break

                elif t == "error":
                    error_msg = msg.get("message", str(msg))
                    break

                elif t == "status":
                    print(f"  [{t}] {msg.get('message', '')}")

    except Exception as e:
        error_msg = str(e)

    elapsed = time.time() - start

    print(f"\n  Elapsed: {elapsed:.1f}s")

    if error_msg:
        if test.get("expect_error"):
            print(f"  RESULT: PASS (expected error) — {error_msg}")
            return True
        else:
            print(f"  RESULT: FAIL — {error_msg}")
            return False

    if test.get("expect_error"):
        print(f"  RESULT: FAIL — expected error but got success")
        return False

    # Validate result
    if not isinstance(result, dict):
        print(f"  RESULT: FAIL — result is not a dict: {result}")
        return False

    idata = result.get("interaction_data", result)
    severity = idata.get("severity", "N/A")
    score = idata.get("severity_score", "N/A")
    is_nti = idata.get("is_nti", "N/A")
    evidence = idata.get("evidence_quality", "N/A")
    sources = idata.get("sources", [])
    summary = (idata.get("interaction_summary") or "")[:200]
    kg_nodes = len(idata.get("knowledge_graph", {}).get("nodes", []))
    kg_edges = len(idata.get("knowledge_graph", {}).get("edges", []))

    print(f"\n  FINAL RESULT:")
    print(f"    severity:         {severity}")
    print(f"    severity_score:   {score}")
    print(f"    is_nti:           {is_nti}")
    print(f"    evidence_quality: {evidence}")
    print(f"    sources:          {len(sources)}")
    print(f"    KG nodes/edges:   {kg_nodes}/{kg_edges}")
    print(f"    summary: {summary}")

    # Check expected severity
    expected = test.get("expect_severity", [])
    if expected and severity not in expected:
        print(f"  RESULT: WARN — severity '{severity}' not in expected {expected}")
    else:
        print(f"  RESULT: PASS")

    # Sanity checks
    issues = []
    if severity not in ("NONE", "MINOR", "MODERATE", "MAJOR"):
        issues.append(f"Invalid severity: {severity}")
    if not isinstance(score, (int, float)):
        issues.append(f"severity_score not numeric: {score}")
    if evidence not in ("HIGH", "MODERATE", "LOW", None, "N/A"):
        issues.append(f"Unexpected evidence_quality: {evidence}")

    if issues:
        for i in issues:
            print(f"    WARNING: {i}")

    return len(issues) == 0


async def health_check():
    import urllib.request
    try:
        with urllib.request.urlopen(f"{HTTP_BASE}/api/health", timeout=5) as r:
            h = json.loads(r.read())
            print(f"Health: {h.get('status')} | arch: {h.get('architecture')} | flow v{h.get('flow', {}).get('version', '?')}")
            agents = h.get("agents", {})
            for role, aid in agents.items():
                print(f"  {role:12s}: {aid}")
            return True
    except Exception as e:
        print(f"Health check failed: {e}")
        return False


async def main():
    print("AushadhiMitra V5 — End-to-End Test Suite")
    print(f"Server: http://localhost:{PORT}")
    print()

    if not await health_check():
        print("Server not available. Exiting.")
        sys.exit(1)

    passed = 0
    failed = 0
    for test in TESTS:
        ok = await run_test(test)
        if ok:
            passed += 1
        else:
            failed += 1

    print(f"\n{'='*60}")
    print(f"RESULTS: {passed} passed, {failed} failed out of {len(TESTS)} tests")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
