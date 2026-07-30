# Data Dictionary — `clean` schema

Complete column reference for the Single-Source-of-Truth (SSOT) tables used by the dashboard, AI Query Assistant, and n8n bridge. Confirmed directly from `information_schema.columns` against the live database.

---

## `dim_customers`
Descriptive dimension — one row per customer.

| Column | Type | Notes |
|---|---|---|
| `customer_id` | text | Primary key, joined against `fact_orders` |
| `customer_unique_id` | text | Stable identifier across repeat orders by the same underlying customer |
| `zip_code_prefix` | text | Joins to `dim_geolocation.zip_code_prefix` |
| `city` | text | |
| `state` | text | Brazilian state abbreviation (e.g. `SP`, `RJ`) — used for all state-level breakdowns |

## `dim_geolocation`
Descriptive dimension — one row per unique zip code (post-deduplication).

| Column | Type | Notes |
|---|---|---|
| `zip_code_prefix` | text | Primary key |
| `lat` | numeric | Averaged across all raw readings per zip |
| `lng` | numeric | Averaged across all raw readings per zip |
| `city` | text | Most frequently occurring spelling per zip, to handle inconsistent raw data |
| `state` | text | |

**Deduplication logic applied:** the raw table had ~1M lat/long readings for a much smaller number of unique zip codes. Resolved by averaging (not picking one row arbitrarily), since each reading was a valid but slightly different measurement of the same true location. Result: 19,015 clean rows, down from ~1M.

## `dim_products`
Descriptive dimension — one row per product.

| Column | Type | Notes |
|---|---|---|
| `product_id` | text | Primary key |
| `category_english` | text | Product category, translated to English from the raw dataset's Portuguese names |
| `product_weight_g` | numeric | |
| `product_length_cm` | numeric | |
| `product_height_cm` | numeric | |
| `product_width_cm` | numeric | |
| `product_photos_qty` | numeric | |

## `dim_sellers`
Descriptive dimension — one row per seller.

| Column | Type | Notes |
|---|---|---|
| `seller_id` | text | Primary key |
| `zip_code_prefix` | text | |
| `city` | text | |
| `state` | text | |

## `fact_orders`
Event fact table — one row per order. The authoritative source for delivery/lateness/status logic — every downstream report uses these fields rather than re-deriving them.

| Column | Type | Notes |
|---|---|---|
| `order_id` | text | Primary key |
| `customer_id` | text | FK → `dim_customers.customer_id` |
| `order_status` | text | Raw order status (e.g. delivered, shipped, canceled) |
| `order_purchase_timestamp` | timestamp | |
| `order_delivered_customer_date` | timestamp | |
| `order_estimated_delivery_date` | timestamp | |
| `delivery_days` | integer | Derived: days between purchase and actual delivery |
| `is_late` | boolean | Derived flag: actual delivery vs. estimated delivery date — the single authoritative "late" definition |
| `is_delivered` | boolean | Derived flag from `order_status` |
| `is_canceled` | boolean | Derived flag from `order_status` |

## `fact_order_items`
Event fact table — one row per line item within an order (an order can have multiple items, possibly from different sellers).

| Column | Type | Notes |
|---|---|---|
| `order_id` | text | FK → `fact_orders.order_id` |
| `order_item_id` | integer | Line-item sequence number within the order |
| `product_id` | text | FK → `dim_products.product_id` |
| `category_english` | text | Denormalized copy of the product's category, for convenient grouping without an extra join |
| `seller_id` | text | FK → `dim_sellers.seller_id` |
| `seller_city` | text | Denormalized from `dim_sellers` |
| `seller_state` | text | Denormalized from `dim_sellers` |
| `price` | numeric | Item price, excluding freight |
| `freight_value` | numeric | Shipping cost for this item |
| `total_item_value` | numeric | `price + freight_value` |

## `fact_payments_summary`
Event fact table — one row per order, summarizing payment behavior (an order may have multiple payment methods, rolled up here to one row).

| Column | Type | Notes |
|---|---|---|
| `order_id` | text | FK → `fact_orders.order_id` |
| `total_paid` | numeric | Sum across all payment methods used for the order |
| `max_installments` | integer | Highest installment count across the order's payment(s) |
| `primary_payment_type` | text | The dominant payment method for the order (e.g. credit card, boleto) |

## `fact_reviews`
Event fact table — one row per order review (post-deduplication).

| Column | Type | Notes |
|---|---|---|
| `order_id` | text | FK → `fact_orders.order_id` |
| `review_score` | integer | 1–5 |
| `review_comment_message` | text | Free-text comment, when provided |
| `review_creation_date` | timestamp | Used as the tiebreaker during dedup |

**Deduplication logic applied:** a small number of orders had duplicate review submissions. Resolved with a most-recent-row-wins rule:
```sql
SELECT DISTINCT ON (order_id) order_id, review_score, review_creation_date
FROM raw.order_reviews
ORDER BY order_id, review_creation_date DESC
```
551 duplicate rows removed this way — a deliberately different strategy from the geolocation fix above, since these are competing records (pick one) rather than noisy measurements of one truth (average).

---

## Design principle: fact vs. dimension split

Dimension tables (`dim_customers`, `dim_products`, `dim_sellers`, `dim_geolocation`) describe the "who/what" — relatively static, descriptive attributes you filter or group by.

Fact tables (`fact_orders`, `fact_order_items`, `fact_payments_summary`, `fact_reviews`) record events or measurements — something that happened, with foreign keys back to the relevant dimensions. Fact tables grow continuously; dimensions update far less often.

Keeping this separation predictable is what makes the joins in `app.py`'s queries (and the AI Query Assistant's generated SQL) reliable — every consumer of this schema uses the same authoritative definitions instead of re-deriving logic independently.
