-- Latest published monthly turnover per company, ranked. Companies whose every month is
-- suppressed do not appear: they have nothing to rank, and the ranking never invents a value.
-- The latest month is picked first (CTE); ranking inside the same SELECT would rank every month.
WITH latest AS (
    SELECT company, month, turnover_pct
    FROM analytics.turnover_rolling
    WHERE turnover_pct IS NOT NULL
    QUALIFY row_number() OVER (PARTITION BY company ORDER BY month DESC) = 1
)
SELECT
    rank() OVER (ORDER BY turnover_pct DESC) AS position,
    company,
    month,
    round(100 * turnover_pct, 2) AS turnover_pct
FROM latest
ORDER BY position, company;
