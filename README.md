# Olist BI Portfolio

A full analytics pipeline built on Olist's real Brazilian e-commerce dataset (~100K orders): raw ingestion → clean Single-Source-of-Truth tables → ad hoc business analysis → a live dashboard → an AI-assisted query tool → an automated BI bridge into Looker Studio.

**Live demos:**
- Dashboard: [olist-bi-portfolio-clclyde.streamlit.app](https://olist-bi-portfolio-clclyde.streamlit.app)
- Source: [github.com/clclyde/olist-bi-portfolio](https://github.com/clclyde/olist-bi-portfolio)
- Looker Studio report: [datastudio.google.com/reporting/f7e8e0f4-0aac-47c9-99cb-82227f018ca4](https://datastudio.google.com/reporting/f7e8e0f4-0aac-47c9-99cb-82227f018ca4)

---

## Why this project exists

This project demonstrates the reporting/analytics workflow end to end, using a real, messy public dataset rather than a toy one — from raw ingestion through data-quality fixes, business analysis, a live BI dashboard, and an AI-assisted natural-language query layer.

## Architecture

```mermaid
flowchart LR
    subgraph Source
        A[Raw Olist CSVs<br/>9 tables, ~100K orders]
    end

    subgraph Supabase [Supabase Postgres]
        B[raw schema<br/>direct load]
        C[clean schema<br/>SSOT tables]
        B --> C
    end

    A --> B

    C --> D[Streamlit Dashboard<br/>live queries on every load]
    C --> E[AI Query Assistant<br/>Gemini NL-to-SQL<br/>read-only role]
    C --> F[n8n Scheduled Workflow<br/>3 branches, hourly]

    F --> G[Google Sheets<br/>one tab per analysis]
    G --> H[Looker Studio Report]

    style C fill:#2d5,stroke:#333
    style E fill:#59c,stroke:#333
```

**Why the Sheets bridge exists:** Looker Studio's native PostgreSQL connector could not establish a working connection to Supabase (a persistent, unresolved system error occurred across both pooler and direct-connection configurations). Rather than being blocked, the pipeline routes through an automated n8n workflow that writes query results into Google Sheets on a schedule, which Looker Studio reads from instead — fully automated, no manual export step.

## Tech stack

| Layer | Tool |
|---|---|
| Database | Supabase (managed Postgres) |
| Dashboard | Streamlit |
| AI query layer | Gemini API (`gemini-3.5-flash-lite`) |
| Automation / BI bridge | n8n (self-hosted) |
| Reporting | Looker Studio, Google Sheets |
| Language | Python (pandas, SQLAlchemy) |

## Data-quality fixes applied

- **Geolocation deduplication:** ~1M noisy lat/long readings collapsed to 19,015 unique zip codes, by averaging coordinates and taking the most frequent city/state spelling per zip.
- **Review deduplication:** 551 duplicate review submissions resolved to one canonical review per order, using a most-recent-row-wins rule.

These two fixes required opposite resolution strategies — see the write-up in `docs/DATA_DICTIONARY.md` for the reasoning behind each.

## Key findings

| Question | Result |
|---|---|
| Which product categories have the worst late-delivery rates? | Health & Beauty: 9.06% late rate on 9,467 items — large enough sample to be a real pattern |
| Does delivery time affect customer satisfaction? | Correlation: **-0.334** (moderate negative) |
| Do higher-value orders get split into more installments? | Correlation: **+0.319** (moderate positive); avg order value rises from ~₱121 at 1 installment to ~₱419 at 10 |

## AI Query Assistant

A natural-language-to-SQL tab lets you ask a question in plain English (e.g. *"Which 5 states have the most orders?"*) and get back the generated SQL, the query results, and a one-line AI-generated interpretation.

**Safety design:**
- Runs on a dedicated Postgres role (`ai_readonly`) with `SELECT`-only access to the `clean` schema — no write ability exists at the database level, regardless of what's asked.
- Generated SQL is validated before execution: must be a single `SELECT` statement, checked against a list of forbidden keywords (`INSERT`, `UPDATE`, `DELETE`, `DROP`, etc.), with a `LIMIT` enforced if missing.
- The generated SQL is always displayed before running — never executed as a black box.

## Setup

```bash
pip3 install streamlit pandas sqlalchemy psycopg2-binary plotly google-generativeai
```

Create `.streamlit/secrets.toml` (never committed — already in `.gitignore`):

```toml
[connections.supabase]
connection_string = "postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres"

[connections.supabase_readonly]
connection_string = "postgresql://ai_readonly.[PROJECT-REF]:[PASSWORD]@aws-0-[region].pooler.supabase.com:5432/postgres"

[gemini]
api_key = "your-gemini-api-key"
```

Run:

```bash
streamlit run app.py
```

## Repo structure

```
.
├── app.py                          # Streamlit dashboard + AI Query Assistant
├── setup_ai_readonly_role.sql      # One-time DB role setup for the AI tab
├── docs/
│   └── DATA_DICTIONARY.md          # Full schema reference
├── n8n/                             # (optional) exported workflow JSON
└── README.md
```

## Roadmap

- [x] Day 1 — Raw schema loaded, row counts verified
- [x] Day 2 — Clean SSOT layer (dims, facts, delivery/dedup logic)
- [x] Day 3 — Three business analyses with insight memos
- [x] Day 4 — Live Streamlit dashboard, deployed
- [x] Day 5 — AI Query Assistant (Gemini NL-to-SQL, read-only role)
- [ ] Day 6 — Documentation (this file + data dictionary + architecture diagram)
- [ ] Day 7 — Rehearsal
