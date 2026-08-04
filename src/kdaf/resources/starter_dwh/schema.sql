CREATE TABLE IF NOT EXISTS fpna_entities (
    entity_id TEXT PRIMARY KEY,
    entity_name TEXT NOT NULL,
    currency_code TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fpna_departments (
    department_id TEXT PRIMARY KEY,
    department_name TEXT NOT NULL,
    parent_department_id TEXT REFERENCES fpna_departments(department_id)
);

CREATE TABLE IF NOT EXISTS fpna_accounts (
    account_id TEXT PRIMARY KEY,
    account_name TEXT NOT NULL,
    statement_section TEXT NOT NULL,
    normal_balance TEXT NOT NULL CHECK (normal_balance IN ('debit', 'credit')),
    is_driver BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS fpna_periods (
    period_id TEXT PRIMARY KEY,
    fiscal_year INTEGER NOT NULL,
    fiscal_quarter INTEGER NOT NULL,
    month_number INTEGER NOT NULL,
    month_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fpna_scenarios (
    scenario_id TEXT PRIMARY KEY,
    scenario_name TEXT NOT NULL,
    scenario_type TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fpna_facts (
    fact_id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL REFERENCES fpna_entities(entity_id),
    department_id TEXT NOT NULL REFERENCES fpna_departments(department_id),
    account_id TEXT NOT NULL REFERENCES fpna_accounts(account_id),
    period_id TEXT NOT NULL REFERENCES fpna_periods(period_id),
    scenario_id TEXT NOT NULL REFERENCES fpna_scenarios(scenario_id),
    amount NUMERIC(18, 2) NOT NULL,
    source_system TEXT NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (entity_id, department_id, account_id, period_id, scenario_id)
);

CREATE OR REPLACE VIEW fpna_budget_vs_actual_monthly AS
SELECT
    actual.period_id,
    actual.account_id,
    account.account_name,
    SUM(actual.amount) AS actual_amount,
    SUM(budget.amount) AS budget_amount,
    SUM(actual.amount - budget.amount) AS variance_amount
FROM fpna_facts AS actual
JOIN fpna_facts AS budget
  ON budget.entity_id = actual.entity_id
 AND budget.department_id = actual.department_id
 AND budget.account_id = actual.account_id
 AND budget.period_id = actual.period_id
 AND budget.scenario_id = 'budget'
JOIN fpna_accounts AS account
  ON account.account_id = actual.account_id
WHERE actual.scenario_id = 'actual'
GROUP BY actual.period_id, actual.account_id, account.account_name;

CREATE OR REPLACE VIEW fpna_department_spend_monthly AS
SELECT
    fact.period_id,
    department.department_name,
    SUM(fact.amount) AS actual_spend
FROM fpna_facts AS fact
JOIN fpna_accounts AS account
  ON account.account_id = fact.account_id
JOIN fpna_departments AS department
  ON department.department_id = fact.department_id
WHERE fact.scenario_id = 'actual'
  AND account.statement_section = 'operating_expense'
GROUP BY fact.period_id, department.department_name;
