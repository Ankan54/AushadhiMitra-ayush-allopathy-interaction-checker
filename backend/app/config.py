import os

REGION = os.environ.get("AWS_REGION", "us-east-1")

# ── Agent IDs and Aliases ────────────────────────────────────
PLANNER_AGENT_ID = os.environ.get("PLANNER_AGENT_ID", "JRARFMAC40")
PLANNER_AGENT_ALIAS = os.environ.get("PLANNER_AGENT_ALIAS", "BAKMQ02PQ7")

AYUSH_AGENT_ID = os.environ.get("AYUSH_AGENT_ID", "0SU1BHJ78L")
AYUSH_AGENT_ALIAS = os.environ.get("AYUSH_AGENT_ALIAS", "6NXIKPLBVB")

ALLOPATHY_AGENT_ID = os.environ.get("ALLOPATHY_AGENT_ID", "CNAZG8LA0H")
ALLOPATHY_AGENT_ALIAS = os.environ.get("ALLOPATHY_AGENT_ALIAS", "BBAJ5HFGKG")

REASONING_AGENT_ID = os.environ.get("REASONING_AGENT_ID", "03NGZ4CNF3")
REASONING_AGENT_ALIAS = os.environ.get("REASONING_AGENT_ALIAS", "DUH94OH0OG")

# ── Bedrock Flow ─────────────────────────────────────────────
FLOW_ID = os.environ.get("FLOW_ID", "4QKIL1MSB5")
FLOW_ALIAS = os.environ.get("FLOW_ALIAS", "CZZIUM9U5W")

# ── Legacy supervisor (deprecated) ───────────────────────────
BEDROCK_AGENT_ID = os.environ.get("BEDROCK_AGENT_ID", "8MIQNGTVWG")
BEDROCK_AGENT_ALIAS_ID = os.environ.get("BEDROCK_AGENT_ALIAS_ID", "IPQMNOORBI")

# ── Database ─────────────────────────────────────────────────
DB_HOST = os.environ.get("DB_HOST", "")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_NAME = os.environ.get("DB_NAME", "aushadhimitra")
DB_USER = os.environ.get("DB_USER", "")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_SSL = os.environ.get("DB_SSL", "require")

# ── Operational Tunables ─────────────────────────────────────
MAX_VALIDATION_RETRIES = int(os.environ.get("MAX_VALIDATION_RETRIES", "2"))
AGENT_INVOKE_MAX_RETRIES = int(os.environ.get("AGENT_INVOKE_MAX_RETRIES", "2"))
AGENT_RETRY_BASE_WAIT = int(os.environ.get("AGENT_RETRY_BASE_WAIT", "3"))

# Max characters for drug name inputs
INPUT_MAX_LENGTH = int(os.environ.get("INPUT_MAX_LENGTH", "200"))
INPUT_MIN_LENGTH = int(os.environ.get("INPUT_MIN_LENGTH", "2"))
