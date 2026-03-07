import os

REGION = os.environ.get("AWS_REGION", "us-east-1")

# ── Agent IDs and Aliases ────────────────────────────────────
# TSTALIASID routes to the latest DRAFT version of each agent
PLANNER_AGENT_ID = os.environ.get("PLANNER_AGENT_ID", "JRARFMAC40")
PLANNER_AGENT_ALIAS = os.environ.get("PLANNER_AGENT_ALIAS", "TSTALIASID")

AYUSH_AGENT_ID = os.environ.get("AYUSH_AGENT_ID", "0SU1BHJ78L")
AYUSH_AGENT_ALIAS = os.environ.get("AYUSH_AGENT_ALIAS", "TSTALIASID")

ALLOPATHY_AGENT_ID = os.environ.get("ALLOPATHY_AGENT_ID", "CNAZG8LA0H")
ALLOPATHY_AGENT_ALIAS = os.environ.get("ALLOPATHY_AGENT_ALIAS", "TSTALIASID")

REASONING_AGENT_ID = os.environ.get("REASONING_AGENT_ID", "03NGZ4CNF3")
REASONING_AGENT_ALIAS = os.environ.get("REASONING_AGENT_ALIAS", "TSTALIASID")

RESEARCH_AGENT_ID = os.environ.get("RESEARCH_AGENT_ID", "7DCGAF6N1A")
RESEARCH_AGENT_ALIAS = os.environ.get("RESEARCH_AGENT_ALIAS", "TSTALIASID")

# ── S3 ───────────────────────────────────────────────────────
# Bucket name is account-specific; resolved at runtime from env or auto-detected
S3_BUCKET = os.environ.get("S3_BUCKET", "")

# ── Database ─────────────────────────────────────────────────
DB_HOST = os.environ.get("DB_HOST", "")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_NAME = os.environ.get("DB_NAME", "aushadhimitra")
DB_USER = os.environ.get("DB_USER", "")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_SSL = os.environ.get("DB_SSL", "require")

# ── CO-MAS Pipeline Config ────────────────────────────────────
# Max iterations for the plan-research-reason-validate loop
MAX_COMAS_ITERATIONS = int(os.environ.get("MAX_COMAS_ITERATIONS", "3"))

# IMPPAT phytochemical page URL — insert URL-encoded scientific name
# e.g. https://cb.imsc.res.in/imppat/phytochemical/Curcuma%20longa
IMPPAT_PHYTO_URL_TEMPLATE = "https://cb.imsc.res.in/imppat/phytochemical/{scientific_name}"

# ── Operational Tunables ─────────────────────────────────────
AGENT_INVOKE_MAX_RETRIES = int(os.environ.get("AGENT_INVOKE_MAX_RETRIES", "2"))
AGENT_RETRY_BASE_WAIT = int(os.environ.get("AGENT_RETRY_BASE_WAIT", "3"))

# Max characters for drug name inputs
INPUT_MAX_LENGTH = int(os.environ.get("INPUT_MAX_LENGTH", "200"))
INPUT_MIN_LENGTH = int(os.environ.get("INPUT_MIN_LENGTH", "2"))
