"""
Web Search Action Group Lambda (Tavily)
Triggered by: All Bedrock Agents (shared)
Functions: web_search

Uses Tavily Search API for drug interaction research.
Returns full source metadata (URL, title, snippet, score) for transparency.
Sources are categorized by type (pubmed, admet, clinical_trial, etc.) for UI display.
"""
import json
import sys
import os
import logging
import re
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

secrets_client = boto3.client("secretsmanager")
_tavily_key_cache = None

SOURCE_CATEGORIES = [
    ("pubmed", ["pubmed.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov/pubmed"]),
    ("clinical_trial", ["clinicaltrials.gov", "cochranelibrary.com"]),
    ("pharmacology_db", ["drugbank.ca", "drugbank.com", "rxlist.com", "drugs.com/drug_interactions",
                         "go.drugbank.com"]),
    ("admet", ["admetlab", "swissadme", "pkcsm", "admet", "toxicity", "pharmacokinetic"]),
    ("research_paper", ["doi.org", "springer.com", "sciencedirect.com", "wiley.com",
                        "nature.com", "plos.org", "mdpi.com", "frontiersin.org",
                        "academic.oup.com", "biorxiv.org", "medrxiv.org"]),
    ("government_health", ["fda.gov", "ema.europa.eu", "who.int", "nih.gov",
                            "nccih.nih.gov", "ayush.gov.in"]),
    ("medical_reference", ["webmd.com", "mayoclinic.org", "medlineplus.gov",
                            "msdmanuals.com", "uptodate.com"]),
    ("herbal_database", ["examine.com", "herbalgram.org", "https://cb.imsc.res.in/imppat/https://cb.imsc.res.in/imppat/",
                         "consumerlab.com", "naturalstandard.com"]),
]


def lambda_handler(event, context):
    logger.info(f"Event: {json.dumps(event, default=str)}")

    action_group = event.get("actionGroup", "web_search")
    function = event.get("function", "")
    params = {p["name"]: p["value"] for p in event.get("parameters", [])}

    try:
        if function == "web_search":
            try:
                max_results = int(params.get("max_results", "5"))
            except (ValueError, TypeError):
                max_results = 5
            result = web_search(
                params.get("query", ""),
                params.get("search_depth", "advanced"),
                max_results,
            )
        else:
            result = {"error": f"Unknown function: {function}"}
    except Exception as e:
        logger.exception(f"Error in {function}")
        result = {"error": str(e)}

    return bedrock_response(action_group, function, result)


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


def _categorize_source(url: str, title: str, snippet: str) -> str:
    """Categorize a web source based on URL domain and content keywords."""
    url_lower = url.lower()
    title_lower = title.lower()
    combined = f"{url_lower} {title_lower} {snippet.lower()}"

    for category, patterns in SOURCE_CATEGORIES:
        for pattern in patterns:
            if pattern in url_lower:
                return category

    admet_keywords = ["admet", "pharmacokinetic", "cyp450", "cyp inhibit",
                      "drug metabolism", "bioavailability", "absorption distribution"]
    if any(kw in combined for kw in admet_keywords):
        return "admet"

    if any(kw in combined for kw in ["clinical trial", "randomized controlled"]):
        return "clinical_trial"

    if any(kw in combined for kw in ["ayurved", "traditional medicine", "herbal", "phytochemical"]):
        return "herbal_database"

    return "general"


def web_search(query: str, search_depth: str = "basic", max_results: int = 5) -> dict:
    """Search the web using Tavily API for drug interaction data.

    Returns structured results with full source metadata and category labels.
    """
    if not query:
        return {"success": False, "message": "query is required"}

    api_key = _get_tavily_key()

    payload = json.dumps({
        "api_key": api_key,
        "query": query,
        "search_depth": search_depth,
        "max_results": max_results,
        "include_answer": True,
        "include_raw_content": False,
    }).encode("utf-8")

    req = Request(
        TAVILY_API_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except URLError as e:
        logger.error(f"Tavily API error: {e}")
        return {"success": False, "message": f"Web search failed: {e}"}

    sources = []
    categories_found = {}
    for r in data.get("results", []):
        url = r.get("url", "")
        title = r.get("title", "")
        snippet = r.get("content", "")[:500]
        category = _categorize_source(url, title, snippet)

        source = {
            "url": url,
            "title": title,
            "snippet": snippet,
            "score": r.get("score", 0),
            "category": category,
        }
        sources.append(source)

        if category not in categories_found:
            categories_found[category] = []
        categories_found[category].append(url)

    return {
        "success": True,
        "query": query,
        "answer": data.get("answer", ""),
        "sources": sources,
        "total_results": len(sources),
        "source_categories": categories_found,
    }
