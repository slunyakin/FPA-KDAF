SELECT
    period_id,
    account_name,
    actual_amount,
    budget_amount,
    variance_amount
FROM fpna_budget_vs_actual_monthly
WHERE account_id = 'revenue'
ORDER BY period_id;

SELECT
    period_id,
    department_name,
    actual_spend
FROM fpna_department_spend_monthly
WHERE period_id = '2026-03'
ORDER BY actual_spend DESC, department_name;
