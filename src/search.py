import json, os, time
from duckduckgo_search import DDGS
from typing import List, Dict, Any

def search_org(query: str, max_results: int = 6) -> List[Dict[str, Any]]:
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=max_results))
    return results
