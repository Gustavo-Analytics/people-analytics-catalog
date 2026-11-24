-- Governed views over the Gold tables. Consumers (BI, an agent, an analyst) query `analytics.*`,
-- never `gold.*` directly. Suppressed cells are NULL, and every aggregate below ignores NULLs
-- on purpose: a hidden value is never filled in, averaged as zero or reconstructed.

CREATE SCHEMA IF NOT EXISTS analytics;

-- Month-over-month headcount change per company.
CREATE OR REPLACE VIEW analytics.headcount_mom AS
SELECT
    month,
    company,
    headcount,
    headcount - LAG(headcount) OVER w AS change,
    round(100.0 * (headcount - LAG(headcount) OVER w) / NULLIF(LAG(headcount) OVER w, 0), 2) AS change_pct
FROM gold.turnover
WINDOW w AS (PARTITION BY company ORDER BY month);

-- Rolling 3-month average of monthly turnover. `months_with_data` says how many of the
-- (up to) 3 months actually had a published value, so a thin average is visible as thin.
CREATE OR REPLACE VIEW analytics.turnover_rolling AS
SELECT
    month,
    company,
    turnover_pct,
    round(avg(turnover_pct) OVER w, 4) AS turnover_3m_avg,
    count(turnover_pct) OVER w AS months_with_data
FROM gold.turnover
WINDOW w AS (PARTITION BY company ORDER BY month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW);

-- Privacy audit: every row here is a k-anonymity violation. A healthy Gold returns zero rows.
-- Thresholds mirror build_gold.py (K_DEFAULT = 3, K_DETAILED = 5).
CREATE OR REPLACE VIEW analytics.privacy_violations AS
SELECT 'headcount_dept' AS table_name, CAST(month AS VARCHAR) AS period, company,
       'published count below k=5' AS rule
FROM gold.headcount_dept WHERE NOT suppressed AND headcount < 5
UNION ALL
SELECT 'headcount_dept', CAST(month AS VARCHAR), company, 'suppressed row still carries a value'
FROM gold.headcount_dept WHERE suppressed AND headcount IS NOT NULL
UNION ALL
SELECT 'headcount_gender', CAST(month AS VARCHAR), company, 'published count below k=3'
FROM gold.headcount_gender WHERE NOT suppressed AND headcount < 3
UNION ALL
SELECT 'headcount_gender', CAST(month AS VARCHAR), company, 'suppressed row still carries a value'
FROM gold.headcount_gender WHERE suppressed AND headcount IS NOT NULL
UNION ALL
SELECT 'turnover', CAST(month AS VARCHAR), company, 'published with fewer than 3 exits or headcount below 5'
FROM gold.turnover WHERE NOT suppressed AND (exits_total < 3 OR headcount < 5)
UNION ALL
SELECT 'turnover', CAST(month AS VARCHAR), company, 'suppressed row still carries a rate'
FROM gold.turnover WHERE suppressed AND (turnover_pct IS NOT NULL OR exits_total IS NOT NULL)
UNION ALL
SELECT 'time_to_hire', CAST(closed_month AS VARCHAR), company, 'published count below k=3'
FROM gold.time_to_hire WHERE NOT suppressed AND closed_reqs < 3
UNION ALL
SELECT 'time_to_hire', CAST(closed_month AS VARCHAR), company, 'suppressed row still carries a value'
FROM gold.time_to_hire WHERE suppressed AND (closed_reqs IS NOT NULL OR avg_days IS NOT NULL)
UNION ALL
SELECT 'regrettable', NULL, company, 'published count below k=5'
FROM gold.regrettable WHERE NOT suppressed AND voluntary_exits < 5
UNION ALL
SELECT 'regrettable', NULL, company, 'suppressed row still carries a value'
FROM gold.regrettable WHERE suppressed AND (voluntary_exits IS NOT NULL OR regrettable_pct IS NOT NULL);
