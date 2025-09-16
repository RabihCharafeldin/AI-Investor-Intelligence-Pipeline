# src/scrape.py
from bs4 import BeautifulSoup
import requests, time
from .utils import clean_text

def fetch_and_parse(session: requests.Session, url: str) -> str:
    """
    Fetch a URL with the session's timeout and return cleaned visible text.
    Never raises; returns "" on failure.
    """
    try:
        r = session.get(url, allow_redirects=True, timeout=session.timeout if hasattr(session, "timeout") else 15)
        if r.status_code != 200 or not r.text:
            return ""
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script","style","noscript"]):
            tag.decompose()
        text = soup.get_text(separator=" ")
        return clean_text(text)
    except Exception:
        return ""

def trafilatura_extract(url: str, timeout: int = 12) -> str:
    """
    Use trafilatura with an explicit timeout. Returns "" on failure.
    """
    try:
        import trafilatura
        # trafilatura can hang if no timeout is set.
        downloaded = trafilatura.fetch_url(url, no_ssl=True, decode=True, timeout=timeout)
        if not downloaded:
            return ""
        content = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=False
        )
        return content or ""
    except Exception:
        return ""

def scrape_site(session: requests.Session, base_url: str, max_pages: int = 5, sleep_sec: float = 1.5) -> dict:
    """
    Try the homepage and some common internal pages (with timeouts).
    For each URL, try trafilatura first, then fallback to fetch_and_parse.
    """
    from .utils import expand_candidate_urls
    texts = {}
    for i, u in enumerate(expand_candidate_urls(base_url)):
        if i >= max_pages: break
        text = trafilatura_extract(u) or fetch_and_parse(session, u)
        if text:
            texts[u] = text[:6000]
        time.sleep(sleep_sec)
    return texts