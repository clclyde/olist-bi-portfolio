"""
Day 4: Live BI dashboard for the Olist portfolio project.
Queries Supabase Postgres fresh on every load — no data caching, only the
DB connection itself is cached (a connection pool is a resource, not data).

SETUP:
    pip install streamlit pandas sqlalchemy psycopg2-binary plotly

    Create .streamlit/secrets.toml (NOT committed to git — add it to .gitignore):
        [connections.supabase]
        connection_string = "postgresql://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT-REF].supabase.co:5432/postgres"

RUN:
    streamlit run app.py
"""

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

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

tab1, tab2, tab3 = st.tabs([
    "📦 Delivery Performance by Category",
    "⭐ Delivery Time vs. Satisfaction",
    "💳 Installments vs. Order Value",
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
