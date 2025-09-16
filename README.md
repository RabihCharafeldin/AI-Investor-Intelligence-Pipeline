# Investor Enrichment Pipeline

> Low-cost, semi-automatic enrichment for ESCWA’s Master Investors List.  
> Scrapes websites, extracts structured facts with a local LLM, and writes back to Excel/CSV.

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)]()
[![Ollama](https://img.shields.io/badge/Ollama-optional-brightgreen.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)]()

---

## ✨ Why this project?

- **Practical AI engineering**: combines scraping, search, and LLM extraction.
- **Cost-aware**: runs fully local with Ollama; OpenAI is optional.
- **Repeatable**: idempotent, checkpointed writes, progress logging, and resume flags.

---

## 🚀 Features

- Reads an Excel sheet (default: `Master sheet`) and iterates each row.
- Picks an official website from the sheet’s `favoriteUrl` (even if written as free-text like `Name (domain.com)`), or searches DuckDuckGo.
- Scrapes homepage + likely pages (About, Investments, Programs, Portfolio).
- Cleans text and prompts an LLM (Ollama by default) for **structured extraction**:
  - Funding Classification (e.g., Venture Capital Funds, Angel Investors, Microfinance Institutions, …)
  - Sectors (multi-label; normalized, e.g., `ICT`, `Energy`, `Health`, …)
  - Ticket size stages (for VC): `Pre-Seed, Seed, Series A, …`
  - Angel type: `individual` / `network`
  - Additional Info: short, natural profile sentence(s)
- Saves results to:
  - `data/output/enriched.csv`
  - `data/output/Master sheet (enriched).xlsx`
- Logs progress per row & checkpoints every 10 rows.
- Resilient: continues on errors; resume from a row index.

---

## 📂 Repo structure

Automation/
README.md
LICENSE
.gitignore
.env.example
requirements.txt
config.yaml
data/
input/ # (ignored) put your Excel here
output/ # (ignored) enriched CSV/Excel outputs
cache/ # (ignored) cached pages & search results
src/
init.py
main.py
utils.py
search.py
scrape.py
classify.py
extract.py
prompts/
extract.py

---

## ⚡ Quickstart

### 1) Python env
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt

2) Choose your LLM provider

Option A — Free/Local (recommended: Ollama)

Install: https://ollama.com

Pull model:

ollama pull llama3:latest


Ensure Ollama is running (http://localhost:11434).

Option B — OpenAI

Create .env from .env.example and set:

OPENAI_API_KEY=your_key_here


In config.yaml:

llm:
  provider: openai
  model: gpt-4o-mini

3) Configure config.yaml

Example:

paths:
  output_dir: data/output
excel:
  sheet: Master sheet
  name_col: Name
  country_col: Country
  website_col: favoriteUrl
  out_cols:
    funding_classification: Funding Classification
    sector: Sector
    ticket_size_vc: Ticket size (for Venture Capital)
    angel_type: Individual or Network (for Angel Investors)
    note: Additional Info
llm:
  provider: ollama
  model: llama3:latest
  temperature: 0.1
  max_tokens: 800
network:
  timeout: 15
  sleep_between_requests_sec: 1.0
limits:
  max_pages_per_site: 2
  max_chars_for_llm: 12000

4) Run
python -m src.main --input-file "data/input/Master Investors List.xlsx" \
                   --sheet "Master sheet" \
                   --only-missing \
                   --log-level INFO


Useful flags:

--limit 30 → process first 30 rows

--start 200 → resume from row 200

--resume → skip rows with Additional Info already filled

--log-level DEBUG → verbose scraping logs

🛠️ Tech stack

Python: requests, pandas, BeautifulSoup, tenacity

Search: DuckDuckGo

Scraping: requests + BeautifulSoup + trafilatura

LLM: Ollama (local) or OpenAI (cloud)

Ops: logging, retries, checkpointing

📈 Roadmap

 Add provenance (record which URLs supported classification)

 Parallelize scraping (thread pool)

 Streamlit UI to preview enriched data

 n8n workflow for automation