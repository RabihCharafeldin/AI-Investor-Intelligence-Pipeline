import os, re, time, json, hashlib, pathlib, tldextract, requests
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin, urlparse

def slugify(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')

def ensure_dir(path: str):
    pathlib.Path(path).mkdir(parents=True, exist_ok=True)

def sha1(text: str) -> str:
    return hashlib.sha1(text.encode('utf-8', errors='ignore')).hexdigest()

def get_session(user_agent: str, timeout: int):
    s = requests.Session()
    s.headers.update({"User-Agent": user_agent})
    s.timeout = timeout
    return s

def is_probable_homepage(url: str) -> bool:
    p = urlparse(url)
    return (p.path in ('', '/', '/en', '/ar', '/en/') and not p.query)

COMMON_PATHS = [
    "/about", "/about-us", "/who-we-are", "/programs", "/programmes",
    "/portfolio", "/investments", "/our-investments", "/companies",
    "/what-we-do", "/strategy"
]

def expand_candidate_urls(base_url: str) -> List[str]:
    out = [base_url]
    for path in COMMON_PATHS:
        out.append(urljoin(base_url, path))
    return out

def clean_text(text: str) -> str:
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def currency_in_text(text: str) -> Optional[str]:
    m = re.search(r'\b(USD|US\$|\$|EUR|GBP|AED|SAR|EGP|MAD|TND|LBP|QAR|KWD|OMR)\b', text, re.I)
    return m.group(1) if m else None
