# US options Phase A runbook

Status: engineering foundation implemented; disabled by default; no licensed data loaded.
Scope: Bulls Atlas US tenant (`bullsofwallst`) only.

This runbook imports Cboe Option Sentiment for schema, identity, and data-quality evaluation. It
does not enable a queue signal, dossier lens, customer display, backtest, shadow portfolio, or
trading action.

## Hard prerequisites

1. The subscription belongs to the Bulls business or Ilias personally during the research phase.
2. Written terms explicitly allow internal research and retention for the intended period.
3. The agreement and applicable terms are retained outside the application and hashed with SHA-256.
4. A dedicated private S3 bucket exists with public access blocked, versioning enabled, encryption,
   lifecycle policy, access logging, and a worker role limited to the configured prefix.
5. Migration `d2a4c6e8f0b1` is applied.

Customer display, derived-data display, redistribution, and alerting are separate entitlements.
Internal-research permission does not enable any of them.

## Request the historical order

Use the Cboe DataShop Sales contact form or an authenticated DataShop account. The request should
be explicit so a cheaper internal-research order is not confused with customer-display rights:

```text
Subject: Option Sentiment historical quote for internal feasibility research

Please quote Cboe Option Sentiment historical data with:
- date range: 2025-07-16 through 2026-07-15;
- coverage: all available US stock, ETF, and index option underlyings;
- complete/final daily files, grouped per trading day;
- current Option Sentiment v1.4 schema;
- internal quantitative research and retention by the named subscriber;
- no external display, redistribution, alerts, or customer-derived-data use in this phase.

Please confirm the price, delivery method, applicable agreement/terms, retention rights,
correction/reissue policy, expected file count, and whether a representative sample is available.
Please also quote or provide samples for Option EOD Summary and Cboe Open-Close Volume Summary
separately; those products are not part of this one-year Option Sentiment feasibility order.
```

Do not substitute screenshots, scraped option chains, an employer's subscription, or an unrelated
free feed. They do not provide the same fields, provenance, opening/closing semantics, or usage
rights and would invalidate this evaluation.

## Record the entitlement

There is deliberately no product API for granting vendor rights. Use the privileged migration/admin
database path and insert one reviewed row:

```sql
INSERT INTO research_data_entitlements (
    tenant_id,
    market,
    dataset_key,
    provider,
    status,
    internal_research_allowed,
    customer_display_allowed,
    derived_display_allowed,
    redistribution_allowed,
    retention_allowed,
    valid_from,
    valid_until,
    agreement_reference,
    terms_sha256,
    approved_by,
    approved_at,
    notes
) VALUES (
    'bullsofwallst',
    'US',
    'cboe_option_sentiment',
    'Cboe DataShop',
    'approved',
    true,
    false,
    false,
    false,
    true,
    DATE '2026-01-01',
    DATE '2026-12-31',
    'internal-contract-reference',
    '<sha256-of-reviewed-terms>',
    '<reviewer>',
    now(),
    'Phase A historical feasibility only'
);
```

Do not mark unreviewed, borrowed, employer-owned, trial, or customer-display-ambiguous terms as
approved.

## Configure the worker

```dotenv
US_OPTIONS_PHASE_A_ENABLED=true
US_OPTIONS_INBOX_DIR=/home/ubuntu/secure-options-inbox
US_OPTIONS_MIN_IDENTITY_COVERAGE=0.95
RESEARCH_OBJECT_STORE_BACKEND=s3
RESEARCH_OBJECT_STORE_S3_BUCKET=<private-bucket>
RESEARCH_OBJECT_STORE_S3_PREFIX=atlas
RESEARCH_OBJECT_STORE_AWS_REGION=eu-central-1
```

No Cboe credentials are stored in this application in Phase A. Download the purchased file through
the approved vendor channel and place it in the protected inbox.

## Import the one-year historical order

Request complete Option Sentiment files for **2025-07-16 through 2026-07-15**. This is the latest
full trailing year available on 2026-07-16 and spans only verified NYSE calendar years in Atlas.
Historical orders normally contain one delivery per trading date. Keep the vendor archive intact.

The timestamp must be when Atlas first received the historical order, not each market close. Place
all daily ZIP/CSV files directly in the protected inbox, with no nested directories, then run:

```bash
uv run python -m ingestion.us_options.cli import-sentiment-directory \
  /home/ubuntu/secure-options-inbox \
  --known-at 2026-07-16T10:00:00Z \
  --revision historical-order-2026-07-16
```

The importer is sequential, transactional per file, and idempotent. It continues after a failed
file, prints a final accepted/rejected/failed count, and exits nonzero unless every delivery was
accepted. A retry with the same revision and same bytes is safe.

For a single sample or subscription delivery:

```bash
uv run python -m ingestion.us_options.cli import-sentiment \
  /home/ubuntu/secure-options-inbox/HighLevelOptionSentiment_Complete_2026-07-15.zip \
  --known-at 2026-07-16T10:00:00Z \
  --completeness complete \
  --delivery-mode historical \
  --revision historical-order-2026-07-16
```

The US arq worker also exposes `import_us_option_sentiment`, restricted to a basename within
`US_OPTIONS_INBOX_DIR`. There is intentionally no options cron schedule.

## Run the feasibility evaluation

After every expected file is accepted:

```bash
uv run python -m ingestion.us_options.cli evaluate-sentiment \
  --start 2025-07-16 \
  --end 2026-07-15
```

The evaluator reads only hash-verified normalized artifacts, selects the newest accepted complete
revision per session, and persists an immutable JSON report plus a small database manifest. It
reports calendar coverage, rejected and superseded deliveries, daily breadth stability, stock-only
identity coverage, unmatched symbols, null rates, delivery modes, split-adjustment candidates, and
descriptive distributions for raw and interpretable derived fields.

The evaluator is bounded-memory: it processes one daily Parquet artifact at a time. Counts, means,
nulls, minima, and maxima are exact; quantiles use a deterministic reservoir capped per metric and
the report records that method explicitly.

It deliberately does not calculate strategy returns, paper trades, alpha, Sharpe, or a buy/sell
score. One year is insufficient for the registered temporal backtest.

## Import acceptance

An `accepted` snapshot means:

- the file exactly matched Cboe Option Sentiment v1.4's 80 columns;
- it contained one trade date and no duplicate underlying;
- documented numeric and aggregate relationships were valid;
- the file was not preliminary;
- at least the configured fraction of stock underlyings matched the versioned US security master.

A `rejected` snapshot and its immutable artifacts remain available for diagnosis but cannot feed
Atlas. Blank vendor values remain null and are counted; they are never converted to zero.

The snapshot records raw and Parquet hashes, dataset fingerprint, schema/normalization/identity
versions, `effective_at`, `known_at`, `ingested_at`, quality report, entitlement, and explicit
previous-settlement open-interest semantics.

Snapshot manifests are append-only at the database layer. A source revision is also immutable:
retrying the same date/completeness/revision with identical bytes is idempotent, while reusing that
revision for different bytes is rejected. Use a new reviewed revision label for a vendor correction.

## Next gate

`ready_for_phase_b_review` means the mechanical feasibility gates passed; it is not automatic
product approval. Review distributions, identity exceptions, corrections, corporate actions,
delivery semantics, and coverage across the one-year set. Only after that review may Phase B add a
US dossier evidence lens. A multi-year purchase and delisted-inclusive stock history are still
required before the registered historical experiment can run.
