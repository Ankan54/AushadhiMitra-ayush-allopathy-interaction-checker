# AushadhiMitra — Known Issues and Errors

Last updated: 2026-03-01

---

## 1. Bedrock Flow Timeout

**Observed:** Flow invocation fails with `Read timed out` when using Bedrock Flow V4 (DoWhile). System falls back to pipeline mode.

```
Flow stream error: AWSHTTPSConnectionPool(host='bedrock-agent-runtime.us-east-1.amazonaws.com', port=443): Read timed out.
```

**Impact:** Flow mode is unreliable; pipeline mode (EC2-orchestrated agent invocation) is used instead.

**Possible causes:**  
- Flow execution exceeds Bedrock agent timeout limits  
- Agents (especially Reasoning) take too long inside the Flow

**Mitigation:** Pipeline fallback works. Consider increasing Flow/agent timeouts if configurable, or keep pipeline as primary path.

---

## 2. Curated DB: Column `interaction_data` Does Not Exist

**Observed:** Planner Agent's `check_curated_interaction` tool fails with:

```
column "interaction_data" does not exist
LINE 2: severity_score, interaction_data, knowledge_graph...
```

**Root cause:** Schema mismatch between Lambda and database.
- **DB schema** (`setup_db_lambda.py`, `curated_interactions`): column is `response_data`
- **Planner tools Lambda** (`lambda/planner_tools/handler.py`): uses `interaction_data`

**Files involved:**
- `lambda/planner_tools/handler.py` lines 155–156: `SELECT ... interaction_data ...`
- `scripts/setup_db_lambda.py` line 55: `response_data JSONB NOT NULL`

**Fix:** Either:
- **A)** Change `planner_tools` to use `response_data` instead of `interaction_data`, or  
- **B)** Add `interaction_data` column to DB (and migrate `response_data` if needed).

**Status:** Not fixed. Curated lookup fails; full analysis runs every time.

---

## 3. Reasoning Tools: `calculate_severity` — NoneType Error

**Observed:** When Reasoning Agent passes `"null"` or empty interactions_data:

```
{"error": "'NoneType' object has no attribute 'get'"}
```

**Root cause:**  
`interactions_data_str` is `"null"` → `json.loads("null")` → Python `None` → `interactions.get("cyp_enzymes", [])` fails because `None` has no `.get()`.

**File:** `lambda/reasoning_tools/handler.py` — `calculate_severity()`

**Fix:**  
Normalize input to a dict before use:

```python
interactions = json.loads(interactions_data_str) if isinstance(interactions_data_str, str) else (interactions_data_str or {})
if interactions is None:
    interactions = {}
```

**Workaround:** Agent retries with valid PD interaction data; analysis completes despite initial error.

---

## 4. Backend DB: `lookup_curated` vs Schema

**Observed:** Backend `lookup_curated` in `db.py` may use different column names than Planner tools. Verify `db.py` uses `response_data` consistently with the schema.

---

## 5. Knowledge Graph in Final Response

**Observed:** Final JSON sometimes has `"knowledge_graph": ""` (empty string) instead of the Cytoscape.js graph object.

**Check:** Ensure `format_professional_response` passes the graph correctly and that the Reasoning Agent builds it before formatting.

---

## Summary

| # | Issue                          | Severity | Status   |
|---|--------------------------------|----------|----------|
| 1 | Flow timeout → fallback        | Low      | Mitigated (pipeline works) |
| 2 | Curated DB column mismatch     | High     | Open     |
| 3 | calculate_severity NoneType    | Medium   | Open     |
| 4 | Backend DB schema alignment    | Medium   | Verify   |
| 5 | Empty knowledge_graph in output| Low      | Verify   |
