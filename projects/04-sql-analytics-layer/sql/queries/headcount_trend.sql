-- Headcount and month-over-month change for the latest 3 months of each company.
SELECT month, company, headcount, change, change_pct
FROM analytics.headcount_mom
QUALIFY row_number() OVER (PARTITION BY company ORDER BY month DESC) <= 3
ORDER BY company, month;
