"""
Research Tools Action Group Lambda
Triggered by: Bedrock Research Agent
Functions: search_research_articles, search_clinical_evidence

Performs domain-restricted academic/PubMed searches using Tavily API.
Uses research preset from S3 domain config to restrict to high-quality sources.
"""
import json
import sys
import os
import logging
from urllib.request import Request, urlopen
from urllib.error import URLError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sys.path.insert(0, "/opt/python")
sys.path.insert(0, "/var/task")

import boto3
from shared.bedrock_utils import bedrock_response

TAVILY_SECRET_ARN = os.environ.get(
    "TAVILY_SECRET_NAME", "ausadhi-mitra/tavily-api-key"
)
TAVILY_API_URL = "https://api.tavily.com/search"
S3_BUCKET = os.environ.get("S3_BUCKET", "")

secrets_client = boto3.client("secretsmanager")
s3 = boto3.client("s3")

_tavily_key_cache = None
_domain_config_cache = None

RESEARCH_DOMAINS_FALLBACK = [
    "pubmed.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov", "doi.org",
    "springer.com", "sciencedirect.com", "nature.com", "wiley.com",
    "academic.oup.com", "frontiersin.org", "mdpi.com",
    "biorxiv.org", "medrxiv.org", "cochranelibrary.com", "clinicaltrials.gov",
]


def lambda_handler(event, context):
    logger.info(f"Event: {json.dumps(event, default=str)}")

    action_group = event.get("actionGroup", "research_tools")
    function = event.get("function", "")
    params = {p["name"]: p["value"] for p in event.get("parameters", [])}

    try:
        if function == "search_research_articles":
            try:
                max_results = int(params.get("max_results", "5"))
            except (ValueError, TypeError):
                max_results = 5
            result = search_research_articles(
                params.get("query", ""),
                max_results,
            )
        elif function == "search_clinical_evidence":
            try:
                max_results = int(params.get("max_results", "5"))
            except (ValueError, TypeError):
                max_results = 5
            result = search_clinical_evidence(
                params.get("ayush_name", ""),
                params.get("allopathy_name", ""),
                max_results,
            )
        else:
            result = {"error": f"Unknown function: {function}"}
    except Exception as e:
        logger.exception(f"Error in {function}")
        result = {"error": str(e)}

    return bedrock_response(action_group, function, result)


def _load_domain_config() -> dict:
    """Load domain preset config from S3, cached in module global."""
    global _domain_config_cache
    if _domain_config_cache is not None:
        return _domain_config_cache
    try:
        resp = s3.get_object(Bucket=S3_BUCKET, Key="reference/search_domains.json")
        _domain_config_cache = json.loads(resp["Body"].read().decode("utf-8"))
        logger.info("Loaded domain config from S3")
        return _domain_config_cache
    except Exception as e:
        logger.warning(f"Could not load search_domains.json from S3: {e}. Using fallback.")
        _domain_config_cache = {
            "version": "1.0",
            "presets": {"research": {"include_domains": RESEARCH_DOMAINS_FALLBACK}},
        }
        return _domain_config_cache


def _get_research_domains() -> list:
    """Get research domain list from S3 config, fallback to hardcoded list."""
    config = _load_domain_config()
    domains = config.get("presets", {}).get("research", {}).get("include_domains", [])
    return domains if domains else RESEARCH_DOMAINS_FALLBACK


def _get_tavily_key() -> str:
    global _tavily_key_cache
    if _tavily_key_cache:
        return _tavily_key_cache

    resp = secrets_client.get_secret_value(SecretId=TAVILY_SECRET_ARN)
    secret = resp["SecretString"]
    try:
        data = json.loads(secret)
        _tavily_key_cache = data.get("api_key") or data.get("TAVILY_API_KEY") or secret
    except json.JSONDecodeError:
        _tavily_key_cache = secret.strip()

    return _tavily_key_cache


def _tavily_search(query: str, max_results: int, include_domains: list) -> dict:
    """Perform a Tavily search with domain restriction."""
    api_key = _get_tavily_key()

    payload = json.dumps({
        "api_key": api_key,
        "query": query,
        "search_depth": "advanced",
        "max_results": max_results,
        "include_answer": True,
        "include_raw_content": False,
        "include_domains": include_domains,
    }).encode("utf-8")

    req = Request(
        TAVILY_API_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except URLError as e:
        logger.error(f"Tavily API error: {e}")
        raise RuntimeError(f"Web search failed: {e}")


def search_research_articles(query: str, max_results: int = 5) -> dict:
    """Search PubMed and academic sources for research articles.

    Restricts results to high-quality academic/research domains only.
    Returns structured results with source metadata.
    """
    if not query:
        return {"success": False, "message": "query is required"}

    domains = _get_research_domains()

    try:
        data = _tavily_search(query, max_results, domains)
    except RuntimeError as e:
        return {"success": False, "message": str(e)}

    sources = []
    for r in data.get("results", []):
        sources.append({
            "url": r.get("url", ""),
            "title": r.get("title", ""),
            "snippet": r.get("content", "")[:500],
            "score": r.get("score", 0),
            "category": "research_paper",
        })

    return {
        "success": True,
        "query": query,
        "answer": data.get("answer", ""),
        "sources": sources,
        "total_results": len(sources),
        "domain_preset": "research",
    }


def search_clinical_evidence(ayush_name: str, allopathy_name: str,
                              max_results: int = 5) -> dict:
    """Search for clinical evidence of interaction between AYUSH and allopathy drug.

    Auto-generates 2 targeted queries, deduplicates results across both searches.
    Restricts to research/PubMed domains only.
    """
    if not ayush_name or not allopathy_name:
        return {"success": False, "message": "ayush_name and allopathy_name are required"}

    queries = [
        f"{ayush_name} {allopathy_name} drug interaction clinical study",
        f"{ayush_name} {allopathy_name} pharmacokinetic pharmacodynamic interaction evidence",
    ]

    domains = _get_research_domains()
    all_sources = []
    seen_urls = set()

    for query in queries:
        try:
            data = _tavily_search(query, max_results, domains)
            for r in data.get("results", []):
                url = r.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_sources.append({
                        "url": url,
                        "title": r.get("title", ""),
                        "snippet": r.get("content", "")[:500],
                        "score": r.get("score", 0),
                        "category": "research_paper",
                        "query_used": query,
                    })
        except RuntimeError as e:
            logger.warning(f"Query failed '{query}': {e}")

    all_sources.sort(key=lambda x: x.get("score", 0), reverse=True)

    return {
        "success": True,
        "ayush_name": ayush_name,
        "allopathy_name": allopathy_name,
        "queries_used": queries,
        "sources": all_sources[:max_results * 2],
        "total_results": len(all_sources),
        "domain_preset": "research",
    }
