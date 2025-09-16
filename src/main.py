# src/main.py
import os, time, argparse, logging, pandas as pd, yaml
from typing import Dict, Any, List
from dotenv import load_dotenv
from tenacity import retry, wait_fixed, stop_after_attempt
from urllib.parse import urlparse, parse_qs

from .utils import ensure_dir, get_session
from . import search as search_mod
from . import scrape as scrape_mod
from . import extract as extract_mod
from . import classify as classify_mod


# -------------------------
# Logging setup
# -------------------------
def setup_logging(level: str = "INFO"):
    lvl = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=lvl,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("duckduckgo_search").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)

log = logging.getLogger("escwa")


# -------------------------
# Helpers & fallbacks
# -------------------------
@retry(wait=wait_fixed(1), stop=stop_after_attempt(2))
def safe_search(query: str, k: int = 6):
    return search_mod.search_org(query, max_results=k)

def _normalize_ddg_href(raw: str) -> str | None:
    """
    DuckDuckGo sometimes returns redirect links like:
      https://duckduckgo.com/l/?uddg=<encoded_url>&rut=...
    Extract a clean http(s) URL from 'uddg' if present, otherwise return the raw if it's http(s).
    """
    if not isinstance(raw, str):
        return None
    raw = raw.strip()
    if not raw:
        return None
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    try:
        p = urlparse(raw)
        if ("duckduckgo.com" in (p.netloc or "")) and (p.path or "").startswith("/l/"):
            qs = parse_qs(p.query or "")
            uddg = qs.get("uddg", [None])[0]
            if isinstance(uddg, str) and (uddg.startswith("http://") or uddg.startswith("https://")):
                return uddg
    except Exception:
        pass
    return None

def _is_social(url: str) -> bool:
    u = (url or "").lower()
    return any(s in u for s in ["linkedin.com","facebook.com","twitter.com","x.com","instagram.com","t.co"])

def choose_website(favorite_url: str, search_results: List[Dict[str,Any]]):
    # Prefer provided favorite_url if we can extract a usable URL/domain from it
    if isinstance(favorite_url, str) and favorite_url.strip():
        fav = _extract_url_from_freeform(favorite_url)
        if fav and not _is_social(fav):
            log.debug(f"favorite_url raw='{favorite_url}' -> parsed='{fav}'")
            return fav
        else:
            log.debug(f"favorite_url raw='{favorite_url}' -> no valid URL parsed")

    # Else first valid non-social http(s) URL from search results
    for r in (search_results or []):
        candidate = r.get("href") or r.get("link")
        candidate = _normalize_ddg_href(candidate) if candidate else None
        if candidate and not _is_social(candidate):
            return candidate
    return None

def clip(s: str, n: int = 220):
    if not s: return None
    s = s.strip()
    return (s[:n] + "...") if len(s) > n else s

def _joined_text(texts_dict: Dict[str, str]) -> str:
    return " ".join(texts_dict.values()) if texts_dict else ""

import re
from urllib.parse import urlparse, parse_qs

DOMAIN_RE = re.compile(
    r"(?:(?:https?://)?)([A-Za-z0-9.-]+\.[A-Za-z]{2,})(?:[/?#][^\s]*)?",
    re.IGNORECASE
)

def _normalize_scheme(url: str) -> str:
    """Ensure a URL has https:// if no scheme present."""
    if not isinstance(url, str):
        return None
    url = url.strip()
    if not url:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return "https://" + url

def _extract_url_from_freeform(text: str) -> str | None:
    """
    Extract a usable URL from a freeform favorite_url cell.
    Handles:
      - real http(s) links inside the string
      - bare domains anywhere (including inside parentheses)
    Returns a normalized https:// URL or None.
    """
    if not isinstance(text, str):
        return None
    s = text.strip()
    if not s:
        return None

    # 1) Any explicit http(s)://... inside?
    m = re.search(r"https?://[^\s)]+", s, re.IGNORECASE)
    if m:
        return m.group(0)

    # 2) Domain-like token anywhere (e.g., inside parentheses)
    m = DOMAIN_RE.search(s)
    if m:
        domain = m.group(1)
        # filter obvious social
        if _is_social(domain):
            return None
        return _normalize_scheme(domain)

    return None

def _normalize_ddg_href(raw: str) -> str | None:
    """
    DuckDuckGo sometimes returns redirect links like:
      https://duckduckgo.com/l/?uddg=<encoded_url>&rut=...
    Extract a clean http(s) URL from 'uddg' if present, otherwise return the raw if it's http(s).
    """
    if not isinstance(raw, str):
        return None
    raw = raw.strip()
    if not raw:
        return None
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    try:
        p = urlparse(raw)
        if ("duckduckgo.com" in (p.netloc or "")) and (p.path or "").startswith("/l/"):
            qs = parse_qs(p.query or "")
            uddg = qs.get("uddg", [None])[0]
            if isinstance(uddg, str) and (uddg.startswith("http://") or uddg.startswith("https://")):
                return uddg
    except Exception:
        pass
    return None

def _is_social(url: str) -> bool:
    u = (url or "").lower()
    return any(s in u for s in ["linkedin.com","facebook.com","twitter.com","x.com","instagram.com","t.co"])


def _as_string_sector_list(raw) -> List[str]:
    """
    Normalize sectors field to list[str]. Accepts: None, str, list[str], list[dict], mixed.
    Tries dict keys: name/label/value/sector.
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw.strip()] if raw.strip() else []
    if isinstance(raw, list):
        out = []
        for item in raw:
            if isinstance(item, str):
                s = item.strip()
                if s: out.append(s)
            elif isinstance(item, dict):
                for k in ("name", "label", "value", "sector"):
                    v = item.get(k)
                    if isinstance(v, str) and v.strip():
                        out.append(v.strip())
                        break
            else:
                s = str(item).strip()
                if s: out.append(s)
        return out
    s = str(raw).strip()
    return [s] if s else []


# -------------------------
# Additional-info synthesis (fallback)
# -------------------------
def synth_additional_info(name: str, country: str|None, fc: str, sectors: List[str]) -> str:
    region = country or "the region"
    sec_txt = ", ".join(sectors) if sectors else "key industries"
    T = {
        "Venture Capital Funds": f"A venture capital firm investing across {sec_txt}. {name} backs startups in {region} with funding and strategic support.",
        "Investment Firms": f"An investment firm providing capital and strategic support across {sec_txt}. {name} partners with companies in {region} to scale and optimize operations.",
        "Angel Investors": f"An angel {('network' if 'network' in (name.lower()) else 'investor')} backing early-stage startups in {sec_txt}. {name} supports founders in {region} with capital and guidance.",
        "Microfinance Institutions": f"A microfinance institution enabling access to finance for micro and small enterprises. {name} serves entrepreneurs in {region} through tailored credit solutions.",
        "Accelerators": f"An accelerator delivering programs and mentorship for startups. {name} helps founders in {region} validate, build, and grow.",
        "Incubators": f"An incubator providing workspace and hands-on support for early ventures. {name} nurtures entrepreneurs in {region} from idea to startup.",
        "Sovereign Wealth Funds": f"A sovereign wealth fund investing for long-term national value. {name} allocates capital to diversified sectors in {region}.",
        "Coworking Spaces": f"A coworking hub offering flexible workspace and community for entrepreneurs. {name} hosts teams and events in {region}.",
        "Entrepreneurship Support Agencies": f"An ecosystem support organization delivering programs and services for entrepreneurs. {name} promotes startup growth in {region}.",
        "Universities & Research Centers": f"A university/research center fostering innovation and commercialization. {name} supports research-based ventures in {region}.",
    }
    text = T.get(fc) or f"An organization operating across {sec_txt}. {name} supports businesses in {region}."
    return clip(text, 220)


# -------------------------
# Normalization for the sheet
# -------------------------
SECTOR_ALIAS_WRITE = {
    "Information & Communication Technology (ICT)": "ICT",
    "ICT": "ICT",
}

DEFAULT_SECTOR_BY_FC = {
    "Investment Firms": "Business & Professional Services",
    "Sovereign Wealth Funds": "Business & Professional Services",
    "Venture Capital Funds": "Business & Professional Services",
    "Angel Investors": "Business & Professional Services",
    "Microfinance Institutions": "Business & Professional Services",
    "Accelerators": "Business & Professional Services",
    "Incubators": "Business & Professional Services",
    "Coworking Spaces": "Business & Professional Services",
    "Entrepreneurship Support Agencies": "Business & Professional Services",
    "Universities & Research Centers": "Education",
}

ALLOWED_SECTORS = {
    "Information & Communication Technology (ICT)", "ICT", "Health", "Energy", "Agriculture", "Environment",
    "Industry & Manufacturing", "Transportation & Mobility", "Education", "Creative Industries",
    "Infrastructure & Real Estate", "Social Impact", "Business & Professional Services"
}

def map_sector_label_for_sheet(s: str) -> str:
    return SECTOR_ALIAS_WRITE.get(s, s)

def normalize_to_columns(record: Dict[str,Any], cfg: Dict[str,Any]) -> Dict[str,Any]:
    out = {}
    cols = cfg["excel"]["out_cols"]

    fc = record.get("funding_classification")
    out[cols["funding_classification"]] = fc

    sectors = [map_sector_label_for_sheet(s) for s in (record.get("sectors") or [])]
    out[cols["sector"]] = ", ".join(sectors) if sectors else None

    stages = record.get("stages") or []
    out[cols["ticket_size_vc"]] = ", ".join(stages) if (fc == "Venture Capital Funds" and stages) else None

    angel_type = record.get("angel_type")
    out[cols["angel_type"]] = angel_type if (fc == "Angel Investors") else None

    out[cols["note"]] = record.get("additional_info")
    return out


# -------------------------
# Record sanitization (policy + fallbacks)
# -------------------------
def sanitize_record(org: Dict[str,Any], record: Dict[str,Any], heuristic_fc: str, inferred_sectors: List[str]) -> Dict[str,Any]:
    fc = (record.get("funding_classification") or "").strip()
    if not fc:
        record["funding_classification"] = heuristic_fc or "Investment Firms"

    if record["funding_classification"] == "Angel Investors":
        at = record.get("angel_type")
        if not at:
            name_lower = (org.get("name") or "").lower()
            record["angel_type"] = "network" if ("network" in name_lower or "group" in name_lower or "syndicate" in name_lower) else "individual"
    else:
        record["angel_type"] = None

    # sectors: normalize to strings, then filter
    model_secs_raw = _as_string_sector_list(record.get("sectors"))
    model_secs = [s for s in model_secs_raw if s in ALLOWED_SECTORS]
    if not model_secs:
        inferred_raw = _as_string_sector_list(inferred_sectors)
        model_secs = [s for s in inferred_raw if s in ALLOWED_SECTORS]
    if not model_secs:
        model_secs = [DEFAULT_SECTOR_BY_FC.get(record["funding_classification"], "Business & Professional Services")]
    record["sectors"] = list(dict.fromkeys(model_secs))[:4]

    # additional info: prefer model text; fallback to synthesized
    ai = record.get("additional_info")
    if ai and isinstance(ai, str) and len(ai.strip()) > 10:
        record["additional_info"] = clip(ai, 220)
    else:
        record["additional_info"] = synth_additional_info(
            org.get("name") or "",
            org.get("country"),
            record["funding_classification"],
            [map_sector_label_for_sheet(s) for s in record["sectors"]],
        )

    if record["funding_classification"] != "Venture Capital Funds":
        record["stages"] = []
        record["ticket_size_usd_min"] = None
        record["ticket_size_usd_max"] = None
        record["ticket_size_currency"] = None

    srcs = record.get("sources") or []
    record["sources"] = (srcs[:5] if isinstance(srcs, list) else [])
    return record


# -------------------------
# Main
# -------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-file", required=True, help="Path to Master Investors List.xlsx")
    ap.add_argument("--sheet", default=None, help="Excel sheet name (default from config)")
    ap.add_argument("--limit", type=int, default=None, help="Limit number of rows to process")
    ap.add_argument("--only-missing", action="store_true", help="Process only rows with empty output columns")
    ap.add_argument("--resume", action="store_true", help="Skip rows with 'Additional Info' already filled (assumes processed)")
    ap.add_argument("--start", type=int, default=0, help="Start processing from this DataFrame index after filtering")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--log-level", default="INFO", help="DEBUG, INFO, WARNING, ERROR")
    args = ap.parse_args()

    setup_logging(args.log_level)
    load_dotenv()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    sheet = args.sheet or cfg["excel"]["sheet"]
    name_col = cfg["excel"]["name_col"]
    country_col = cfg["excel"]["country_col"]
    website_col = cfg["excel"]["website_col"]
    out_cols = cfg["excel"]["out_cols"]

    df = pd.read_excel(args.input_file, sheet_name=sheet)

    # Ensure output columns exist and are object dtype
    for _, colname in out_cols.items():
        if colname not in df.columns:
            df[colname] = pd.Series([None] * len(df), dtype="object")
        else:
            try:
                df[colname] = df[colname].astype("object")
            except Exception:
                df[colname] = df[colname].astype("string").astype("object")

    # Build indices to process
    indices = list(range(len(df)))
    if args.only_missing:
        mask = (
            df[out_cols["funding_classification"]].isna() &
            df[out_cols["sector"]].isna() &
            df[out_cols["ticket_size_vc"]].isna() &
            df[out_cols["angel_type"]].isna() &
            df[out_cols["note"]].isna()
        )
        indices = list(df[mask].index)

    if args.resume:
        indices = [i for i in indices if pd.isna(df.loc[i, out_cols["note"]])]

    # Apply start offset after filters
    if args.start and args.start > 0:
        indices = [i for i in indices if i >= args.start]

    if args.limit is not None:
        indices = indices[:args.limit]

    ensure_dir(cfg["paths"]["output_dir"])
    session = get_session(cfg["network"]["user_agent"], cfg["network"]["timeout"])

    total = len(indices)
    log.info(f"Starting run | rows to process: {total} | sheet: {sheet}")

    results = []
    from .prompts.extract import INSTRUCTIONS

    for n, i in enumerate(indices, start=1):
        t0 = time.perf_counter()
        try:
            row = df.iloc[i]
            org = {
                "name": str(row.get(name_col) or "").strip(),
                "country": str(row.get(country_col) or "").strip() or None,
                "website": str(row.get(website_col) or "").strip() or None
            }
            if not org["name"]:
                log.warning(f"[{n}/{total}] Row {i} skipped (no name)")
                continue

            # Search if needed
            sr = []
            if not org["website"]:
                q = f'{org["name"]} {org["country"] or ""}'.strip()
                try:
                    sr = safe_search(q, 6)
                except Exception as e:
                    log.warning(f"[{n}/{total}] Search failed for '{org['name']}' | {e}")
                    sr = []

            website = choose_website(org.get("website"), sr)
            org["website"] = website
            if website:
                # Try to log the matching search result title (best effort)
                chosen_title = None
                for r in (sr or []):
                    if _normalize_ddg_href(r.get("href") or r.get("link")) == website:
                        chosen_title = r.get("title")
                        break
                if chosen_title:
                    log.debug(f"[{n}/{total}] Website chosen: {chosen_title} -> {website}")
                else:
                    log.debug(f"[{n}/{total}] Website chosen: {website}")
            else:
                log.info(f"[{n}/{total}] No official website found; will use search fallbacks")

            # Scrape texts
            pages_scraped = 0
            texts = {}
            if website:
                texts = scrape_mod.scrape_site(
                    session,
                    website,
                    max_pages=cfg["limits"]["max_pages_per_site"],
                    sleep_sec=cfg["network"]["sleep_between_requests_sec"],
                ) or {}
                pages_scraped = len(texts)

            # If still empty, try top 2 search results as backup context (normalized URLs only)
            if not texts and sr:
                for r in sr[:2]:
                    raw = r.get("href") or r.get("link")
                    url = _normalize_ddg_href(raw)
                    if not url or _is_social(url):
                        continue
                    # Prefer fast, safe fetch with the session timeout; then try trafilatura with its timeout.
                    content = scrape_mod.fetch_and_parse(session, url) or scrape_mod.trafilatura_extract(url, timeout=12)
                    if content:
                        texts[url] = content
                pages_scraped = len(texts)


            joined = _joined_text(texts)[:8000]

            # Heuristic classification (new taxonomy)
            if hasattr(classify_mod, "heuristic_funding_classification"):
                heuristic_fc = classify_mod.heuristic_funding_classification(org["name"], joined)
            else:
                heur_legacy = getattr(classify_mod, "keyword_classify", lambda n,t: "")(org["name"], joined) or ""
                mapping = {
                    "venture_capital": "Venture Capital Funds",
                    "angel_investor": "Angel Investors",
                    "microfinance": "Microfinance Institutions",
                    "accelerator": "Accelerators",
                    "incubator": "Incubators",
                    "bank_or_sovereign_fund": "Sovereign Wealth Funds",
                }
                heuristic_fc = mapping.get(heur_legacy, "Investment Firms")

            # Sector inference (multi) as fallback
            if hasattr(classify_mod, "infer_sectors_multi"):
                inferred_sectors = classify_mod.infer_sectors_multi(joined)
            else:
                s = getattr(classify_mod, "infer_sector_from_text", lambda t: None)(joined)
                inferred_sectors = [s] if s else []

            # LLM extraction
            try:
                t_llm0 = time.perf_counter()
                record = extract_mod.extract_record(
                    cfg["llm"]["provider"],
                    cfg["llm"]["model"],
                    INSTRUCTIONS,
                    org,
                    texts,
                    cfg["llm"]["max_tokens"],
                    cfg["llm"]["temperature"],
                )
                t_llm1 = time.perf_counter()
                log.info(f"[{n}/{total}] {org['name']} — website:{website or 'N/A'} — scraped:{pages_scraped} — LLM:{t_llm1 - t_llm0:.1f}s")
            except Exception:
                log.exception(f"[{n}/{total}] LLM extraction failed for '{org['name']}' — using heuristic fallback")
                record = {
                    "name": org.get("name"),
                    "country": org.get("country"),
                    "website": org.get("website"),
                    "funding_classification": heuristic_fc,
                    "sectors": [],
                    "angel_type": None,
                    "ticket_size_usd_min": None,
                    "ticket_size_usd_max": None,
                    "ticket_size_currency": None,
                    "stages": [],
                    "additional_info": None,
                    "sources": [],
                    "confidence": 0.0,
                }

            # Sanitize & normalize
            record = sanitize_record(org, record, heuristic_fc, inferred_sectors)
            normalized = normalize_to_columns(record, cfg)

            # Update dataframe in-memory
            for col, val in normalized.items():
                df.at[i, col] = val

            # CSV row for checkpoints
            res = {"index": i, **org, **normalized}
            results.append(res)

            # Periodic save
            if len(results) % 10 == 0:
                log.info(f"Saving checkpoint at {len(results)} rows…")
                pd.DataFrame(results).to_csv(
                    os.path.join(cfg["paths"]["output_dir"], "enriched.csv"),
                    index=False,
                    encoding="utf-8-sig"
                )
                df.to_excel(os.path.join(cfg["paths"]["output_dir"], f"{sheet} (enriched).xlsx"), index=False)

            t1 = time.perf_counter()
            log.debug(f"[{n}/{total}] Done in {t1 - t0:.1f}s")

        except Exception:
            log.exception(f"[{n}/{total}] Hard failure on row {i} — skipping")
            # continue to next row

        time.sleep(0.5)

    # Final save
    log.info("Saving final outputs…")
    pd.DataFrame(results).to_csv(
        os.path.join(cfg["paths"]["output_dir"], "enriched.csv"),
        index=False,
        encoding="utf-8-sig"
    )
    df.to_excel(os.path.join(cfg["paths"]["output_dir"], f"{sheet} (enriched).xlsx"), index=False)
    log.info("All done.")


if __name__ == "__main__":
    main()
