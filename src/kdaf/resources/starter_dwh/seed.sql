INSERT INTO fpna_entities (entity_id, entity_name, currency_code)
VALUES ('acme-us', 'Acme Software US', 'USD')
ON CONFLICT (entity_id) DO UPDATE SET
    entity_name = EXCLUDED.entity_name,
    currency_code = EXCLUDED.currency_code;

INSERT INTO fpna_departments (department_id, department_name, parent_department_id)
VALUES
    ('sales', 'Sales', NULL),
    ('marketing', 'Marketing', NULL),
    ('engineering', 'Engineering', NULL),
    ('g_and_a', 'G&A', NULL)
ON CONFLICT (department_id) DO UPDATE SET
    department_name = EXCLUDED.department_name,
    parent_department_id = EXCLUDED.parent_department_id;

INSERT INTO fpna_accounts
    (account_id, account_name, statement_section, normal_balance, is_driver)
VALUES
    ('revenue', 'Revenue', 'revenue', 'credit', FALSE),
    ('cogs', 'Cost of Goods Sold', 'cost_of_revenue', 'debit', FALSE),
    ('payroll', 'Payroll Expense', 'operating_expense', 'debit', FALSE),
    ('cloud_hosting', 'Cloud Hosting', 'operating_expense', 'debit', FALSE),
    ('marketing_spend', 'Marketing Spend', 'operating_expense', 'debit', FALSE),
    ('headcount', 'Headcount', 'driver', 'debit', TRUE)
ON CONFLICT (account_id) DO UPDATE SET
    account_name = EXCLUDED.account_name,
    statement_section = EXCLUDED.statement_section,
    normal_balance = EXCLUDED.normal_balance,
    is_driver = EXCLUDED.is_driver;

INSERT INTO fpna_periods
    (period_id, fiscal_year, fiscal_quarter, month_number, month_name)
VALUES
    ('2026-01', 2026, 1, 1, 'January'),
    ('2026-02', 2026, 1, 2, 'February'),
    ('2026-03', 2026, 1, 3, 'March')
ON CONFLICT (period_id) DO UPDATE SET
    fiscal_year = EXCLUDED.fiscal_year,
    fiscal_quarter = EXCLUDED.fiscal_quarter,
    month_number = EXCLUDED.month_number,
    month_name = EXCLUDED.month_name;

INSERT INTO fpna_scenarios (scenario_id, scenario_name, scenario_type)
VALUES
    ('actual', 'Actuals', 'actual'),
    ('budget', 'Board Budget', 'plan'),
    ('forecast', 'Q1 Forecast', 'forecast')
ON CONFLICT (scenario_id) DO UPDATE SET
    scenario_name = EXCLUDED.scenario_name,
    scenario_type = EXCLUDED.scenario_type;

INSERT INTO fpna_facts
    (
        fact_id,
        entity_id,
        department_id,
        account_id,
        period_id,
        scenario_id,
        amount,
        source_system
    )
VALUES
    ('acme-us:sales:revenue:2026-01:actual', 'acme-us', 'sales', 'revenue', '2026-01', 'actual', 100000, 'kdaf_starter_seed'),
    ('acme-us:sales:revenue:2026-01:budget', 'acme-us', 'sales', 'revenue', '2026-01', 'budget', 95000, 'kdaf_starter_seed'),
    ('acme-us:sales:revenue:2026-01:forecast', 'acme-us', 'sales', 'revenue', '2026-01', 'forecast', 101000, 'kdaf_starter_seed'),
    ('acme-us:sales:revenue:2026-02:actual', 'acme-us', 'sales', 'revenue', '2026-02', 'actual', 108000, 'kdaf_starter_seed'),
    ('acme-us:sales:revenue:2026-02:budget', 'acme-us', 'sales', 'revenue', '2026-02', 'budget', 102000, 'kdaf_starter_seed'),
    ('acme-us:sales:revenue:2026-02:forecast', 'acme-us', 'sales', 'revenue', '2026-02', 'forecast', 109000, 'kdaf_starter_seed'),
    ('acme-us:sales:revenue:2026-03:actual', 'acme-us', 'sales', 'revenue', '2026-03', 'actual', 115000, 'kdaf_starter_seed'),
    ('acme-us:sales:revenue:2026-03:budget', 'acme-us', 'sales', 'revenue', '2026-03', 'budget', 110000, 'kdaf_starter_seed'),
    ('acme-us:sales:revenue:2026-03:forecast', 'acme-us', 'sales', 'revenue', '2026-03', 'forecast', 116000, 'kdaf_starter_seed'),
    ('acme-us:sales:payroll:2026-01:actual', 'acme-us', 'sales', 'payroll', '2026-01', 'actual', 18000, 'kdaf_starter_seed'),
    ('acme-us:marketing:marketing_spend:2026-01:actual', 'acme-us', 'marketing', 'marketing_spend', '2026-01', 'actual', 12000, 'kdaf_starter_seed'),
    ('acme-us:engineering:payroll:2026-01:actual', 'acme-us', 'engineering', 'payroll', '2026-01', 'actual', 46000, 'kdaf_starter_seed'),
    ('acme-us:engineering:cloud_hosting:2026-01:actual', 'acme-us', 'engineering', 'cloud_hosting', '2026-01', 'actual', 8280, 'kdaf_starter_seed'),
    ('acme-us:g_and_a:payroll:2026-01:actual', 'acme-us', 'g_and_a', 'payroll', '2026-01', 'actual', 15000, 'kdaf_starter_seed'),
    ('acme-us:sales:payroll:2026-02:actual', 'acme-us', 'sales', 'payroll', '2026-02', 'actual', 19000, 'kdaf_starter_seed'),
    ('acme-us:marketing:marketing_spend:2026-02:actual', 'acme-us', 'marketing', 'marketing_spend', '2026-02', 'actual', 13500, 'kdaf_starter_seed'),
    ('acme-us:engineering:payroll:2026-02:actual', 'acme-us', 'engineering', 'payroll', '2026-02', 'actual', 47000, 'kdaf_starter_seed'),
    ('acme-us:engineering:cloud_hosting:2026-02:actual', 'acme-us', 'engineering', 'cloud_hosting', '2026-02', 'actual', 8460, 'kdaf_starter_seed'),
    ('acme-us:g_and_a:payroll:2026-02:actual', 'acme-us', 'g_and_a', 'payroll', '2026-02', 'actual', 15250, 'kdaf_starter_seed'),
    ('acme-us:sales:payroll:2026-03:actual', 'acme-us', 'sales', 'payroll', '2026-03', 'actual', 20500, 'kdaf_starter_seed'),
    ('acme-us:marketing:marketing_spend:2026-03:actual', 'acme-us', 'marketing', 'marketing_spend', '2026-03', 'actual', 15000, 'kdaf_starter_seed'),
    ('acme-us:engineering:payroll:2026-03:actual', 'acme-us', 'engineering', 'payroll', '2026-03', 'actual', 48500, 'kdaf_starter_seed'),
    ('acme-us:engineering:cloud_hosting:2026-03:actual', 'acme-us', 'engineering', 'cloud_hosting', '2026-03', 'actual', 8730, 'kdaf_starter_seed'),
    ('acme-us:g_and_a:payroll:2026-03:actual', 'acme-us', 'g_and_a', 'payroll', '2026-03', 'actual', 15750, 'kdaf_starter_seed')
ON CONFLICT (entity_id, department_id, account_id, period_id, scenario_id) DO UPDATE SET
    amount = EXCLUDED.amount,
    source_system = EXCLUDED.source_system,
    loaded_at = NOW();
