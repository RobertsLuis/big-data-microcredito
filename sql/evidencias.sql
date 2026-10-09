SELECT COUNT(*) AS linhas FROM fato_microcredito;

SELECT pg_size_pretty(pg_total_relation_size('fato_microcredito')) AS tabela_com_indices,
       pg_size_pretty(pg_relation_size('fato_microcredito'))       AS so_dados,
       pg_size_pretty(pg_database_size(current_database()))        AS banco_inteiro;

SELECT MIN(data_base) AS primeira, MAX(data_base) AS ultima,
       COUNT(DISTINCT data_base) AS meses
FROM fato_microcredito;

SELECT EXTRACT(YEAR FROM data_base)::int AS ano, COUNT(*) AS linhas
FROM fato_microcredito GROUP BY 1 ORDER BY 1;

SELECT COUNT(*) FILTER (WHERE ops_suprimido) AS suprimidas,
       ROUND(100.0 * COUNT(*) FILTER (WHERE ops_suprimido) / COUNT(*), 1) AS pct,
       COUNT(*) FILTER (WHERE numero_de_operacoes < 0) AS ainda_negativas
FROM fato_microcredito;

SELECT column_name, data_type, character_maximum_length, numeric_precision, numeric_scale
FROM information_schema.columns
WHERE table_name = 'fato_microcredito' ORDER BY ordinal_position;

SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'fato_microcredito';
