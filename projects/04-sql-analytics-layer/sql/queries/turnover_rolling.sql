-- Rolling 3-month turnover, only where at least 2 of the 3 months were published.
SELECT month, company, round(100 * turnover_3m_avg, 2) AS turnover_3m_pct, months_with_data
FROM analytics.turnover_rolling
WHERE months_with_data >= 2
ORDER BY company, month;
