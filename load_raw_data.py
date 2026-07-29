"""
Day 1: loads the 9 Olist CSVs into the `raw` schema in Supabase Postgres.

USAGE:
    pip install pandas sqlalchemy psycopg2-binary
    1. Update CONNECTION_STRING below with your Supabase connection string
    2. Update CSV_FOLDER to wherever you extracted the Kaggle download
    3. Run: python3 load_raw_data.py
"""

import pandas as pd
from sqlalchemy import create_engine

# ---- CONFIG ----
CONNECTION_STRING = "postgresql://postgres:Clydeborrega1973!@db.namkclyyxexdntxikzsi.supabase.co:5432/postgres"
CSV_FOLDER = "./olist_data/"  # wherever you extracted the Kaggle zip
# -----------------

# Maps: CSV filename -> (table name, columns to parse as datetime)
FILES = {
    "olist_customers_dataset.csv": ("customers", []),
    "olist_geolocation_dataset.csv": ("geolocation", []),
    "olist_orders_dataset.csv": ("orders", [
        "order_purchase_timestamp", "order_approved_at",
        "order_delivered_carrier_date", "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ]),
    "olist_order_items_dataset.csv": ("order_items", ["shipping_limit_date"]),
    "olist_order_payments_dataset.csv": ("order_payments", []),
    "olist_order_reviews_dataset.csv": ("order_reviews", [
        "review_creation_date", "review_answer_timestamp",
    ]),
    "olist_products_dataset.csv": ("products", []),
    "olist_sellers_dataset.csv": ("sellers", []),
    "product_category_name_translation.csv": ("category_translation", []),
}


def main():
    engine = create_engine(CONNECTION_STRING)

    for filename, (table_name, date_cols) in FILES.items():
        path = CSV_FOLDER + filename
        print(f"Loading {filename} -> raw.{table_name} ...")

        df = pd.read_csv(path, parse_dates=date_cols)

        # Geolocation has millions of near-duplicate rows in the raw file;
        # dedupe isn't required for loading, but if it's slow, consider
        # df.drop_duplicates() here — leaving it raw for now per the
        # "raw layer = minimal transformation" principle.

        df.to_sql(
            table_name,
            engine,
            schema="raw",
            if_exists="append",
            index=False,
            method="multi",
            chunksize=5000,  # keeps large tables (order_items, geolocation) from timing out
        )
        print(f"  -> {len(df)} rows loaded")

    print("\nAll 9 tables loaded into the raw schema.")


if __name__ == "__main__":
    main()
