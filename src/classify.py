import re
from typing import List, Optional

BANK_WORDS = ["bank", "sovereign", "treasury", "sovereign wealth", " صندوق ", "بنك"]
ACCEL_WORDS = ["accelerator", "acceleration"]
INCUB_WORDS = ["incubator", "incubation"]
ANGEL_WORDS = ["angel", "angel network"]
VC_WORDS = ["venture capital", "vc fund", "vc", "seed fund", "growth fund", "equity fund"]
MICROFIN_WORDS = ["microfinance", "micro-finance", "micro finance"]

def keyword_classify(name: str, text: str) -> Optional[str]:
    s = f"{name} {text}".lower()
    if any(w in s for w in BANK_WORDS): return "bank_or_sovereign_fund"
    if any(w in s for w in MICROFIN_WORDS): return "microfinance"
    if any(w in s for w in ANGEL_WORDS): return "angel_investor"
    if any(w in s for w in ACCEL_WORDS): return "accelerator"
    if any(w in s for w in INCUB_WORDS): return "incubator"
    if any(w in s for w in VC_WORDS): return "venture_capital"
    return None

def infer_stage_from_ticket(amount_usd: float) -> Optional[str]:
    if amount_usd is None: return None
    if 100_000 <= amount_usd <= 500_000: return "Pre-seed"
    if 500_000 < amount_usd <= 2_000_000: return "Seed"
    if 2_000_000 < amount_usd <= 10_000_000: return "Series A"
    if 10_000_000 < amount_usd <= 30_000_000: return "Series B"
    if amount_usd > 30_000_000: return "Series C"
    return None

SECTOR_KEYWORDS = {
    "WASH": [
        "water", "sanitation", "hygiene", "drinking water", "wastewater",
        "sewage", "latrine", "handwashing", "cholera", "public health",
        "wash program", "water supply", "safe water", "sanitary"
    ],
    "RE (renewable energy)": [
        "renewable energy", "solar", "photovoltaic", "pv",
        "wind", "hydro", "geothermal", "clean energy", "green energy",
        "energy transition", "power purchase agreement", "ppa"
    ],
    "Agritech": [
        "agritech", "agri-tech", "agriculture", "farming", "farm",
        "agri-food", "agri supply chain", "crop", "livestock",
        "precision agriculture", "agronomy", "agri inputs"
    ],
    "entrepreneurship": [
        "startup", "startups", "sme", "incubation", "acceleration",
        "venture", "founder", "entrepreneur", "entrepreneurship",
        "ecosystem", "innovation hub", "coworking"
    ],
}

def infer_sector_from_text(text: str) -> Optional[str]:
    """
    Score sectors by keyword matches and return ONE sector.
    Priority if tie: WASH > RE (renewable energy) > Agritech > entrepreneurship.
    Returns None if no meaningful hits.
    """
    if not text:
        return None
    s = text.lower()
    scores = {k: 0 for k in SECTOR_KEYWORDS.keys()}
    for sector, kws in SECTOR_KEYWORDS.items():
        for kw in kws:
            if kw in s:
                scores[sector] += 1

    # No hits?
    if all(v == 0 for v in scores.values()):
        return None

    # Tie-break by priority
    priority = ["WASH", "RE (renewable energy)", "Agritech", "entrepreneurship"]
    best = max(priority, key=lambda k: (scores[k], -priority.index(k)))
    # If the winning score is tiny (e.g., 1) and it's only "entrepreneurship" type words,
    # we keep it; but you can require >=2 if you want stricter matching.
    return best


# --- Funding classification keyword hints (fallbacks) ---
CLS_HINTS = [
    ("Sovereign Wealth Funds", ["sovereign wealth", "fund for future generations", "pif", "mubadala", "qia"]),
    ("Venture Capital Funds", ["venture capital", "vc fund", "seed fund", "growth fund", "series a", "series b"]),
    ("Angel Investors", ["angel investor", "angel network", "angel group", "syndicate"]),
    ("Microfinance Institutions", ["microfinance", "micro-credit", "micro finance"]),
    ("Accelerators", ["accelerator program", "acceleration program"]),
    ("Incubators", ["incubator", "incubation program"]),
    ("Investment Firms", ["investment firm", "investment company", "private equity", "holding company", "investment bank", "merchant bank"]),
    ("Coworking Spaces", ["coworking", "co-working", "shared workspace"]),
    ("Entrepreneurship Support Agencies", ["agency", "authority", "ministry", "directorate", "national program", "ecosystem support", "policy program"]),
    ("Universities & Research Centers", ["university", "research center", "research institute", "technology transfer", "tto"]),
]

def heuristic_funding_classification(name: str, text: str) -> str:
    s = f"{name} {text}".lower()
    for label, kws in CLS_HINTS:
        if any(kw in s for kw in kws):
            return label
    # banks → Investment Firms (unless sovereign already detected)
    if "bank" in s:
        return "Investment Firms"
    return "Investment Firms"  # safe default

# --- Sector inference for your new taxonomy (multi) ---
NEW_SECTOR_KEYWORDS = {
    "ICT": ["software", "ai", "cloud", "big data", "cybersecurity", "fintech", "insurtech", "proptech", "e-commerce"],
    "Health": ["biotech", "pharma", "medtech", "digital health", "life sciences"],
    "Energy": ["renewable", "solar", "wind", "hydro", "cleantech", "energy storage", "efficiency", "oil", "gas"],
    "Agriculture": ["agritech", "agri-tech", "agriculture", "farming", "foodtech", "crop", "livestock"],
    "Environment": ["water management", "waste", "recycling", "climate", "conservation", "carbon"],
    "Industry & Manufacturing": ["robotics", "automation", "advanced materials", "3d printing", "manufacturing"],
    "Transportation & Mobility": ["aviation", "automotive", "shipping", "logistics", "ev", "mobility", "space tech"],
    "Education": ["edtech", "education", "training", "skills", "learning"],
    "Creative Industries": ["media", "gaming", "film", "design", "digital content", "creative"],
    "Infrastructure & Real Estate": ["real estate", "housing", "smart city", "construction", "industrial zone", "infrastructure"],
    "Social Impact": ["poverty", "women", "refugee", "youth employment", "inclusive"],
    "Business & Professional Services": ["banking", "insurance", "asset management", "consulting", "law firm", "advisory", "professional services"]
}

def infer_sectors_multi(text: str):
    s = (text or "").lower()
    hits = []
    for sector, kws in NEW_SECTOR_KEYWORDS.items():
        for kw in kws:
            if kw in s:
                hits.append(sector)
                break
    return hits[:4]  # cap to keep it concise

