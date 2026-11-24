-- Must return zero rows. Any row is a published cell that breaks the k-anonymity rule.
SELECT * FROM analytics.privacy_violations ORDER BY table_name, period, company;
