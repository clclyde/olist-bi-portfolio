"""
Day 4-5: Live BI dashboard for the Olist portfolio project, now with an
AI Query Assistant tab (natural-language-to-SQL via Gemini).

Queries Supabase Postgres fresh on every load — no data caching, only the
DB connection itself is cached (a connection pool is a resource, not data).

SETUP:
    pip3 install streamlit pandas sqlalchemy psycopg2-binary plotly google-generativeai

    .streamlit/secrets.toml (NOT committed to git — add it to .gitignore):
        [connections.supabase]
        connection_string = "postgresql://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT-REF].supabase.co:5432/postgres"

        [connections.supabase_readonly]
        connection_string = "postgresql://ai_readonly.[YOUR-PROJECT-REF]:[PASSWORD]@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres"

        [gemini]
        api_key = "your-gemini-api-key"

RUN:
    streamlit run app.py
"""

import re
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import google.generativeai as genai

st.set_page_config(page_title="Olist BI Portfolio", layout="wide")


@st.cache_resource
def get_engine():
    """The connection pool is a reusable resource — cache the ENGINE, not query results,
    so every page load still queries fresh, live data."""
    conn_string = st.secrets["connections"]["supabase"]["connection_string"]
    return create_engine(conn_string)


def run_query(sql: str) -> pd.DataFrame:
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn)


# ---------------- Day 5: AI Query Assistant helpers ----------------

@st.cache_resource
def get_readonly_engine():
    """Separate, restricted connection — this is the ONLY engine the AI
    feature is allowed to use. Never reuse the main app's credentials here."""
    conn_string = st.secrets["connections"]["supabase_readonly"]["connection_string"]
    return create_engine(conn_string)


@st.cache_data(ttl=3600)
def get_schema_context() -> str:
    """Introspect the clean schema so the model always sees the real,
    current structure instead of a hardcoded (and eventually stale) description."""
    engine = get_readonly_engine()
    with engine.connect() as conn:
        df = pd.read_sql(text("""
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'clean'
            ORDER BY table_name, ordinal_position
        """), conn)

    lines = []
    for table, group in df.groupby("table_name"):
        cols = ", ".join(f"{r.column_name} ({r.data_type})" for r in group.itertuples())
        lines.append(f"- {table}: {cols}")
    return "\n".join(lines)


FORBIDDEN_KEYWORDS = [
    "insert", "update", "delete", "drop", "alter", "truncate",
    "grant", "revoke", "create", ";", "--",
]


def validate_sql(sql: str) -> tuple[bool, str]:
    """Defense in depth: even though ai_readonly can't write, still refuse
    to execute anything that isn't a plain single SELECT."""
    stripped = sql.strip().lower()
    if not stripped.startswith("select"):
        return False, "Generated query must be a SELECT statement."
    for kw in FORBIDDEN_KEYWORDS:
        if kw in stripped:
            return False, f"Generated query contains a disallowed keyword: '{kw}'."
    if "limit" not in stripped:
        sql = sql.rstrip().rstrip(";") + " LIMIT 200"
    return True, sql


def generate_sql(question: str, schema_context: str) -> str:
    genai.configure(api_key=st.secrets["gemini"]["api_key"])
    model = genai.GenerativeModel("gemini-3.5-flash-lite")

    system_prompt = f"""You are a PostgreSQL query generator for an e-commerce
analytics database (Olist Brazilian e-commerce dataset).

Schema (schema name: clean):
{schema_context}

Rules:
- Output ONLY a single valid PostgreSQL SELECT statement. No explanation,
  no markdown code fences, no semicolon.
- Always qualify table names with the clean schema, e.g. clean.fact_orders.
- Never write anything other than a SELECT.
- Add a reasonable LIMIT if the question doesn't imply an aggregate/single row.
"""

    response = model.generate_content(
        [system_prompt, question],
        generation_config={"max_output_tokens": 500},
    )
    raw = response.text.strip()
    # Gemini sometimes wraps output in code fences despite instructions - strip them.
    raw = re.sub(r"^```(?:sql)?\s*|\s*```$", "", raw, flags=re.IGNORECASE).strip()
    return raw


def explain_results(question: str, df: pd.DataFrame) -> str:
    """Optional: ask Gemini for a one-line plain-language read of the result,
    matching the insight-memo style used in Tabs 1-3."""
    genai.configure(api_key=st.secrets["gemini"]["api_key"])
    model = genai.GenerativeModel("gemini-3.5-flash-lite")

    prompt = (
        f"Question: {question}\n\n"
        f"Result (first rows):\n{df.head(10).to_string()}\n\n"
        "Give a single, concise sentence summarizing what this shows. "
        "Do not restate the raw numbers verbatim, interpret them."
    )
    response = model.generate_content(prompt, generation_config={"max_output_tokens": 200})
    return response.text.strip()


# ---------------- Sidebar ----------------
with st.sidebar:
    st.title("Olist BI Portfolio")
    st.markdown(
        "A full analytics pipeline built on Olist's real Brazilian "
        "e-commerce dataset (~100K orders): raw ingestion → clean "
        "Single-Source-of-Truth tables → ad hoc business analysis."
    )
    st.markdown("**Data-quality fixes applied:**")
    st.markdown(
        "- Deduplicated geolocation: ~1M rows → 19,015 unique zip codes\n"
        "- Deduplicated reviews: removed 551 duplicate submissions"
    )
    st.markdown("[View source on GitHub](#)")  # replace with actual repo link
    st.caption("Data refreshes live from Supabase on every page load.")

st.title("Olist E-Commerce Analytics")

tab1, tab2, tab3, tab4 = st.tabs([
    "📦 Delivery Performance by Category",
    "⭐ Delivery Time vs. Satisfaction",
    "💳 Installments vs. Order Value",
    "🤖 AI Query Assistant",
])

# ---------------- Tab 1: Category delivery performance ----------------
with tab1:
    st.subheader("Late-delivery rate by product category")
    st.caption("Categories with 30+ items only, to avoid small-sample noise.")

    df1 = run_query("""
        SELECT
            oi.category_english,
            COUNT(*) AS total_items,
            SUM(CASE WHEN fo.is_late THEN 1 ELSE 0 END) AS late_items,
            ROUND(100.0 * SUM(CASE WHEN fo.is_late THEN 1 ELSE 0 END) / COUNT(*), 2) AS late_rate_pct
        FROM clean.fact_order_items oi
        JOIN clean.fact_orders fo ON oi.order_id = fo.order_id
        WHERE fo.is_late IS NOT NULL
        GROUP BY oi.category_english
        HAVING COUNT(*) >= 30
        ORDER BY late_rate_pct DESC
        LIMIT 15
    """)

    col1, col2 = st.columns([2, 1])
    with col1:
        st.bar_chart(df1.set_index("category_english")["late_rate_pct"])
    with col2:
        st.metric("Highest late rate (large sample)", "health_beauty", "9.06% on 9,467 items")
    st.dataframe(df1, use_container_width=True)

    st.info(
        "**Insight:** Health & Beauty is the highest-priority concern — it combines "
        "a large volume (9,467 items) with an above-typical late rate, making it a "
        "real, high-impact pattern rather than small-sample noise. Smaller categories "
        "showing higher rates (e.g. Home Comfort 2 at 16.67%) warrant monitoring, not "
        "immediate action, given their low item counts."
    )

# ---------------- Tab 2: Delivery time vs review score ----------------
with tab2:
    st.subheader("Does delivery time affect customer satisfaction?")

    corr_df = run_query("""
        SELECT ROUND(CORR(fo.delivery_days, fr.review_score)::numeric, 3) AS correlation
        FROM clean.fact_orders fo
        JOIN clean.fact_reviews fr ON fo.order_id = fr.order_id
        WHERE fo.delivery_days IS NOT NULL AND fr.review_score IS NOT NULL
    """)
    correlation = corr_df["correlation"].iloc[0]

    st.metric("Correlation: delivery days vs. review score", correlation,
              help="Negative = longer delivery associates with lower review scores")

    df2 = run_query("""
        SELECT
            dc.state,
            COUNT(*) AS num_orders,
            ROUND(AVG(fo.delivery_days), 1) AS avg_delivery_days,
            ROUND(AVG(fr.review_score), 2) AS avg_review_score
        FROM clean.fact_orders fo
        JOIN clean.dim_customers dc ON fo.customer_id = dc.customer_id
        LEFT JOIN clean.fact_reviews fr ON fo.order_id = fr.order_id
        WHERE fo.delivery_days IS NOT NULL
        GROUP BY dc.state
        HAVING COUNT(*) >= 30
        ORDER BY avg_delivery_days DESC
        LIMIT 15
    """)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Slowest-delivery states**")
        st.bar_chart(df2.set_index("state")["avg_delivery_days"])
    with col2:
        st.markdown("**Review scores, same states**")
        st.bar_chart(df2.set_index("state")["avg_review_score"])
    st.dataframe(df2, use_container_width=True)

    st.info(
        f"**Insight:** A correlation of {correlation} confirms a real, moderate "
        "relationship — longer deliveries measurably associate with lower "
        "satisfaction. State-level data isn't perfectly linear (small states have "
        "noisier averages), so the order-level correlation above is the number to "
        "trust over any single state's pairing."
    )

# ---------------- Tab 3: Installments vs order value ----------------
with tab3:
    st.subheader("Do higher-value orders get split into more installments?")

    corr_df3 = run_query("""
        SELECT ROUND(CORR(max_installments, total_paid)::numeric, 3) AS correlation
        FROM clean.fact_payments_summary
        WHERE max_installments > 0
    """)
    correlation3 = corr_df3["correlation"].iloc[0]

    st.metric("Correlation: installment count vs. order value", correlation3)

    df3 = run_query("""
        SELECT max_installments, num_orders, avg_order_value FROM (
            SELECT
                max_installments,
                COUNT(*) AS num_orders,
                ROUND(AVG(total_paid)::numeric, 2) AS avg_order_value
            FROM clean.fact_payments_summary
            WHERE max_installments > 0
            GROUP BY max_installments
        ) t
        WHERE num_orders >= 30  -- filter noisy tiny buckets, matches Day 3 caveat
        ORDER BY max_installments
    """)

    st.line_chart(df3.set_index("max_installments")["avg_order_value"])
    st.dataframe(df3, use_container_width=True)

    st.info(
        f"**Insight:** A correlation of {correlation3} shows a moderate positive "
        "relationship. Average order value rises from ~₱121 at 1 installment to "
        "~₱419 at 10 installments. Buckets above 10 installments are excluded here "
        "due to very small sample sizes (some under 30 orders), which would "
        "otherwise show misleadingly extreme averages."
    )

# ---------------- Tab 4: AI Query Assistant ----------------
with tab4:
    st.subheader("Ask a question about the data")
    st.caption(
        "Runs on a dedicated read-only database role — this tab can never "
        "write, alter, or delete anything, regardless of what's asked."
    )

    with st.form(key="ai_question_form"):
        question = st.text_input(
            "e.g. Which 5 states have the most orders?",
            key="ai_question",
        )
        submitted = st.form_submit_button("Ask")

    if submitted and question:
        with st.spinner("Generating SQL..."):
            schema_context = get_schema_context()
            raw_sql = generate_sql(question, schema_context)
            is_valid, result = validate_sql(raw_sql)

        if not is_valid:
            st.error(f"Query rejected before execution: {result}")
        else:
            safe_sql = result
            st.code(safe_sql, language="sql")
            try:
                with st.spinner("Running query..."):
                    readonly_engine = get_readonly_engine()
                    with readonly_engine.connect() as conn:
                        result_df = pd.read_sql(text(safe_sql), conn)
                st.dataframe(result_df, use_container_width=True)

                if not result_df.empty:
                    with st.spinner("Summarizing..."):
                        summary = explain_results(question, result_df)
                    st.info(f"**Insight:** {summary}")
            except Exception as e:
                st.error(f"Query failed to execute: {e}")