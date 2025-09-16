# src/extract.py
import os
import json
import time
from typing import Dict, Any, Optional
from .utils import clean_text

def build_prompt(instructions: str, org: Dict[str, Any], texts: Dict[str, str]) -> str:
    scraped_snippets = []
    for url, t in texts.items():
        scraped_snippets.append(f"URL: {url}\nTEXT: {t[:4000]}")
    scraped = "\n\n".join(scraped_snippets[:6])
    user = f"""ORGANIZATION:
name: {org.get('name')}
country: {org.get('country')}
website: {org.get('website')}

SCRAPED:
{scraped}
"""
    return instructions + "\n\n" + user

def _first_string_leaf(obj: Any) -> Optional[str]:
    """Recursively find first string leaf in a JSON-like structure."""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        for v in obj.values():
            found = _first_string_leaf(v)
            if found:
                return found
    if isinstance(obj, list):
        for item in obj:
            found = _first_string_leaf(item)
            if found:
                return found
    return None

def call_ollama(model: str, prompt: str, max_tokens: int = 800, temperature: float = 0.1) -> str:
    """
    Robust Ollama caller:
      - Tries /api/generate first (common older style).
      - Falls back to /api/chat with messages payload.
      - Accepts several response shapes and returns a best-effort string.
    Raises RuntimeError if all attempts fail.
    """
    import requests

    base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    headers = {"Content-Type": "application/json"}
    endpoints = [
        ("/api/generate", "generate"),
        ("/api/chat", "chat")
    ]

    last_exc = None
    for ep, kind in endpoints:
        url = base + ep
        try:
            if kind == "generate":
                payload = {
                    "model": model,
                    "prompt": prompt,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "stream": False,
                    "format": "json"
                }
                r = requests.post(url, json=payload, headers=headers, timeout=120)
                # If endpoint doesn't exist, try next
                if r.status_code == 404:
                    last_exc = f"404 {url}"
                    continue
                r.raise_for_status()
                try:
                    data = r.json()
                except ValueError:
                    # non-json body -> return text
                    return r.text
                # common shapes: {"response": "..."} or {"results": [...]}
                if isinstance(data, dict):
                    if "response" in data and isinstance(data["response"], str):
                        return data["response"]
                    if "results" in data and isinstance(data["results"], list):
                        # join any text-ish values
                        texts = []
                        for item in data["results"]:
                            if isinstance(item, dict):
                                for v in item.values():
                                    if isinstance(v, str):
                                        texts.append(v)
                        if texts:
                            return "\n".join(texts)
                # fallback: first string leaf
                s = _first_string_leaf(data)
                if s:
                    return s
                # nothing found, return empty
                return ""
            else:  # chat
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "Respond with a SINGLE valid JSON object only."},
                        {"role": "user", "content": prompt}],                
                    "temperature": temperature
                }
                r = requests.post(url, json=payload, headers=headers, timeout=120)
                if r.status_code == 404:
                    last_exc = f"404 {url}"
                    continue
                r.raise_for_status()
                try:
                    data = r.json()
                except ValueError:
                    return r.text
                # common shapes:
                # 1) {"choices":[{"message":{"content":"..."}}]}
                # 2) {"message": {"content": "..."}}
                if isinstance(data, dict):
                    choices = data.get("choices")
                    if isinstance(choices, list) and len(choices) > 0:
                        first = choices[0]
                        if isinstance(first, dict):
                            if "message" in first and isinstance(first["message"], dict):
                                content = first["message"].get("content")
                                if content:
                                    return content
                            if "content" in first and isinstance(first["content"], str):
                                return first["content"]
                    if "message" in data and isinstance(data["message"], dict):
                        return data["message"].get("content", "")
                s = _first_string_leaf(data)
                if s:
                    return s
                return ""
        except requests.exceptions.RequestException as e:
            last_exc = e
            # try next endpoint
            continue

    raise RuntimeError(f"Ollama call failed for endpoints {endpoints}. Last error: {last_exc}")

def call_openai(model: str, prompt: str, max_tokens: int = 800, temperature: float = 0.1) -> str:
    """
    Minimal OpenAI adapter (kept mostly as-is). If you use OpenAI, ensure your
    API key is set in OPENAI_API_KEY environment variable.
    """
    import requests, os
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a strict information extraction assistant. Output ONLY valid JSON."},
            {"role": "user", "content": prompt}
        ],
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    r = requests.post(f"{base}/chat/completions", headers=headers, json=payload, timeout=120)
    r.raise_for_status()
    data = r.json()
    # Expect standard OpenAI response
    try:
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        # fallback: first string leaf
        s = _first_string_leaf(data)
        if s:
            return s
        raise

def extract_record(provider: str, model: str, instructions: str, org: Dict[str,Any], texts: Dict[str,str],
                   max_tokens: int, temperature: float) -> Dict[str,Any]:
    prompt = build_prompt(instructions, org, texts)
    if provider == "ollama":
        out = call_ollama(model, prompt, max_tokens, temperature)
    elif provider == "openai":
        out = call_openai(model, prompt, max_tokens, temperature)
    else:
        raise ValueError("Unknown provider")

    # Try strict parse
    try:
        return json.loads(out)
    except Exception:
        # Try to extract the first {...} block
        import re
        m = re.search(r'\{.*\}', out, flags=re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass  # fall through to fallback

        # Fallback: return a structured "empty" record with a helpful note
        snippet = (out or "").strip()
        if len(snippet) > 400:
            snippet = snippet[:400] + "..."
        return {
            "name": org.get("name"),
            "country": org.get("country"),
            "website": org.get("website"),
            "classification": None,
            "sectors": [],
            "angel_type": None,
            "ticket_size_usd_min": None,
            "ticket_size_usd_max": None,
            "ticket_size_currency": None,
            "stages": [],
            "notes": f"Model returned non-JSON. Raw snippet: {snippet}",
            "sources": [],
            "confidence": 0.0
        }