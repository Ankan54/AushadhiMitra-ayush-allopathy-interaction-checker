import os

REGION = os.environ.get("AWS_REGION", "us-east-1")

# Individual agent IDs and aliases (for pipeline orchestration)
PLANNER_AGENT_ID = os.environ.get("PLANNER_AGENT_ID", "JRARFMAC40")
PLANNER_AGENT_ALIAS = os.environ.get("PLANNER_AGENT_ALIAS", "BAKMQ02PQ7")

AYUSH_AGENT_ID = os.environ.get("AYUSH_AGENT_ID", "0SU1BHJ78L")
AYUSH_AGENT_ALIAS = os.environ.get("AYUSH_AGENT_ALIAS", "6NXIKPLBVB")

ALLOPATHY_AGENT_ID = os.environ.get("ALLOPATHY_AGENT_ID", "CNAZG8LA0H")
ALLOPATHY_AGENT_ALIAS = os.environ.get("ALLOPATHY_AGENT_ALIAS", "BBAJ5HFGKG")

REASONING_AGENT_ID = os.environ.get("REASONING_AGENT_ID", "03NGZ4CNF3")
REASONING_AGENT_ALIAS = os.environ.get("REASONING_AGENT_ALIAS", "DUH94OH0OG")

# Bedrock Flow (for architecture visualization; async execution backup)
FLOW_ID = os.environ.get("FLOW_ID", "4QKIL1MSB5")
FLOW_ALIAS = os.environ.get("FLOW_ALIAS", "CZZIUM9U5W")

# Legacy supervisor (deprecated, replaced by Flow + pipeline)
BEDROCK_AGENT_ID = os.environ.get("BEDROCK_AGENT_ID", "8MIQNGTVWG")
BEDROCK_AGENT_ALIAS_ID = os.environ.get("BEDROCK_AGENT_ALIAS_ID", "IPQMNOORBI")

DB_HOST = os.environ.get("DB_HOST", "scm-postgres.c2na6oc62pb7.us-east-1.rds.amazonaws.com")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_NAME = os.environ.get("DB_NAME", "aushadhimitra")
DB_USER = os.environ.get("DB_USER", "scm_admin")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_SSL = os.environ.get("DB_SSL", "require")
