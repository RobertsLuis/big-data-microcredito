SELECT COUNT(*)                                                       AS total,
       COUNT(*) FILTER (WHERE numero_de_operacoes = -1)               AS menos_um,
       COUNT(*) FILTER (WHERE numero_de_operacoes < -1)               AS menor_que_menos_um,
       COUNT(*) FILTER (WHERE numero_de_operacoes = 0)                AS zeros,
       ROUND(100.0 * COUNT(*) FILTER (WHERE numero_de_operacoes < 0) / COUNT(*), 1) AS pct_negativo,
       SUM(carteira_ativa) FILTER (WHERE numero_de_operacoes < 0)     AS carteira_nessas_linhas
FROM fato_microcredito;

SELECT numero_de_operacoes, COUNT(*) AS linhas
FROM fato_microcredito
WHERE numero_de_operacoes <= 0
GROUP BY 1 ORDER BY 1;