MATCH (concept:SemanticConcept)-[:REFERENCES_DWH_DIMENSION]->(reference:DwhDimension)
RETURN
  concept.id AS concept_id,
  concept.name AS concept_name,
  reference.table AS dwh_table,
  reference.key AS dwh_key,
  reference.value AS dwh_value
ORDER BY concept_id;

MATCH (metric:MetricConcept)-[:DEPENDS_ON]->(dependency:SemanticConcept)
RETURN
  metric.id AS metric_id,
  metric.name AS metric_name,
  collect(dependency.id) AS dependency_ids
ORDER BY metric_id;

MATCH path = (:FinanceDomain {id: 'domain:fpna_starter'})-[:HAS_CONCEPT]->(:SemanticConcept)
RETURN path
LIMIT 50;
