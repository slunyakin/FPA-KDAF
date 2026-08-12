CREATE CONSTRAINT semantic_concept_id IF NOT EXISTS
FOR (concept:SemanticConcept)
REQUIRE concept.id IS UNIQUE;

CREATE CONSTRAINT kdaf_dwh_dimension_id IF NOT EXISTS
FOR (dimension:DwhDimension)
REQUIRE dimension.id IS UNIQUE;

MERGE (domain:FinanceDomain:SemanticConcept {id: 'domain:fpna_starter'})
SET domain.name = 'FP&A Starter Kit',
    domain.description = 'Starter semantic context for finance analytics';

MATCH (domain:FinanceDomain:SemanticConcept {id: 'domain:fpna_starter'})
WITH domain
UNWIND [
  {id: 'account:revenue', name: 'Revenue', table: 'fpna_accounts', key: 'account_id', value: 'revenue'},
  {id: 'account:cogs', name: 'Cost of Goods Sold', table: 'fpna_accounts', key: 'account_id', value: 'cogs'},
  {id: 'account:payroll', name: 'Payroll Expense', table: 'fpna_accounts', key: 'account_id', value: 'payroll'},
  {id: 'account:cloud_hosting', name: 'Cloud Hosting', table: 'fpna_accounts', key: 'account_id', value: 'cloud_hosting'},
  {id: 'account:marketing_spend', name: 'Marketing Spend', table: 'fpna_accounts', key: 'account_id', value: 'marketing_spend'},
  {id: 'account:headcount', name: 'Headcount', table: 'fpna_accounts', key: 'account_id', value: 'headcount'}
] AS row
MERGE (concept:AccountConcept:SemanticConcept {id: row.id})
SET concept.name = row.name,
    concept.validation_state = 'seeded'
MERGE (reference:DwhDimension {id: 'dwh:' + row.table + ':' + row.value})
SET reference.table = row.table,
    reference.key = row.key,
    reference.value = row.value
MERGE (domain)-[:HAS_CONCEPT]->(concept)
MERGE (concept)-[:REFERENCES_DWH_DIMENSION]->(reference);

MATCH (domain:FinanceDomain:SemanticConcept {id: 'domain:fpna_starter'})
WITH domain
UNWIND [
  {id: 'department:sales', name: 'Sales', table: 'fpna_departments', key: 'department_id', value: 'sales'},
  {id: 'department:marketing', name: 'Marketing', table: 'fpna_departments', key: 'department_id', value: 'marketing'},
  {id: 'department:engineering', name: 'Engineering', table: 'fpna_departments', key: 'department_id', value: 'engineering'},
  {id: 'department:g_and_a', name: 'G&A', table: 'fpna_departments', key: 'department_id', value: 'g_and_a'}
] AS row
MERGE (concept:DepartmentConcept:SemanticConcept {id: row.id})
SET concept.name = row.name,
    concept.validation_state = 'seeded'
MERGE (reference:DwhDimension {id: 'dwh:' + row.table + ':' + row.value})
SET reference.table = row.table,
    reference.key = row.key,
    reference.value = row.value
MERGE (domain)-[:HAS_CONCEPT]->(concept)
MERGE (concept)-[:REFERENCES_DWH_DIMENSION]->(reference);

MATCH (domain:FinanceDomain:SemanticConcept {id: 'domain:fpna_starter'})
WITH domain
UNWIND [
  {id: 'scenario:actual', name: 'Actuals', table: 'fpna_scenarios', key: 'scenario_id', value: 'actual'},
  {id: 'scenario:budget', name: 'Board Budget', table: 'fpna_scenarios', key: 'scenario_id', value: 'budget'},
  {id: 'scenario:forecast', name: 'Q1 Forecast', table: 'fpna_scenarios', key: 'scenario_id', value: 'forecast'}
] AS row
MERGE (concept:ScenarioConcept:SemanticConcept {id: row.id})
SET concept.name = row.name,
    concept.validation_state = 'seeded'
MERGE (reference:DwhDimension {id: 'dwh:' + row.table + ':' + row.value})
SET reference.table = row.table,
    reference.key = row.key,
    reference.value = row.value
MERGE (domain)-[:HAS_CONCEPT]->(concept)
MERGE (concept)-[:REFERENCES_DWH_DIMENSION]->(reference);

MATCH (domain:FinanceDomain:SemanticConcept {id: 'domain:fpna_starter'})
WITH domain
UNWIND [
  {
    id: 'metric:budget_vs_actuals',
    name: 'Budget vs actuals',
    description: 'Compares actual financial performance against the board budget.',
    depends_on: ['account:revenue', 'scenario:actual', 'scenario:budget']
  },
  {
    id: 'metric:forecast_movement',
    name: 'Forecast movement',
    description: 'Compares current forecast expectations against actuals.',
    depends_on: ['account:revenue', 'scenario:actual', 'scenario:forecast']
  },
  {
    id: 'metric:department_spend',
    name: 'Department spend',
    description: 'Explains operating expense by department.',
    depends_on: [
      'account:payroll',
      'account:cloud_hosting',
      'account:marketing_spend',
      'department:sales',
      'department:marketing',
      'department:engineering',
      'department:g_and_a',
      'scenario:actual'
    ]
  },
  {
    id: 'metric:revenue_driver',
    name: 'Revenue driver',
    description: 'Connects revenue outcomes to operational drivers.',
    depends_on: ['account:revenue', 'account:headcount', 'scenario:actual']
  },
  {
    id: 'metric:variance',
    name: 'Variance',
    description: 'Computes actual minus plan variance for finance review.',
    depends_on: ['scenario:actual', 'scenario:budget']
  }
] AS row
MERGE (metric:MetricConcept:SemanticConcept {id: row.id})
SET metric.name = row.name,
    metric.description = row.description,
    metric.validation_state = 'seeded'
MERGE (domain)-[:HAS_CONCEPT]->(metric)
WITH metric, row
UNWIND row.depends_on AS dependency_id
MATCH (dependency:SemanticConcept {id: dependency_id})
MERGE (metric)-[:DEPENDS_ON]->(dependency);
